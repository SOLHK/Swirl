using AdShield.Network;
using System.IO;
using Microsoft.Win32;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

internal static class NetworkChecks
{
    internal static void Pure(Action<bool, string> check)
    {
        var plugin = LoonPlugin.Parse("""
            #!name=Local regression fixture
            [Rule]
            DOMAIN,ads.example,REJECT
            [Rewrite]
            ^https://example\.test/ad reject-dict
            [Script]
            http-response pattern=^https://api\.example\.test/data script-path=https://example.test/ad.js requires-body=true
            [MITM]
            hostname = %APPEND% api.example.test, *.example.test
            """, "local fixture");
        check(plugin.Unsupported.Count == 0 && plugin.Rules.Count == 1 && plugin.Scripts.Count == 1 && plugin.Rewrites.Count == 1, "Loon rule/rewrite/script/MITM parsed");
        check(plugin.MatchesHost("api.example.test") && plugin.MatchesHost("a.example.test") && !plugin.MatchesHost("otherexample.test"), "MITM wildcard matches domain boundary");
        check(!plugin.Enabled, "imported plugins are disabled by default");
        check(LoonPlugin.Parse("[Script]\ncron 0 * * * * script-path=https://example.test/a.js", "fixture").Unsupported.Count == 0, "legacy cron scripts are parsed and scheduled");
        check(LoonPlugin.ResolveImportUrl("loon://import?plugin=https://kelee.one/Tool/Loon/Lpx/Tencent_Video_remove_ads.lpx").EndsWith(".lpx"), "author LPX links are accepted without an extension blacklist");
        var lpx = LoonPlugin.Parse("\uFEFF#!name = Plain LPX\n[Script]\nhttp-response ^https://api.example.test/data script-path=remove.js,requires-body=true,argument='ad=remove'\n[MITM]\nhostname = api*.example.test, *.example.test\n[Host]\napi.example.test = 127.0.0.1\n", "https://example.test/plugins/ad.lpx");
        check(lpx.Unsupported.Count == 0 && lpx.Name == "Plain LPX" && lpx.Scripts[0].Url == "https://example.test/plugins/remove.js" && lpx.Scripts[0].Argument == "ad=remove", "LPX content, BOM, spaced metadata, positional scripts and relative resources parse");
        check(lpx.MatchesHost("api2.example.test") && lpx.MatchesHost("a.b.example.test") && !lpx.MatchesHost("evil-example.test"), "MITM supports wildcard hosts without crossing suffix boundary");
        check(lpx.DnsHosts["api.example.test"] == "127.0.0.1", "plugin Host mappings parsed");
        bool htmlRejected = false;
        try { LoonPlugin.Parse("<html>403 Forbidden</html>", "https://example.test/plugin.lpx"); } catch { htmlRejected = true; }
        check(htmlRejected, "web error pages cannot masquerade as imported LPX plugins");
        var jq = LoonPlugin.Parse("[Rewrite]\n^https://example.test/data response-body-json-jq '.ads = []'\nresponse if ${url} ~= /^https:\\/\\/example\\.test\\/data/ then response.json.jq(\"del(.ads)\")\n", "https://example.test/plugin.lpx");
        check(jq.Unsupported.Count == 0 && jq.Rewrites.All(r => r.Phase == "http-response" && r.Syntax.Length > 0), "old and new jq rewrites enter one ordered execution pipeline");
        check(LoonPlugin.Parse("[Rewrite]\nresponse if ${url} ~= /api/ && ${response.status} == 200 then response.json.jq(\"del(.ads)\")", "fixture").Unsupported.Count == 0, "compound URL and response status conditions are preserved");
        check(LoonPlugin.ResolveImportUrl("loon://import?plugin=https%3A%2F%2Fexample.test%2Fad.plugin") == "https://example.test/ad.plugin", "Loon import URI unwraps original HTTPS URL");
        var request = new ScriptMessage("https://api.example.test/data", "GET", new(), "");
        var response = new ScriptMessage(request.Url, "GET", new(), "{\"ads\":[1,2],\"video\":\"keep\"}");
        plugin.Scripts[0].Code = "let b=JSON.parse($response.body);b.ads=[];$done({body:JSON.stringify(b)});";
        var change = PluginScriptRunner.Run(plugin, plugin.Scripts[0], request, response)!;
        using (var json = JsonDocument.Parse(change.Body!))
            check(json.RootElement.GetProperty("ads").GetArrayLength() == 0 && json.RootElement.GetProperty("video").GetString() == "keep", "Loon response script edits ads and preserves video data");
        plugin.Scripts[0].Code = "Promise.resolve().then(()=> $done({body:'async-ok'}));";
        check(PluginScriptRunner.Run(plugin, plugin.Scripts[0], request, response)?.Body == "async-ok", "promise continuation can call $done");
        plugin.Scripts[0].Code = "let t=setTimeout(()=> $done({body:'wrong'}),20);clearTimeout(t);setTimeout(()=> $done({body:'timer-ok'}),30);";
        check(PluginScriptRunner.Run(plugin, plugin.Scripts[0], request, response)?.Body == "timer-ok", "bounded timers execute later and can be cancelled");
        plugin.Scripts[0].Code = "$done({response:{status:200,body:'local-ad-response'}});";
        check(PluginScriptRunner.Run(plugin, plugin.Scripts[0], request, null) is { SyntheticResponse: true, Body: "local-ad-response" }, "request scripts can return synthetic responses");
        plugin.Scripts[0].Code = "while(true){}";
        bool bounded = false;
        try { PluginScriptRunner.Run(plugin, plugin.Scripts[0], request, response); } catch { bounded = true; }
        check(bounded, "runaway script is stopped by execution constraints");
        var profile = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect("proxies:\n  - name: demo\n    type: http\n    server: 127.0.0.1\n    port: 9999\nexternal-controller: 0.0.0.0:9090\nallow-lan: true\n") };
        var config = MihomoConfig.Parse(MihomoConfig.Build(profile, "test-secret"));
        check(config["external-controller"].ToString() == "127.0.0.1:17909" && config["allow-lan"].ToString() == "False", "imported config cannot expose controller/LAN listeners");
        check(MihomoConfig.Build(profile, "test-secret").Contains("demo"), "imported node survives generated config");
        check(ProxyProfile.Unprotect(ProxyProfile.Protect("private-node-token")) == "private-node-token", "user-scoped encrypted profile round trip");
        check(!WindowsSystemProxy.Owns("127.0.0.1:7890", 1) && WindowsSystemProxy.Owns("127.0.0.1:17891", 1), "restore only owns exact AdShield proxy");
        profile.Tun = profile.Mitm = true;
        string capture = MihomoConfig.Build(profile, "test-secret");
        check(capture.Contains(MihomoConfig.CaptureRule) && capture.Contains(MihomoConfig.PluginOutbound), "TUN and HTTPS share plugin path with ingress-specific recursion guard");
        foreach (string mode in new[] { "rule", "global", "direct" })
        {
            profile.Mode = mode;
            var generated = MihomoConfig.Parse(MihomoConfig.Build(profile, "test-secret"));
            check(generated["mode"].ToString() == "rule" && generated["rules"] is IEnumerable<object> routeRules && routeRules.First().ToString() == MihomoConfig.CaptureRule && routeRules.Last().ToString() == "MATCH," + (mode == "global" ? "GLOBAL" : mode == "direct" ? "DIRECT" : "Swirl 节点"), "TUN plugin interception survives " + mode + " mode");
        }
        var global = new ProxyProfile { Mode = "global" };
        check(MihomoConfig.PreferredGroup(global) == "GLOBAL", "global mode selects the effective GLOBAL group");
        var imported = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect("rules:\n  - MATCH,ImportedGroup\n") };
        check(MihomoConfig.PreferredGroup(imported) == "ImportedGroup", "imported rule mode selects its effective final group");
        check(MihomoConfig.Build(new ProxyProfile { BasicAds = true }, "test-secret").Contains("doubleclick.net"), "first-party basic ad domain rules included");
        check(!MihomoConfig.Build(new ProxyProfile { BasicAds = false }, "test-secret").Contains("doubleclick.net"), "basic ad domain rules can be disabled");
        var protectedCapture = new ProxyProfile { Tun = true, ProtectedYaml = ProxyProfile.Protect("dns:\n  enable: false\n  nameserver: []\nproxy-groups:\n  - name: all\n    type: select\n    include-all: true\n") };
        string protectedConfig = MihomoConfig.Build(protectedCapture, "fixture");
        check(protectedConfig.Contains("exclude-filter: ^" + MihomoConfig.PluginOutbound + "$") && protectedConfig.Contains("nameserver:") && protectedConfig.Contains("enable: true"), "TUN enables a usable DNS resolver and hides internal proxy from include-all groups");
        var proxyRule = LoonPlugin.Parse("[Rule]\nDOMAIN,example.test,PROXY", "https://example.test/rule.lpx");
        proxyRule.Enabled = true;
        check(MihomoConfig.Build(new ProxyProfile { Plugins = new() { proxyRule } }, "fixture").Contains("DOMAIN,example.test,Swirl 节点"), "Loon PROXY rule resolves to user-selectable node group");
        var catalog = PluginCatalog.Parse("""
            {"notice":["author notice"],"lists":[{"name":"fixture","desc":"test","url":"loon://import?plugin=https://example.test/a.lpx"},{"name":"bad","url":"javascript:bad"}]}
            """);
        check(catalog.Notice == "author notice" && catalog.Entries.Length == 1 && catalog.Entries[0].Url == "https://example.test/a.lpx", "catalog preserves author notice and accepts only original HTTPS plugin URLs");
    }

    internal static async Task IntegrationAsync(Action<bool, string> check)
    {
        var originalDirectory = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.GetFullPath(Path.Combine("..", "network-integration-" + Guid.NewGuid().ToString("N")));
        string before = SystemProxyFingerprint();
        string registryPath = @"Software\AdShield.Tests\" + Guid.NewGuid().ToString("N");
        try
        {
            using (var key = Registry.CurrentUser.CreateSubKey(registryPath))
            {
                key.SetValue("ProxyEnable", 1); key.SetValue("ProxyServer", "original-proxy:7890"); key.SetValue("AutoConfigURL", "https://original.example/pac");
            }
            WindowsSystemProxy.TestRegistryPath = registryPath;
            WindowsSystemProxy.Enable();
            WindowsSystemProxy.Restore();
            using (var key = Registry.CurrentUser.OpenSubKey(registryPath))
                check(key?.GetValue("ProxyServer")?.ToString() == "original-proxy:7890" && key.GetValue("AutoConfigURL")?.ToString() == "https://original.example/pac", "native proxy backup restores original proxy and PAC in isolated registry");
            WindowsSystemProxy.Enable();
            using (var key = Registry.CurrentUser.OpenSubKey(registryPath, true)) key!.SetValue("ProxyServer", "new-user-proxy:9999");
            WindowsSystemProxy.Restore();
            using (var key = Registry.CurrentUser.OpenSubKey(registryPath)) check(key!.GetValue("ProxyServer")!.ToString() == "new-user-proxy:9999", "restore preserves user's later proxy change");
            WindowsSystemProxy.TestRegistryPath = null;
            await using var origin = new LocalOrigin();
            string firstRoot, secondRoot;
            using (var certificates = new PluginProxy(Array.Empty<LoonPlugin>(), false, _ => { })) firstRoot = certificates.PrepareRootFingerprint();
            using (var certificates = new PluginProxy(Array.Empty<LoonPlugin>(), false, _ => { })) secondRoot = certificates.PrepareRootFingerprint();
            check(firstRoot == secondRoot, "certificate identity survives helper/runtime recreation");
            var profile = new ProxyProfile();
            var plugin = LoonPlugin.Parse($"""
                #!name=Local network fixture
                [Rule]
                DOMAIN,localhost,REJECT
                [Rewrite]
                ^http://127\.0\.0\.1:{origin.Port}/advert reject-dict
                [Script]
                http-response pattern=^http://127\.0\.0\.1:{origin.Port}/data script-path=https://example.test/test.js requires-body=true
                """, "local fixture");
            plugin.Enabled = true;
            plugin.Scripts[0].Code = "var b=JSON.parse($response.body); b.ads=[]; $done({body:JSON.stringify(b)});";
            plugin.Scripts.Add(new LoonScript { Phase = "http-request", Pattern = "^http://127\\.0\\.0\\.1:" + origin.Port + "/synthetic", Code = "$done({response:{status:200,body:'local-script-response'}});" });
            plugin.Scripts.Add(new LoonScript { Phase = "http-response", Pattern = "^http://127\\.0\\.0\\.1:" + origin.Port + "/helper", NeedsBody = true,
                Code = "$httpClient.get('http://127.0.0.1:" + origin.Port + "/inner',(e,r,b)=>$done({body:JSON.stringify({helper:r.status})}));" });
            profile.Plugins.Add(plugin);
            var records = new List<string>();
            using var controller = new ProxyController(message => { lock(records) records.Add(message); });
            await controller.StartAsync(profile, false);
            check(controller.Running, "bundled Mihomo core starts with validated config");
            check(SystemProxyFingerprint() == before, "integration test does not change user's system proxy");
            var groups = await controller.GroupsAsync();
            check(groups.Values.Any(values => values.Contains("DIRECT")), "loopback controller exposes selectable node groups");
            await controller.SelectAsync(groups.Keys.First(), "DIRECT");
            using var handler = new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.PluginPort), UseProxy = true };
            using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(10) };
            string rewritten = await client.GetStringAsync("http://127.0.0.1:" + origin.Port + "/data");
            using (var json = JsonDocument.Parse(rewritten))
                check(json.RootElement.GetProperty("ads").GetArrayLength() == 0 && json.RootElement.GetProperty("video").GetString() == "keep", "real HTTP traffic passes core and response-script layer");
            int hits = origin.Hits;
            check(await client.GetStringAsync("http://127.0.0.1:" + origin.Port + "/advert") == "{}" && origin.Hits == hits, "URL rejection responds locally without hitting origin");
            check(await client.GetStringAsync("http://127.0.0.1:" + origin.Port + "/synthetic") == "local-script-response" && origin.Hits == hits, "request script returns real local response without origin call");
            using (var json = JsonDocument.Parse(await client.GetStringAsync("http://127.0.0.1:" + origin.Port + "/helper")))
                check(json.RootElement.GetProperty("helper").GetInt32() == 200, "Loon httpClient helper uses core without rewrite recursion");
            hits = origin.Hits;
            bool blocked = false;
            try { using var rejected = await client.GetAsync("http://localhost:" + origin.Port + "/blocked"); blocked = !rejected.IsSuccessStatusCode; } catch (HttpRequestException) { blocked = true; }
            check(blocked && origin.Hits == hits, "Mihomo domain REJECT stops matching request");
            controller.Stop();
            check(!controller.Running && SystemProxyFingerprint() == before, "stop kills managed core and leaves system settings intact");
        }
        finally
        {
            WindowsSystemProxy.TestRegistryPath = null;
            ProxyProfile.TestDirectory = originalDirectory;
            if (registryPath.StartsWith(@"Software\AdShield.Tests\", StringComparison.Ordinal)) Registry.CurrentUser.DeleteSubKeyTree(registryPath, false);
        }
    }
    private static string SystemProxyFingerprint()
    {
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Internet Settings");
        return string.Join("|", new[] { "ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL", "AutoDetect" }.Select(name => name + "=" + key?.GetValue(name)));
    }
}

