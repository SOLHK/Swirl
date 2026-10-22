using System.Text.Json;

namespace AdShield.Network;

internal sealed record CatalogPlugin(string Name, string Description, string Url)
{
    public override string ToString() => Name;
}

internal static class PluginCatalog
{
    internal static (string Notice, CatalogPlugin[] Entries) Parse(string text)
    {
        using var document = JsonDocument.Parse(text);
        var root = document.RootElement;
        string notice = root.TryGetProperty("notice", out var notices) && notices.ValueKind == JsonValueKind.Array
            ? string.Join("\r\n", notices.EnumerateArray().Select(n => n.GetString()).Take(10)) : "";
        var entries = new List<CatalogPlugin>();
        foreach (var item in root.GetProperty("lists").EnumerateArray().Take(1000))
        {
            try
            {
                string url = LoonPlugin.ResolveImportUrl(item.GetProperty("url").GetString() ?? "");
                string name = item.GetProperty("name").GetString() ?? "";
                if (name.Length == 0 || name.Length > 200) continue;
                string description = item.TryGetProperty("desc", out var desc) ? desc.GetString() ?? "" : "";
                entries.Add(new(name, description.Length > 16000 ? description[..16000] : description, url));
            }
            catch (Exception e) when (e is InvalidOperationException or KeyNotFoundException or ArgumentException) { }
        }
        return (notice, entries.ToArray());
    }

    internal static async Task<string?> ChooseAsync(IWin32Window owner)
    {
        var catalog = Parse(await NetworkFetch.TextAsync("https://hub.kelee.one/list.json", 4 * 1024 * 1024));
        using var dialog = new Form { Text = "可莉插件目录 · 从作者原链接导入", Size = new Size(820, 640), StartPosition = FormStartPosition.CenterParent, MinimizeBox = false, MaximizeBox = false };
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 5, ColumnCount = 1, Padding = new Padding(12) };
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 75)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 145)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
        var note = new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Text = catalog.Notice };
        var search = new TextBox { Dock = DockStyle.Fill, PlaceholderText = "搜索插件名称，例如：腾讯、爱奇艺" };
        var list = new ListBox { Dock = DockStyle.Fill };
        var detail = new TextBox { Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical };
        var choose = new Button { Text = "导入选中插件", Dock = DockStyle.Right, Width = 160, Enabled = false };
        string? selected = null;
        search.TextChanged += (_, _) =>
        {
            list.Items.Clear(); list.Items.AddRange(catalog.Entries.Where(e => e.Name.Contains(search.Text.Trim(), StringComparison.OrdinalIgnoreCase)).Cast<object>().ToArray());
            detail.Clear(); choose.Enabled = false;
        };
        list.SelectedIndexChanged += (_, _) =>
        {
            choose.Enabled = list.SelectedItem is CatalogPlugin;
            detail.Text = list.SelectedItem is CatalogPlugin entry ? entry.Description.Replace("\\n", "\r\n") + "\r\n\r\n" + entry.Url + "\r\n\r\n导入后会检查兼容性，默认停用。移动端插件需核对 Windows 接口。" : "";
        };
        choose.Click += (_, _) => { if (list.SelectedItem is CatalogPlugin entry) { selected = entry.Url; dialog.DialogResult = DialogResult.OK; } };
        layout.Controls.Add(note, 0, 0); layout.Controls.Add(search, 0, 1); layout.Controls.Add(list, 0, 2); layout.Controls.Add(detail, 0, 3); layout.Controls.Add(choose, 0, 4);
        dialog.Controls.Add(layout); list.Items.AddRange(catalog.Entries.Cast<object>().ToArray());
        return dialog.ShowDialog(owner) == DialogResult.OK ? selected : null;
    }
}
