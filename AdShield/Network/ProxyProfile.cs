using System.Security.Cryptography;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using YamlDotNet.Serialization;

namespace AdShield.Network;

internal sealed class ProxyProfile
{
    public string ProtectedYaml { get; set; } = "";
    public string ProtectedSubscription { get; set; } = "";
    public string Mode { get; set; } = "rule";
    public bool Tun { get; set; }
    public bool Mitm { get; set; }
    public bool BasicAds { get; set; }
    public List<LoonPlugin> Plugins { get; set; } = new();
    public List<UserRoutingRule> UserRules { get; set; } = new();
    public string SyncFolder { get; set; } = "";
    public string SyncRemoteRevision { get; set; } = "";
    public string SyncRemoteHash { get; set; } = "";
    public string SyncContentHash { get; set; } = "";
    internal UserRoutingSnapshot? RoutingSnapshot { get; set; }

    internal static string Protect(string text) => string.IsNullOrEmpty(text) ? "" : Convert.ToBase64String(
        ProtectedData.Protect(Encoding.UTF8.GetBytes(text), null, DataProtectionScope.CurrentUser));
    internal static string Unprotect(string text) => string.IsNullOrEmpty(text) ? "" : Encoding.UTF8.GetString(
        ProtectedData.Unprotect(Convert.FromBase64String(text), null, DataProtectionScope.CurrentUser));
    internal string Yaml => Unprotect(ProtectedYaml);
    internal string Subscription => Unprotect(ProtectedSubscription);

    internal static string? TestDirectory { get; set; }
    internal static string DirectoryPath => TestDirectory ?? Path.Combine(Store.Dir, "network");
    internal static ProxyProfile Load()
    {
        try
        {
            var profile = JsonSerializer.Deserialize<ProxyProfile>(File.ReadAllText(Path.Combine(DirectoryPath, "profile.json"))) ?? new();
            profile.ReparsePlugins();
            profile.UserRules ??= new();
            profile.BasicAds = false;
            return profile;
        }
        catch { return new(); }
    }
    internal void ReparsePlugins()
    {
        Plugins ??= new();
        Plugins = Plugins.Select(old =>
            {
                if (old.Original.Length == 0) return old;
                try
                {
                    var parsed = LoonPlugin.Parse(old.Original, old.Source);
                    parsed.Id = old.Id; parsed.Argument = old.Argument; parsed.ProtectedParameterValues = old.ProtectedParameterValues; parsed.ProxyPolicy = old.ProxyPolicy;
                    parsed.Enabled = old.Enabled && parsed.Unsupported.Count == 0;
                    foreach (var script in parsed.Scripts) script.Code = old.Scripts.FirstOrDefault(s => s.Url == script.Url)?.Code ?? "";
                    foreach (var rewrite in parsed.Rewrites)
                    {
                        var cached = old.Rewrites.FirstOrDefault(r => r.Syntax == rewrite.Syntax || r.Pattern == rewrite.Pattern && r.Action == rewrite.Action);
                        if (cached == null) continue;
                        rewrite.Resources = cached.Resources;
                        if (rewrite.ResourceUrl.Length > 0) rewrite.Target = cached.Target;
                    }
                    foreach (var remote in parsed.RemoteRules) remote.Rules = old.RemoteRules.FirstOrDefault(r => r.Url == remote.Url)?.Rules ?? new();
                    return parsed;
                }
                catch { old.Enabled = false; old.Unsupported.Add("原文重新解析失败，请重新导入。"); return old; }
        }).ToList();
    }
    internal void Save()
    {
        Directory.CreateDirectory(DirectoryPath);
        var file = Path.Combine(DirectoryPath, "profile.json");
        ConfigurationSync.WriteAtomic(file, Encoding.UTF8.GetBytes(JsonSerializer.Serialize(this)));
    }
}

internal static class MihomoConfig
{
    internal const int MixedPort = 17890, PluginPort = 17891, ControllerPort = 17909;
    internal static Dictionary<string, object> Parse(string yaml)
    {
        if (Encoding.UTF8.GetByteCount(yaml) > 4 * 1024 * 1024) throw new InvalidOperationException("配置超过 4 MB。");
        var root = new DeserializerBuilder().WithDuplicateKeyChecking().WithAttemptingUnquotedStringTypeDeserialization().Build()
            .Deserialize<Dictionary<string, object>>(yaml) ?? new();
        if (root.Count == 0) throw new InvalidOperationException("配置为空。请使用 Clash/Mihomo YAML 配置。");
        return root;
    }

