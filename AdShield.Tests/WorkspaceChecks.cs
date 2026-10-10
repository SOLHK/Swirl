using AdShield.Network;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

internal static class WorkspaceChecks
{
    internal static void Pure(Action<bool, string> check)
    {
        var usage = SubscriptionUsage.Parse("upload=1073741824; download=2147483648; total=10737418240; expire=1790000000");
        check(usage?.Used == 3221225472 && usage.Percent == 30 && usage.Expires != null, "subscription usage parses real provider totals and expiration without guessing");
        check(SubscriptionUsage.Parse(null) == null && SubscriptionUsage.Parse("not-a-number") == null, "missing provider metadata stays unknown");
        check(SubscriptionUsage.Parse("total=100")?.Used == null && SubscriptionUsage.Parse("upload=-1; download=overflow; total=0; expire=999999999999")?.Percent == null, "incomplete or invalid usage cannot display fake zero usage or an invalid date");
        check(SubscriptionUsage.Parse("upload=9223372036854775807; download=1")?.Used == null, "provider usage overflow is bounded");
        var profile = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(NodeSelectionChecks.Fixture), ProtectedSubscription = ProxyProfile.Protect("https://one.example.test/sub?token=fixture-secret-token"), SelectedProxies = new() { ["Proxy"] = "SG" } };
        SubscriptionLibrary.Ensure(profile); string first = profile.ActiveSubscriptionId;
        check(SubscriptionLibrary.Read(profile).Count == 1 && profile.Yaml == NodeSelectionChecks.Fixture, "legacy single subscription migrates without changing its configuration");
        var second = SubscriptionLibrary.Add(profile, "备用订阅", new(NodeSelectionChecks.Fixture, "https://two.example.test/sub?token=second-fixture-secret-token", usage), SubscriptionClientProfile.Clash, SubscriptionDownloadRoute.SystemProxy);
        check(SubscriptionLibrary.Read(profile).Count == 2 && profile.ActiveSubscriptionId == first, "adding another subscription keeps the active configuration");
        SubscriptionLibrary.Activate(profile, second.Id); profile.SelectedProxies = new() { ["Proxy"] = "HK" }; SubscriptionLibrary.CaptureActive(profile); SubscriptionLibrary.Activate(profile, first);
        check(profile.SelectedProxies["Proxy"] == "SG", "each subscription restores its own selected node");
        var custom = new PolicyGroupSettings { Name = "我的自动选择", Type = "url-test", AllNodes = true, Tolerance = 75, Interval = 300, Timeout = 4000 };
        UserProxyGroups.Save(profile, custom, true); SubscriptionLibrary.CaptureActive(profile);
        check(UserRouting.Policies(profile).Contains(custom.Name) && ProxyCatalog.FromProfile(profile).Groups[custom.Name].Members.Length == 2, "new policy groups are usable by routing and contain the selected node source");
        SubscriptionLibrary.Activate(profile, second.Id); check(profile.GroupSettings.Count == 0, "policy edits remain scoped to the subscription that owns them");
        SubscriptionLibrary.Activate(profile, first); check(profile.GroupSettings.Single().Tolerance == 75, "subscription switching restores its policy edits");
        SubscriptionLibrary.Add(profile, "日常订阅", new(NodeSelectionChecks.Fixture, "https://one.example.test/sub?token=fixture-secret-token", usage), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic);
        check(SubscriptionLibrary.Read(profile).Count == 2 && profile.GroupSettings.Count == 1, "updating the same URL preserves custom groups and avoids duplicate subscription cards");
        check(!JsonSerializer.Serialize(profile).Contains("fixture-secret-token") && !JsonSerializer.Serialize(profile).Contains("我的自动选择"), "subscription URLs, nodes and custom policy definitions stay encrypted on disk");
        string oldYaml = profile.ProtectedYaml; bool rejected = false;
        try { SubscriptionLibrary.Add(profile, "坏配置", new("<html>error</html>", "https://bad.example.test/sub"), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Direct); } catch (InvalidOperationException) { rejected = true; }
        check(rejected && profile.ProtectedYaml == oldYaml && SubscriptionLibrary.Read(profile).Count == 2, "invalid subscription updates cannot replace a working configuration");
        var pinned = new ProxyProfile(); SubscriptionLibrary.Add(pinned, "Pinned", new(NodeSelectionChecks.Fixture, "https://pinned.example.test/sub"), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic); UserProxyGroups.Save(pinned, new PolicyGroupSettings { Name = "固定节点", Members = ["SG"] }, true);
        oldYaml = pinned.ProtectedYaml; rejected = false;
        try { SubscriptionLibrary.Add(pinned, "Pinned", new(NodeSelectionChecks.Fixture.Replace("- {name: SG, type: http, server: 192.0.2.2, port: 8080}", ""), "https://pinned.example.test/sub"), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic); } catch (InvalidOperationException) { rejected = true; }
        check(rejected && pinned.ProtectedYaml == oldYaml, "subscription updates retain the working config when custom groups still reference removed nodes");
        var local = new ProxyProfile(); var localEntry = SubscriptionLibrary.Add(local, "Local", new(NodeSelectionChecks.Fixture, ""), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic); SubscriptionLibrary.Add(local, "Local", new(NodeSelectionChecks.Fixture, ""), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic, localEntry.Id);
        check(SubscriptionLibrary.Read(local).Count == 1, "local file reimport updates the intended card instead of creating a duplicate");
        SubscriptionLibrary.Rename(profile, second.Id, "备用线路"); check(SubscriptionLibrary.Read(profile).Single(e => e.Id == second.Id).Name == "备用线路", "subscription cards can be renamed without changing the source URL");
        SubscriptionLibrary.Configure(profile, first, SubscriptionClientProfile.Clash, SubscriptionDownloadRoute.Direct); SubscriptionLibrary.CaptureActive(profile);
        check(SubscriptionLibrary.Read(profile).Single(e => e.Id == first).Client == SubscriptionClientProfile.Clash && profile.SubscriptionRoute == SubscriptionDownloadRoute.Direct, "per-card download options update the active metadata without changing routing mode");
        var cycle = new PolicyGroupSettings { Name = "循环策略", Members = ["循环策略"] }; rejected = false;
        try { UserProxyGroups.Save(profile, cycle, true); } catch (InvalidOperationException) { rejected = true; }
        check(rejected && profile.GroupSettings.Count == 1, "cyclic policy membership is rejected without changing saved settings");
        var broken = new PolicyGroupSettings { Name = "无效成员", Members = ["不存在的节点"] }; rejected = false;
        try { UserProxyGroups.Save(profile, broken, true); } catch (InvalidOperationException) { rejected = true; }
        check(rejected, "policy editing rejects removed or nonexistent node names before persistence");
        var edited = new PolicyGroupSettings { Name = "Proxy", Type = "fallback", Members = ["SG", "HK"], Interval = 60, Timeout = 2500 };
        UserProxyGroups.Save(profile, edited, false); var definitions = UserProxyGroups.Read(profile);
        check(definitions["Proxy"].Type == "fallback" && definitions["Proxy"].Members.SequenceEqual(["SG", "HK"]), "editing an imported group changes the real type and preserves fallback ordering");
        UserProxyGroups.RemoveEdit(profile, "Proxy"); check(UserProxyGroups.Read(profile)["Proxy"].Type == "select", "removing an imported group override restores the original subscription definition");
        var selection = new PolicyGroupSettings { Name = "嵌套", Members = [custom.Name, "DIRECT"] }; UserProxyGroups.Save(profile, selection, true);
        check(UserProxyGroups.Read(profile)["嵌套"].Members.Contains(custom.Name), "custom groups can contain other policy groups and explicit direct routing");
        var loop = new PolicyGroupSettings { Name = custom.Name, Members = ["嵌套"] }; rejected = false;
        try { UserProxyGroups.Save(profile, loop, false); } catch (InvalidOperationException) { rejected = true; }
        check(rejected, "mutual policy nesting cannot create a routing loop");
        var importedFilter = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(NodeSelectionChecks.Fixture.Replace("proxies: [DIRECT, Auto, HK, SG]", "proxies: [DIRECT, Auto], include-all-proxies: true, filter: '^SG$'")) };
        check(ProxyCatalog.FromProfile(importedFilter).Groups["Proxy"].Members.SequenceEqual(["DIRECT", "Auto", "SG"]), "node name filters leave explicit direct and nested strategy members intact");
        string directory = Path.Combine(Path.GetTempPath(), "Swirl-workspace-check-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory);
        string file = Path.Combine(directory, "library.swirl"); ConfigurationSync.Export(profile, file, "subscription-library-test-password"); var restored = ConfigurationSync.Import(file, "subscription-library-test-password");
        check(SubscriptionLibrary.Read(restored).Count == 2 && restored.GroupSettings.Count == 2 && restored.SelectedProxies["Proxy"] == "SG", "portable sync restores the whole subscription library, active choices and custom groups");
        check(!File.ReadAllText(file).Contains("fixture-secret-token"), "portable subscription library contains only authenticated encrypted data");
        SubscriptionLibrary.Remove(restored, first); check(restored.ActiveSubscriptionId == second.Id && restored.SelectedProxies["Proxy"] == "HK", "removing the active card switches to a remaining saved configuration");
        SubscriptionLibrary.Remove(restored, second.Id); check(restored.ProtectedYaml.Length == 0 && SubscriptionLibrary.Read(restored).Count == 0, "removing the last card leaves an honest empty configuration");
    }
    internal static async Task IntegrationAsync(Action<bool, string> check)
    {
        using (var handler = new MetadataHandler())
        {
            var downloaded = await SubscriptionImport.DownloadAsync("https://metadata.example.test/sub?token=fixture", SubscriptionClientProfile.Mihomo, handler);
            check(downloaded.Usage?.Used == 30 && downloaded.Usage.Total == 100, "subscription download retains provider response headers for real usage cards");
        }
        var original = ProxyProfile.TestDirectory; ProxyProfile.TestDirectory = Path.Combine(Path.GetTempPath(), "Swirl-policy-core-" + Guid.NewGuid().ToString("N"));
        using var fast = new FixtureProxy(20); using var slow = new FixtureProxy(180);
        try
        {
            var profile = new ProxyProfile { Mode = "global", ProtectedYaml = ProxyProfile.Protect($"proxies:\n  - {{name: Slow, type: http, server: 127.0.0.1, port: {slow.Port}}}\n  - {{name: Fast, type: http, server: 127.0.0.1, port: {fast.Port}}}\n") };
            foreach (string type in new[] { "select", "url-test", "fallback", "load-balance" }) UserProxyGroups.Save(profile, new PolicyGroupSettings { Name = type, Type = type, Members = ["Slow", "Fast"], Url = "http://127.0.0.1:18800/check", Interval = 86400, Timeout = 2500, Strategy = "round-robin", Tolerance = 10 }, true);
            using var controller = new ProxyController(_ => { }); await controller.StartAsync(profile, false); var live = await controller.CatalogAsync();
            check(live.Groups["select"].Selectable && live.Groups["url-test"].Type == "URLTest" && live.Groups["fallback"].Type == "Fallback" && live.Groups["load-balance"].Type == "LoadBalance", "real Mihomo runs all four user-created policy types");
            var delays = await controller.TestGroupAsync("url-test", "http://127.0.0.1:18800/check", 2500); live = await controller.CatalogAsync();
            check(delays["Fast"] > 0 && delays["Fast"] < delays["Slow"] && live.Groups["url-test"].Current == "Fast", "real group health check returns measured delays and selects the fastest node");
            await controller.TestGroupAsync("fallback", "http://127.0.0.1:18800/check", 2500);
            check((await controller.CatalogAsync()).Groups["fallback"].Current == "Slow", "real fallback uses the first available node even when another node is faster");
            slow.Available = false; await controller.TestGroupAsync("fallback", "http://127.0.0.1:18800/check", 2500);
            check((await controller.CatalogAsync()).Groups["fallback"].Current == "Fast", "real fallback switches to the backup when the preferred proxy stops responding");
            slow.Available = true;
            await controller.TestGroupAsync("load-balance", "http://127.0.0.1:18800/check", 2500); await controller.SelectAsync("GLOBAL", "load-balance"); int beforeFast = fast.Requests, beforeSlow = slow.Requests;
            using var client = new HttpClient(new HttpClientHandler { UseProxy = true, Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.MixedPort) });
            for (int i = 0; i < 6; i++) { using var result = await client.GetAsync("http://127.0.0.1:18800/check?id=" + i); result.EnsureSuccessStatusCode(); }
            check(fast.Requests > beforeFast && slow.Requests > beforeSlow, "round-robin load balance forwards real connections through both member proxies");
        }
        finally { ProxyProfile.TestDirectory = original; }
    }
    private sealed class FixtureProxy : IDisposable
    {
        private readonly TcpListener listener = new(IPAddress.Loopback, 0);
        private readonly CancellationTokenSource lifetime = new();
        private readonly int delay;
        private int requests;
        internal bool Available { get; set; } = true;
        internal int Requests => Volatile.Read(ref requests);
        internal int Port => ((IPEndPoint)listener.LocalEndpoint).Port;
        internal FixtureProxy(int milliseconds) { delay = milliseconds; listener.Start(); _ = AcceptAsync(); }
        private async Task AcceptAsync()
        {
            try { while (!lifetime.IsCancellationRequested) { var client = await listener.AcceptTcpClientAsync(lifetime.Token); _ = ReplyAsync(client); } } catch (OperationCanceledException) { } catch (SocketException) { }
        }
        private async Task ReplyAsync(TcpClient client)
        {
            using (client)
            try
            {
                if (!Available) return;
                using var stream = client.GetStream(); byte[] bytes = new byte[8192]; int length = 0;
                while (length < bytes.Length) { int read = await stream.ReadAsync(bytes.AsMemory(length), lifetime.Token); if (read == 0) return; length += read; if (Encoding.ASCII.GetString(bytes, 0, length).Contains("\r\n\r\n")) break; }
                if (Encoding.ASCII.GetString(bytes, 0, length).StartsWith("CONNECT "))
                {
                    await stream.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 200 Connection Established\r\n\r\n"), lifetime.Token); length = 0;
                    while (length < bytes.Length) { int read = await stream.ReadAsync(bytes.AsMemory(length), lifetime.Token); if (read == 0) return; length += read; if (Encoding.ASCII.GetString(bytes, 0, length).Contains("\r\n\r\n")) break; }
                }
                await Task.Delay(delay, lifetime.Token); Interlocked.Increment(ref requests);
                await stream.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"), lifetime.Token);
            }
            catch (Exception) when (lifetime.IsCancellationRequested) { }
            catch (IOException) { }
        }
        public void Dispose() { lifetime.Cancel(); listener.Stop(); }
    }
    private sealed class MetadataHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(NodeSelectionChecks.Fixture) };
            response.Headers.TryAddWithoutValidation("subscription-userinfo", "upload=10; download=20; total=100; expire=1790000000"); return Task.FromResult(response);
        }
    }
}
