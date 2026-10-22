namespace AdShield.Network;

internal sealed record ProxyProtocolCapability(string Type, string Name, string Notes);
internal sealed record ProxyProtocolSummary(string Name, int NodeCount);

internal static class ProxyProtocols
{
    // These are Mihomo outbound capabilities, not a promise that every Loon
    // node URI or subscription syntax is accepted as a configuration format.
    internal static readonly IReadOnlyList<ProxyProtocolCapability> Supported = new[]
    {
        new ProxyProtocolCapability("ss", "Shadowsocks / SS2022", "SS2022 使用 2022-blake3 系列加密方式。"),
        new ProxyProtocolCapability("ssr", "ShadowsocksR", "使用 Clash/Mihomo YAML 节点配置。"),
        new ProxyProtocolCapability("vmess", "VMess", "可配置 TCP、WebSocket 等传输。"),
        new ProxyProtocolCapability("vless", "VLESS", "TLS、REALITY 等选项由核心处理。"),
        new ProxyProtocolCapability("trojan", "Trojan", "TLS 连接。"),
        new ProxyProtocolCapability("hysteria2", "Hysteria2", "QUIC 传输。"),
        new ProxyProtocolCapability("wireguard", "WireGuard", "通过核心中的 WireGuard 出站节点。"),
        new ProxyProtocolCapability("http", "HTTP / HTTPS", "HTTPS 上游设置 tls: true。"),
        new ProxyProtocolCapability("socks5", "SOCKS5", "可使用带认证的上游代理。")
    };

    internal static IReadOnlyList<ProxyProtocolSummary> Configured(ProxyProfile profile)
    {
        if (string.IsNullOrWhiteSpace(profile.Yaml)) return Array.Empty<ProxyProtocolSummary>();
        var root = MihomoConfig.Parse(profile.Yaml);
        if (!root.TryGetValue("proxies", out var value) || value is not IEnumerable<object> nodes) return Array.Empty<ProxyProtocolSummary>();
        return nodes.OfType<IDictionary<object, object>>().Select(node =>
        {
            string type = node.TryGetValue("type", out var kind) ? kind?.ToString()?.ToLowerInvariant() ?? "未知" : "未知";
            if (type == "ss" && node.TryGetValue("cipher", out var cipher) && cipher?.ToString()?.StartsWith("2022-", StringComparison.OrdinalIgnoreCase) == true) return "SS2022";
            if (type == "http") return node.TryGetValue("tls", out var tls) && bool.TryParse(tls?.ToString(), out bool enabled) && enabled ? "HTTPS" : "HTTP";
            return Supported.FirstOrDefault(p => p.Type == type)?.Name ?? type;
        }).GroupBy(name => name, StringComparer.Ordinal).Select(group => new ProxyProtocolSummary(group.Key, group.Count())).ToArray();
    }
}
