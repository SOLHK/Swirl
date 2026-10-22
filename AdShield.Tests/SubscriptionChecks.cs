using AdShield.Network;
using System.Net;
using System.Net.Http;
using System.Text;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

internal static class SubscriptionChecks
{
    private const string ValidConfig = "proxies:\n  - name: Fixture node\n    type: http\n    server: 192.0.2.1\n    port: 8080\nproxy-groups:\n  - name: Fixture group\n    type: select\n    proxies: [Fixture node]\nrules: ['MATCH,Fixture group']\n";

    internal static void Pure(Action<bool, string> check)
    {
        string imported = MihomoConfig.ParseSubscription(ValidConfig);
        check(imported == ValidConfig && MihomoConfig.Parse(imported).ContainsKey("proxy-groups"), "Clash subscription preserves nodes, groups and rules without conversion");
        string emptyProviders = ValidConfig + "proxy-providers: {}\n";
        check(MihomoConfig.ParseSubscription(emptyProviders) == emptyProviders, "Clash static-node configuration accepts an empty optional provider map");
        string provider = "proxy-providers:\n  Fixture provider:\n    type: http\n    url: https://example.test/provider.yaml\n    path: ./providers/fixture.yaml\n    interval: 3600\nproxy-groups:\n  - name: Fixture group\n    type: select\n    use: [Fixture provider]\nrules: ['MATCH,Fixture group']\n";
        check(MihomoConfig.ParseSubscription(provider) == provider, "provider-only Clash configuration remains importable");
        check(MihomoConfig.ParseSubscription(provider + "proxies: []\n").Contains("proxies: []"), "Clash provider-only configuration accepts an empty optional node list");
        string inline = "proxy-providers:\n  Fixture provider:\n    type: inline\n    payload:\n      - name: Fixture node\n        type: http\n        server: 192.0.2.1\n        port: 8080\n";
        check(MihomoConfig.Parse(MihomoConfig.ParseSubscription(inline)).ContainsKey("proxy-providers"), "Mihomo inline node providers remain importable");
        string payload = "payload:\n  - name: Provider fixture\n    type: socks5\n    server: 192.0.2.1\n    port: 1080\n";
        var wrapped = MihomoConfig.Parse(MihomoConfig.ParseSubscription(payload));
        check(wrapped.ContainsKey("proxies") && !wrapped.ContainsKey("payload"), "standalone node-provider payload is wrapped as Clash proxies");

        foreach (var (content, description) in new (string, string)[]
        {
            ("", "empty response"),
            ("<html><title>Access denied</title></html>", "HTML access-denied page"),
            ("{\"status\":\"failed\",\"message\":\"private-fixture-token\"}", "JSON service error"),
            ("status: denied\nmessage: private-fixture-token\n", "unrelated YAML service map"),
            ("rules: ['MATCH,DIRECT']\n", "rules-only configuration without subscription nodes"),
            ("proxies: []\nproxy-providers: {}\n", "empty node and provider collections"),
            ("proxies: 'not a list'\n", "scalar node collection"),
            ("proxies: [not-a-node]\n", "nonmapping node entries"),
            ("proxies: [{name: Fixture node}]\n", "node missing protocol type"),
            ("proxies: [{name: '', type: http}]\n", "node missing name"),
            ("proxy-providers: 'not a mapping'\n", "scalar provider collection"),
            ("proxy-providers: {Fixture: 'not a provider'}\n", "nonmapping provider entries"),
            ("proxy-providers: {Fixture: {type: missing-protocol}}\n", "unknown provider type"),
            ("payload: [DOMAIN-SUFFIX,ads.example,REJECT]\n", "rule-provider payload mistaken for nodes"),
            ("ss://ZmFrZS1ub2RlQGV4YW1wbGUudGVzdDo0NDM=", "URI node subscription"),
            (Convert.ToBase64String(Encoding.UTF8.GetBytes("ss://fake-node@example.test:443")), "base64 URI node subscription")
        })
        {
            string? error = Failure(() => MihomoConfig.ParseSubscription(content));
            check(error != null && !error.Contains("private-fixture-token"), "subscription rejects " + description + " without echoing credentials");
        }
        check(Failure(() => MihomoConfig.ParseSubscription("proxies: []\nproxies: [{name: Fixture, type: http}]\n")) != null, "subscription rejects ambiguous duplicate YAML keys");
        check(Failure(() => MihomoConfig.ParseSubscription(new string('a', 4 * 1024 * 1024 + 1))) != null, "subscription YAML remains bounded to four megabytes");

        const string outer = "https://converter.example.test/sub?target=clash&config=https%3A%2F%2Fexample.test%2Ftemplate%20name.yaml&url=https%3A%2F%2Fapi.example.test%2Fsubscribe%3Ftoken%3Dsynthetic%252Btoken%2526suffix%2525";
        check(SubscriptionImport.ParseAddress(outer).OriginalString == outer, "subscription conversion URL is preserved instead of extracting its nested source");
        check(SubscriptionImport.ParseAddress("clash://install-config?url=" + Uri.EscapeDataString(outer) + "&name=Fixture").OriginalString == outer, "Clash one-click import unwraps exactly once and retains nested query encoding");
        check(SubscriptionImport.ParseAddress(Uri.EscapeDataString(outer)).OriginalString == outer, "fully encoded HTTPS subscription unwraps without double-decoding tokens");
        const string protectedQuery = "https://example.test/sub?token=synthetic%2Btoken%26suffix%25&name=Fixture+Name";
        check(SubscriptionImport.ParseAddress(protectedQuery).OriginalString == protectedQuery, "plain subscription preserves encoded token delimiters and plus characters");
        check(SubscriptionImport.ParseAddress("clash://install-config?url=https://example.test/sub?token=synthetic%2Btoken%26suffix%25").OriginalString == "https://example.test/sub?token=synthetic%2Btoken%26suffix%25", "unescaped Clash wrapper target preserves an already encoded private token");
        check(SubscriptionImport.ParseAddress("  " + protectedQuery + "\r\n").OriginalString == protectedQuery, "subscription address tolerates pasted surrounding whitespace");
        foreach (string address in new[] { "http://example.test/sub", "https://user:secret@example.test/sub", "file:///C:/fixture.yaml", "javascript:alert(1)", "clash://install-config?name=Fixture", "https://", "not-an-address" })
            check(Failure(() => SubscriptionImport.ParseAddress(address)) != null, "subscription rejects unsafe or malformed address without network access");
    }