    internal static string Build(ProxyProfile profile, string secret)
    {
        UserRouting.Snapshot(profile);
        var effectivePlugins = UserRouting.EffectivePlugins(profile).ToArray();
        var root = string.IsNullOrWhiteSpace(profile.Yaml) ? new Dictionary<string, object>() : Parse(profile.Yaml);
        root["mixed-port"] = MixedPort;
        foreach (var key in new[] { "port", "socks-port", "redir-port", "tproxy-port", "external-controller-tls", "external-controller-unix", "external-controller-pipe", "external-ui", "external-ui-url", "listeners" }) root.Remove(key);
        root["allow-lan"] = false;
        root["bind-address"] = "127.0.0.1";
        root["external-controller"] = "127.0.0.1:" + ControllerPort;
        root["secret"] = secret;
        // TUN ingress must run capture rules even in global/direct mode. Only the
        // final routing policy changes; plugin upstream enters DEFAULT-HTTP.
        root["mode"] = profile.Tun ? "rule" : profile.Mode is "global" or "direct" ? profile.Mode : "rule";
        root["log-level"] = "warning";
        root["ipv6"] = false;
        var hostMappings = root.TryGetValue("hosts", out var hostValue) && hostValue is IDictionary<object, object> hostEntries
            ? hostEntries.ToDictionary(e => e.Key.ToString()!, e => e.Value) : new Dictionary<string, object>();
        foreach (var plugin in effectivePlugins.Where(p => p.Enabled && p.Unsupported.Count == 0))
            foreach (var host in plugin.DnsHosts) hostMappings[host.Key] = host.Value;
        if (hostMappings.Count > 0) root["hosts"] = hostMappings;
        root["tun"] = new Dictionary<string, object>
        {
            ["enable"] = profile.Tun, ["stack"] = "mixed", ["auto-route"] = true,
            ["auto-detect-interface"] = true, ["dns-hijack"] = new[] { "any:53" }
        };
        if (profile.Tun)
        {
            var dns = root.TryGetValue("dns", out var dnsValue) && dnsValue is IDictionary<object, object> dnsEntries
                ? dnsEntries.ToDictionary(e => e.Key.ToString()!, e => e.Value) : new Dictionary<string, object>();
            dns["enable"] = true;
            if (!dns.ContainsKey("enhanced-mode")) dns["enhanced-mode"] = "fake-ip";
            if (!dns.TryGetValue("nameserver", out var nameservers) || nameservers is not IEnumerable<object> servers || !servers.Any())
                dns["nameserver"] = new[] { "https://dns.alidns.com/dns-query", "https://doh.pub/dns-query" };
            root["dns"] = dns;
        }
        if (profile.Tun) root["sniffer"] = new Dictionary<string, object>
        {
            ["enable"] = true, ["force-dns-mapping"] = true, ["parse-pure-ip"] = true,
            ["sniff"] = new Dictionary<string, object>
            {
                ["HTTP"] = new Dictionary<string, object> { ["ports"] = new[] { 80 }, ["override-destination"] = false },
                ["TLS"] = new Dictionary<string, object> { ["ports"] = new[] { 443 } },
                ["QUIC"] = new Dictionary<string, object> { ["ports"] = new[] { 443 } }
            }
        };
        var nodes = new List<string>();
        if (root.TryGetValue("proxies", out var proxies) && proxies is IEnumerable<object> nodeObjects)
            foreach (var node in nodeObjects.OfType<IDictionary<object, object>>())
                if (node.TryGetValue("name", out var name) && name != null) nodes.Add(name.ToString()!);
        var providers = new List<string>();
        if (root.TryGetValue("proxy-providers", out var value) && value is IDictionary<object, object> mappings)
            providers.AddRange(mappings.Keys.Select(key => key.ToString()!));
        var groups = root.TryGetValue("proxy-groups", out var groupsValue) && groupsValue is IEnumerable<object> items
            ? items.ToList() : new List<object>();
        string groupName = "Swirl 节点";
        while (nodes.Contains(groupName) || providers.Contains(groupName) || groups.OfType<IDictionary<object, object>>().Any(g => g.TryGetValue("name", out var n) && n?.ToString() == groupName)) groupName += "_";
        var group = new Dictionary<string, object> { ["name"] = groupName, ["type"] = "select", ["proxies"] = nodes.Count > 0 ? nodes : new List<string> { "DIRECT" } };
        if (providers.Count > 0) group["use"] = providers;
        groups.Insert(0, group);
        var configuredPolicies = nodes.Concat(groups.OfType<IDictionary<object, object>>().Where(g => g.TryGetValue("name", out _)).Select(g => g["name"].ToString()!)).Concat(new[] { groupName }).ToArray();
        // Validate every active user policy before producing either core rules or
        // HTTP listeners. URL listeners select a real core policy directly.
        var userRules = UserRouting.CoreRules(profile, groupName, configuredPolicies).ToArray();
        var urlListeners = UserRouting.CoreListeners(profile, groupName);
        if (urlListeners.Count > 0) root["listeners"] = urlListeners;
        // Imported include-all groups must not select the local plugin as an
        // upstream node; doing so would send plugin output back to its own input.
        if (profile.Tun)
            foreach (var importedGroup in groups.OfType<IDictionary<object, object>>())
            {
                importedGroup.TryGetValue("exclude-filter", out var filter);
                importedGroup["exclude-filter"] = (string.IsNullOrWhiteSpace(filter?.ToString()) ? "" : "(?:" + filter + ")|") + "^" + PluginOutbound + "$";
            }
        root["proxy-groups"] = groups;
        var rules = new List<string>();
        if (profile.Tun)
        {
            var outbound = root.TryGetValue("proxies", out var configured) && configured is IEnumerable<object> entries ? entries.ToList() : new List<object>();
            if (nodes.Contains(PluginOutbound) || providers.Contains(PluginOutbound) || groups.OfType<IDictionary<object, object>>().Any(g => g.TryGetValue("name", out var n) && n?.ToString() == PluginOutbound)) throw new InvalidOperationException("配置中的名称与内部插件入口冲突，请重命名该项。");
            outbound.Add(new Dictionary<string, object> { ["name"] = PluginOutbound, ["type"] = "http", ["server"] = "127.0.0.1", ["port"] = PluginPort });
            root["proxies"] = outbound;
            rules.Add(CaptureRule);
            if (profile.Mitm)
                foreach (var plugin in effectivePlugins.Where(p => p.Enabled && p.Unsupported.Count == 0))
                    foreach (var host in plugin.Hosts.Where(h => !h.StartsWith('-')))
                        rules.Add("AND,((IN-NAME,DEFAULT-TUN),(NETWORK,udp),(DST-PORT,443),(DOMAIN-REGEX," + LoonPlugin.HostRegex(host) + ")" + string.Concat(plugin.Hosts.Where(h => h.StartsWith('-')).Select(h => ",(NOT,((DOMAIN-REGEX," + LoonPlugin.HostRegex(h[1..]) + ")))")) + "),REJECT");
        }
        if (profile.Mode == "rule")
        {
            rules.AddRange(userRules);
            foreach (var plugin in profile.Plugins.Where(p => p.Enabled && p.Unsupported.Count == 0))
                foreach (var rule in plugin.Rules.Concat(plugin.RemoteRules.SelectMany(r => r.Rules)))
                {
                    var parts = rule.Split(',');
                    if (parts.Length >= 3 && parts[2] == "PROXY") parts[2] = plugin.ProxyPolicy.Length == 0 || plugin.ProxyPolicy == "AdShield 节点" && !configuredPolicies.Contains(plugin.ProxyPolicy) ? groupName : plugin.ProxyPolicy;
                    rules.Add(string.Join(',', parts));
                }
            if (profile.BasicAds) rules.AddRange(new[] { "DOMAIN-SUFFIX,doubleclick.net,REJECT", "DOMAIN-SUFFIX,googlesyndication.com,REJECT", "DOMAIN-SUFFIX,googleadservices.com,REJECT" });
        }
        if (profile.Mode == "rule" && root.TryGetValue("rules", out var rulesValue) && rulesValue is IEnumerable<object> original)
            rules.AddRange(original.Select(rule => rule.ToString()!).Where(rule => !string.IsNullOrWhiteSpace(rule)));
        if (!rules.Any(rule => rule.StartsWith("MATCH,", StringComparison.OrdinalIgnoreCase))) rules.Add("MATCH," + (profile.Mode == "global" ? "GLOBAL" : profile.Mode == "direct" ? "DIRECT" : groupName));
        root["rules"] = rules.Distinct().ToArray();
        return new SerializerBuilder().Build().Serialize(root);
    }

