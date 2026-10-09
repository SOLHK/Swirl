using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using Windows.Networking.Connectivity;

namespace AdShield.Network;

internal sealed class UserRoutingRule
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public bool Enabled { get; set; } = true;
    public string Kind { get; set; } = "DOMAIN-SUFFIX";
    public string Value { get; set; } = "";
    public string Policy { get; set; } = "DIRECT";
    public string Ssid { get; set; } = "";
    public string HttpsHosts { get; set; } = "";

    internal void Validate()
    {
        Kind = Kind.Trim().ToUpperInvariant();
        Policy = Policy.Trim();
        if (Policy.Equals("DIRECT", StringComparison.OrdinalIgnoreCase) || Policy.Equals("REJECT", StringComparison.OrdinalIgnoreCase) || Policy.Equals("PROXY", StringComparison.OrdinalIgnoreCase)) Policy = Policy.ToUpperInvariant();
        if (Policy.Length is 0 or > 200 || Policy.Any(c => c is ',' or '\r' or '\n' || char.IsControl(c)) || Policy == MihomoConfig.PluginOutbound)
            throw new InvalidOperationException("规则策略无效，请选择直连、拒绝、代理或已有节点/策略组。");
        if (Encoding.UTF8.GetByteCount(Ssid) > 32 || Ssid.Any(char.IsControl)) throw new InvalidOperationException("Wi-Fi 名称需为不超过 32 字节的 SSID。");
        if (Kind == "SSID")
        {
            if (Value.Length == 0 || Encoding.UTF8.GetByteCount(Value) > 32 || Value.Any(char.IsControl)) throw new InvalidOperationException("SSID 规则需要填写准确的 Wi-Fi 名称。");
            if (Ssid.Length > 0) throw new InvalidOperationException("SSID 规则自身已指定 Wi-Fi，无需附加 Wi-Fi 条件。");
        }
        else
        {
            Value = Value.Trim();
            if (Kind is "DOMAIN" or "DOMAIN-SUFFIX")
            {
                Value = new IdnMapping().GetAscii(Value.TrimEnd('.')).ToLowerInvariant();
                if (Value.Length > 253 || !Regex.IsMatch(Value, @"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", RegexOptions.IgnoreCase) || IPAddress.TryParse(Value, out _))
                    throw new InvalidOperationException("请填写域名，不含协议、路径或通配符。");
            }
            else if (Kind is "IP-CIDR" or "IP-CIDR6")
            {
                var parts = Value.Split('/');
                bool ipv6 = Kind == "IP-CIDR6";
                if (parts.Length != 2 || !IPAddress.TryParse(parts[0], out var address) || address.AddressFamily != (ipv6 ? AddressFamily.InterNetworkV6 : AddressFamily.InterNetwork) || !int.TryParse(parts[1], out int prefix) || prefix < 0 || prefix > (ipv6 ? 128 : 32))
                    throw new InvalidOperationException("请填写有效的 IP 网段，例如 192.168.1.0/24 或 2001:db8::/32。");
                Value = address + "/" + prefix;
            }
            else if (Kind == "URL-REGEX")
            {
                if (Value.Length is 0 or > 2048) throw new InvalidOperationException("URL 正则长度应为 1–2048 个字符。");
                LoonPlugin.ValidatePattern(Value);
            }
            else throw new InvalidOperationException("不支持的分流类型：" + Kind);
        }
        if (HttpsHosts.Length > 4096) throw new InvalidOperationException("HTTPS 域名列表过长。");
        foreach (string host in MitmHosts())
            if (host == "*" || !Regex.IsMatch(host, @"^[a-zA-Z0-9_*?-]+(?:\.[a-zA-Z0-9_*?-]+)+$"))
                throw new InvalidOperationException("HTTPS URL 规则需指定域名，例如 api.example.com 或 *.example.com；不能使用全局 *。");
        if (Kind != "URL-REGEX" && HttpsHosts.Length > 0) throw new InvalidOperationException("只有 URL 规则需要指定 HTTPS 解密域名。");
    }

    internal IEnumerable<string> MitmHosts() => HttpsHosts.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Select(h => h.ToLowerInvariant()).Distinct(StringComparer.OrdinalIgnoreCase);
    public override string ToString() => (Enabled ? "✓ " : "○ ") + Kind + ", " + Value + " → " + Policy + (Ssid.Length == 0 ? "" : " · Wi-Fi " + Ssid);
}

internal sealed record UserUrlRoute(bool Reject, int Port, string Policy);

internal sealed class UserRoutingSnapshot
{
    internal string CurrentSsid { get; init; } = "";
    internal string Mode { get; init; } = "rule";
    internal List<UserRoutingRule> Rules { get; init; } = new();
    internal Dictionary<string, int> PolicyPorts { get; init; } = new(StringComparer.Ordinal);
}

internal static class UserRouting
{
    internal const int FirstListenerPort = 18000;

    // GetConnectedSsid reads the connected network only. Unlike WLAN scans or
    // WlanQueryInterface(current_connection), it does not query nearby BSSIDs.
    internal static string ReadCurrentSsid()
    {
        try
        {
            var connection = NetworkInformation.GetInternetConnectionProfile();
            return connection is { IsWlanConnectionProfile: true } ? connection.WlanConnectionProfileDetails.GetConnectedSsid() ?? "" : "";
        }
        catch { return ""; }
    }