    internal static async Task DownloadAsync(Action<bool, string> check)
    {
        const string privateSource = "https://example.test/sub?token=synthetic-private-fixture%2Btoken%26suffix";
        foreach (var (profile, agent) in new[] { (SubscriptionClientProfile.Mihomo, "clash.meta"), (SubscriptionClientProfile.Clash, "clash"), (SubscriptionClientProfile.Browser, "Mozilla/") })
        {
            using var handler = new FixtureHandler((_, _) => Task.FromResult(Reply(HttpStatusCode.OK, ValidConfig, "application/yaml")));
            var result = await SubscriptionImport.DownloadAsync(privateSource, profile, handler);
            check(result.Content == ValidConfig && result.NormalizedSource == privateSource && handler.LastAddress == privateSource, "subscription download preserves Clash configuration and private source with " + profile + " client profile");
            check(handler.UserAgent.StartsWith(agent, StringComparison.OrdinalIgnoreCase), "subscription sends selected " + profile + " client identity");
            check(handler.Accept.Length > 0 && handler.Calls == 1, "subscription sends a content preference without contacting a conversion service");
        }
        using (var handler = new FixtureHandler((_, _) => Task.FromResult(Reply(HttpStatusCode.Forbidden, "Forbidden: " + privateSource, "text/html"))))
        {
            string? error = await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler));
            check(error != null && error.Contains("403") && !error.Contains("synthetic-private-fixture") && !error.Contains("example.test"), "HTTP 403 explains source denial without echoing the private subscription address");
            check(handler.Calls == 1, "HTTP 403 makes no automatic third-party conversion or alternate-client retry");
        }
        using (var handler = new FixtureHandler((_, _) => throw new HttpRequestException("Transport failed for " + privateSource)))
        {
            string? error = await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler));
            check(error != null && !error.Contains("synthetic-private-fixture") && !error.Contains("example.test"), "transport exceptions are sanitized instead of exposing URI credentials");
        }
        using (var handler = new FixtureHandler((request, _) =>
        {
            if (request.RequestUri!.AbsolutePath == "/sub")
            {
                var redirect = Reply(HttpStatusCode.Redirect, "", "text/plain");
                redirect.Headers.Location = new Uri("/config.yaml?token=synthetic%2Btoken", UriKind.Relative);
                return Task.FromResult(redirect);
            }
            return Task.FromResult(Reply(HttpStatusCode.OK, ValidConfig, "application/yaml"));
        }))
        {
            var result = await SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler);
            check(result.Content == ValidConfig && result.NormalizedSource == privateSource && handler.Calls == 2 && handler.LastAddress == "https://example.test/config.yaml?token=synthetic%2Btoken", "subscription follows relative HTTPS redirect while retaining the original saved source");
        }
        using (var handler = new FixtureHandler((_, _) =>
        {
            var redirect = Reply(HttpStatusCode.Redirect, "", "text/plain");
            redirect.Headers.Location = new Uri("http://example.test/config.yaml?token=synthetic-private-fixture");
            return Task.FromResult(redirect);
        }))
        {
            string? error = await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler));
            check(error != null && handler.Calls == 1 && !error.Contains("synthetic-private-fixture"), "subscription blocks an HTTP downgrade redirect without exposing its target");
        }
        using (var handler = new FixtureHandler((_, _) =>
        {
            var redirect = Reply(HttpStatusCode.Redirect, "", "text/plain");
            redirect.Headers.Location = new Uri("https://example.test/loop");
            return Task.FromResult(redirect);
        }))
            check(await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler)) != null && handler.Calls == 6, "subscription stops after the bounded five-redirect allowance");
        foreach (var (content, media) in new[] { ("<html><title>Denied</title></html>", "application/yaml"), ("<!DOCTYPE html><html>Denied</html>", "text/html"), ("", "application/yaml") })
        {
            using var handler = new FixtureHandler((_, _) => Task.FromResult(Reply(HttpStatusCode.OK, content, media)));
            check(await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler)) != null, "subscription download rejects an empty or HTML success response before YAML import");
        }
        using (var handler = new FixtureHandler((_, _) =>
        {
            var content = new StringContent(ValidConfig, Encoding.UTF8, "application/yaml");
            content.Headers.ContentLength = 4 * 1024 * 1024 + 1;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = content });
        }))
            check(await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler)) != null, "subscription rejects oversized declared response before reading its body");
        using (var handler = new FixtureHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new UnknownLengthContent(new byte[4 * 1024 * 1024 + 1]) })))
            check(await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler)) != null, "subscription enforces four-megabyte limit on streaming responses without Content-Length");
        using (var handler = new FixtureHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(new byte[] { 0xC3, 0x28 }) })))
            check(await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler)) != null, "subscription rejects malformed UTF-8 instead of silently replacing configuration bytes");
        using (var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(60)))
        using (var handler = new FixtureHandler(async (_, token) =>
        {
            await Task.Delay(TimeSpan.FromSeconds(5), token);
            return Reply(HttpStatusCode.OK, ValidConfig, "application/yaml");
        }))
        {
            var started = System.Diagnostics.Stopwatch.StartNew();
            string? error = await FailureAsync(() => SubscriptionImport.DownloadAsync(privateSource, SubscriptionClientProfile.Mihomo, handler, cancel.Token));
            check(error != null && started.Elapsed < TimeSpan.FromSeconds(2), "subscription cancellation interrupts the pending request promptly");
        }
    }

    internal static async Task IntegrationAsync(Action<bool, string> check)
    {
        await using var origin = await SubscriptionOrigin.CreateAsync();
        using var handler = new HttpClientHandler
        {
            AllowAutoRedirect = false, UseCookies = false, UseProxy = false,
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate | DecompressionMethods.Brotli,
            ServerCertificateCustomValidationCallback = (_, certificate, _, _) => certificate?.Thumbprint == origin.Certificate.Thumbprint
        };
        string direct = origin.Address + "/ua?token=synthetic%2Btoken%26suffix%25";
        var downloaded = await SubscriptionImport.DownloadAsync(direct, SubscriptionClientProfile.Mihomo, handler);
        check(downloaded.Content == ValidConfig && MihomoConfig.ParseSubscription(downloaded.Content) == ValidConfig && origin.LastAgent == "clash.meta", "real HTTPS subscription server accepts the Mihomo identity and gzip YAML configuration");
        check(origin.LastQuery == "?token=synthetic%2Btoken%26suffix%25" && origin.LastEncoding.Contains("gzip"), "HTTPS subscription preserves private query encoding and negotiates decompression");
        int before = origin.Hits;
        string? denied = await FailureAsync(() => SubscriptionImport.DownloadAsync(direct, SubscriptionClientProfile.Clash, handler));
        check(denied != null && denied.Contains("403") && !denied.Contains("synthetic") && origin.Hits == before + 1, "real HTTPS denial is sanitized and does not trigger an automatic profile fallback");
        string redirected = origin.Address + "/redirect?token=synthetic%2Btoken%26suffix%25";
        before = origin.Hits;
        var viaRedirect = await SubscriptionImport.DownloadAsync(redirected, SubscriptionClientProfile.Mihomo, handler);
        check(viaRedirect.Content == ValidConfig && viaRedirect.NormalizedSource == redirected && origin.Hits == before + 2 && origin.LastQuery == "?token=synthetic%2Btoken%26suffix%25", "real HTTPS relative redirect retains the encoded token and original saved source");
    }

    private static HttpResponseMessage Reply(HttpStatusCode status, string body, string media)
        => new(status) { Content = new StringContent(body, Encoding.UTF8, media) };

    private static async Task<string?> FailureAsync(Func<Task> action)
    {
        try { await action(); return null; }
        catch (Exception ex) { return ex.Message; }
    }

    private sealed class FixtureHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> respond) : HttpMessageHandler
    {
        internal int Calls;
        internal string LastAddress = "", UserAgent = "", Accept = "";
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            LastAddress = request.RequestUri!.OriginalString;
            UserAgent = request.Headers.UserAgent.ToString();
            Accept = request.Headers.Accept.ToString();
            return respond(request, cancellationToken);
        }
    }

    private sealed class UnknownLengthContent(byte[] bytes) : HttpContent
    {
        protected override bool TryComputeLength(out long length) { length = 0; return false; }
        protected override Task SerializeToStreamAsync(Stream stream, TransportContext? context) => stream.WriteAsync(bytes).AsTask();
        protected override Task<Stream> CreateContentReadStreamAsync() => Task.FromResult<Stream>(new MemoryStream(bytes, false));
    }

    private sealed class SubscriptionOrigin : IAsyncDisposable
    {
        private readonly WebApplication app;
        internal X509Certificate2 Certificate { get; }
        internal string Address { get; private set; } = "";
        internal string LastAgent = "", LastQuery = "", LastEncoding = "";
        private int hits;
        internal int Hits => Volatile.Read(ref hits);
        private SubscriptionOrigin()
        {
            using var rsa = RSA.Create(2048);
            var request = new CertificateRequest("CN=localhost", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            var names = new SubjectAlternativeNameBuilder();
            names.AddDnsName("localhost"); names.AddIpAddress(IPAddress.Loopback); request.CertificateExtensions.Add(names.Build());
            using var temporary = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddHours(1));
            Certificate = X509CertificateLoader.LoadPkcs12(temporary.Export(X509ContentType.Pfx), null, X509KeyStorageFlags.UserKeySet);
            var builder = WebApplication.CreateSlimBuilder(); builder.Logging.ClearProviders();
            builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0, listen => { listen.Protocols = HttpProtocols.Http1; listen.UseHttps(Certificate); }));
            app = builder.Build(); app.Run(HandleAsync);
        }
        internal static async Task<SubscriptionOrigin> CreateAsync()
        {
            var origin = new SubscriptionOrigin();
            await origin.app.StartAsync();
            origin.Address = origin.app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            return origin;
        }
        private async Task HandleAsync(HttpContext context)
        {
            Interlocked.Increment(ref hits);
            LastAgent = context.Request.Headers.UserAgent.ToString();
            LastQuery = context.Request.QueryString.Value ?? "";
            LastEncoding = context.Request.Headers.AcceptEncoding.ToString();
            if (LastAgent != "clash.meta")
            {
                context.Response.StatusCode = 403;
                await context.Response.WriteAsync("Denied for synthetic private fixture", context.RequestAborted);
                return;
            }
            if (context.Request.Path == "/redirect")
            {
                context.Response.StatusCode = 302;
                context.Response.Headers.Location = "/ua" + LastQuery;
                return;
            }
            using var buffer = new MemoryStream();
            using (var compressed = new GZipStream(buffer, CompressionMode.Compress, leaveOpen: true))
                await compressed.WriteAsync(Encoding.UTF8.GetBytes(ValidConfig), context.RequestAborted);
            context.Response.ContentType = "application/yaml";
            context.Response.Headers.ContentEncoding = "gzip";
            context.Response.ContentLength = buffer.Length;
            await context.Response.Body.WriteAsync(buffer.ToArray(), context.RequestAborted);
        }
        public async ValueTask DisposeAsync() { await app.StopAsync(); await app.DisposeAsync(); Certificate.Dispose(); }
    }

    private static string? Failure(Action action)
    {
        try { action(); return null; }
        catch (Exception ex) { return ex.Message; }
    }
}
