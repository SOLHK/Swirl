using AdShield.Network;
using System.Text.Json;
using W = System.Windows;
using C = System.Windows.Controls;

namespace AdShield.Desktop;

internal sealed partial class SwirlWindow
{
    private static string PolicyType(string type) => type switch { "select" or "Selector" => "手动选择", "url-test" or "URLTest" => "自动选最快", "fallback" or "Fallback" => "故障转移", "load-balance" or "LoadBalance" => "负载均衡", _ => "自动策略" };
    private static string PolicyExplanation(string type) => type switch { "select" or "Selector" => "由你决定使用哪条线路，切换后会记住你的选择。", "url-test" or "URLTest" => "定期检测，自动使用延迟最低的可用节点。", "fallback" or "Fallback" => "优先使用排在前面的节点，连接失败时自动换下一个。", "load-balance" or "LoadBalance" => "把不同连接分配到多个节点，适合分担流量。", _ => "沿用订阅提供的策略。" };
    private void BuildPolicyWorkspace()
    {
        var page = Page("groups", "策略组", "决定不同用途用哪条线路。节点的具体选择放在“节点”页。");
        Row(page, Button("＋ 新建策略组", () => { OpenPolicyEditor(null); return Task.CompletedTask; }, true), SmallButton("刷新状态", RefreshCatalogAsync), SmallButton("分流规则", () => { SelectPage("routing"); return Task.CompletedTask; }));
        policySearch.ToolTip = "搜索策略组名称"; policySearch.TextChanged += (_, _) => RefreshPolicyCards(); page.Children.Add(policySearch);
        page.Children.Add(policyCards);
    }
    private void RefreshPolicyCards()
    {
        policyCards.Children.Clear();
        var visible = VisibleGroups().Where(g => g.Name.Contains(policySearch.Text.Trim(), StringComparison.OrdinalIgnoreCase)).ToArray();
        Dictionary<string, PolicyGroupSettings> definitions = new(); try { if (profile.ProtectedYaml.Length > 0) definitions = UserProxyGroups.Read(profile); } catch { }
        var edits = profile.GroupSettings.Select(g => g.Name).ToHashSet(StringComparer.Ordinal);
        if (visible.Length == 0) { var empty = Card(policyCards, "还没有可显示的策略组", profile.ProtectedYaml.Length == 0 ? "先添加订阅，服务商的策略组会自动显示在这里。" : "没有匹配的名称，试试其他关键词。"); Row(empty, SmallButton("添加订阅", () => { SelectPage("subscriptions"); return Task.CompletedTask; })); return; }
        foreach (var group in visible)
        {
            var content = new C.StackPanel(); var header = new C.Grid(); header.ColumnDefinitions.Add(new C.ColumnDefinition()); header.ColumnDefinitions.Add(new C.ColumnDefinition { Width = W.GridLength.Auto });
            var labels = new C.StackPanel(); labels.Children.Add(Text(group.Name, 17, true)); var meta = new C.WrapPanel { Margin = new W.Thickness(0, 9, 0, 3) }; meta.Children.Add(Badge(PolicyType(group.Type), true)); meta.Children.Add(Badge(edits.Contains(group.Name) ? "自定义" : group.Name == "GLOBAL" ? "全局线路" : definitions.ContainsKey(group.Name) ? "来自订阅" : "默认线路")); meta.Children.Add(Badge(group.Members.Length + " 个成员")); labels.Children.Add(meta); header.Children.Add(labels);
            var actions = new C.WrapPanel { VerticalAlignment = W.VerticalAlignment.Center };
            var test = SmallButton(controller.Running ? "测速" : "连接后测速", () => TestPolicyAsync(group.Name)); test.IsEnabled = controller.Running && !testingNodes; actions.Children.Add(test);
            if (group.Selectable) actions.Children.Add(SmallButton("选节点", () => BrowsePolicyNodesAsync(group)));
            if (definitions.TryGetValue(group.Name, out var definition)) actions.Children.Add(SmallButton("编辑", () => { OpenPolicyEditor(definition); return Task.CompletedTask; }));
            var expand = SmallButton(expandedPolicies.Contains(group.Name) ? "收起" : "详情", () => { if (!expandedPolicies.Add(group.Name)) expandedPolicies.Remove(group.Name); RefreshPolicyCards(); return Task.CompletedTask; }); actions.Children.Add(expand); C.Grid.SetColumn(actions, 1); header.Children.Add(actions); content.Children.Add(header);
            string resolved = catalog.Resolve(group.Name, selections);
            var route = Text((controller.Running ? "正在使用  " : "连接后使用  ") + (selections.GetValueOrDefault(group.Name) is { } choice && choice != resolved ? choice + "  →  " : "") + resolved, 13); route.Margin = new W.Thickness(0, 7, 0, 0); content.Children.Add(route);
            if (expandedPolicies.Contains(group.Name))
            {
                content.Children.Add(Note(PolicyExplanation(definition?.Type ?? group.Type)));
                var children = group.Members.Where(m => catalog.Groups.ContainsKey(m) || m is "DIRECT" or "REJECT").ToArray();
                if (children.Length > 0)
                {
                    content.Children.Add(Note(group.Selectable ? "使用其他策略或直连" : "此策略包含的子策略")); var choices = new C.WrapPanel();
                    foreach (string member in children) { var pick = SmallButton(member == "DIRECT" ? "直连" : member == "REJECT" ? "拒绝连接" : member, () => ApplySelectionAsync(group.Name, member), selections.GetValueOrDefault(group.Name) == member); pick.IsEnabled = group.Selectable; choices.Children.Add(pick); } content.Children.Add(choices);
                }
                content.Children.Add(Note(group.Members.Count(catalog.Nodes.ContainsKey) + " 个服务器节点 · 可在节点页查看名称与延迟"));
                if (edits.Contains(group.Name)) Row(content, SmallButton("删除自定义 / 恢复订阅设置", () => RemovePolicyEditAsync(group.Name)));
            }
            var card = Surface(content, 18); card.Margin = new W.Thickness(0, 0, 0, 10); policyCards.Children.Add(card);
        }
    }
    private Task BrowsePolicyNodesAsync(ProxyGroup group)
    {
        var seen = new HashSet<string>(); ProxyGroup? Find(ProxyGroup candidate)
        {
            if (!seen.Add(candidate.Name)) return null;
            if (candidate.Selectable && candidate.Members.Any(catalog.Nodes.ContainsKey)) return candidate;
            foreach (string member in candidate.Members) if (catalog.Groups.TryGetValue(member, out var child) && Find(child) is { } found) return found;
            return null;
        }
        var target = Find(group);
        if (target == null) throw new InvalidOperationException("这个策略自动管理节点，或节点仍在加载。可编辑策略成员，连接后再刷新状态。");
        nodeTargetGroup.SelectedItem = target; SelectPage("nodes"); return Task.CompletedTask;
    }
    private async Task TestPolicyAsync(string name)
    {
        if (!controller.Running) throw new InvalidOperationException("先连接网络，才能检测节点实际延迟。");
        if (testingNodes) return; testingNodes = true; status.Text = "正在检测“" + name + "”的成员…"; RefreshPolicyCards();
        try { PolicyGroupSettings? settings = null; try { settings = UserProxyGroups.Read(activeProfile ?? profile).GetValueOrDefault(name); } catch { } var values = await controller.TestGroupAsync(name, settings?.Url ?? "https://www.gstatic.com/generate_204", settings?.Timeout ?? 5000); foreach (var value in values) measuredDelays[value.Key] = value.Value; await LoadGroupsAsync(); status.Text = "测速完成，" + values.Count(v => v.Value > 0) + " / " + values.Count + " 条线路可用。"; }
        finally { testingNodes = false; RefreshPolicyCards(); FillNodes(); }
    }
    private sealed record Choice(string Key, string Label) { public override string ToString() => Label; }
    internal W.Window CreatePolicyEditor(PolicyGroupSettings? initial)
    {
        if (profile.ProtectedYaml.Length == 0) throw new InvalidOperationException("先添加订阅或本地配置，才能选择策略组的成员。");
        bool creating = initial == null;
        var edited = initial == null ? new PolicyGroupSettings { Name = "新策略组", AllNodes = true, AllProviders = MihomoConfig.Parse(profile.Yaml).ContainsKey("proxy-providers") } : JsonSerializer.Deserialize<PolicyGroupSettings>(JsonSerializer.Serialize(initial))!;
        var content = new C.StackPanel(); var name = new C.TextBox { Text = edited.Name, IsReadOnly = !creating };
        content.Children.Add(Note("策略组名称")); content.Children.Add(name);
        var type = new C.ComboBox { ItemsSource = new[] { new Choice("select", "手动选择 · 自己挑选线路"), new Choice("url-test", "自动选最快 · 选延迟最低的节点"), new Choice("fallback", "故障转移 · 按顺序使用可用节点"), new Choice("load-balance", "负载均衡 · 多个节点分担连接") } }; type.SelectedItem = type.Items.Cast<Choice>().FirstOrDefault(c => c.Key == edited.Type) ?? type.Items[0];
        content.Children.Add(Note("如何选线路")); content.Children.Add(type); var explanation = Note(PolicyExplanation(edited.Type)); content.Children.Add(explanation);
        var allNodes = new C.CheckBox { Content = "自动包含这份配置中的所有节点", IsChecked = edited.AllNodes }; var allProviders = new C.CheckBox { Content = "自动包含所有节点提供器（订阅更新后跟随变化）", IsChecked = edited.AllProviders }; content.Children.Add(allNodes); content.Children.Add(allProviders);
        var root = MihomoConfig.Parse(profile.Yaml); var definitions = UserProxyGroups.Read(profile);
        var configuredNodes = root.TryGetValue("proxies", out var raw) && raw is IEnumerable<object> items ? items.OfType<IDictionary<object, object>>().Where(n => n.ContainsKey("name")).Select(n => n["name"].ToString()!).ToArray() : [];
        var candidates = new C.ComboBox { ItemsSource = configuredNodes.Concat(definitions.Keys).Where(n => n != edited.Name).Concat(["DIRECT", "REJECT"]).Distinct().ToArray() }; candidates.SelectedIndex = 0;
        var members = new C.ListBox { Height = 140 }; void FillMembers() { members.ItemsSource = null; members.ItemsSource = edited.Members.ToArray(); } FillMembers();
        var memberContent = new C.StackPanel(); var memberExpander = new C.Expander { Header = "指定成员和优先顺序", IsExpanded = edited.Members.Count > 0 || !edited.AllNodes, Content = memberContent, Margin = new W.Thickness(0, 10, 0, 10) }; content.Children.Add(memberExpander);
        memberContent.Children.Add(Note("可添加节点或子策略组；故障转移按这里的顺序尝试")); memberContent.Children.Add(candidates);
        Row(memberContent, SmallButton("添加成员", () => { if (candidates.SelectedItem is string member && !edited.Members.Contains(member)) { edited.Members.Add(member); FillMembers(); } return Task.CompletedTask; })); memberContent.Children.Add(members);
        Task Move(int direction) { if (members.SelectedItem is not string member) return Task.CompletedTask; int from = edited.Members.IndexOf(member), to = from + direction; if (to >= 0 && to < edited.Members.Count) { edited.Members.RemoveAt(from); edited.Members.Insert(to, member); FillMembers(); members.SelectedItem = member; } return Task.CompletedTask; }
        Row(memberContent, SmallButton("上移", () => Move(-1)), SmallButton("下移", () => Move(1)), SmallButton("移除成员", () => { if (members.SelectedItem is string member) { edited.Members.Remove(member); FillMembers(); } return Task.CompletedTask; }));
        if (root.TryGetValue("proxy-providers", out var providerValue) && providerValue is IDictionary<object, object> providers)
        {
            content.Children.Add(Note("指定节点提供器"));
            foreach (string provider in providers.Keys.Select(p => p.ToString()!)) { var check = new C.CheckBox { Content = provider, IsChecked = edited.Providers.Contains(provider) }; check.Click += (_, _) => { edited.Providers.Remove(provider); if (check.IsChecked == true) edited.Providers.Add(provider); }; content.Children.Add(check); }
        }
        var filter = new C.TextBox { Text = edited.Filter }; content.Children.Add(Note("筛选节点名称（可留空，例如：香港|HK；只用于自动包含或提供器）")); content.Children.Add(filter);
        var automatic = new C.StackPanel(); var url = new C.TextBox { Text = edited.Url }; automatic.Children.Add(Note("检测网址")); automatic.Children.Add(url);
        var interval = new C.TextBox { Text = edited.Interval.ToString() }; var timeout = new C.TextBox { Text = edited.Timeout.ToString() }; var tolerance = new C.TextBox { Text = edited.Tolerance.ToString() };
        automatic.Children.Add(Note("每隔多少秒检测")); automatic.Children.Add(interval); automatic.Children.Add(Note("超过多少毫秒算不可用")); automatic.Children.Add(timeout); var toleranceLabel = Note("延迟至少改善多少毫秒才换节点（避免频繁切换）"); automatic.Children.Add(toleranceLabel); automatic.Children.Add(tolerance);
        var strategy = new C.ComboBox { ItemsSource = new[] { new Choice("consistent-hashing", "同一网站固定节点（类似 Loon PCC）"), new Choice("round-robin", "轮流使用各个节点"), new Choice("sticky-sessions", "同一来源和网站保持节点") } }; strategy.SelectedItem = strategy.Items.Cast<Choice>().FirstOrDefault(c => c.Key == edited.Strategy) ?? strategy.Items[0]; var strategyLabel = Note("如何分配连接"); automatic.Children.Add(strategyLabel); automatic.Children.Add(strategy); content.Children.Add(automatic);
        void ChangeType() { string key = ((Choice)type.SelectedItem).Key; explanation.Text = PolicyExplanation(key); automatic.Visibility = key == "select" ? W.Visibility.Collapsed : W.Visibility.Visible; tolerance.Visibility = toleranceLabel.Visibility = key == "url-test" ? W.Visibility.Visible : W.Visibility.Collapsed; strategy.Visibility = strategyLabel.Visibility = key == "load-balance" ? W.Visibility.Visible : W.Visibility.Collapsed; }
        type.SelectionChanged += (_, _) => ChangeType(); ChangeType();
        var footer = new C.StackPanel { Margin = new W.Thickness(0, 12, 0, 0) };
        var dialog = Sheet(creating ? "新建策略组" : "编辑策略组", "先选用途，再选成员。保存后可在分流规则中使用这个策略组。", content, footer: footer);
        Row(footer, Button("保存策略组", async () => { edited.Name = name.Text; edited.Type = ((Choice)type.SelectedItem).Key; edited.AllNodes = allNodes.IsChecked == true; edited.AllProviders = allProviders.IsChecked == true; edited.Filter = filter.Text.Trim(); edited.Url = url.Text.Trim(); if (edited.Type != "select" && (!int.TryParse(interval.Text, out int _) || !int.TryParse(timeout.Text, out int _) || !int.TryParse(tolerance.Text, out int _))) throw new InvalidOperationException("间隔、超时和容差请填写整数。"); if (int.TryParse(interval.Text, out int seconds)) edited.Interval = seconds; if (int.TryParse(timeout.Text, out int limit)) edited.Timeout = limit; if (int.TryParse(tolerance.Text, out int margin)) edited.Tolerance = margin; edited.Strategy = ((Choice)strategy.SelectedItem).Key; await SavePolicyAsync(edited, creating); dialog.Close(); }, true), SmallButton("取消", () => { dialog.Close(); return Task.CompletedTask; })); return dialog;
    }
    private void OpenPolicyEditor(PolicyGroupSettings? initial) => CreatePolicyEditor(initial).ShowDialog();
    private async Task SavePolicyAsync(PolicyGroupSettings settings, bool creating)
    {
        if (busy) return;
        var candidate = JsonSerializer.Deserialize<ProxyProfile>(JsonSerializer.Serialize(profile))!; UserProxyGroups.Save(candidate, settings, creating);
        bool restart = controller.Running; if (restart) Stop(); busy = true;
        try { await controller.ValidateAsync(candidate); profile.GroupSettings = candidate.GroupSettings; profile.Save(); LoadOfflineCatalog(); SaveRules(false); RefreshPolicyCards(); status.Text = "策略组保存好了，已通过核心检查。"; }
        finally { busy = false; if (restart) await StartAsync(); }
    }
    private async Task RemovePolicyEditAsync(string name)
    {
        if (busy) return; var candidate = JsonSerializer.Deserialize<ProxyProfile>(JsonSerializer.Serialize(profile))!; UserProxyGroups.RemoveEdit(candidate, name);
        bool restart = controller.Running; if (restart) Stop(); busy = true;
        try { await controller.ValidateAsync(candidate); profile.GroupSettings = candidate.GroupSettings; profile.Save(); LoadOfflineCatalog(); SaveRules(false); }
        finally { busy = false; if (restart) await StartAsync(); }
    }
}