internal sealed class LocalOrigin : IAsyncDisposable
{
    private readonly TcpListener listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource stopping = new();
    private readonly Task loop;
    private int hits;
    internal int Hits => Volatile.Read(ref hits);
    internal int Port { get; }
    internal LocalOrigin()
    {
        listener.Start(); Port = ((IPEndPoint)listener.LocalEndpoint).Port; loop = RunAsync();
    }
    private async Task RunAsync()
    {
        while (!stopping.IsCancellationRequested)
        {
            try
            {
                using var client = await listener.AcceptTcpClientAsync(stopping.Token);
                // The proxy may probe ALPN before it knows a CONNECT carries
                // plain HTTP. A real HTTP origin rejects a TLS ClientHello.
                var probe = new byte[1];
                if (await client.Client.ReceiveAsync(probe, SocketFlags.Peek, stopping.Token) == 0 || probe[0] == 22) continue;
                using var stream = client.GetStream();
                using var reader = new StreamReader(stream, Encoding.ASCII, false, 4096, true);
                string? line;
                while ((line = await reader.ReadLineAsync(stopping.Token)) != null && line.Length > 0) { }
                Interlocked.Increment(ref hits);
                const string body = "{\"ads\":[1,2],\"video\":\"keep\"}";
                string response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + Encoding.UTF8.GetByteCount(body) + "\r\nConnection: close\r\n\r\n" + body;
                await stream.WriteAsync(Encoding.UTF8.GetBytes(response), stopping.Token);
            }
            catch (OperationCanceledException) { break; }
            catch (IOException) { /* A client may probe or abandon a connection. */ }
            catch (SocketException) when (stopping.IsCancellationRequested) { break; }
            catch (SocketException e) when (e.SocketErrorCode is SocketError.ConnectionReset or SocketError.ConnectionAborted) { }
        }
    }
    public async ValueTask DisposeAsync() { stopping.Cancel(); listener.Stop(); await loop; stopping.Dispose(); }
}