    internal static UserRoutingSnapshot Prepare(ProxyProfile profile) => Prepare(profile, profile.UserRules.Any(r => r.Enabled && (r.Kind.Equals("SSID", StringComparison.OrdinalIgnoreCase) || r.Ssid.Length > 0)) ? ReadCurrentSsid() : "");
    internal static UserRoutingSnapshot Prepare(ProxyProfile profile, string currentSsid)
    {
        if (profile.UserRules.Count > 500) throw new InvalidOperationException("自定义分流规则不能超过 500 条。");
        var active = new List<UserRoutingRule>();
        foreach (var saved in profile.UserRules.Where(r => r.Enabled))
        {
            var rule = new UserRoutingRule { Id = saved.Id, Enabled = true, Kind = saved.Kind, Value = saved.Value, Policy = saved.Policy, Ssid = saved.Ssid, HttpsHosts = saved.HttpsHosts };
            rule.Validate();
            if (rule.Kind == "SSID" ? !string.Equals(rule.Value, currentSsid, StringComparison.Ordinal) : rule.Ssid.Length > 0 && !string.Equals(rule.Ssid, currentSsid, StringComparison.Ordinal)) continue;
            active.Add(rule);
        }
        var policies = profile.Mode == "rule" ? active.Where(r => r.Kind == "URL-REGEX" && r.Policy != "REJECT").Select(r => r.Policy).Distinct(StringComparer.Ordinal).OrderBy(p => p, StringComparer.Ordinal).ToArray() : Array.Empty<string>();
        if (policies.Length > 100) throw new InvalidOperationException("URL 规则最多使用 100 个不同策略。");
        var snapshot = new UserRoutingSnapshot { CurrentSsid = currentSsid, Mode = profile.Mode, Rules = active, PolicyPorts = policies.Select((policy, i) => new { policy, port = FirstListenerPort + i }).ToDictionary(p => p.policy, p => p.port, StringComparer.Ordinal) };
        profile.RoutingSnapshot = snapshot;
        return snapshot;
    }

    internal static UserRoutingSnapshot Snapshot(ProxyProfile profile) => profile.RoutingSnapshot ?? Prepare(profile);
    internal static IEnumerable<int> ListenerPorts(ProxyProfile profile) => Snapshot(profile).PolicyPorts.Values;

    internal static UserUrlRoute? ResolveUrlRoute(ProxyProfile profile, string url)
    {
        var snapshot = Snapshot(profile);
        if (snapshot.Mode != "rule") return null;
        foreach (var rule in snapshot.Rules.Where(r => r.Kind == "URL-REGEX"))
            if (LoonPlugin.Matches(rule.Value, url)) return rule.Policy == "REJECT" ? new(true, 0, "REJECT") : new(false, snapshot.PolicyPorts[rule.Policy], rule.Policy);
        return null;
    }

    internal static IEnumerable<LoonPlugin> EffectivePlugins(ProxyProfile profile)
    {
        var snapshot = Snapshot(profile);
        var plugins = profile.Plugins.AsEnumerable();
        if (snapshot.Mode != "rule") return plugins;
        var hosts = snapshot.Rules.Where(r => r.Kind == "URL-REGEX").SelectMany(r => r.MitmHosts()).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        return hosts.Count == 0 ? plugins : plugins.Concat(new[] { new LoonPlugin { Id = "swirl-user-url-routing", Name = "用户 URL 分流", Enabled = true, Hosts = hosts } });
    }

    internal static string[] Policies(ProxyProfile profile)
    {
        var names = new List<string> { "DIRECT", "REJECT", "PROXY" };
        if (!string.IsNullOrWhiteSpace(profile.Yaml))
        {
            var root = MihomoConfig.Parse(profile.Yaml);
            foreach (string key in new[] { "proxies", "proxy-groups" })
                if (root.TryGetValue(key, out var value) && value is IEnumerable<object> items)
                    foreach (var item in items.OfType<IDictionary<object, object>>())
                        if (item.TryGetValue("name", out var name) && name != null && name.ToString() != MihomoConfig.PluginOutbound) names.Add(name.ToString()!);
        }
        return names.Distinct(StringComparer.Ordinal).ToArray();
    }

    internal static IEnumerable<string> CoreRules(ProxyProfile profile, string defaultGroup, IEnumerable<string> configuredPolicies)
    {
        var snapshot = Snapshot(profile);
        if (snapshot.Mode != "rule") yield break;
        var allowed = configuredPolicies.Concat(new[] { "DIRECT", "REJECT", "PROXY", "GLOBAL" }).ToHashSet(StringComparer.Ordinal);
        foreach (var rule in snapshot.Rules)
        {
            if (!allowed.Contains(rule.Policy)) throw new InvalidOperationException("自定义规则引用了不存在的节点或策略组：" + rule.Policy);
            if (rule.Kind == "URL-REGEX") continue;
            string policy = rule.Policy == "PROXY" ? defaultGroup : rule.Policy;
            yield return rule.Kind == "SSID" ? "MATCH," + policy : rule.Kind + "," + rule.Value + "," + policy + (rule.Kind is "IP-CIDR" or "IP-CIDR6" ? ",no-resolve" : "");
        }
    }

    internal static List<object> CoreListeners(ProxyProfile profile, string defaultGroup) => Snapshot(profile).PolicyPorts.Select(entry => (object)new Dictionary<string, object>
    {
        ["name"] = "Swirl-URL-" + (entry.Value - FirstListenerPort).ToString("D3"), ["type"] = "http", ["listen"] = "127.0.0.1", ["port"] = entry.Value,
        ["proxy"] = entry.Key == "PROXY" ? defaultGroup : entry.Key, ["users"] = Array.Empty<object>()
    }).ToList();
}
