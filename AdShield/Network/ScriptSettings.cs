using System.Globalization;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed record ScriptSettings(bool Enabled, bool NeedsBody, double Timeout, object? Argument, string Tag, string Cron, bool BinaryBody)
{
    internal static ScriptSettings For(LoonPlugin plugin, LoonScript script, SyntaxContext? context = null)
    {
        context ??= new();
        foreach (var parameter in plugin.EffectiveParameters()) context.Parameters[parameter.Key] = parameter.Value;
        bool enabled = true, body = script.NeedsBody, binary = script.BinaryBody; double timeout = script.Timeout; object? argument = null; string tag = script.Tag, cron = script.Cron;
        if (script.Syntax.Length > 0)
        {
            var program = LoonSyntax.Parse(script.Syntax, true);
            object? Option(string key, object? fallback) => program.Options.TryGetValue(key, out var value) ? value.Resolve(context) ?? fallback : fallback;
            enabled = Option("enable", true) is bool flag ? flag : throw new InvalidOperationException("Script enable 必须是 Boolean。");
            body = Option("requires_body", false) is bool need ? need : throw new InvalidOperationException("requires_body 必须是 Boolean。");
            binary = Option("binary_body_mode", false) is bool binaryFlag ? binaryFlag : throw new InvalidOperationException("binary_body_mode 必须是 Boolean。");
            timeout = Number(Option("timeout", program.Phase.StartsWith("http-") ? 20d : 300d));
            tag = Option("tag", DefaultTag(script)) as string ?? throw new InvalidOperationException("Script tag 必须是字符串。");
            argument = program.Calls[0].Arguments.Length > 1 ? program.Calls[0].Arguments[1].Resolve(context) : null;
            cron = program.Cron?.Resolve(context) as string ?? "";
        }
        else
        {
            object? Legacy(string expression) => Regex.Match(expression, @"^\{(\w+)\}$") is { Success: true } match ? context.Variable(match.Groups[1].Value) : expression;
            object? flag = Legacy(script.EnableExpression);
            enabled = flag is bool b ? b : flag is string s && bool.TryParse(s, out bool parsed) ? parsed : throw new InvalidOperationException("Script enable 参数无效。");
            if (script.TimeoutExpression.Length > 0) timeout = Number(Legacy(script.TimeoutExpression));
            if (script.Phase == "cron") cron = Legacy(cron) as string ?? throw new InvalidOperationException("Cron 参数必须是字符串。");
            if (Regex.IsMatch(script.Argument, @"^\[\s*\{\w+\}(?:\s*,\s*\{\w+\})*\s*\]$"))
            {
                var names = Regex.Matches(script.Argument, @"\{(\w+)\}").Select(m => m.Groups[1].Value).ToArray();
                if (names.Distinct().Count() != names.Length) throw new InvalidOperationException("重复脚本对象参数。");
                argument = names.ToDictionary(n => n, n => context.Variable(n));
            }
            else argument = script.Argument;
        }
        if (plugin.Argument.Length > 0) argument = plugin.Argument;
        if (timeout <= 0 || timeout > 300 || !double.IsFinite(timeout)) throw new InvalidOperationException("脚本超时范围为 0～300 秒。");
        return new(enabled, body, timeout, argument, tag.Length == 0 ? DefaultTag(script) : tag, cron, binary);
    }
    private static string DefaultTag(LoonScript script) => Uri.TryCreate(script.Url, UriKind.Absolute, out var uri) ? Path.GetFileName(uri.AbsolutePath) : "脚本";
    private static double Number(object? value) => value is double n ? n : value is string text && double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out double number) ? number : throw new InvalidOperationException("Script timeout 必须是数字。");
    internal static void Validate(LoonPlugin plugin, LoonScript script)
    {
        SyntaxContext? validationContext = null;
        if (script.Syntax.Length > 0)
        {
            var program = LoonSyntax.Parse(script.Syntax, true); LoonSyntax.Validate(program, plugin, true);
            foreach (var name in new[] { "requires_body", "binary_body_mode", "tag", "img_url" })
                if (program.Options.TryGetValue(name, out var option) && option.Variables.Any()) throw new InvalidOperationException(name + " 不接受动态变量。");
            // Runtime URL/header/status templates have no live message during
            // import. Validate their grammar and types with placeholders;
            // resolve their actual values for each execution below.
            validationContext = new SyntaxContext { Request = new("https://validation.test/", "GET", new(), ""), Response = new("", "GET", new(), "", 200) };
            var variables = program.Calls.SelectMany(c => c.Arguments.SelectMany(a => a.Variables)).Concat(program.Options.Values.SelectMany(v => v.Variables));
            foreach (string variable in variables)
            {
                var header = Regex.Match(variable, @"^(request|response)\.header\['([^']+)'\]$");
                if (header.Success)
                    (header.Groups[1].Value == "request" ? validationContext.Request.Headers : validationContext.Response!.Headers)[header.Groups[2].Value] = "1";
            }
        }
        var settings = For(plugin, script, validationContext);
        if (script.Phase == "cron") _ = new PluginCron(settings.Cron);
    }
    internal static bool Matches(LoonPlugin plugin, LoonScript script, SyntaxContext context)
    {
        var settings = For(plugin, script, context);
        if (!settings.Enabled) return false;
        return script.Syntax.Length > 0 ? LoonSyntax.Parse(script.Syntax, true).Matches(context) : LoonPlugin.Matches(script.Pattern, context.Request.Url);
    }
}
