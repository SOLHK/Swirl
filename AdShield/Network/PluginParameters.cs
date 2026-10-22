using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed class PluginParameter
{
    public string Name { get; set; } = "";
    public string Kind { get; set; } = "";
    public bool Numeric { get; set; }
    public string Title { get; set; } = "";
    public string Description { get; set; } = "";
    public JsonElement? Default { get; set; }
    public List<JsonElement> Choices { get; set; } = new();
    internal static PluginParameter Parse(string line)
    {
        var pair = line.Split('=', 2, StringSplitOptions.TrimEntries);
        if (pair.Length != 2 || !Regex.IsMatch(pair[0], @"^[a-zA-Z_]\w*$") || pair[0] is "url" or "request" or "response") throw new InvalidOperationException("Argument 参数名无效。");
        var fields = Split(pair[1]);
        if (fields.Count == 0 || fields[0] is not ("input" or "select" or "switch")) throw new InvalidOperationException("Argument 控件类型无效。");
        var parameter = new PluginParameter { Name = pair[0], Kind = fields[0], Title = pair[0] };
        var values = new List<string>();
        foreach (string field in fields.Skip(1))
        {
            var option = Regex.Match(field, @"^(tag|desc|type)\s*=\s*(.*)$");
            if (!option.Success) { values.Add(field); continue; }
            string value = Text(option.Groups[2].Value);
            switch (option.Groups[1].Value)
            {
                case "tag": parameter.Title = value; break;
                case "desc": parameter.Description = value; break;
                case "type": if (value != "number") throw new InvalidOperationException("Argument 仅支持 number 类型选项。"); parameter.Numeric = true; break;
            }
        }
        if (values.Count > 100 || parameter.Kind == "input" && values.Count > 1) throw new InvalidOperationException("Argument 值数量无效。");
        if (parameter.Kind == "switch")
        {
            if (values.Count > 2 || parameter.Numeric || values.Any(v => v is not ("true" or "false"))) throw new InvalidOperationException("switch 必须为 Boolean。");
            parameter.Default = JsonSerializer.SerializeToElement(values.FirstOrDefault() == "true");
        }
        else
        {
            foreach (string value in values)
            {
                string text = Text(value);
                JsonElement json = parameter.Numeric
                    ? double.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out double number) && double.IsFinite(number) ? JsonSerializer.SerializeToElement(number) : throw new InvalidOperationException("Argument 数字无效。")
                    : JsonSerializer.SerializeToElement(text);
                parameter.Choices.Add(json);
            }
            parameter.Default = parameter.Choices.FirstOrDefault();
            if (parameter.Choices.Count == 0) parameter.Default = null;
        }
        return parameter;
    }
    internal static List<string> Split(string text)
    {
        var result = new List<string>(); var value = new StringBuilder(); char quote = '\0'; int brackets = 0;
        for (int i = 0; i < text.Length; i++)
        {
            char c = text[i];
            if (quote != '\0')
            {
                value.Append(c);
                if (c == '\\' && quote != '`' && i + 1 < text.Length) { value.Append(text[++i]); continue; }
                if (c == quote) quote = '\0'; continue;
            }
            if (c is '"' or '\'' or '`') { quote = c; value.Append(c); continue; }
            if (c is '[' or '{' or '(') brackets++; if (c is ']' or '}' or ')') brackets--;
            if (c == ',' && brackets == 0) { result.Add(value.ToString().Trim()); value.Clear(); } else value.Append(c);
        }
        if (quote != '\0' || brackets != 0) throw new InvalidOperationException("参数括号或引号未闭合。");
        result.Add(value.ToString().Trim()); return result;
    }
    internal static string Text(string text) => text.Length >= 2 && text[0] == '`' && text[^1] == '`' ? text[1..^1].Replace("``", "`") : LoonPlugin.Unquote(text);
    internal object? Read(JsonElement? value) => value?.ValueKind switch { JsonValueKind.String => value.Value.GetString(), JsonValueKind.Number => value.Value.GetDouble(), JsonValueKind.True => true, JsonValueKind.False => false, _ => null };
    internal JsonElement Validate(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Null) return value;
        if (Kind == "switch" ? value.ValueKind is not (JsonValueKind.True or JsonValueKind.False) : Numeric ? value.ValueKind != JsonValueKind.Number || !double.IsFinite(value.GetDouble()) : value.ValueKind != JsonValueKind.String)
            throw new InvalidOperationException("参数值类型无效：" + Title);
        if (Kind == "select" && !Choices.Any(c => Equals(Read(c), Read(value)))) throw new InvalidOperationException("请选择声明的参数选项：" + Title);
        return value;
    }
}

internal static class PluginParameterEditor
{
    internal static bool Edit(IWin32Window owner, LoonPlugin plugin)
    {
        if (plugin.Parameters.Count == 0) throw new InvalidOperationException("此插件没有 Argument 参数控件。");
        var values = plugin.EffectiveParameters();
        using var dialog = new Form { Text = "插件参数 · " + plugin.Name, Size = new Size(720, 560), StartPosition = FormStartPosition.CenterParent };
        var list = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(12) };
        var editors = new List<(PluginParameter Parameter, Control Editor)>();
        foreach (var parameter in plugin.Parameters)
        {
            list.Controls.Add(new Label { Text = parameter.Title, AutoSize = true }); values.TryGetValue(parameter.Name, out var value);
            Control editor;
            if (parameter.Kind == "switch") editor = new CheckBox { Text = parameter.Description, AutoSize = true, Checked = value is true };
            else if (parameter.Kind == "select")
            {
                var select = new ComboBox { Width = 620, DropDownStyle = ComboBoxStyle.DropDownList };
                foreach (var choice in parameter.Choices) select.Items.Add(PluginParameter.Text(choice.ToString()));
                select.SelectedIndex = parameter.Choices.FindIndex(c => Equals(parameter.Read(c), value)); editor = select;
            }
            else editor = new TextBox { Width = 620, Text = value == null ? "" : SyntaxValue.Format(value) };
            list.Controls.Add(editor); editors.Add((parameter, editor));
            if (parameter.Kind != "switch" && parameter.Description.Length > 0) list.Controls.Add(new Label { Text = parameter.Description, AutoSize = true, MaximumSize = new Size(620, 0) });
        }
        var save = new Button { Text = "保存参数", Width = 150, Height = 36 };
        save.Click += (_, _) =>
        {
            try
            {
                var chosen = new Dictionary<string, JsonElement>();
                foreach (var (parameter, editor) in editors)
                {
                    JsonElement value = editor is CheckBox check ? JsonSerializer.SerializeToElement(check.Checked) : editor is ComboBox select ? select.SelectedIndex >= 0 ? parameter.Choices[select.SelectedIndex] : JsonSerializer.SerializeToElement<object?>(null)
                        : editor.Text.Length == 0 ? JsonSerializer.SerializeToElement<object?>(null) : parameter.Numeric ? JsonSerializer.SerializeToElement(double.Parse(editor.Text, CultureInfo.InvariantCulture)) : JsonSerializer.SerializeToElement(editor.Text);
                    chosen[parameter.Name] = parameter.Validate(value);
                }
                plugin.ProtectedParameterValues = ProxyProfile.Protect(JsonSerializer.Serialize(chosen)); dialog.DialogResult = DialogResult.OK;
            }
            catch (Exception e) { MessageBox.Show(dialog, e.Message, "参数未保存"); }
        };
        list.Controls.Add(save); dialog.Controls.Add(list); return dialog.ShowDialog(owner) == DialogResult.OK;
    }
}
