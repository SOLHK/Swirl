using AdShield.Network;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;

internal static class ScriptRuntimeChecks
{
    internal static void Pure(Action<bool, string> check)
    {
        var plugin = LoonPlugin.Parse("[Script]\nhttp-response ^https://example.test/body script-path=https://example.test/a.js,requires-body=true,binary-body-mode=true", "https://example.test/a.plugin");
        check(plugin.Unsupported.Count == 0 && ScriptSettings.For(plugin, plugin.Scripts[0]).BinaryBody, "legacy binary script mode imports without rejection");
        var script = plugin.Scripts[0];
        script.Code = "if(!($response.body instanceof Uint8Array))throw Error('body');$response.body[1]=7;$done({body:$response.body});";
        var response = new ScriptMessage("https://example.test/body", "GET", new(), "", BodyBytes: new byte[] { 0, 255, 128, 1 });
        check(PluginScriptRunner.Run(plugin, script, response, response)?.BodyBytes?.SequenceEqual(new byte[] { 0, 7, 128, 1 }) == true, "Uint8Array script input and output preserve non UTF8 bytes");
        script.Code = "$done({response:{status:201,body:new Uint8Array([0,255,128])}});";
        check(PluginScriptRunner.Run(plugin, script, response, null) is { SyntheticResponse: true, Status: 201, BodyBytes: [0, 255, 128] }, "synthetic request response returns exact binary bytes");
        script.Code = "let b=new Uint8Array([0,255,128,1]);let zipped=$utils.gzip(b);let result=$utils.ungzip(zipped);$done({body:result});";
        check(PluginScriptRunner.Run(plugin, script, response, response)?.BodyBytes?.SequenceEqual(new byte[] { 0, 255, 128, 1 }) == true, "gzip helpers round trip binary bytes");
        script.Code = "let b=new Uint8Array([0,255,128,1]);let o={mode:'gcm',key:new Uint8Array(32),iv:new Uint8Array(12),aad:new Uint8Array([1])};let e=$crypto.aes.encrypt(b,o);o.tag=e.tag;$done({body:$crypto.aes.decrypt(e.ciphertext,o)});";
        check(PluginScriptRunner.Run(plugin, script, response, response)?.BodyBytes?.SequenceEqual(new byte[] { 0, 255, 128, 1 }) == true, "AES GCM helper round trip authenticated binary bytes");
        script.Code = "let o={mode:'gcm',key:new Uint8Array(16),iv:new Uint8Array(12)};let e=$crypto.aes.encrypt(new Uint8Array([1]),o);e.tag[0]^=1;o.tag=e.tag;try{$crypto.aes.decrypt(e.ciphertext,o);$done({body:'wrong'});}catch(e){$done({body:'rejected'});}";
        check(PluginScriptRunner.Run(plugin, script, response, response)?.Body == "rejected", "AES GCM rejects changed authentication tag inside script try catch");
        script.Code = "try{$utils.ungzip(new Uint8Array([1,2]));$done({body:'wrong'});}catch(e){$done({body:'rejected'});}";
        check(PluginScriptRunner.Run(plugin, script, response, response)?.Body == "rejected", "invalid gzip error is catchable inside script");
        foreach (var mode in new[] { "ecb", "cbc", "ctr" })
        {
            script.Code = "let b=new Uint8Array([0,255,128,1]);let o={mode:'" + mode + "',key:new Uint8Array(16)};if(o.mode!=='ecb')o.iv=new Uint8Array(16);let e=$crypto.aes.encrypt(b,o);$done({body:$crypto.aes.decrypt(e.ciphertext,o)});";
            check(PluginScriptRunner.Run(plugin, script, response, response)?.BodyBytes?.SequenceEqual(new byte[] { 0, 255, 128, 1 }) == true, "AES " + mode + " helper round trip binary bytes");
        }
        script.Tag = "named-storage";
        script.Code = "$persistentStore.write('saved');if($persistentStore.read('named-storage')!=='saved')throw Error('default key');$persistentStore.write(undefined);$done({body:String($persistentStore.read())});";
        check(PluginScriptRunner.Run(plugin, script, response, response)?.Body == "null", "persistent store defaults to script name and supports key deletion");
        var modern = LoonPlugin.Parse("[Script]\nresponse if ${url} ~= /body/ then script(\"a.js\") with binary_body_mode=true", "https://example.test/a.plugin");
        var settings = ScriptSettings.For(modern, modern.Scripts[0]);
        check(settings.BinaryBody && !settings.NeedsBody, "binary representation does not implicitly require body buffering");
        var dynamic = LoonPlugin.Parse("""
            [Script]
            response if ${url} ~= /body/ then script("dynamic.js", "${url}|${request.header['X-Session']}|${response.status}|${response.header['Content-Type']}")
            """, "https://example.test/a.plugin");
        check(dynamic.Unsupported.Count == 0, "HTTP context script arguments import as supported dynamic templates");
        dynamic.Scripts[0].Code = "$done({body:$argument});";
        var argumentRequest = new ScriptMessage("https://example.test/body?region=cn", "POST", new(StringComparer.OrdinalIgnoreCase) { ["x-session"] = "fixture-session" }, "");
        var argumentResponse = new ScriptMessage(argumentRequest.Url, "POST", new(StringComparer.OrdinalIgnoreCase) { ["content-type"] = "application/json" }, "", 202);
        check(PluginScriptRunner.Run(dynamic, dynamic.Scripts[0], argumentRequest, argumentResponse)?.Body == "https://example.test/body?region=cn|fixture-session|202|application/json", "dynamic script argument uses actual URL request header response status and header");
        script.BinaryBody = false; script.Code = "$done('x'.repeat(3*1024*1024));";
        bool oversized = false; try { PluginScriptRunner.Run(plugin, script, argumentRequest, argumentResponse); } catch (InvalidOperationException) { oversized = true; }
        check(oversized, "direct string script completion cannot bypass two MB body limit");
    }