    internal const string PluginOutbound = "Swirl Internal Plugin";
    internal const string CaptureRule = "AND,((IN-NAME,DEFAULT-TUN),(NETWORK,tcp),(DST-PORT,80/443))," + PluginOutbound;

    internal static string? PreferredGroup(ProxyProfile profile)
    {
        if (profile.Mode == "global") return "GLOBAL";
        if (string.IsNullOrWhiteSpace(profile.Yaml)) return null;
        var root = Parse(profile.Yaml);
        if (root.TryGetValue("rules", out var value) && value is IEnumerable<object> rules)
        {
            var final = rules.Select(rule => rule.ToString()!).FirstOrDefault(rule => rule.StartsWith("MATCH,", StringComparison.OrdinalIgnoreCase));
            if (final != null) return final.Split(',')[1].Trim();
        }
        return null;
    }
}

internal static class NetworkFetch
{
    internal static async Task<string> TextAsync(string url, int limit = 2 * 1024 * 1024)
        => Encoding.UTF8.GetString(await BytesAsync(url, limit));

    internal static async Task<byte[]> BytesAsync(string url, int limit = 2 * 1024 * 1024)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme != "https" || !string.IsNullOrEmpty(uri.UserInfo))
            throw new InvalidOperationException("请提供 HTTPS 原作者链接或 HTTPS 订阅地址。");
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        client.DefaultRequestHeaders.UserAgent.ParseAdd("Swirl/0.6.0 mihomo");
        using var response = await client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead);
        if (!response.IsSuccessStatusCode) throw new InvalidOperationException("下载失败，HTTP " + (int)response.StatusCode + "；可在浏览器下载后本地导入。");
        if (response.Content.Headers.ContentLength > limit) throw new InvalidOperationException("下载文件过大。");
        using var source = await response.Content.ReadAsStreamAsync();
        using var output = new MemoryStream();
        var buffer = new byte[8192];
        int read;
        while ((read = await source.ReadAsync(buffer)) > 0)
        {
            if (output.Length + read > limit) throw new InvalidOperationException("下载文件超过大小上限。");
            output.Write(buffer, 0, read);
        }
        return output.ToArray();
    }
}
