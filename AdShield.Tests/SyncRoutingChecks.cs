using AdShield.Network;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;

internal static class SyncRoutingChecks
{
    internal static void Run(Action<bool, string> check)
    {
        static bool Rejects(Action action)
        {
            try { action(); return false; }
            catch (Exception ex) when (ex is InvalidOperationException or ArgumentException) { return true; }
        }
        var unicode = new UserRoutingRule { Kind = "DOMAIN", Value = "例子.测试", Policy = "direct" }; unicode.Validate();
        check(unicode.Value.StartsWith("xn--") && unicode.Policy == "DIRECT", "routing normalizes Unicode domains and built-in policy names");
        check(Rejects(() => new UserRoutingRule { Kind = "DOMAIN", Value = "https://example.com/path" }.Validate()), "routing rejects protocol and path in domain rules");
        check(Rejects(() => new UserRoutingRule { Kind = "IP-CIDR", Value = "192.168.1.0/99" }.Validate()), "routing rejects malformed IP network prefix");
        check(Rejects(() => new UserRoutingRule { Kind = "IP-CIDR6", Value = "192.168.1.0/24" }.Validate()), "IPv6 rule rejects IPv4 address");
        check(Rejects(() => new UserRoutingRule { Kind = "URL-REGEX", Value = "[" }.Validate()), "routing validates URL regular expressions before startup");
        check(Rejects(() => new UserRoutingRule { Kind = "URL-REGEX", Value = ".*", HttpsHosts = "*" }.Validate()), "user URL routing cannot request global HTTPS interception");
        var profile = new ProxyProfile
        {
            ProtectedYaml = ProxyProfile.Protect("""
                proxies:
                  - name: Fixture node
                    type: http
                    server: 127.0.0.1
                    port: 19201
                proxy-groups:
                  - name: Fixture group
                    type: select
                    proxies: [Fixture node, DIRECT]
                rules: ["MATCH,Fixture group"]
                """),
            UserRules = new()
            {
                new() { Kind = "DOMAIN-SUFFIX", Value = "ads.example", Policy = "REJECT", Ssid = "Office" },
                new() { Kind = "IP-CIDR", Value = "192.168.1.0/24", Policy = "DIRECT" },
                new() { Kind = "URL-REGEX", Value = "^https?://api\\.example/ad", Policy = "REJECT", HttpsHosts = "api.example" },
                new() { Kind = "URL-REGEX", Value = "^https?://api\\.example/", Policy = "Fixture group", HttpsHosts = "api.example" },
                new() { Kind = "SSID", Value = "Home", Policy = "DIRECT" }
            }
        };
        UserRouting.Prepare(profile, "Office");
        string yaml = MihomoConfig.Build(profile, "fixture-controller-secret");
        check(yaml.Contains("DOMAIN-SUFFIX,ads.example,REJECT") && yaml.Contains("IP-CIDR,192.168.1.0/24,DIRECT,no-resolve"), "active Wi-Fi conditional domain and IP rules enter core config");
        check(UserRouting.Policies(profile).Contains("Fixture group") && UserRouting.Policies(profile).Contains("Fixture node"), "routing exposes existing named groups and nodes as policies");
        check(UserRouting.ResolveUrlRoute(profile, "https://api.example/ad") is { Reject: true }, "first matching URL reject rule takes precedence");
        var route = UserRouting.ResolveUrlRoute(profile, "https://api.example/data");
        check(route is { Reject: false, Port: 18000, Policy: "Fixture group" } && yaml.Contains("proxy: Fixture group"), "URL named-group policy has a matching loopback core listener");
        check(UserRouting.ResolveUrlRoute(profile, "https://other.example/data") == null, "unmatched URL falls back to ordinary core rules");
        check(UserRouting.EffectivePlugins(profile).Any(p => p.Enabled && p.MatchesHost("api.example")), "URL HTTPS scopes share plugin interception and certificate scope");
        UserRouting.Prepare(profile, "Home");
        yaml = MihomoConfig.Build(profile, "fixture-controller-secret");
        check(!yaml.Contains("DOMAIN-SUFFIX,ads.example,REJECT") && yaml.Contains("MATCH,DIRECT"), "SSID change activates only matching conditional rules at startup");
        profile.Mode = "global"; UserRouting.Prepare(profile, "Office");
        check(UserRouting.ResolveUrlRoute(profile, "https://api.example/ad") == null && !UserRouting.ListenerPorts(profile).Any(), "global mode does not apply rule-mode URL policy overrides");
        profile.Mode = "rule";
        profile.UserRules.Add(new() { Kind = "URL-REGEX", Value = "^http://bad.example/", Policy = "Missing group" });
        UserRouting.Prepare(profile, "Office");
        check(Rejects(() => MihomoConfig.Build(profile, "fixture-controller-secret")), "missing URL strategy prevents startup instead of silently falling back");
        profile.UserRules.RemoveAt(profile.UserRules.Count - 1);
        profile.Plugins.Add(new LoonPlugin { Enabled = true, Rules = new() { "DOMAIN,old.example,PROXY" }, ProxyPolicy = "AdShield 节点" });
        UserRouting.Prepare(profile, "Office");
        check(MihomoConfig.Build(profile, "fixture-controller-secret").Contains("DOMAIN,old.example,Swirl 节点"), "old generated AdShield default policy migrates to Swirl default group");
        var summary = ProxyProtocols.Configured(profile);
        check(summary.Any(p => p.Name == "HTTP" && p.NodeCount == 1), "protocol summary counts configured nodes without printing credentials");

        string temporary = Path.Combine(Path.GetTempPath(), "Swirl-sync-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temporary);
        try
        {
            const string password = "correct test password 123";
            const string secret = "private-node-fixture-secret";
            var plugin = LoonPlugin.Parse("#!name=Sync fixture\n[Argument]\nfeature = switch, false, true\n[Rule]\nDOMAIN,ads.example,REJECT", "https://example.test/fixture.plugin");
            plugin.ProtectedParameterValues = ProxyProfile.Protect("{\"feature\":true}"); plugin.Enabled = true;
            var source = new ProxyProfile
            {
                ProtectedYaml = ProxyProfile.Protect("proxies: [{name: Fixture, type: http, server: localhost, port: 8080, password: " + secret + "}]\nrules: ['MATCH,DIRECT']"),
                ProtectedSubscription = ProxyProfile.Protect("https://example.test/subscription?token=" + secret),
                Tun = true, Mitm = true, Plugins = new() { plugin }, UserRules = new() { new() { Kind = "DOMAIN", Value = "example.test" } }
            };
            string export = Path.Combine(temporary, "portable.swirl");
            ConfigurationSync.Export(source, export, password);
            string encrypted = File.ReadAllText(export);
            check(!encrypted.Contains(secret) && !encrypted.Contains("Sync fixture") && !encrypted.Contains(source.ProtectedYaml), "portable export encrypts nodes, subscription and plugin settings together");
            var imported = ConfigurationSync.Import(export, password);
            check(imported.Yaml == source.Yaml && imported.Subscription == source.Subscription, "portable encrypted config restores locally DPAPI-protected nodes and subscription");
            check(!imported.Tun && !imported.Mitm && imported.Plugins.All(p => !p.Enabled), "portable import keeps network interception and scripts disabled for review");
            check(imported.Plugins[0].EffectiveParameters()["feature"] is true && imported.UserRules.Count == 1, "portable export restores protected plugin parameters and custom routing rules");
            check(Rejects(() => ConfigurationSync.Import(export, "wrong test password 123")), "wrong portable password rejects import without modifying active profile");
            var envelope = JsonSerializer.Deserialize<SyncEnvelope>(encrypted)!;
            envelope.WrittenUtc = DateTimeOffset.UtcNow.AddHours(1).ToString("O");
            string modified = Path.Combine(temporary, "tampered.swirl"); File.WriteAllText(modified, JsonSerializer.Serialize(envelope));
            check(Rejects(() => ConfigurationSync.Import(modified, password)), "encrypted config authenticates timestamp and revision metadata");
            check(Rejects(() => ConfigurationSync.Export(source, Path.Combine(temporary, "short.swirl"), "short")), "portable export rejects weak short passwords before file creation");
            string folder = Path.Combine(temporary, "provider-folder");
            var upload = ConfigurationSync.Upload(source, folder, password);
            check(upload.HasRemote && !ConfigurationSync.GetStatus(source, folder).LocalChanged && !ConfigurationSync.GetStatus(source, folder).Conflict, "manual folder upload records matching revision and content fingerprint");
            source.UserRules.Add(new() { Kind = "DOMAIN", Value = "changed.example", Policy = "REJECT" });
            check(ConfigurationSync.GetStatus(source, folder).LocalChanged, "folder synchronization detects local edits without uploading automatically");
            ConfigurationSync.Upload(source, folder, password);
            check(Directory.GetFiles(Path.Combine(folder, "Swirl-config-history"), "*.swirl").Length == 1, "replacing accepted remote config keeps previous encrypted revision");
            var secondMachine = new ProxyProfile { ProtectedYaml = source.ProtectedYaml };
            string remote = Path.Combine(folder, ConfigurationSync.SyncFileName);
            string before = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(remote)));
            check(Rejects(() => ConfigurationSync.Upload(secondMachine, folder, password)), "unseen remote revision blocks automatic overwrite");
            check(before == Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(remote))), "sync conflict leaves remote encrypted file unchanged");
            var downloaded = ConfigurationSync.Download(folder, password);
            check(downloaded.UserRules.Count == source.UserRules.Count && !ConfigurationSync.GetStatus(downloaded, folder).Conflict, "folder download is reviewable and tracks exact accepted remote revision");
            ConfigurationSync.Upload(secondMachine, folder, password, true);
            check(Directory.GetFiles(Path.Combine(folder, "Swirl-config-history"), "*.swirl").Length == 2, "explicit remote replacement preserves conflict backup");
            string conflictCopy = Path.Combine(folder, "Swirl-config-other-device.swirl"); File.Copy(remote, conflictCopy);
            check(ConfigurationSync.GetStatus(secondMachine, folder) is { Conflict: true, ConflictCopies: 1 }, "manual sync status reports cloud conflict copies without deleting them");
            check(Rejects(() => ConfigurationSync.Upload(secondMachine, folder, password)) && File.Exists(conflictCopy), "cloud conflict copies stop ordinary uploads and remain preserved");
            ConfigurationSync.Apply(source, downloaded);
            check(!source.Tun && !source.Mitm && source.Plugins.All(p => !p.Enabled), "applying reviewed portable configuration cannot auto-start interception or scripts");
            check(!Directory.EnumerateFiles(temporary, "*.tmp", SearchOption.AllDirectories).Any(), "atomic export and folder synchronization leave no temporary configuration files");
        }
        finally { Directory.Delete(temporary, true); }
    }
}
