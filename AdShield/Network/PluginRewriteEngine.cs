using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed record RewriteResult(bool Matched, bool BodyMatched, bool BodyChanged, byte[]? SyntheticBody, byte[]? RequestBytes = null);
internal static class PluginRewriteEngine
{
    internal static bool IsMock(LoonRewrite rewrite) => rewrite.Syntax.Length > 0 && LoonSyntax.Parse(rewrite.Syntax, false).Calls.Any(c => c.Name.StartsWith("response.body.mock"));
    internal static async Task<RewriteResult> ApplyAsync(LoonPlugin plugin, LoonRewrite rewrite, SyntaxContext context, Func<Task<string>> readBody, Action<string> report)
    {
        var program = LoonSyntax.Parse(rewrite.Syntax, false);
        foreach (var pair in plugin.EffectiveParameters()) context.Parameters[pair.Key] = pair.Value;
        context.Captures.Clear();
        if (!program.Matches(context)) return new(false, false, false, null);
        bool bodyMatched = program.Calls.Any(c => c.Name.Contains(".json.") || c.Name.Contains(".body."));
        bool loaded = false, bodyChanged = false; byte[]? synthetic = null, requestBytes = null;
        if (IsMock(rewrite) && context.Response == null) context.Response = new(context.Request.Url, context.Request.Method, new(StringComparer.OrdinalIgnoreCase), "");
        foreach (var call in program.Calls)
        {
            try
            {
                var arguments = call.Arguments.Select(v => v.Resolve(context)).ToArray();
                int count = arguments.Length > 0 && arguments[0] is object?[] batch ? batch.Length : 1;
                for (int i = 0; i < count; i++)
                {
                    object?[] args = arguments.Select(a => a is object?[] values ? values[i] : a).ToArray();
                    bool response = call.Name.StartsWith("response.");
                    if ((call.Name.Contains(".json.") || call.Name == "request.body.replace" || call.Name == "response.body.replace") && !loaded)
                    {
                        string body = await readBody();
                        if (response) context.Response = context.Response! with { Body = body }; else context.Request = context.Request with { Body = body };
                        loaded = true;
                    }
                    if (call.Name is "url.replace" or "redirect")
                    {
                        var matchCondition = program.Condition!.UrlPatterns.Single();
                        var sourcePattern = matchCondition.B!.Resolve(context);
                        var pattern = sourcePattern is SyntaxRegex regex ? regex.Compile() : new Regex(S(sourcePattern), RegexOptions.None, TimeSpan.FromMilliseconds(100));
                        string replacement = S(args[call.Name == "redirect" ? 1 : 0]);
                        if (Regex.IsMatch(replacement, @"\$\d")) throw new InvalidOperationException("新版 URL 替换只支持条件捕获变量。");
                        string url = pattern.Replace(context.Request.Url, _ => replacement, 1);
                        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https")) throw new InvalidOperationException("替换后的 URL 无效。");
                        if (call.Name == "url.replace") { context.Request = context.Request with { Url = url }; if (context.Request.Headers.ContainsKey("Host")) context.Request.Headers["Host"] = uri.Authority; }
                        else
                        {
                            int status = Status(args[0]); if (status is not (302 or 307)) throw new InvalidOperationException("重定向状态只支持 302/307。");
                            context.Response = new(url, context.Request.Method, new(StringComparer.OrdinalIgnoreCase) { ["Location"] = url }, "", status); synthetic = Array.Empty<byte>();
                        }
                    }
                    else if (call.Name.StartsWith("reject"))
                    {
                        int status = Status(args[0]);
                        string body = call.Name switch { "reject_dict" => "{}", "reject_array" => "[]", "reject" when args.Length > 1 => S(args[1]), _ => "" };
                        string type = call.Name is "reject_dict" or "reject_array" ? "application/json" : "text/plain";
                        synthetic = call.Name == "reject_img" ? Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII=") : Encoding.UTF8.GetBytes(body);
                        context.Response = new(context.Request.Url, context.Request.Method, new(StringComparer.OrdinalIgnoreCase) { ["Content-Type"] = call.Name == "reject_img" ? "image/png" : type }, body, status);
                    }
                    else if (call.Name.Contains(".header."))
                    {
                        var headers = response ? context.Response!.Headers : context.Request.Headers;
                        string name = S(args[0]); ValidateHeader(name, "");
                        string operation = call.Name.Split('.').Last();
                        if (operation == "del") headers.Remove(name);
                        else if (operation == "replace")
                        {
                            if (!headers.TryGetValue(name, out var value)) continue;
                            string changed = R(args[1]).Replace(value, S(args[2])); ValidateHeader(name, changed); headers[name] = changed;
                        }
                        else
                        {
                            string value = S(args[1]); ValidateHeader(name, value);
                            if (operation == "add" && headers.TryGetValue(name, out var previous)) value = previous + "," + value;
                            headers[name] = value;
                        }
                    }
                    else if (call.Name.EndsWith("body.replace"))
                    {
                        var message = response ? context.Response! : context.Request;
                        string changed = R(args[0]).Replace(message.Body, S(args[1])); CheckSize(changed);
                        if (response) context.Response = message with { Body = changed }; else context.Request = message with { Body = changed };
                        bodyChanged = true;
                    }
                    else if (call.Name.Contains(".json."))
                    {
                        var message = response ? context.Response! : context.Request;
                        string changed;
                        if (call.Name.EndsWith(".jq") || call.Name.EndsWith(".jq_file"))
                        {
                            string expression = call.Name.EndsWith("_file") ? Encoding.UTF8.GetString(Resource(rewrite, S(args[0]))) : S(args[0]);
                            changed = await PluginJq.RunAsync(expression, message.Body);
                        }
                        else changed = JsonPath(message.Body, S(args[0]), call.Name.Split('.').Last(), args.Length > 1 ? args[1] : null);
                        CheckSize(changed); if (response) context.Response = message with { Body = changed }; else context.Request = message with { Body = changed };
                        bodyChanged = true;
                    }
                    else if (call.Name.Contains(".body.mock"))
                    {
                        string type = ContentType(S(args[0])); bool file = call.Name.EndsWith("_file");
                        bool base64 = args.Length > (response ? 3 : 2) && args[response ? 3 : 2] is true;
                        byte[] bytes = file ? Resource(rewrite, S(args[1])) : Encoding.UTF8.GetBytes(S(args[1]));
                        if (base64) bytes = Convert.FromBase64String(Encoding.UTF8.GetString(bytes));
                        if (bytes.Length > 2 * 1024 * 1024) throw new InvalidOperationException("Mock 正文超限。");
                        if (response)
                        {
                            int status = args.Length > 2 ? Status(args[2]) : 200;
                            var headers = context.Response?.Headers ?? new(StringComparer.OrdinalIgnoreCase);
                            headers["Content-Type"] = type;
                            context.Response = new(context.Request.Url, context.Request.Method, headers, Encoding.UTF8.GetString(bytes), status); synthetic = bytes;
                        }
                        else { context.Request.Headers["Content-Type"] = type; context.Request = context.Request with { Body = Encoding.UTF8.GetString(bytes) }; bodyChanged = true; requestBytes = bytes; }
                    }
                    else throw new InvalidOperationException("Action 尚未实现。");
                }
            }
            catch { report("复写 Action 失败，保留已完成变更：" + plugin.Name + " / " + call.Name); }
        }
        return new(true, bodyMatched, bodyChanged, synthetic, requestBytes);
    }
    private static string S(object? value) => value as string ?? throw new InvalidOperationException("参数必须是字符串。");
    private static Regex R(object? value) => value is SyntaxRegex r ? r.Compile() : throw new InvalidOperationException("参数必须是正则。");
    private static int Status(object? value) => value is double code && code == Math.Truncate(code) && code is >= 100 and <= 599 ? (int)code : throw new InvalidOperationException("HTTP 状态码无效。");
    private static void CheckSize(string text) { if (Encoding.UTF8.GetByteCount(text) > 2 * 1024 * 1024) throw new InvalidOperationException("正文超限。"); }
    internal static void ValidateHeader(string name, string value)
    {
        if (!Regex.IsMatch(name, @"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$") || value.Contains('\r') || value.Contains('\n')) throw new InvalidOperationException("HTTP Header 无效。");
    }
    private static byte[] Resource(LoonRewrite rewrite, string path) => rewrite.Resources.TryGetValue(path, out var bytes) ? Convert.FromBase64String(bytes) : throw new InvalidOperationException("资源未缓存。");
    private static string ContentType(string type) => type switch
    {
        "json" => "application/json", "text" or "plain" => "text/plain", "html" => "text/html", "css" => "text/css", "javascript" => "application/javascript", "png" => "image/png", "gif" => "image/gif", "jpeg" => "image/jpeg", "svg" => "image/svg+xml", "mp4" => "video/mp4", _ => throw new InvalidOperationException("未知 Mock 内容类型。")
    };
    internal static string JsonPath(string body, string path, string operation, object? value)
    {
        var root = JsonNode.Parse(body) ?? throw new InvalidOperationException("JSON 根值无效。");
        var parts = Regex.Matches(path, @"(?:^|\.)([a-zA-Z_$][\w$-]*)|\[(\d+)\]");
        if (parts.Count == 0 || string.Concat(parts.Select(p => p.Value)) != path) throw new InvalidOperationException("JSON Key Path 无效。");
        JsonNode current = root;
        for (int i = 0; i < parts.Count; i++)
        {
            var part = parts[i]; bool last = i == parts.Count - 1; JsonNode? replacement = value == null ? null : JsonSerializer.SerializeToNode(value);
            if (part.Groups[1].Success)
            {
                if (current is not JsonObject obj) throw new InvalidOperationException("JSON 路径不是对象。");
                string key = part.Groups[1].Value;
                if (last)
                {
                    if (operation == "delete") obj.Remove(key);
                    else if (operation == "replace" && obj.ContainsKey(key) || operation == "add" && !obj.ContainsKey(key)) obj[key] = replacement;
                }
                else current = obj[key] ?? throw new InvalidOperationException("JSON 路径不存在。");
            }
            else
            {
                int index = int.Parse(part.Groups[2].Value);
                if (current is not JsonArray array || index < 0 || index >= array.Count) throw new InvalidOperationException("JSON 数组索引无效。");
                if (last) { if (operation == "delete") array.RemoveAt(index); else if (operation == "replace") array[index] = replacement; else if (operation == "add") array.Insert(index, replacement); }
                else current = array[index] ?? throw new InvalidOperationException("JSON 路径不存在。");
            }
        }
        return root.ToJsonString();
    }
}
