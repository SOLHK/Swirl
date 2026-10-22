using System.Collections.Concurrent;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed record SyntaxRegex(string Pattern, string Flags)
{
    internal Regex Compile() => new(Pattern.Replace(@"\/", "/"),
        (Flags.Contains('i') ? RegexOptions.IgnoreCase : 0) | (Flags.Contains('m') ? RegexOptions.Multiline : 0) | (Flags.Contains('s') ? RegexOptions.Singleline : 0), TimeSpan.FromMilliseconds(100));
}
internal sealed class SyntaxContext
{
    internal ScriptMessage Request { get; set; } = new("", "GET", new(), "");
    internal ScriptMessage? Response { get; set; }
    internal Dictionary<string, object?> Parameters { get; init; } = new();
    internal Dictionary<string, Match> Captures { get; } = new();
    internal object? Variable(string name)
    {
        if (name == "url") return Request.Url;
        if (name == "request.method") return Request.Method;
        if (name == "response.status") return Response == null ? null : (double)Response.Status;
        var header = Regex.Match(name, @"^(request|response)\.header\['([^']+)'\]$");
        if (header.Success)
        {
            var headers = header.Groups[1].Value == "request" ? Request.Headers : Response?.Headers;
            return headers?.FirstOrDefault(h => h.Key.Equals(header.Groups[2].Value, StringComparison.OrdinalIgnoreCase)).Value;
        }
        var capture = Regex.Match(name, @"^([a-zA-Z_]\w*)\.(\d+)$");
        if (capture.Success && Captures.TryGetValue(capture.Groups[1].Value, out var match))
        {
            int index = int.Parse(capture.Groups[2].Value);
            if (index < match.Groups.Count && match.Groups[index].Success) return match.Groups[index].Value;
            throw new InvalidOperationException("条件捕获缺值。");
        }
        if (Parameters.TryGetValue(name, out var value)) return value;
        throw new InvalidOperationException("参数未声明或没有值。");
    }
}
internal sealed record SyntaxValue(string Kind, object? Literal, string Name = "", SyntaxValue[]? Items = null)
{
    internal object? Resolve(SyntaxContext context) => Kind switch
    {
        "variable" => context.Variable(Name),
        "array" => Items!.Select(item => item.Resolve(context)).ToArray(),
        "object" => Items!.ToDictionary(item => item.Name, item => item.Resolve(context)),
        "template" => Regex.Replace((string)Literal!, @"\$\{([^}]+)\}", m => Format(context.Variable(m.Groups[1].Value))).Replace("\uE000", "${"),
        _ => Literal
    };
    internal IEnumerable<string> Variables => Kind is "variable" ? new[] { Name } : Kind is "template"
        ? Regex.Matches((string)Literal!, @"\$\{([^}]+)\}").Select(m => m.Groups[1].Value)
        : Items?.SelectMany(item => item.Variables) ?? Array.Empty<string>();
    internal static string Format(object? value) => value switch { null => throw new InvalidOperationException("模板参数缺值。"), bool b => b ? "true" : "false", double n => n.ToString(CultureInfo.InvariantCulture), string s => s, _ => throw new InvalidOperationException("模板类型无效。") };
}
internal sealed class SyntaxCondition
{
    internal string Op { get; init; } = "";
    internal SyntaxCondition? Left { get; init; }
    internal SyntaxCondition? Right { get; init; }
    internal SyntaxValue? A { get; init; }
    internal SyntaxValue? B { get; init; }
    internal string Alias { get; init; } = "";
    internal bool Evaluate(SyntaxContext context)
    {
        if (Op == "&&") return Left!.Evaluate(context) && Right!.Evaluate(context);
        if (Op == "||") return Left!.Evaluate(context) || Right!.Evaluate(context);
        object? a = A!.Resolve(context), b = B!.Resolve(context);
        if (Op == "==") return Equals(a, b);
        if (a is not string input) return false;
        var regex = b is SyntaxRegex literal ? literal.Compile() : b is string pattern ? new Regex(pattern, RegexOptions.None, TimeSpan.FromMilliseconds(100)) : throw new InvalidOperationException("正则条件类型无效。");
        var match = regex.Match(input);
        if (match.Success && Alias.Length > 0) context.Captures[Alias] = match;
        return match.Success;
    }
    internal bool UrlGuard => Op == "&&" ? Left!.UrlGuard || Right!.UrlGuard : Op == "||" ? Left!.UrlGuard && Right!.UrlGuard : A?.Name == "url" && Op is "==" or "~=";
    internal HashSet<string> MandatoryAliases => Op is "&&" or "||" ? Combine(Left!.MandatoryAliases, Right!.MandatoryAliases, Op == "&&") : Alias.Length > 0 ? new() { Alias } : new();
    private static HashSet<string> Combine(HashSet<string> a, HashSet<string> b, bool union) { if (union) a.UnionWith(b); else a.IntersectWith(b); return a; }
    internal IEnumerable<string> Variables => Op is "&&" or "||" ? Left!.Variables.Concat(Right!.Variables) : A!.Variables.Concat(B!.Variables);
    internal IEnumerable<SyntaxCondition> UrlPatterns => Op is "&&" or "||" ? Left!.UrlPatterns.Concat(Right!.UrlPatterns) : A?.Name == "url" && Op == "~=" ? new[] { this } : Array.Empty<SyntaxCondition>();
}
internal sealed record SyntaxCall(string Name, SyntaxValue[] Arguments);
internal sealed record SyntaxProgram(string Phase, SyntaxCondition? Condition, SyntaxCall[] Calls, Dictionary<string, SyntaxValue> Options, SyntaxValue? Cron = null)
{
    internal bool Matches(SyntaxContext context) => Condition == null || Condition.Evaluate(context);
}