    internal static async Task IntegrationAsync(Action<bool, string> check)
    {
        string? oldDirectory = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.GetFullPath(Path.Combine("..", "script-h2-integration-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        try
        {
            await using var origin = await ScriptH2Origin.CreateAsync();
            string address = origin.Address;
            var plugin = LoonPlugin.Parse($$"""
                #!name=HTTP2 binary fixture
                [Script]
                http-request ^{{address}}/json script-path=https://example.test/request.js,requires-body=true
                http-response ^{{address}}/json script-path=https://example.test/response.js,requires-body=true
                http-request ^{{address}}/binary script-path=https://example.test/request-binary.js,requires-body=true,binary-body-mode=true
                http-response ^{{address}}/binary script-path=https://example.test/response-binary.js,requires-body=true,binary-body-mode=true
                http-request ^{{address}}/synthetic script-path=https://example.test/local.js,binary-body-mode=true
                [MITM]
                hostname=127.0.0.1
                """, "https://example.test/fixture.plugin");
            check(plugin.Unsupported.Count == 0, "HTTP2 integration fixture imports as supported plugin");
            plugin.Enabled = true;
            plugin.Scripts[0].Code = "let b=JSON.parse($request.body);b.request='changed';$request.headers['x-swirl-request']='yes';setTimeout(()=>$done({body:JSON.stringify(b),headers:$request.headers}),30);";
            plugin.Scripts[1].Code = "let b=JSON.parse($response.body);b.ads=[];$response.headers['x-swirl-response']='yes';$done({body:JSON.stringify(b),headers:$response.headers,status:201});";
            plugin.Scripts[2].Code = "let b=new Uint8Array($request.body.length+2);b.set($request.body);b[0]=7;b[b.length-2]=42;b[b.length-1]=43;setTimeout(()=>$done({body:b}),20);";
            plugin.Scripts[3].Code = "let b=new Uint8Array($response.body.length+1);b.set($response.body);b[1]=9;b[b.length-1]=90;$done({body:b});";
            plugin.Scripts[4].Code = "$done({response:{status:200,headers:{'content-type':'application/octet-stream'},body:new Uint8Array([0,255,128])}});";
            string file = Path.Combine(ProxyProfile.DirectoryPath, "config.yaml");
            File.WriteAllText(file, MihomoConfig.Build(new ProxyProfile { Plugins = new() { plugin }, BasicAds = false }, "runtime-fixture"));
            using var core = Process.Start(ProxyController.StartInfo(ProxyProfile.DirectoryPath, file))!;
            using var job = new CoreProcessJob(core);
            Task<string> stdout = core.StandardOutput.ReadToEndAsync(), stderr = core.StandardError.ReadToEndAsync();
            try
            {
                using var health = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(1) };
                bool ready = false;
                for (int i = 0; i < 80 && !core.HasExited; i++)
                {
                    try { using var result = await health.GetAsync("http://127.0.0.1:" + MihomoConfig.ControllerPort + "/version"); ready = true; } catch (HttpRequestException) { }
                    if (ready) break; await Task.Delay(100);
                }
                check(ready, "HTTP2 fixture core starts without system proxy or TUN routes");
                var logs = new List<string>();
                using var proxy = new PluginProxy(new[] { plugin }, true, message => { lock (logs) logs.Add(message); }, false, origin.Certificate.Thumbprint);
                using var root = proxy.ExportRootCertificate(); proxy.Start();
                using var handler = new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.PluginPort), UseProxy = true };
                handler.ServerCertificateCustomValidationCallback = (_, certificate, _, _) =>
                {
                    if (certificate == null) return false;
                    using var chain = new X509Chain(); chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
                    chain.ChainPolicy.CustomTrustStore.Add(root); chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
                    return chain.Build(certificate);
                };
                using var client = new HttpClient(handler) { DefaultRequestVersion = HttpVersion.Version20, DefaultVersionPolicy = HttpVersionPolicy.RequestVersionExact, Timeout = TimeSpan.FromSeconds(15) };
                using var request = new HttpRequestMessage(HttpMethod.Post, address + "/json") { Version = HttpVersion.Version20, VersionPolicy = HttpVersionPolicy.RequestVersionExact, Content = new StringContent("{\"ads\":[1,2],\"request\":\"old\"}", Encoding.UTF8, "application/json") };
                using var response = await client.SendAsync(request);
                string text = await response.Content.ReadAsStringAsync();
                check(response.Version == HttpVersion.Version20 && origin.LastProtocol == "HTTP/2", "client and origin negotiate real HTTP2 through HTTPS MITM");
                using (var json = JsonDocument.Parse(text))
                    check(json.RootElement.GetProperty("ads").GetArrayLength() == 0 && json.RootElement.GetProperty("request").GetString() == "changed", "HTTP2 request and response script body mutations reach both peers");
                check(response.StatusCode == HttpStatusCode.Created && response.Headers.GetValues("x-swirl-response").Single() == "yes" && origin.LastRequestHeader == "yes", "HTTP2 status and request response headers are modified");
                check(origin.LastContentLength == Encoding.UTF8.GetByteCount("{\"ads\":[1,2],\"request\":\"changed\"}"), "HTTP2 request Content-Length follows buffered body size change");
                using (var freshHandler = new HttpClientHandler { Proxy = handler.Proxy, UseProxy = true, ServerCertificateCustomValidationCallback = handler.ServerCertificateCustomValidationCallback })
                using (var freshClient = new HttpClient(freshHandler) { Timeout = TimeSpan.FromSeconds(15) })
                using (var freshRequest = new HttpRequestMessage(HttpMethod.Post, address + "/json") { Version = HttpVersion.Version20, VersionPolicy = HttpVersionPolicy.RequestVersionExact, Content = new StringContent("{\"ads\":[1,2],\"request\":\"old\"}", Encoding.UTF8, "application/json") })
                using (var freshResponse = await freshClient.SendAsync(freshRequest))
                    check(freshResponse.Version == HttpVersion.Version20 && freshResponse.StatusCode == HttpStatusCode.Created && (await freshResponse.Content.ReadAsStringAsync()).Contains("changed"), "fresh TLS connection retains HTTP2 asynchronous script mutations");
                using var binary = new HttpRequestMessage(HttpMethod.Post, address + "/binary") { Version = HttpVersion.Version20, VersionPolicy = HttpVersionPolicy.RequestVersionExact, Content = new ByteArrayContent(new byte[] { 0, 255, 128, 1 }) };
                using var binaryResponse = await client.SendAsync(binary);
                check((await binaryResponse.Content.ReadAsByteArrayAsync()).SequenceEqual(new byte[] { 7, 9, 128, 1, 42, 43, 90 }) && origin.LastContentLength == 6, "HTTP2 binary scripts change lengths and preserve exact bytes");
                int hits = origin.Hits;
                check((await client.GetByteArrayAsync(address + "/synthetic")).SequenceEqual(new byte[] { 0, 255, 128 }) && origin.Hits == hits, "HTTP2 synthetic binary response does not call origin");
                var helper = new LoonScript { Phase = "generic", Tag = "helper" };
                helper.Code = "let base='" + address + "';$httpClient.post({url:base+'/binary',body:new Uint8Array([0,255,128]),'binary-mode':true,insecure:true,alpn:'h2'},(e,r,b)=>{if(e)throw Error(e);if(!(b instanceof Uint8Array))throw Error('not binary');$done({body:b});});";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.BodyBytes?.SequenceEqual(new byte[] { 0, 255, 128 }) == true && origin.LastProtocol == "HTTP/2", "HTTP helper binary mode and h2 ALPN send exact bytes through core");
                helper.Code = "$httpClient.post({url:'" + address + "/binary',body:'AP+A','body-base64':true,insecure:true},(e,r,b)=>{if(e)throw Error(e);$done({body:b});});";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.BodyBytes?.SequenceEqual(new byte[] { 0, 255, 128 }) == true, "HTTP helper base64 upload and invalid UTF8 response use binary representation");
                helper.Code = "let base='" + address + "';$httpClient.get({url:base+'/cookie',insecure:true},(e)=>{$httpClient.get({url:base+'/check-cookie',insecure:true},(e,r,b)=>$done({body:b}));});";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.Body == "fixture=kept", "HTTP helper reuses cookies only within current script execution");
                helper.Code = "$httpClient.get({url:'" + address + "/check-cookie',insecure:true},(e,r,b)=>$done({body:b}));";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.Body == "", "cookie state does not leak between separate script executions");
                helper.Code = "$httpClient.get({url:'" + address + "/redirect',insecure:true,'auto-redirect':false},(e,r,b)=>$done({body:String(r.status)}));";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.Body == "302", "HTTP helper respects disabled automatic redirects");
                helper.Code = "$httpClient.get({url:'" + address + "/delay',insecure:true,timeout:30},(e,r,b)=>$done({body:e?'timeout':'wrong'}));";
                check(PluginScriptRunner.Run(plugin, helper, null, null)?.Body == "timeout", "HTTP helper bounds delayed response by request timeout");
            }
            finally { if (!core.HasExited) core.Kill(true); await core.WaitForExitAsync(); await Task.WhenAll(stdout, stderr); }
            await UrlRoutingChecksAsync(origin, check);
        }
        finally { ProxyProfile.TestDirectory = oldDirectory; }
    }

    private static async Task UrlRoutingChecksAsync(ScriptH2Origin origin, Action<bool, string> check)
    {
        using var upstream = new Titanium.Web.Proxy.ProxyServer(false, false, false);
        upstream.Logging.Enabled = false;
        int policyHits = 0;
        var endpoint = new Titanium.Web.Proxy.Models.ExplicitProxyEndPoint(IPAddress.Loopback, 0, false);
        endpoint.BeforeTunnelConnectRequest += (_, _) => { Interlocked.Increment(ref policyHits); return Task.CompletedTask; };
        upstream.AddEndPoint(endpoint); upstream.Start(false);
        var profile = new ProxyProfile
        {
            Mitm = true, BasicAds = false,
            ProtectedYaml = ProxyProfile.Protect($"proxies:\n  - name: FixtureRoute\n    type: http\n    server: 127.0.0.1\n    port: {endpoint.Port}\nproxy-groups:\n  - name: RouteGroup\n    type: select\n    proxies: [FixtureRoute]\nrules:\n  - MATCH,REJECT\n")
        };
        foreach (var path in new[] { ("/routed", "RouteGroup"), ("/direct", "DIRECT"), ("/blocked", "REJECT") })
            profile.UserRules.Add(new UserRoutingRule { Kind = "URL-REGEX", Value = "^" + System.Text.RegularExpressions.Regex.Escape(origin.Address + path.Item1) + "$", Policy = path.Item2, HttpsHosts = "127.0.0.1" });
        UserRouting.Prepare(profile);
        string file = Path.Combine(ProxyProfile.DirectoryPath, "url-config.yaml"); File.WriteAllText(file, MihomoConfig.Build(profile, "url-fixture"));
        using var proxy = new PluginProxy(UserRouting.EffectivePlugins(profile), true, _ => { }, false, origin.Certificate.Thumbprint, profile);
        using var root = proxy.ExportRootCertificate(); proxy.Start();
        using var core = Process.Start(ProxyController.StartInfo(ProxyProfile.DirectoryPath, file))!; using var job = new CoreProcessJob(core);
        Task<string> stdout = core.StandardOutput.ReadToEndAsync(), stderr = core.StandardError.ReadToEndAsync();
        try
        {
            using var health = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(1) };
            bool ready = false;
            for (int i = 0; i < 80 && !core.HasExited; i++)
            {
                try { using var result = await health.GetAsync("http://127.0.0.1:" + MihomoConfig.ControllerPort + "/version"); ready = true; } catch (HttpRequestException) { }
                if (ready) break; await Task.Delay(100);
            }
            check(ready, "core starts real URL policy listeners");
            using var handler = new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.PluginPort), UseProxy = true };
            handler.ServerCertificateCustomValidationCallback = (_, certificate, _, _) =>
            {
                if (certificate == null) return false; using var chain = new X509Chain(); chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
                chain.ChainPolicy.CustomTrustStore.Add(root); chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck; return chain.Build(certificate);
            };
            using var client = new HttpClient(handler) { DefaultRequestVersion = HttpVersion.Version20, DefaultVersionPolicy = HttpVersionPolicy.RequestVersionExact, Timeout = TimeSpan.FromSeconds(12) };
            using var routed = await client.GetAsync(origin.Address + "/routed");
            check(routed.IsSuccessStatusCode && routed.Version == HttpVersion.Version20 && policyHits > 0, "HTTPS URL rule routes real HTTP2 client through named node policy");
            int before = policyHits;
            using var direct = await client.GetAsync(origin.Address + "/direct");
            check(direct.IsSuccessStatusCode && direct.Version == HttpVersion.Version20 && policyHits == before, "same HTTP2 connection chooses DIRECT independently for another URL");
            int originBefore = origin.Hits;
            using var blocked = await client.GetAsync(origin.Address + "/blocked");
            check(blocked.StatusCode == HttpStatusCode.Forbidden && origin.Hits == originBefore, "HTTPS URL REJECT stops HTTP2 request before origin");
            using var unmatched = await client.GetAsync(origin.Address + "/unmatched");
            check(!unmatched.IsSuccessStatusCode && origin.Hits == originBefore, "URL listener override preserves REJECT fallback for unmatched HTTPS paths");
        }
        finally { if (!core.HasExited) core.Kill(true); await core.WaitForExitAsync(); await Task.WhenAll(stdout, stderr); upstream.Stop(); }
    }
}

