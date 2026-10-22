using AdShield.Network;
using System.Globalization;
using System.Windows.Data;
using System.Windows.Shell;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;

namespace AdShield.Desktop;

internal sealed partial class SwirlWindow
{
    private readonly C.WrapPanel subscriptionCards = new();
    private readonly C.StackPanel policyCards = new();
    private readonly C.TextBox subscriptionName = new(), policySearch = new();
    private readonly C.ComboBox nodeSort = new();
    private readonly C.TextBlock librarySummary = new(), nodesSummary = new();
    private readonly Dictionary<string, int> measuredDelays = new(StringComparer.Ordinal);
    private readonly HashSet<string> expandedPolicies = new(StringComparer.Ordinal);
    private bool testingNodes;
    private C.Button applySubscriptionChanges = null!;
    private bool PendingConfiguration => controller.Running && activeProfile != null && (activeProfile.ActiveSubscriptionId != profile.ActiveSubscriptionId || activeProfile.Yaml != profile.Yaml);

    private C.Border Surface(W.UIElement child, double padding = 18, bool selected = false)
    {
        var border = new C.Border { Child = child, CornerRadius = new W.CornerRadius(18), Padding = new W.Thickness(padding), Margin = new W.Thickness(0, 0, 12, 12), BorderThickness = new W.Thickness(selected ? 2 : 1) };
        border.SetResourceReference(C.Border.BackgroundProperty, "Card"); border.SetResourceReference(C.Border.BorderBrushProperty, selected ? "Accent" : "Line"); return border;
    }
    private C.Border Badge(string text, bool accent = false)
    {
        var label = Text(text, 11, true); label.SetResourceReference(C.TextBlock.ForegroundProperty, accent ? "Accent" : "Muted");
        var tag = new C.Border { Child = label, CornerRadius = new W.CornerRadius(8), Padding = new W.Thickness(9, 4, 9, 4), Margin = new W.Thickness(0, 0, 7, 0) };
        tag.SetResourceReference(C.Border.BackgroundProperty, accent ? "Selection" : "Field"); return tag;
    }
    private static string Bytes(long? value) => !value.HasValue ? "未提供" : value.Value >= 1073741824 ? (value.Value / 1073741824d).ToString("0.0") + " GB" : value.Value >= 1048576 ? (value.Value / 1048576d).ToString("0.0") + " MB" : (value.Value / 1024d).ToString("0.0") + " KB";
    private C.Button SmallButton(string label, Func<Task> action, bool primary = false)
    { var button = Button(label, action, primary); button.Padding = new W.Thickness(11, 7, 11, 7); button.FontSize = 12; button.VerticalAlignment = W.VerticalAlignment.Center; return button; }

