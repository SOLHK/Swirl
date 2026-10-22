using AdShield.Network;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using YamlDotNet.Serialization;

internal static class CaptureChecks
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        var originalDirectory = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.GetFullPath(Path.Combine("..", "capture-integration-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        try
        {
            await using var http = new LocalOrigin();
            await using var tls = new TlsOrigin();
            var plugin = LoonPlugin.Parse($$"""
                #!name = Capture fixture
                [Rewrite]
                ^http://127\.0\.0\.1:{{http.Port}}/data response-body-json-jq '.ads = []'
                ^https://127\.0\.0\.1:{{tls.Port}}/data response-body-json-jq 'del(.ads)'
                ^https://127\.0\.0\.1:{{tls.Port}}/mock mock-response-body data-type=json data="{}" status-code=200
                [Script]
                http-response ^https://127\.0\.0\.1:{{tls.Port}}/script script-path=https://example.test/test.js,requires-body=true
                [MITM]
                hostname = 127.0.0.1
                """, "https://example.test/fixture.lpx");
            check(plugin.Unsupported.Count == 0, "capture fixture imports as LPX with jq and positional script");
            plugin.Enabled = true;
            plugin.Scripts[0].Code = "let b=JSON.parse($response.body);b.ads=[];$done({body:JSON.stringify(b)});";
            check((await PluginJq.RunAsync(".ads = []", "{\"ads\":[1],\"video\":\"keep\"}")).Contains("\"ads\":[]"), "bundled jq edits only selected JSON fields");
            bool runaway = false;
            try { await PluginJq.RunAsync("[range(1000000000)]", "{}"); } catch { runaway = true; }
            check(runaway, "jq runaway allocation is stopped by job limit or timeout");
            bool module = false;
            try { await PluginJq.RunAsync("include \"private\"; .", "{}"); } catch { module = true; }
            check(module, "jq cannot import host modules");
            foreach (string mode in new[] { "rule", "global", "direct" })
            {
                var profile = new ProxyProfile { Tun = true, Mitm = true, Mode = mode, BasicAds = false, Plugins = new() { plugin } };
                string runtime = Path.Combine(ProxyProfile.DirectoryPath, mode);
                Directory.CreateDirectory(runtime);
                string file = Path.Combine(runtime, "config.yaml");
                string generated = MihomoConfig.Build(profile, "fixture-secret");
                File.WriteAllText(file, generated);
                var validationStart = ProxyController.StartInfo(runtime, file);
                validationStart.ArgumentList.Add("-t");
                using (var validation = Process.Start(validationStart)!)
                {
                    var logs = validation.StandardOutput.ReadToEndAsync(); var errors = validation.StandardError.ReadToEndAsync();
                    await validation.WaitForExitAsync(); await Task.WhenAll(logs, errors);
                    check(validation.ExitCode == 0, "real core validates simultaneous TUN and MITM in " + mode + " mode");
                }
                // Exercise exactly the DEFAULT-TUN routing metadata with a
                // loopback ingress, without installing routes on the user's PC.
                var config = MihomoConfig.Parse(generated);
                ((IDictionary<object, object>)config["tun"])["enable"] = false;
                config["listeners"] = new[] { new Dictionary<string, object> { ["name"] = "DEFAULT-TUN", ["type"] = "mixed", ["port"] = 17892, ["listen"] = "127.0.0.1" } };
                var rules = ((IEnumerable<object>)config["rules"]).Select(r => r.ToString()!).ToArray();
                rules[0] = MihomoConfig.CaptureRule.Replace("80/443", http.Port + "/" + tls.Port);
                config["rules"] = rules;
                File.WriteAllText(file, new SerializerBuilder().Build().Serialize(config));
                using var proxy = new PluginProxy(new[] { plugin }, true, message => Console.WriteLine("Capture: " + message), requireTrustedRoot: false, pinnedTestOrigin: tls.Certificate.Thumbprint);
                using var rootCertificate = proxy.ExportRootCertificate();
                proxy.Start();
                using var core = Process.Start(ProxyController.StartInfo(runtime, file))!;
                using var job = new CoreProcessJob(core);
                var stdout = core.StandardOutput.ReadToEndAsync(); var stderr = core.StandardError.ReadToEndAsync();
                try
                {
                    using var health = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(1) };
                    bool ready = false;
                    for (int i = 0; i < 80 && !core.HasExited; i++)
                    {
                        try { using var result = await health.GetAsync("http://127.0.0.1:" + MihomoConfig.ControllerPort + "/version"); ready = true; } catch (HttpRequestException) { }
                        if (ready) break; await Task.Delay(100);
                    }
                    check(ready, "capture ingress starts in " + mode + " mode");
                    using var handler = new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:17892"), UseProxy = true };
                    handler.ServerCertificateCustomValidationCallback = (_, certificate, _, _) =>
                    {
                        if (certificate == null) return false;
                        if (certificate.Thumbprint == tls.Certificate.Thumbprint) return true;
                        using var chain = new X509Chain();
                        chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
                        chain.ChainPolicy.CustomTrustStore.Add(rootCertificate);
                        chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
                        return chain.Build(certificate);
                    };
                    using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(12) };
                    string body = await client.GetStringAsync($"http://127.0.0.1:{http.Port}/data");
                    check(body.Contains("\"ads\":[]") && body.Contains("keep"), "captured HTTP applies jq and returns through core once: " + mode);
                    using var rawHandler = new SocketsHttpHandler { UseProxy = false, ConnectCallback = RawCaptureConnection };
                    rawHandler.SslOptions.RemoteCertificateValidationCallback = (_, certificate, _, _) =>
                    {
                        if (certificate == null) return false;
                        using var leaf = new X509Certificate2(certificate);
                        using var chain = new X509Chain();
                        chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
                        chain.ChainPolicy.CustomTrustStore.Add(rootCertificate);
                        chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
                        return chain.Build(leaf);
                    };
                    using var rawClient = new HttpClient(rawHandler) { Timeout = TimeSpan.FromSeconds(12) };
                    body = await rawClient.GetStringAsync($"http://127.0.0.1:{http.Port}/data");
                    check(body.Contains("\"ads\":[]") && body.Contains("keep"), "raw captured origin-form HTTP is rewritten: " + mode);
                    body = await rawClient.GetStringAsync($"https://127.0.0.1:{tls.Port}/data");
                    check(!body.Contains("ads") && body.Contains("keep"), "raw captured TLS stream is decrypted and rewritten: " + mode);
                    body = await client.GetStringAsync($"https://127.0.0.1:{tls.Port}/data");
                    check(!body.Contains("ads") && body.Contains("keep"), "captured HTTPS is decrypted and jq rewritten: " + mode);
                    body = await client.GetStringAsync($"https://127.0.0.1:{tls.Port}/script");
                    check(body.Contains("\"ads\":[]") && body.Contains("keep"), "captured HTTPS runs Loon response script: " + mode);
                    int hits = tls.Hits;
                    check(await client.GetStringAsync($"https://127.0.0.1:{tls.Port}/mock") == "{}" && tls.Hits == hits, "captured HTTPS mock never reaches origin: " + mode);
                    body = await client.GetStringAsync($"https://localhost:{tls.Port}/untouched");
                    check(body.Contains("[1,2]"), "HTTPS outside MITM host list remains unchanged: " + mode);
                }
                finally { if (!core.HasExited) core.Kill(true); await core.WaitForExitAsync(); await Task.WhenAll(stdout, stderr); }
            }
        }
        finally { ProxyProfile.TestDirectory = originalDirectory; }
    }

    private static async ValueTask<Stream> RawCaptureConnection(SocketsHttpConnectionContext context, CancellationToken token)
    {
        var socket = new Socket(SocketType.Stream, ProtocolType.Tcp);
        try
        {
            await socket.ConnectAsync(new IPEndPoint(IPAddress.Loopback, 17892), token);
            var stream = new NetworkStream(socket, ownsSocket: true);
            await stream.WriteAsync(new byte[] { 5, 1, 0 }, token);
            var answer = new byte[2]; await stream.ReadExactlyAsync(answer, token);
            if (!answer.SequenceEqual(new byte[] { 5, 0 })) throw new IOException("Fixture SOCKS handshake failed");
            byte[] host = Encoding.ASCII.GetBytes(context.DnsEndPoint.Host);
            await stream.WriteAsync(new byte[] { 5, 1, 0, 3, (byte)host.Length }.Concat(host).Concat(new byte[] { (byte)(context.DnsEndPoint.Port >> 8), (byte)context.DnsEndPoint.Port }).ToArray(), token);
            var header = new byte[4]; await stream.ReadExactlyAsync(header, token);
            if (header[1] != 0) throw new IOException("Fixture SOCKS connect failed");
            int length = header[3] switch { 1 => 4, 4 => 16, 3 => stream.ReadByte(), _ => throw new IOException("Fixture SOCKS address invalid") };
            await stream.ReadExactlyAsync(new byte[length + 2], token);
            return stream;
        }
        catch { socket.Dispose(); throw; }
    }
}