internal static class LoonSyntax
{
    private static readonly ConcurrentDictionary<string, SyntaxProgram> Cache = new();
    internal static SyntaxProgram Parse(string source, bool script)
    {
        if (Cache.Count > 4096) Cache.Clear();
        return Cache.GetOrAdd((script ? "S:" : "R:") + source, _ => new Parser(source).Program(script));
    }
    internal static void Validate(SyntaxProgram program, LoonPlugin plugin, bool script)
    {
        var variables = (program.Condition?.Variables ?? Array.Empty<string>()).Concat(program.Calls.SelectMany(c => c.Arguments.SelectMany(a => a.Variables))).Concat(program.Options.Values.SelectMany(v => v.Variables)).Concat(program.Cron?.Variables ?? Array.Empty<string>());
        var aliases = program.Condition?.MandatoryAliases ?? new();
        foreach (var variable in variables)
        {
            if (variable is "url" or "request.method" || Regex.IsMatch(variable, @"^request\.header\['[^']+'\]$")) continue;
            if (variable == "response.status" || Regex.IsMatch(variable, @"^response\.header\['[^']+'\]$"))
            {
                if (program.Phase != "http-response") throw new InvalidOperationException("请求条件不能使用响应变量。");
                continue;
            }
            var capture = Regex.Match(variable, @"^(\w+)\.\d+$");
            if (!script && capture.Success && aliases.Contains(capture.Groups[1].Value)) continue;
            if (!plugin.Parameters.Any(p => p.Name == variable)) throw new InvalidOperationException("未声明参数或非必选捕获：" + variable);
        }
        if (script)
        {
            if (program.Phase == "http-response" && program.Condition?.UrlGuard != true) throw new InvalidOperationException("响应脚本需要每个成功分支都有 URL 条件。");
            if (program.Condition?.MandatoryAliases.Count > 0) throw new InvalidOperationException("Script 条件不支持 as 捕获。");
            foreach (var option in program.Options)
                if (!new[] { "enable", "tag", "img_url", "timeout", "debug", "requires_body", "binary_body_mode" }.Contains(option.Key)) throw new InvalidOperationException("未知 Script 选项：" + option.Key);
            if (program.Phase is not ("http-request" or "http-response") && program.Options.Keys.Any(k => k is "requires_body" or "binary_body_mode")) throw new InvalidOperationException("非 HTTP 脚本不能设置正文选项。");
            return;
        }
        bool mock = program.Calls.Any(c => c.Name is "response.body.mock" or "response.body.mock_file");
        if (mock && (program.Calls.Count(c => c.Name.StartsWith("response.body.mock")) != 1 || program.Calls.Any(c => !c.Name.StartsWith("response.header.") && !c.Name.StartsWith("response.body.mock")) || variables.Any(v => v.StartsWith("response."))))
            throw new InvalidOperationException("响应 Mock 只能组合响应头，条件不能依赖尚未生成的响应。");
        foreach (var call in program.Calls)
        {
            var schema = Schemas.GetValueOrDefault(call.Name) ?? throw new InvalidOperationException("未知 Rewrite action：" + call.Name);
            if (call.Arguments.Length < schema.Min || call.Arguments.Length > schema.Max) throw new InvalidOperationException("Rewrite 参数数量无效：" + call.Name);
            if (call.Name.StartsWith("request.") && program.Phase != "http-request" || call.Name.StartsWith("response.") && program.Phase != "http-response") throw new InvalidOperationException("Rewrite 阶段不一致。");
            if (call.Name is "url.replace" or "redirect")
            {
                if (program.Phase != "http-request" || program.Condition?.UrlGuard != true || program.Condition.UrlPatterns.Count() != 1 || HasOptionalUrl(program.Condition)) throw new InvalidOperationException("URL 替换需要唯一必选 URL 正则。");
            }
            for (int i = 0; i < call.Arguments.Length; i++)
            {
                var value = call.Arguments[i];
                if (value.Kind == "array" && !schema.Batch) throw new InvalidOperationException("此 Action 不支持批量数组。");
                if (value.Kind == "array" && (value.Items!.Length == 0 || value.Items.Any(v => v.Kind is "array" or "object"))) throw new InvalidOperationException("批量参数无效。");
                foreach (var item in value.Kind == "array" ? value.Items! : new[] { value })
                {
                    char type = schema.Types[Math.Min(i, schema.Types.Length - 1)];
                    if (item.Kind == "variable") continue;
                    bool valid = type switch { 's' => item.Literal is string, 'n' => item.Literal is double, 'b' => item.Literal is bool, 'r' => item.Literal is SyntaxRegex, 'a' => item.Literal is not SyntaxRegex, _ => false };
                    if (!valid) throw new InvalidOperationException("Rewrite 参数类型无效：" + call.Name);
                }
            }
            if (call.Arguments.Any(a => a.Kind == "array") && (call.Arguments.Any(a => a.Kind != "array") || call.Arguments.Select(a => a.Items!.Length).Distinct().Count() != 1)) throw new InvalidOperationException("批量参数必须同长且全部为数组。");
        }
    }
    private static bool HasOptionalUrl(SyntaxCondition node) => node.Op == "||" && node.UrlPatterns.Any() || node.Left != null && HasOptionalUrl(node.Left) || node.Right != null && HasOptionalUrl(node.Right);
    private sealed record Schema(int Min, int Max, string Types, bool Batch = false);
    private static readonly Dictionary<string, Schema> Schemas = new()
    {
        ["url.replace"] = new(1, 1, "s"), ["redirect"] = new(2, 2, "ns"), ["reject"] = new(1, 2, "ns"),
        ["reject_dict"] = new(1, 1, "n"), ["reject_array"] = new(1, 1, "n"), ["reject_img"] = new(1, 1, "n"),
        ["request.header.add"] = new(2, 2, "ss", true), ["request.header.set"] = new(2, 2, "ss", true), ["request.header.del"] = new(1, 1, "s", true), ["request.header.replace"] = new(3, 3, "srs", true),
        ["response.header.add"] = new(2, 2, "ss", true), ["response.header.set"] = new(2, 2, "ss", true), ["response.header.del"] = new(1, 1, "s", true), ["response.header.replace"] = new(3, 3, "srs", true),
        ["request.body.replace"] = new(2, 2, "rs", true), ["response.body.replace"] = new(2, 2, "rs", true),
        ["request.json.add"] = new(2, 2, "sa", true), ["request.json.replace"] = new(2, 2, "sa", true), ["request.json.delete"] = new(1, 1, "s", true), ["request.json.jq"] = new(1, 1, "s"), ["request.json.jq_file"] = new(1, 1, "s"),
        ["response.json.add"] = new(2, 2, "sa", true), ["response.json.replace"] = new(2, 2, "sa", true), ["response.json.delete"] = new(1, 1, "s", true), ["response.json.jq"] = new(1, 1, "s"), ["response.json.jq_file"] = new(1, 1, "s"),
        ["request.body.mock"] = new(2, 3, "ssb"), ["request.body.mock_file"] = new(2, 3, "ssb"), ["response.body.mock"] = new(2, 4, "ssnb"), ["response.body.mock_file"] = new(2, 4, "ssnb")
    };
    private sealed record Token(string Kind, string Text, object? Value = null);
    private sealed class Parser
    {
        private readonly List<Token> tokens = new();
        private int index, depth, comparisons;
        internal Parser(string source)
        {
            if (source.Length > 128 * 1024) throw new InvalidOperationException("单行语法超限。");
            int i = 0;
            while (i < source.Length)
            {
                char c = source[i];
                if (char.IsWhiteSpace(c)) { i++; continue; }
                if (c == '$' && i + 1 < source.Length && source[i + 1] == '{')
                {
                    int end = source.IndexOf('}', i + 2); if (end < 0) throw new InvalidOperationException("变量未闭合。");
                    tokens.Add(new("variable", source[(i + 2)..end])); i = end + 1;
                }
                else if (c is '"' or '`')
                {
                    char quote = c; i++; var value = new StringBuilder(); bool closed = false;
                    while (i < source.Length)
                    {
                        c = source[i++];
                        if (c == quote) { if (quote == '`' && i < source.Length && source[i] == '`') { value.Append('`'); i++; continue; } closed = true; break; }
                        if (quote == '"' && c == '\\')
                        {
                            if (i >= source.Length) break; c = source[i++];
                            if (c == '$' && i < source.Length && source[i] == '{') { value.Append('\uE000'); i++; continue; }
                            if (c == 'u')
                            {
                                if (i + 4 > source.Length || !ushort.TryParse(source.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out ushort unicode)) throw new InvalidOperationException("Unicode 转义无效。");
                                value.Append((char)unicode); i += 4; continue;
                            }
                            value.Append(c switch { 'n' => '\n', 'r' => '\r', 't' => '\t', '"' => '"', '\\' => '\\', '/' => '/', _ => throw new InvalidOperationException("未知字符串转义。") });
                        }
                        else value.Append(c);
                    }
                    if (!closed) throw new InvalidOperationException("字符串未闭合。");
                    tokens.Add(new(quote == '`' ? "raw" : "string", value.ToString(), value.ToString()));
                }
                else if (c == '/')
                {
                    i++; var pattern = new StringBuilder(); bool closed = false, bracket = false;
                    while (i < source.Length)
                    {
                        c = source[i++];
                        if (c == '\\' && i < source.Length) { pattern.Append(c).Append(source[i++]); continue; }
                        if (c == '[') bracket = true; if (c == ']') bracket = false;
                        if (c == '/' && !bracket) { closed = true; break; } pattern.Append(c);
                    }
                    if (!closed) throw new InvalidOperationException("正则未闭合。");
                    int flagStart = i; while (i < source.Length && char.IsLetter(source[i])) i++;
                    string flags = source[flagStart..i]; if (flags.Any(f => !"ims".Contains(f)) || flags.Distinct().Count() != flags.Length) throw new InvalidOperationException("正则 flags 无效。");
                    var regex = new SyntaxRegex(pattern.ToString(), flags); regex.Compile(); tokens.Add(new("regex", "", regex));
                }
                else if (i + 1 < source.Length && new[] { "&&", "||", "==", "~=" }.Contains(source.Substring(i, 2))) { tokens.Add(new("symbol", source.Substring(i, 2))); i += 2; }
                else if (char.IsLetter(c) || c == '_')
                {
                    int start = i++; while (i < source.Length && (char.IsLetterOrDigit(source[i]) || source[i] is '_' or '-' or '.')) i++;
                    tokens.Add(new("identifier", source[start..i]));
                }
                else if (char.IsDigit(c) || c == '-' && i + 1 < source.Length && char.IsDigit(source[i + 1]))
                {
                    int start = i++; while (i < source.Length && (char.IsDigit(source[i]) || source[i] is '.' or 'e' or 'E' or '+' or '-')) i++;
                    if (!double.TryParse(source[start..i], NumberStyles.Float, CultureInfo.InvariantCulture, out double number) || !double.IsFinite(number)) throw new InvalidOperationException("数字无效。");
                    tokens.Add(new("number", source[start..i], number));
                }
                else if ("(),|=[]{}".Contains(c)) { tokens.Add(new("symbol", c.ToString())); i++; }
                else throw new InvalidOperationException("未知语法字符。");
                if (tokens.Count > 20000) throw new InvalidOperationException("语法 token 超限。");
            }
        }
        private Token Peek => index < tokens.Count ? tokens[index] : new("end", "");
        private Token Take() => index < tokens.Count ? tokens[index++] : throw new InvalidOperationException("语法意外结束。");
        private bool Eat(string text) { if (Peek.Text != text) return false; index++; return true; }
        private void Require(string text) { if (!Eat(text)) throw new InvalidOperationException("语法需要：" + text); }
        private void Enter() { if (++depth > 32) throw new InvalidOperationException("语法嵌套过深。"); }
        internal SyntaxProgram Program(bool script)
        {
            string phase = Take().Text; SyntaxCondition? condition = null; SyntaxValue? cron = null;
            if (phase is "request" or "response") { Require("if"); condition = Or(); phase = "http-" + phase; }
            else if (script && phase == "cron") cron = Value();
            else if (!script || phase is not ("generic" or "network-changed")) throw new InvalidOperationException("未知触发阶段。");
            Require("then"); var calls = new List<SyntaxCall>(); do { calls.Add(Call()); if (calls.Count > 64) throw new InvalidOperationException("Action 过多。"); } while (!script && Eat("|"));
            var options = new Dictionary<string, SyntaxValue>();
            if (script && Eat("with")) do { string name = Take().Text; Require("="); if (!options.TryAdd(name, Value())) throw new InvalidOperationException("重复 Script 选项。"); } while (Eat(","));
            if (Peek.Kind != "end") throw new InvalidOperationException("存在未解析的语法。");
            if (script && (calls.Count != 1 || calls[0].Name != "script" || calls[0].Arguments.Length is < 1 or > 2 || calls[0].Arguments[0].Kind is not ("template" or "raw") || calls[0].Arguments[0].Variables.Any())) throw new InvalidOperationException("Script 必须指定固定路径及可选参数。");
            return new(phase, condition, calls.ToArray(), options, cron);
        }
        private SyntaxCall Call()
        {
            string name = Take().Text; Require("("); var values = new List<SyntaxValue>();
            if (!Eat(")")) { do { values.Add(Value()); } while (Eat(",")); Require(")"); }
            return new(name, values.ToArray());
        }
        private SyntaxCondition Or() { var left = And(); while (Eat("||")) left = new() { Op = "||", Left = left, Right = And() }; return left; }
        private SyntaxCondition And() { var left = Compare(); while (Eat("&&")) left = new() { Op = "&&", Left = left, Right = Compare() }; return left; }
        private SyntaxCondition Compare()
        {
            Enter();
            try
            {
                if (Eat("(")) { var value = Or(); Require(")"); return value; }
                if (++comparisons > 128) throw new InvalidOperationException("条件比较过多。");
                var a = Value(); string op = Take().Text; if (op is not ("==" or "~=")) throw new InvalidOperationException("条件仅支持 == 和 ~=。");
                var b = Value(); string alias = "";
                if (Eat("as")) { alias = Take().Text; if (!Regex.IsMatch(alias, @"^[a-zA-Z_]\w*$") || op != "~=") throw new InvalidOperationException("捕获名无效。"); }
                return new() { Op = op, A = a, B = b, Alias = alias };
            }
            finally { depth--; }
        }
        private SyntaxValue Value()
        {
            Enter();
            try
            {
                var token = Take();
                if (token.Text is "[" or "{")
                {
                    bool obj = token.Text == "{"; string end = obj ? "}" : "]"; var values = new List<SyntaxValue>();
                    if (!Eat(end)) { do { var value = Value(); if (obj && value.Kind != "variable") throw new InvalidOperationException("插件对象只能包含声明的参数。"); values.Add(value); } while (Eat(",")); Require(end); }
                    if (obj && (values.Count == 0 || values.Select(v => v.Name).Distinct().Count() != values.Count)) throw new InvalidOperationException("插件对象参数无效。");
                    return new(obj ? "object" : "array", null, Items: values.ToArray());
                }
                return token.Kind switch
                {
                    "string" => new("template", token.Value), "raw" or "number" or "regex" => new(token.Kind, token.Value), "variable" => new("variable", null, token.Text),
                    "identifier" when token.Text is "true" or "false" => new("boolean", token.Text == "true"), "identifier" when token.Text == "null" => new("null", null),
                    _ => throw new InvalidOperationException("值类型无效。")
                };
            }
            finally { depth--; }
        }
    }
}