    private void BuildSubscriptionWorkspace()
    {
        var page = Page("subscriptions", "订阅", "保存多份配置，点“使用”切换。当前连接用的是哪份，一眼就能找到。");
        var add = new C.Expander { Header = "添加配置", IsExpanded = profile.ProtectedYaml.Length == 0, Margin = new W.Thickness(0, 8, 0, 12) };
        applySubscriptionChanges = SmallButton("应用更新并重新连接", async () => { if (busy) return; Stop(); await StartAsync(); });
        Row(page, Button("＋ 添加订阅", () => { add.IsExpanded = !add.IsExpanded; if (add.IsExpanded) { add.BringIntoView(); subscriptionName.Focus(); } return Task.CompletedTask; }, true), SmallButton("导入本地文件", ImportLocalSubscriptionAsync), applySubscriptionChanges);
        librarySummary.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); librarySummary.Margin = new W.Thickness(0, 4, 0, 14); page.Children.Add(librarySummary);
        page.Children.Add(subscriptionCards); subscriptionCards.SizeChanged += (_, _) => ResizeSubscriptionCards();
        var form = new C.StackPanel(); form.Children.Add(Note("给它起个名字")); form.Children.Add(subscriptionName); subscriptionName.Text = "我的订阅";
        form.Children.Add(Note("粘贴订阅链接（地址会加密保存在本机）")); form.Children.Add(subscription); subscriptionShown.Visibility = W.Visibility.Collapsed; form.Children.Add(subscriptionShown);
        Row(form, Button("添加订阅", UpdateSubscriptionAsync, true), Button("导入本地文件", ImportLocalSubscriptionAsync), SmallButton("显示链接", () => { bool show = subscriptionShown.Visibility != W.Visibility.Visible; if (show) subscriptionShown.Text = subscription.Password; else subscription.Password = subscriptionShown.Text; subscriptionShown.Visibility = show ? W.Visibility.Visible : W.Visibility.Collapsed; subscription.Visibility = show ? W.Visibility.Collapsed : W.Visibility.Visible; return Task.CompletedTask; }));
        var advanced = new C.Expander { Header = "下载选项 · 导入失败时再调整", Margin = new W.Thickness(0, 12, 0, 0) };
        var options = new C.StackPanel(); options.Children.Add(Note("订阅格式")); subscriptionClient.ItemsSource = new[] { "Mihomo / Clash Meta（推荐）", "Clash 兼容", "浏览器请求" }; options.Children.Add(subscriptionClient);
        options.Children.Add(Note("通过哪条网络下载")); subscriptionRoute.ItemsSource = new[] { "自动选择（推荐）", "直接下载", "使用 Windows 当前代理", "使用正在运行的 Swirl" }; options.Children.Add(subscriptionRoute); advanced.Content = options; form.Children.Add(advanced); add.Content = Surface(form); page.Children.Add(add);
        Row(page, SmallButton("查看节点", () => { SelectPage("nodes"); return Task.CompletedTask; }), SmallButton("检查当前配置", () => Mutate(async () => { SaveFlags(); await controller.ValidateAsync(profile); status.Text = "当前配置检查通过，可以连接。"; })));
    }
    private void RefreshSubscriptionCards()
    {
        SubscriptionLibrary.Ensure(profile); var entries = SubscriptionLibrary.Read(profile); subscriptionCards.Children.Clear();
        string? runningId = controller.Running ? activeProfile?.ActiveSubscriptionId : null;
        bool pending = PendingConfiguration; applySubscriptionChanges.Visibility = pending ? W.Visibility.Visible : W.Visibility.Collapsed;
        librarySummary.Text = entries.Count == 0 ? "还没有订阅。先添加服务商给你的链接，或导入 YAML 文件。" : entries.Count + " 份配置" + (pending ? " · 有更新待应用，重新连接后使用新配置" : controller.Running ? " · 已连接" : " · 选择配置后，去首页连接网络");
        foreach (var entry in entries)
        {
            bool selected = profile.ActiveSubscriptionId == entry.Id;
            var body = new C.StackPanel(); var header = new C.DockPanel();
            var badge = Badge(runningId == entry.Id ? pending ? "有更新待应用" : "连接中" : selected ? "当前使用" : "已保存", selected); C.DockPanel.SetDock(badge, C.Dock.Right); header.Children.Add(badge);
            var title = Text(entry.Name, 18, true); title.TextTrimming = W.TextTrimming.CharacterEllipsis; title.TextWrapping = W.TextWrapping.NoWrap; header.Children.Add(title); body.Children.Add(header);
            var origin = Note(entry.Origin, 11); origin.Margin = new W.Thickness(0, 5, 0, 12); body.Children.Add(origin);
            int count = 0; try { count = new ProxyCatalogCount(entry.Yaml).Nodes; } catch { }
            var updated = Note((count > 0 ? count + " 个节点 · " : "提供器节点 · ") + (entry.UpdatedAt.HasValue ? "更新于 " + entry.UpdatedAt.Value.ToLocalTime().ToString("MM-dd HH:mm") : "尚无更新时间"), 11); updated.Margin = new W.Thickness(0, 0, 0, 12); body.Children.Add(updated);
            var usage = entry.Usage;
            body.Children.Add(Text(entry.Source.Length == 0 ? "本地文件，不统计订阅流量" : usage?.Used != null && usage.Total != null ? "已用 " + Bytes(usage.Used) + " / " + Bytes(usage.Total) : "服务商未提供完整流量信息", 12));
            var progress = new C.ProgressBar { Minimum = 0, Maximum = 100, Value = usage?.Percent ?? 0, Height = 5, Margin = new W.Thickness(0, 9, 0, 7), Visibility = entry.Source.Length == 0 ? W.Visibility.Collapsed : W.Visibility.Visible }; progress.SetResourceReference(C.ProgressBar.ForegroundProperty, "Accent"); progress.SetResourceReference(C.ProgressBar.BackgroundProperty, "Selection"); body.Children.Add(progress);
            var expiresLabel = Note(usage?.Expires is { } expires ? "到期 " + expires.ToLocalTime().ToString("yyyy-MM-dd") + (expires <= DateTimeOffset.UtcNow ? " · 已过期" : "") : entry.Source.Length == 0 ? "本地配置没有服务商流量或到期数据" : "到期时间：服务商未提供", 11); expiresLabel.Margin = new W.Thickness(0, 0, 0, 8); body.Children.Add(expiresLabel);
            var use = SmallButton(selected ? "已选用" : "使用", () => ActivateSubscriptionAsync(entry.Id), !selected); use.IsEnabled = !selected;
            Row(body, use, SmallButton(entry.Source.Length == 0 ? "重新导入" : "更新", () => entry.Source.Length == 0 ? ImportLocalSubscriptionAsync(entry.Id) : UpdateEntryAsync(entry)), SmallButton("更多", () => { var menu = new C.ContextMenu(); var rename = new C.MenuItem { Header = "重命名" }; rename.Click += (_, _) => RenameSubscription(entry); menu.Items.Add(rename); if (entry.Source.Length > 0) { var options = new C.MenuItem { Header = "下载选项" }; options.Click += (_, _) => SubscriptionOptions(entry); menu.Items.Add(options); var copy = new C.MenuItem { Header = "复制订阅链接" }; copy.Click += (_, _) => W.Clipboard.SetText(entry.Source); menu.Items.Add(copy); } var remove = new C.MenuItem { Header = "移除这份配置" }; remove.Click += async (_, _) => { try { await RemoveSubscriptionAsync(entry); } catch (Exception e) { status.Text = e.Message; } }; menu.Items.Add(remove); menu.IsOpen = true; return Task.CompletedTask; }));
            var card = Surface(body, 20, selected); card.Tag = entry.Id; card.MinWidth = 280; subscriptionCards.Children.Add(card);
        }
        ResizeSubscriptionCards();
    }
    private sealed class ProxyCatalogCount
    {
        internal int Nodes { get; }
        internal ProxyCatalogCount(string yaml) { var root = MihomoConfig.Parse(yaml); Nodes = root.TryGetValue("proxies", out var value) && value is IEnumerable<object> nodes ? nodes.Count() : 0; }
    }
    private void ResizeSubscriptionCards()
    {
        double width = subscriptionCards.ActualWidth; if (width <= 0) return;
        int columns = width >= 680 ? 2 : 1;
        foreach (C.Border card in subscriptionCards.Children) card.Width = Math.Max(260, width / columns - 12);
    }
    private Task ImportLocalSubscriptionAsync() => ImportLocalSubscriptionAsync(null);
    private async Task ImportLocalSubscriptionAsync(string? replaceId)
    {
        using var dialog = new OpenFileDialog { Filter = "Clash / Mihomo 配置|*.yaml;*.yml" };
        if (dialog.ShowDialog(OwnerHandle) != System.Windows.Forms.DialogResult.OK) return;
        if (new FileInfo(dialog.FileName).Length > SubscriptionImport.SizeLimit) throw new InvalidOperationException("配置文件不能超过 4 MB。");
        await Mutate(async () => { string name = replaceId != null ? SubscriptionLibrary.Read(profile).FirstOrDefault(e => e.Id == replaceId)?.Name ?? "本地配置" : Path.GetFileNameWithoutExtension(dialog.FileName); SubscriptionLibrary.Add(profile, name, new(await File.ReadAllTextAsync(dialog.FileName), ""), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic, replaceId); profile.Save(); RefreshSubscriptionCards(); status.Text = PendingConfiguration ? "本地配置更新好了，重新连接后生效。" : "本地配置已保存。点“使用”可切换到这份配置。"; }, allowConnected: true);
    }
    private async Task ActivateSubscriptionAsync(string id)
    {
        if (busy || id == profile.ActiveSubscriptionId) return;
        var candidate = System.Text.Json.JsonSerializer.Deserialize<ProxyProfile>(System.Text.Json.JsonSerializer.Serialize(profile))!;
        SubscriptionLibrary.Activate(candidate, id); _ = MihomoConfig.Build(candidate, "preview");
        bool restart = controller.Running; if (restart) Stop(); busy = true;
        try { if (File.Exists(ProxyController.CorePath)) await controller.ValidateAsync(candidate); SubscriptionLibrary.Activate(profile, id); profile.Save(); measuredDelays.Clear(); LoadProfile(); RefreshSubscriptionCards(); status.Text = "已切换配置，可以选节点并连接网络。"; }
        finally { busy = false; if (restart) await StartAsync(); }
    }
    private Task UpdateEntryAsync(SubscriptionEntry entry) => Mutate(async () =>
    {
        if (entry.Source.Length == 0) throw new InvalidOperationException("这份配置来自本地文件。请重新导入更新后的 YAML 文件。");
        if (entry.Route == SubscriptionDownloadRoute.Swirl && !controller.Running) throw new InvalidOperationException("请先连接 Swirl，或在下载选项中选择其他网络。");
        var download = await SubscriptionImport.DownloadRoutedAsync(entry.Source, entry.Client, entry.Route, lifetime.Token, text => status.Text = text);
        SubscriptionLibrary.Add(profile, entry.Name, download, entry.Client, entry.Route); profile.Save(); RefreshSubscriptionCards();
        status.Text = controller.Running && entry.Id == activeProfile?.ActiveSubscriptionId ? "订阅更新好了，重新连接后使用新节点。" : "订阅更新好了。";
    }, allowConnected: true);
    private Task RemoveSubscriptionAsync(SubscriptionEntry entry) => Mutate(() =>
    {
        if (controller.Running && (entry.Id == profile.ActiveSubscriptionId || entry.Id == activeProfile?.ActiveSubscriptionId)) throw new InvalidOperationException("请先断开连接，再移除正在使用的配置。");
        if (W.MessageBox.Show(this, "移除“" + entry.Name + "”？只会移除本机保存的配置。", "移除配置", W.MessageBoxButton.YesNo) != W.MessageBoxResult.Yes) return Task.CompletedTask;
        SubscriptionLibrary.Remove(profile, entry.Id); profile.Save(); RefreshSubscriptionCards(); return Task.CompletedTask;
    }, allowConnected: true);
    private void RenameSubscription(SubscriptionEntry entry)
    {
        var name = new C.TextBox { Text = entry.Name }; var content = new C.StackPanel(); content.Children.Add(name);
        var dialog = Sheet("重命名订阅", "起一个容易认出的名称，例如“日常使用”或“备用线路”。", content, 480);
        Row(content, Button("保存名称", () => { SubscriptionLibrary.Rename(profile, entry.Id, name.Text); profile.Save(); RefreshSubscriptionCards(); dialog.Close(); return Task.CompletedTask; }, true)); dialog.ShowDialog();
    }
    private void SubscriptionOptions(SubscriptionEntry entry)
    {
        var content = new C.StackPanel(); var client = new C.ComboBox { ItemsSource = new[] { "Mihomo / Clash Meta（推荐）", "Clash 兼容", "浏览器请求" }, SelectedIndex = (int)entry.Client }; var route = new C.ComboBox { ItemsSource = new[] { "自动选择（推荐）", "直接下载", "使用 Windows 当前代理", "使用正在运行的 Swirl" }, SelectedIndex = (int)entry.Route };
        content.Children.Add(Note("请求格式")); content.Children.Add(client); content.Children.Add(Note("通过哪条网络下载")); content.Children.Add(route);
        var dialog = Sheet("订阅下载选项", "只影响这份订阅的更新方式，不改变日常上网模式。", content, 540);
        Row(content, Button("保存选项", () => { SubscriptionLibrary.Configure(profile, entry.Id, (SubscriptionClientProfile)client.SelectedIndex, (SubscriptionDownloadRoute)route.SelectedIndex); profile.Save(); RefreshSubscriptionCards(); dialog.Close(); return Task.CompletedTask; }, true)); dialog.ShowDialog();
    }
    private W.Window Sheet(string title, string description, C.StackPanel content, double width = 780, C.StackPanel? footer = null)
    {
        var dialog = new W.Window { Owner = this, Title = title, Width = width, MaxHeight = 760, SizeToContent = W.SizeToContent.Height, MinHeight = 220, WindowStartupLocation = W.WindowStartupLocation.CenterOwner, WindowStyle = W.WindowStyle.None, ResizeMode = W.ResizeMode.NoResize, FontFamily = FontFamily, FontSize = 13, ShowInTaskbar = false };
        dialog.Resources.MergedDictionaries.Add(Resources);
        WindowChrome.SetWindowChrome(dialog, new WindowChrome { CaptionHeight = 45, CornerRadius = new W.CornerRadius(20), GlassFrameThickness = new W.Thickness(0), UseAeroCaptionButtons = false });
        var shell = new C.DockPanel(); var heading = new C.StackPanel(); var header = new C.DockPanel(); var close = SmallButton("关闭", () => { dialog.Close(); return Task.CompletedTask; }); WindowChrome.SetIsHitTestVisibleInChrome(close, true); C.DockPanel.SetDock(close, C.Dock.Right); header.Children.Add(close); header.Children.Add(Text(title, 21, true)); heading.Children.Add(header); heading.Children.Add(Note(description)); C.DockPanel.SetDock(heading, C.Dock.Top); shell.Children.Add(heading);
        if (footer != null) { C.DockPanel.SetDock(footer, C.Dock.Bottom); shell.Children.Add(footer); }
        shell.Children.Add(new C.ScrollViewer { Content = content, MaxHeight = footer == null ? 620 : 540, VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled });
        var surface = Surface(shell, 24); surface.Margin = new W.Thickness(0); surface.SetResourceReference(C.Border.BackgroundProperty, "PopupSurface"); dialog.Content = surface;
        dialog.SourceInitialized += (_, _) => WindowBackdrop.Apply(dialog, false); return dialog;
    }
}