internal sealed class ScriptH2Origin : IAsyncDisposable
{
    private readonly WebApplication app;
    internal X509Certificate2 Certificate { get; }
    internal string Address { get; private set; } = "";
    internal string LastProtocol { get; private set; } = "";
    internal string LastRequestHeader { get; private set; } = "";
    internal long? LastContentLength { get; private set; }
    private int hits;
    internal int Hits => Volatile.Read(ref hits);
    private ScriptH2Origin()
    {
        using var rsa = RSA.Create(2048); var request = new CertificateRequest("CN=localhost", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        var names = new SubjectAlternativeNameBuilder(); names.AddDnsName("localhost"); names.AddIpAddress(IPAddress.Loopback); request.CertificateExtensions.Add(names.Build());
        using var temporary = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddHours(1));
        Certificate = X509CertificateLoader.LoadPkcs12(temporary.Export(X509ContentType.Pfx), null, X509KeyStorageFlags.UserKeySet);
        var builder = WebApplication.CreateSlimBuilder(); builder.Logging.ClearProviders();
        builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0, listen => { listen.Protocols = HttpProtocols.Http1AndHttp2; listen.UseHttps(Certificate); }));
        app = builder.Build(); app.Run(HandleAsync);
    }
    internal static async Task<ScriptH2Origin> CreateAsync()
    {
        var origin = new ScriptH2Origin(); await origin.app.StartAsync();
        origin.Address = origin.app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
        return origin;
    }
    private async Task HandleAsync(HttpContext context)
    {
        Interlocked.Increment(ref hits); LastProtocol = context.Request.Protocol; LastRequestHeader = context.Request.Headers["x-swirl-request"].ToString(); LastContentLength = context.Request.ContentLength;
        byte[] body;
        switch (context.Request.Path.Value)
        {
            case "/cookie": context.Response.Headers.SetCookie = "fixture=kept; Path=/"; body = Encoding.UTF8.GetBytes("ok"); break;
            case "/check-cookie": body = Encoding.UTF8.GetBytes(context.Request.Headers.Cookie.ToString()); break;
            case "/redirect": context.Response.StatusCode = 302; context.Response.Headers.Location = "/check-cookie"; body = Array.Empty<byte>(); break;
            case "/delay": await Task.Delay(300, context.RequestAborted); body = Array.Empty<byte>(); break;
            default:
                using (var buffer = new MemoryStream()) { await context.Request.Body.CopyToAsync(buffer); body = buffer.ToArray(); }
                if (body.Length == 0) body = Encoding.UTF8.GetBytes("{\"ads\":[1,2],\"request\":\"old\"}");
                context.Response.ContentType = context.Request.Path == "/binary" ? "application/octet-stream" : "application/json";
                break;
        }
        context.Response.ContentLength = body.Length; await context.Response.Body.WriteAsync(body);
    }
    public async ValueTask DisposeAsync() { await app.StopAsync(); await app.DisposeAsync(); Certificate.Dispose(); }
}
