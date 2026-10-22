using AdShield.Network;
using System.Diagnostics;
using System.Text;
using YamlDotNet.Serialization;

internal static class CoreStartupChecks
{
    internal static void Pure(Action<bool, string> check)
    {
        const string secret = "fixture-private-token-DO-NOT-DISPLAY";
        foreach (var input in new[] {
            "Parse config error: can't download MMDB: https://example.test/?token=" + secret,
            "Parse config error: proxy 7: unsupported cipher " + secret,
            "Parse config error: rules[42] [DOMAIN,x," + secret + "] error: proxy not found",
            "Parse config error: yaml: unmarshal errors: value " + secret,
            "Parse config error: path is not subpath of home directory or SAFE_PATHS: " + secret,
            "unknown fatal failure " + secret })
        {
            string explanation = CoreDiagnostics.Describe(input, 1);
            check(!explanation.Contains(secret) && !explanation.Contains("https://") && explanation.Contains("退出码 1"), "core error explains failure without echoing private configuration");
        }
        check(CoreDiagnostics.Describe("Parse config error: can't download MMDB", 1).Contains("分流数据库"), "missing GEO database has actionable explanation");
        check(CoreDiagnostics.Describe("Parse config error: rules[42] error: proxy not found", 1).Contains("索引 42"), "rule errors expose numeric location only");
        check(CoreAssets.Assets.Length == 4 && CoreAssets.Assets.All(a => a.Sha256.Length == 64), "bundled GEO manifest pins all four core database formats");
    }

    internal static async Task RunAsync(Action<bool, string> check)
    {
        string source = Path.Combine(AppContext.BaseDirectory, "core", "geodata");
        string directory = Path.Combine(Path.GetTempPath(), "Swirl-core-startup-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string fixture = "proxies:\n  - {name: fixture, type: http, server: 192.0.2.1, port: 8080}\nproxy-groups:\n  - {name: Select, type: select, proxies: [fixture, DIRECT]}\nrules:\n  - GEOSITE,cn,DIRECT\n  - GEOIP,CN,DIRECT,no-resolve\n  - IP-ASN,13335,DIRECT,no-resolve\n  - MATCH,Select\n";
        var profile = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(fixture) };
        check(CoreAssets.Prepare(profile, directory, source) == 4, "first connection seeds verified bundled databases without downloading");
        var times = CoreAssets.Assets.ToDictionary(a => a.File, a => File.GetLastWriteTimeUtc(Path.Combine(directory, a.File)));
        check(CoreAssets.Prepare(profile, directory, source) == 0 && times.All(p => File.GetLastWriteTimeUtc(Path.Combine(directory, p.Key)) == p.Value), "existing GEO caches are preserved on reconnect");
        foreach (bool geodata in new[] { false, true })
        {
            // Make every download destination fail. Success must come from the
            // packaged database, even on the first run and with GEOIP dat mode.
            var root = MihomoConfig.Parse(MihomoConfig.Build(profile, "fixture-secret"));
            root["geodata-mode"] = geodata;
            root["geox-url"] = CoreAssets.Assets.ToDictionary(a => a.Key, _ => "http://127.0.0.1:9/unavailable");
            string filename = Path.Combine(directory, "config.yaml");
            File.WriteAllText(filename, new SerializerBuilder().Build().Serialize(root), new UTF8Encoding(false));
            using var controller = new ProxyController(_ => { });
            await controller.TestConfigAsync(directory, filename);
            check(true, "real core validates GEOIP/GEOSITE/IP-ASN offline in " + (geodata ? "dat" : "metadb") + " mode");
        }
        string customized = fixture + "geox-url:\n  mmdb: https://example.test/custom-db\n  geoip: https://example.test/custom-dat\n  geosite: https://example.test/custom-site\n  asn: https://example.test/custom-asn\n";
        var custom = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(customized) };
        string customDirectory = Path.Combine(directory, "custom");
        check(CoreAssets.Prepare(custom, customDirectory, source) == 0 && !Directory.EnumerateFiles(customDirectory).Any(), "explicit custom GEO sources are not replaced by default data");
        string aliases = Path.Combine(directory, "aliases"); Directory.CreateDirectory(aliases); File.WriteAllText(Path.Combine(aliases, "Country.mmdb"), "user data");
        CoreAssets.Prepare(profile, aliases, source);
        check(!File.Exists(Path.Combine(aliases, "geoip.metadb")) && File.ReadAllText(Path.Combine(aliases, "Country.mmdb")) == "user data", "legacy MMDB user database is preserved instead of shadowed");
        string badSource = Path.Combine(directory, "bad-source"); Directory.CreateDirectory(badSource); File.WriteAllText(Path.Combine(badSource, "geoip.metadb"), "corrupt");
        bool rejected = false;
        try { CoreAssets.Prepare(profile, Path.Combine(directory, "invalid"), badSource); } catch (InvalidOperationException e) { rejected = e.Message.Contains("校验失败"); }
        check(rejected, "corrupt packaged database is rejected before core startup");
        string invalidYaml = "proxies:\n  - {name: fixture-private-node, type: http, server: 192.0.2.1, port: 8080}\nrules: [MATCH,missing-private-group]\n";
        string invalidFile = Path.Combine(directory, "invalid.yaml"); File.WriteAllText(invalidFile, invalidYaml);
        bool explained = false;
        using (var controller = new ProxyController(_ => { }))
            try { await controller.TestConfigAsync(directory, invalidFile); }
            catch (InvalidOperationException e) { explained = e.Message.Contains("检查失败") && !e.Message.Contains("private"); }
        check(explained, "actual rejected core config returns a safe actionable failure");
    }
}
