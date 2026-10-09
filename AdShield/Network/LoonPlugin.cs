using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed class LoonScript
{
    public string Phase { get; set; } = "";
    public string Pattern { get; set; } = "";
    public string Url { get; set; } = "";
    public string Code { get; set; } = "";
    public bool NeedsBody { get; set; }
    public bool BinaryBody { get; set; }
    public string Argument { get; set; } = "";
    public string Syntax { get; set; } = "";
    public string Tag { get; set; } = "";
    public string EnableExpression { get; set; } = "true";
    public string TimeoutExpression { get; set; } = "";
    public string Cron { get; set; } = "";
    public double Timeout { get; set; } = 20;
    public override string ToString() => Tag.Length > 0 ? Tag : Uri.TryCreate(Url, UriKind.Absolute, out var uri) ? Path.GetFileName(uri.AbsolutePath) : "脚本";
}
internal sealed class LoonRewrite
{
    public string Pattern { get; set; } = "";
    public string Action { get; set; } = "";
    public string Target { get; set; } = "";
    public string Phase { get; set; } = "http-request";
    public string ResourceUrl { get; set; } = "";
    public string Syntax { get; set; } = "";
    public Dictionary<string, string> Resources { get; set; } = new();
}
internal sealed class LoonRemoteRules
{
    public string Url { get; set; } = "";
    public string Policy { get; set; } = "DIRECT";
    public List<string> Rules { get; set; } = new();
}
internal sealed class LoonPlugin
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Name { get; set; } = "导入插件";
    public string Source { get; set; } = "";
    public string Original { get; set; } = "";
    public string Argument { get; set; } = "";
    public bool Enabled { get; set; }
    public List<string> Rules { get; set; } = new();
    public List<string> Hosts { get; set; } = new();
    public List<LoonScript> Scripts { get; set; } = new();
    public List<LoonRewrite> Rewrites { get; set; } = new();
    public List<string> Unsupported { get; set; } = new();
    public Dictionary<string, string> DnsHosts { get; set; } = new();
    public List<PluginParameter> Parameters { get; set; } = new();
    public string ProtectedParameterValues { get; set; } = "";
    public List<LoonRemoteRules> RemoteRules { get; set; } = new();
    public string ProxyPolicy { get; set; } = "";
    public override string ToString() => (Enabled ? "✓ " : "○ ") + Name + (Unsupported.Count > 0 ? "（不兼容，禁止启用）" : "");

    internal static string ResolveImportUrl(string url)
    {
        if (url.StartsWith("loon://", StringComparison.OrdinalIgnoreCase))
        {
            var match = Regex.Match(url, @"[?&]plugin=([^&]+)");
            if (!match.Success) throw new InvalidOperationException("Loon 链接缺少 plugin 参数。");
            url = Uri.UnescapeDataString(match.Groups[1].Value);
        }
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme != "https") throw new InvalidOperationException("请使用 HTTPS 插件原文链接。");
        return uri.AbsoluteUri;
    }

    internal static LoonPlugin Parse(string text, string source)
    {
        text = text.TrimStart('\uFEFF');
        if (text.Length > 2 * 1024 * 1024 || text.Contains('\0') || text.TrimStart().StartsWith("<"))
            throw new InvalidOperationException("内容不是明文 Loon 插件，可能是加密格式或网站错误页。");
        var result = new LoonPlugin { Source = source, Original = text };
        string section = "";
        bool recognizedSection = false;
        foreach (var raw in text.Split('\n'))
        {
            string line = raw.Trim();
            var title = Regex.Match(line, @"^#!name\s*=\s*(.+)$", RegexOptions.IgnoreCase);
            if (title.Success) result.Name = title.Groups[1].Value.Trim();
            if (line.StartsWith("#") || line.StartsWith(";") || line.Length == 0) continue;
            if (line.StartsWith('[') && line.EndsWith(']'))
            {
                section = line[1..^1].ToLowerInvariant();
                if (section is "rule" or "rewrite" or "script" or "mitm" or "host" or "general" or "argument" or "remote rule") recognizedSection = true;
                else result.Unsupported.Add("不支持节：[" + section + "]");
                continue;
            }
            try
            {
                if (section == "rule")
                {
                    result.Rules.Add(ParseRule(line));
                }
                else if (section == "rewrite")
                {
                    result.Rewrites.Add(ParseRewrite(line, source));
                }
                else if (section == "script")
                {
                    if (Regex.IsMatch(line, @"^(request|response)\s+if\b|^(generic|network-changed)\s+then\b|^cron\s+.*\s+then\b"))
                    {
                        var program = LoonSyntax.Parse(line, true);
                        result.Scripts.Add(new() { Syntax = line, Phase = program.Phase, Url = ResourceUrl(source, (string)program.Calls[0].Arguments[0].Literal!), Tag = program.Options.TryGetValue("tag", out var tag) && tag.Literal is string label ? label : "" });
                        continue;
                    }
                    var task = Regex.Match(line, @"^(cron|generic|network-changed)\s+(.*?)\s*script-path\s*=");
                    if (task.Success)
                    {
                        result.Scripts.Add(new() { Phase = task.Groups[1].Value, Cron = PluginParameter.Text(task.Groups[2].Value.Trim().TrimEnd(',')), Url = ResourceUrl(source, Option(line, "script-path")), Tag = Option(line, "tag"), Argument = Option(line, "argument"), EnableExpression = Option(line, "enable") is { Length: > 0 } taskEnable ? taskEnable : "true", TimeoutExpression = Option(line, "timeout"), Timeout = 300 });
                        continue;
                    }
                    var phase = Regex.Match(line, @"^(http-request|http-response)\b", RegexOptions.IgnoreCase);
                    string pattern = Option(line, "pattern"), url = Option(line, "script-path");
                    if (phase.Success && pattern.Length == 0)
                    {
                        var positional = Regex.Match(line, @"^http-(?:request|response)\s+(\S+)\s+script-path\s*=");
                        if (positional.Success) pattern = positional.Groups[1].Value;
                    }
                    if (!phase.Success || pattern.Length == 0 || url.Length == 0) throw new InvalidOperationException("仅支持 http-request/http-response，需 pattern 和 script-path");
                    ValidatePattern(pattern);
                    string enabled = Option(line, "enable");
                    result.Scripts.Add(new() { Phase = phase.Value.ToLowerInvariant(), Pattern = pattern, Url = ResourceUrl(source, url), Argument = Option(line, "argument"), Tag = Option(line, "tag"), EnableExpression = enabled.Length == 0 ? "true" : enabled, TimeoutExpression = Option(line, "timeout"), NeedsBody = Option(line, "requires-body").Equals("true", StringComparison.OrdinalIgnoreCase), BinaryBody = Option(line, "binary-body-mode").Equals("true", StringComparison.OrdinalIgnoreCase) });
                }
                else if (section == "mitm")
                {
                    if (!line.StartsWith("hostname", StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("仅支持 hostname");
                    var hosts = line[(line.IndexOf('=') + 1)..].Replace("%APPEND%", "").Split(',').Select(h => h.Trim()).Where(h => h.Length > 0);
                    foreach (string host in hosts)
                    {
                        if (host != "*" && !Regex.IsMatch(host.TrimStart('-'), @"^[a-zA-Z0-9_*?-]+(?:\.[a-zA-Z0-9_*?-]+)+$")) throw new InvalidOperationException("不支持此 MITM 主机表达式");
                        result.Hosts.Add(host.ToLowerInvariant());
                    }
                }
                else if (section == "argument")
                {
                    var parameter = PluginParameter.Parse(line);
                    if (result.Parameters.Count >= 100 || result.Parameters.Any(p => p.Name == parameter.Name)) throw new InvalidOperationException("参数过多或重名。");
                    result.Parameters.Add(parameter);
                }
                else if (section == "remote rule")
                {
                    var pieces = PluginParameter.Split(line); string policy = Option(line, "policy");
                    if (policy.Length == 0) policy = pieces.Count > 1 && !pieces[1].Contains('=') ? pieces[1] : "DIRECT";
                    if (policy is not ("REJECT" or "REJECT-DROP" or "DIRECT" or "PROXY") || result.RemoteRules.Count >= 32) throw new InvalidOperationException("远程规则策略无效或过多。");
                    if (Option(line, "enabled") == "false") continue;
                    result.RemoteRules.Add(new() { Url = ResourceUrl(source, pieces[0]), Policy = policy });
                }
                else if (section == "host")
                {
                    var pair = line.Split('=', 2, StringSplitOptions.TrimEntries);
                    if (pair.Length != 2 || !Regex.IsMatch(pair[0], @"^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+$") || !System.Net.IPAddress.TryParse(pair[1], out _))
                        throw new InvalidOperationException("Host 仅支持域名 = IP 地址");
                    result.DnsHosts[pair[0]] = pair[1];
                }
                else if (section == "general")
                {
                    var pair = line.Split('=', 2);
                    if (pair.Length != 2 || pair[1].Trim().Length > 0) throw new InvalidOperationException("General 非空参数尚不支持");
                }
                else result.Unsupported.Add("未识别的配置行");
            }
            catch (Exception e) { result.Unsupported.Add(section + "：" + e.Message); }
            if (result.Rules.Count + result.Scripts.Count + result.Rewrites.Count > 3000) throw new InvalidOperationException("插件规则过多。");
        }
        if (!recognizedSection) throw new InvalidOperationException("未找到明文 Loon 插件的 Rule/Rewrite/Script/MITM 节。");
        foreach (var script in result.Scripts)
            try { ScriptSettings.Validate(result, script); } catch (Exception e) { result.Unsupported.Add("script：" + e.Message); }
        foreach (var rewrite in result.Rewrites.Where(r => r.Syntax.Length > 0))
            try { LoonSyntax.Validate(LoonSyntax.Parse(rewrite.Syntax, false), result, false); } catch (Exception e) { result.Unsupported.Add("rewrite：" + e.Message); }
        result.Unsupported = result.Unsupported.Distinct().Take(50).ToList();
        return result;
    }

    private static LoonRewrite ParseRewrite(string line, string source)
    {
        if (Regex.IsMatch(line, @"^(request|response)\s+if\b"))
        {
            var program = LoonSyntax.Parse(line, false);
            return new() { Syntax = line, Phase = program.Phase, Action = "syntax" };
        }
        var match = Regex.Match(line, @"^(\S+)\s+(\S+)(?:\s+(.*))?$", RegexOptions.IgnoreCase);
        if (!match.Success) throw new InvalidOperationException("Rewrite 格式无效");
        string action = match.Groups[2].Value.ToLowerInvariant(), arguments = match.Groups[3].Value.Trim();
        ValidatePattern(match.Groups[1].Value);
        var rewrite = new LoonRewrite { Pattern = match.Groups[1].Value, Action = action, Target = arguments };
        if (action is "request-body-json-jq" or "response-body-json-jq")
        {
            rewrite.Phase = action.StartsWith("response") ? "http-response" : "http-request";
            rewrite.Action = "json-jq";
            rewrite.Target = Unquote(arguments);
            if (rewrite.Target.Length == 0) throw new InvalidOperationException("缺少 jq 表达式");
        }
        else if (action == "mock-response-body")
        {
            if (Option(arguments, "data-path").Length > 0 || Option(arguments, "mock-data-is-base64") == "true") throw new InvalidOperationException("此 Mock 资源形式尚不支持");
            string type = Option(arguments, "data-type"), status = Option(arguments, "status-code");
            if (type is not ("json" or "text" or "plain" or "html" or "css" or "javascript") || (status.Length > 0 && (!int.TryParse(status, out int code) || code is < 100 or > 599))) throw new InvalidOperationException("Mock 参数无效");
        }
        else if (action is "302" or "307" or "header")
        {
            if (!Uri.TryCreate(arguments, UriKind.Absolute, out var target) || target.Scheme is not ("http" or "https")) throw new InvalidOperationException("重定向/URL 替换目标无效");
        }
        else if (Regex.IsMatch(action, @"^(?:response-)?header-(add|del|replace|replace-regex)$|^(request|response)-body-replace-regex$")) { }
        else if (!Regex.IsMatch(action, @"^reject(?:-200|-dict|-array|-img)?$")) throw new InvalidOperationException("未实现的 Rewrite action：" + action);
        else if (arguments.Length > 0) throw new InvalidOperationException("Reject 不接受额外参数");
        rewrite.Syntax = LegacyRewrite(rewrite, arguments);
        return rewrite;
    }

    private static string LegacyRewrite(LoonRewrite rewrite, string arguments)
    {
        string Q(string value) => JsonSerializer.Serialize(value, new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        string pattern = Regex.Replace(rewrite.Pattern, @"(?<!\\)/", @"\/");
        string prefix = (rewrite.Phase == "http-response" || rewrite.Action.StartsWith("response-") ? "response" : "request");
        string condition = prefix + " if ${url} ~= /" + pattern + "/";
        string action;
        if (rewrite.Action == "json-jq") action = prefix + ".json.jq(" + Q(rewrite.Target) + ")";
        else if (rewrite.Action.StartsWith("reject"))
            action = rewrite.Action switch { "reject" => "reject(403)", "reject-200" => "reject(200)", "reject-dict" => "reject_dict(200)", "reject-array" => "reject_array(200)", "reject-img" => "reject_img(200)", _ => throw new InvalidOperationException() };
        else if (rewrite.Action is "302" or "307" or "header")
        {
            condition += " as oldurl";
            string replacement = Regex.Replace(rewrite.Target, @"\$(\d+)", m => "${oldurl." + m.Groups[1].Value + "}");
            action = rewrite.Action == "header" ? "url.replace(" + Q(replacement) + ")" : "redirect(" + rewrite.Action + "," + Q(replacement) + ")";
        }
        else if (rewrite.Action == "mock-response-body")
        {
            prefix = "response"; condition = prefix + " if ${url} ~= /" + pattern + "/";
            string code = Option(arguments, "status-code");
            action = "response.body.mock(" + Q(Option(arguments, "data-type")) + "," + Q(Option(arguments, "data")) + "," + (code.Length == 0 ? "200" : code) + ")";
        }
        else
        {
            var values = Regex.Matches(arguments, @"""(?:\\.|[^""\\])*""|'[^']*'|\S+").Select(m => PluginParameter.Text(m.Value)).ToArray();
            var calls = new List<string>();
            bool body = rewrite.Action.Contains("body-replace");
            string method = body ? "body.replace" : rewrite.Action.EndsWith("replace-regex") ? "header.replace" : rewrite.Action.EndsWith("replace") ? "header.set" : rewrite.Action.EndsWith("add") ? "header.add" : "header.del";
            int width = body ? 2 : method == "header.replace" ? 3 : method == "header.del" ? 1 : 2;
            if (values.Length == 0 || values.Length % width != 0) throw new InvalidOperationException("旧版复写参数数量无效。");
            for (int i = 0; i < values.Length; i += width)
            {
                string regex = body ? values[i] : method == "header.replace" ? values[i + 1] : "";
                if (regex.Length > 0) ValidatePattern(regex);
                string literal = "/" + Regex.Replace(regex, @"(?<!\\)/", @"\/") + "/";
                string args = body ? literal + "," + Q(values[i + 1]) : method == "header.replace" ? Q(values[i]) + "," + literal + "," + Q(values[i + 2]) : string.Join(',', values.Skip(i).Take(width).Select(Q));
                calls.Add(prefix + "." + method + "(" + args + ")");
            }
            action = string.Join(" | ", calls);
        }
        rewrite.Phase = "http-" + prefix;
        return condition + " then " + action;
    }

    internal static string Unquote(string value)
    {
        if (value.Length >= 2 && value[0] == '\'' && value[^1] == '\'') return value[1..^1];
        if (value.Length >= 2 && value[0] == '"' && value[^1] == '"') return JsonSerializer.Deserialize<string>(value)!;
        return value;
    }
    internal static string ResourceUrl(string source, string resource)
    {
        if (Uri.TryCreate(resource, UriKind.Absolute, out _)) return ResolveImportUrl(resource);
        if (!Uri.TryCreate(source, UriKind.Absolute, out var basis) || basis.Scheme != "https") throw new InvalidOperationException("本地插件的相对资源需改为作者 HTTPS 链接");
        return ResolveImportUrl(new Uri(basis, resource).AbsoluteUri);
    }

    internal static string Option(string line, string key)
    {
        var match = Regex.Match(line, @"(?:^|[\s,])" + Regex.Escape(key) + @"\s*=\s*(\[[^\]]*\]|""(?:\\.|[^""\\])*""|'[^']*'|[^\s,]+)");
        return match.Success ? Unquote(match.Groups[1].Value) : "";
    }
    internal static void ValidatePattern(string pattern) => _ = new Regex(pattern, RegexOptions.None, TimeSpan.FromMilliseconds(100));
    internal static bool Matches(string pattern, string url)
    {
        try { return Regex.IsMatch(url, pattern, RegexOptions.None, TimeSpan.FromMilliseconds(100)); }
        catch (RegexMatchTimeoutException) { return false; }
    }
    internal static string HostRegex(string host) => "(?i)^" + Regex.Escape(host).Replace(@"\*", ".*").Replace(@"\?", ".") + "$";
    internal bool MatchesHost(string host) => Hosts.Any(pattern => !pattern.StartsWith('-') && Matches(HostRegex(pattern), host)) && !Hosts.Any(pattern => pattern.StartsWith('-') && Matches(HostRegex(pattern[1..]), host));
    internal Dictionary<string, object?> EffectiveParameters()
    {
        var saved = ProtectedParameterValues.Length == 0 ? new Dictionary<string, JsonElement>() : JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(ProxyProfile.Unprotect(ProtectedParameterValues))!;
        return Parameters.ToDictionary(p => p.Name, p => p.Read(saved.TryGetValue(p.Name, out var value) ? p.Validate(value) : p.Default));
    }
    internal static string ParseRule(string line, string? policy = null)
    {
        var pieces = line.Split(',').Select(p => p.Trim()).ToList();
        if (pieces.Count == 2) pieces.Add(policy ?? "DIRECT");
        else if (policy != null && pieces.Count >= 3) pieces[2] = policy;
        if (pieces.Count is < 3 or > 4 || pieces[0].ToUpperInvariant() is not ("DOMAIN" or "DOMAIN-SUFFIX" or "DOMAIN-KEYWORD" or "DOMAIN-WILDCARD" or "DOMAIN-REGEX" or "IP-CIDR" or "IP-CIDR6" or "PROCESS-NAME" or "PROCESS-PATH" or "DST-PORT" or "NETWORK" or "GEOIP") || pieces[2].ToUpperInvariant() is not ("REJECT" or "REJECT-DROP" or "DIRECT" or "PROXY") || pieces.Count == 4 && pieces[3] != "no-resolve") throw new InvalidOperationException("不支持规则类型或策略");
        pieces[0] = pieces[0].ToUpperInvariant(); pieces[2] = pieces[2].ToUpperInvariant(); return string.Join(',', pieces);
    }

    internal async Task DownloadScriptsAsync()
    {
        foreach (var script in Scripts) script.Code = await NetworkFetch.TextAsync(script.Url);
        foreach (var rewrite in Rewrites.Where(r => r.ResourceUrl.Length > 0)) rewrite.Target = await NetworkFetch.TextAsync(rewrite.ResourceUrl, 128 * 1024);
        foreach (var rewrite in Rewrites.Where(r => r.Syntax.Length > 0))
            foreach (var call in LoonSyntax.Parse(rewrite.Syntax, false).Calls.Where(c => c.Name.EndsWith("_file")))
            {
                if (call.Arguments[call.Name.EndsWith("jq_file") ? 0 : 1].Literal is not string path) throw new InvalidOperationException("资源路径需为固定字符串。");
                string url = ResourceUrl(Source, path);
                rewrite.Resources[path] = Convert.ToBase64String(await NetworkFetch.BytesAsync(url));
            }
        foreach (var remote in RemoteRules)
        {
            string text = await NetworkFetch.TextAsync(remote.Url);
            remote.Rules = text.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0 && !l.StartsWith('#') && !l.StartsWith(';')).Select(l => ParseRule(l, remote.Policy)).ToList();
            if (remote.Rules.Count > 20000) throw new InvalidOperationException("远程规则超过 20000 条。");
        }
    }
}
