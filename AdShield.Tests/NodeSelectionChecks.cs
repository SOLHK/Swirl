using AdShield.Network;
using System.Text.Json;
using System.IO;

internal static class NodeSelectionChecks
{
    internal const string Fixture = """
        proxies:
          - {name: HK, type: http, server: 192.0.2.1, port: 8080}
          - {name: SG, type: http, server: 192.0.2.2, port: 8080}
        proxy-groups:
          - {name: Proxy, type: select, proxies: [DIRECT, Auto, HK, SG]}
          - {name: Auto, type: url-test, proxies: [HK, SG], url: 'http://127.0.0.1:9/check', interval: 86400}
        rules: ['MATCH,Proxy']
        """;

    internal static void Pure(Action<bool, string> check)
    {
        var profile = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(Fixture) };
        var catalog = ProxyCatalog.FromProfile(profile);
        check(profile.Mode == "rule" && catalog.Nodes.Count == 2 && catalog.Groups.ContainsKey("Auto"), "imported nodes and automatic groups are available before connecting; first run defaults to rule mode");
        var initial = catalog.InitialSelections(profile);
        check(initial["Proxy"] == "Auto" && initial["GLOBAL"] == "Proxy", "fresh selectors and GLOBAL choose a real upstream instead of DIRECT");
        profile.SelectedProxies = new() { ["Proxy"] = "DIRECT", ["Swirl 节点"] = "SG" };
        check(catalog.InitialSelections(profile)["Proxy"] == "DIRECT" && catalog.InitialSelections(profile)["Swirl 节点"] == "SG", "explicit DIRECT and node choices survive reconnection");
        check(!JsonSerializer.Serialize(profile).Contains("\"SG\"") && profile.SelectedProxies["Swirl 节点"] == "SG", "saved node choices stay user-scoped encrypted on disk");
        profile.SelectedProxies = new() { ["Proxy"] = "Removed node" };
        check(catalog.InitialSelections(profile)["Proxy"] == "Auto", "removed subscription nodes cannot leave an invalid saved selection");
        check(catalog.Resolve("Proxy", new Dictionary<string, string> { ["Proxy"] = "Auto", ["Auto"] = "SG" }) == "SG", "overview resolves nested group choices to the actual node");
        check(catalog.Resolve("Proxy", new Dictionary<string, string> { ["Proxy"] = "Proxy" }) == "策略组循环", "route resolution handles cyclic strategies without hanging the UI");
        var cyclic = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(Fixture.Replace("proxies: [DIRECT, Auto, HK, SG]", "proxies: [Other, HK]").Replace("- {name: Auto,", "- {name: Other, type: select, proxies: [Proxy, SG]}\n  - {name: Auto,")) };
        var cycleCatalog = ProxyCatalog.FromProfile(cyclic);
        check(cycleCatalog.Resolve("Proxy", cycleCatalog.InitialSelections(cyclic)) == "SG", "default selection avoids loops between mutually referenced selectors");
        var inline = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect("""
            proxy-providers:
              Provider:
                type: inline
                payload: [{name: ProviderNode, type: http, server: 192.0.2.1, port: 8080}]
            proxy-groups:
              - {name: ProviderGroup, type: select, use: [Provider]}
            rules: ['MATCH,ProviderGroup']
            """) };
        var providerCatalog = ProxyCatalog.FromProfile(inline);
        check(providerCatalog.Nodes.ContainsKey("ProviderNode") && providerCatalog.Groups["Swirl 节点"].Members.SequenceEqual(["ProviderNode"]), "provider-only default group has real nodes and no injected DIRECT placeholder");
        var remote = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect("proxy-providers:\n  Remote: {type: http, url: 'https://example.test/nodes', path: ./nodes.yaml, interval: 3600}\n") };
        var remoteCatalog = ProxyCatalog.FromProfile(remote);
        check(remoteCatalog.Groups["Swirl 节点"].PendingProvider && remoteCatalog.Groups["Swirl 节点"].Members.Length == 0, "offline remote provider shows an explicit loading state rather than an empty DIRECT selection");
        using var json = JsonDocument.Parse("""
            {"proxies": {
              "DIRECT": {"type": "Direct"},
              "HK": {"type": "Http"},
              "Swirl Internal Plugin": {"type": "Http"},
              "Select": {"type": "Selector", "all": ["HK", "Swirl Internal Plugin"], "now": "HK"},
              "Auto": {"type": "URLTest", "all": ["HK"], "now": "HK"},
              "Backup": {"type": "Fallback", "all": ["HK"], "now": "HK"},
              "Balance": {"type": "LoadBalance", "all": ["HK"]}
            }}
            """);
        var live = ProxyCatalog.FromController(json.RootElement);
        check(live.Groups.Count == 4 && live.Groups.Values.Count(g => g.Selectable) == 1 && live.Nodes.Keys.SequenceEqual(["HK"]), "runtime catalog separates servers from selectors, auto, fallback and load-balance groups");
        check(!live.Groups["Select"].Members.Contains(MihomoConfig.PluginOutbound), "internal plugin outbound can never be selected as a proxy server");
        var filtered = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(Fixture.Replace("proxies: [DIRECT, Auto, HK, SG]", "include-all-proxies: true, filter: '^SG$'")) };
        check(ProxyCatalog.FromProfile(filtered).Groups["Proxy"].Members.SequenceEqual(["SG"]), "offline include-all-proxies respects the imported group filter");
        string directory = Path.Combine(Path.GetTempPath(), "Swirl-selection-sync-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(directory);
        profile.SelectedProxies = new() { ["Proxy"] = "SG" };
        string export = Path.Combine(directory, "selection.swirl"); ConfigurationSync.Export(profile, export, "selection-test-password");
        check(ConfigurationSync.Import(export, "selection-test-password").SelectedProxies["Proxy"] == "SG", "portable sync re-protects node choices for the receiving user");
    }

    internal static async Task IntegrationAsync(Action<bool, string> check)
    {
        string? original = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.Combine(Path.GetTempPath(), "Swirl-selection-core-" + Guid.NewGuid().ToString("N"));
        try
        {
            var profile = new ProxyProfile { Mode = "global", ProtectedYaml = ProxyProfile.Protect(Fixture), SelectedProxies = new() { ["Proxy"] = "SG" } };
            using var controller = new ProxyController(_ => { });
            await controller.StartAsync(profile, false);
            var live = await controller.CatalogAsync();
            check(live.Groups["Proxy"].Current == "SG" && live.Resolve("GLOBAL", live.Groups.Values.Where(g => g.Current != null).ToDictionary(g => g.Name, g => g.Current!)) != "直连", "real Mihomo restores the saved node and starts global mode on a proxy route before capture");
            await controller.SelectAsync("Proxy", "HK");
            check((await controller.CatalogAsync()).Groups["Proxy"].Current == "HK", "real controller applies node changes to the selected strategy");
            controller.Stop();
            profile.SelectedProxies = new() { ["Proxy"] = "DIRECT" };
            await controller.StartAsync(profile, false);
            check((await controller.CatalogAsync()).Groups["Proxy"].Current == "DIRECT", "real core preserves a deliberately saved DIRECT policy after restart");
            controller.Stop();
            profile.ProtectedYaml = ProxyProfile.Protect("proxy-providers:\n  Inline: {type: inline, payload: [{name: InlineNode, type: http, server: 192.0.2.1, port: 8080}]}\n"); profile.SelectedProxies = new();
            await controller.StartAsync(profile, false);
            check((await controller.CatalogAsync()).Groups["Swirl 节点"].Current == "InlineNode", "real provider-only core selects its provider node without a DIRECT placeholder");
        }
        finally { ProxyProfile.TestDirectory = original; }
    }
}