internal sealed class TlsOrigin : IAsyncDisposable
{
    private readonly TcpListener listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource stopping = new();
    private readonly Task loop;
    private readonly List<Task> connections = new();
    private int hits;
    internal int Hits => Volatile.Read(ref hits);
    internal int Port { get; }
    internal X509Certificate2 Certificate { get; }
    internal TlsOrigin()
    {
        using var rsa = RSA.Create(2048);
        var request = new CertificateRequest("CN=localhost", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var names = new SubjectAlternativeNameBuilder(); names.AddDnsName("localhost"); names.AddIpAddress(IPAddress.Loopback);
        request.CertificateExtensions.Add(names.Build());
        using var temporary = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddHours(1));
        // Schannel cannot serve a TLS certificate backed by an ephemeral key.
        Certificate = new X509Certificate2(temporary.Export(X509ContentType.Pfx), (string?)null, X509KeyStorageFlags.UserKeySet);
        listener.Start(); Port = ((IPEndPoint)listener.LocalEndpoint).Port; loop = RunAsync();
    }
    private async Task RunAsync()
    {
        try { while (!stopping.IsCancellationRequested) connections.Add(HandleAsync(await listener.AcceptTcpClientAsync(stopping.Token))); }
        catch (OperationCanceledException) { }
        catch (SocketException) when (stopping.IsCancellationRequested) { }
    }
    private async Task HandleAsync(TcpClient client)
    {
        using (client)
        using (var stream = new SslStream(client.GetStream()))
            try
            {
                await stream.AuthenticateAsServerAsync(new SslServerAuthenticationOptions { ServerCertificate = Certificate, EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13 }, stopping.Token);
                using var reader = new StreamReader(stream, Encoding.ASCII, false, 4096, true);
                string? line; while ((line = await reader.ReadLineAsync(stopping.Token)) != null && line.Length > 0) { }
                Interlocked.Increment(ref hits);
                const string body = "{\"ads\":[1,2],\"video\":\"keep\"}";
                await stream.WriteAsync(Encoding.UTF8.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + Encoding.UTF8.GetByteCount(body) + "\r\nConnection: close\r\n\r\n" + body), stopping.Token);
            }
            catch (Exception e) when (e is OperationCanceledException or IOException or AuthenticationException) { }
    }
    public async ValueTask DisposeAsync() { stopping.Cancel(); listener.Stop(); await loop; await Task.WhenAll(connections); Certificate.Dispose(); stopping.Dispose(); }
}
