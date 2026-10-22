using System.Text.RegularExpressions;

namespace AdShield.Network;

internal static class CoreDiagnostics
{
    // Core output may contain whole URLs, credentials or arbitrary YAML values.
    // Return only fixed explanations and bounded numeric locations, never raw text.
    internal static string Describe(string output, int exitCode)
    {
        string lower = output.ToLowerInvariant();
        string location = "";
        var index = Regex.Match(lower, @"\b(proxy|rules?|proxy group|proxy-group)\s*\[?(\d{1,6})(?:\]|\s*:)", RegexOptions.CultureInvariant);
        if (index.Success) location = "（" + (index.Groups[1].Value == "proxy" ? "节点" : index.Groups[1].Value.StartsWith("rule") ? "规则" : "策略组") + "索引 " + index.Groups[2].Value + "）";
        string detail;
        if ((lower.Contains("geoip") || lower.Contains("geosite") || lower.Contains("mmdb") || lower.Contains("asn.mmdb")) && (lower.Contains("download") || lower.Contains("timeout") || lower.Contains("no such file") || lower.Contains("not exist") || lower.Contains("invalid") || lower.Contains("failed") || lower.Contains("can't") || lower.Contains("unable")))
            detail = "GEOIP / GEOSITE 分流数据库无法读取或下载。请检查自定义 GEO 数据来源；使用默认数据时请完整安装新版 Swirl。";
        else if (lower.Contains("not subpath") || lower.Contains("safe_paths"))
            detail = "节点或规则提供器的文件路径超出了核心数据目录。请使用该目录内的相对路径。";
        else if (lower.Contains("proxy") && (lower.Contains("not found") || lower.Contains("not exist")))
            detail = "规则或策略组引用了不存在的节点 / 策略组。请更新订阅或检查引用名称。";
        else if (lower.Contains("rule") && (lower.Contains("not support") || lower.Contains("unsupported")))
            detail = "分流规则类型或语法不受当前 Mihomo 支持。请检查订阅的 Clash/Mihomo 格式。";
        else if (lower.Contains("cipher") || lower.Contains("uuid") || lower.Contains("private key") || lower.Contains("private-key"))
            detail = "节点的加密方式、UUID 或密钥格式无效。请更新订阅或检查节点参数。";
        else if (lower.Contains("proxy") && (lower.Contains("not support") || lower.Contains("unsupported")))
            detail = "节点协议不受当前 Mihomo 支持。请导出兼容的 Clash/Mihomo 配置。";
        else if (lower.Contains("unmarshal") || lower.Contains("yaml:") || lower.Contains("parse yaml"))
            detail = "YAML 字段格式或类型不正确。请检查数字、布尔值和列表是否符合 Clash/Mihomo 格式。";
        else if (lower.Contains("provider") && (lower.Contains("download") || lower.Contains("failed") || lower.Contains("not found")))
            detail = "节点或规则提供器无法加载。请检查来源是否可访问，以及本地提供器文件是否齐全。";
        else if (lower.Contains("bind") || lower.Contains("address already in use"))
            detail = "本机端口无法监听，请关闭占用该端口的应用后重试。";
        else detail = "核心无法加载配置，请更新订阅；若同一配置可在其他 Clash 客户端使用，请反馈此错误码。";
        return "配置检查失败" + location + "：" + detail + "（核心退出码 " + exitCode + "）";
    }
}
