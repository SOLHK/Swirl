using AdShield.Network;
using System.Diagnostics;
using System.Text.Json;
using System.Windows.Interop;
using System.Windows.Media.Imaging;
using System.Windows.Shell;
using System.Windows.Threading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;

namespace AdShield.Desktop;

internal sealed class SwirlWindow : W.Window
{
    private readonly ProxyProfile profile;
    private readonly ProxyController controller;
    private readonly Dictionary<string, C.StackPanel> pages = new();
    private readonly Dictionary<string, C.Button> navigation = new();
    private readonly C.ScrollViewer viewport = new() { VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled };
    private readonly C.TextBlock status = new(), headline = new(), detail = new(), diagnostic = new(), scope = new(), pluginMetric = new(), uploadMetric = new(), downloadMetric = new(), routeMetric = new(), pluginInfo = new(), syncStatus = new();
    private readonly C.TextBox subscriptionShown = new(), pluginUrl = new(), argument = new(), pluginPolicy = new(), ruleValue = new(), ruleSsid = new(), ruleHosts = new(), syncFolder = new(), log = new();
    private readonly C.PasswordBox subscription = new(), syncPassword = new();
    private readonly C.ComboBox subscriptionClient = new(), subscriptionRoute = new(), groups = new(), mode = new(), scriptPlugins = new(), tasks = new(), ruleKind = new(), rulePolicy = new();
    private ProxyProfile? activeProfile;
    private readonly C.ListBox nodes = new(), plugins = new(), rules = new();
    private readonly C.CheckBox systemProxy = new() { Content = "系统代理 · 浏览器与遵循 Windows 代理的应用" }, tun = new() { Content = "TUN · 接管更多应用流量（需要管理员权限）" }, mitm = new() { Content = "启用 HTTPS 解密 · 仅限插件指定域名" }, glass = new() { Content = "窗口玻璃效果 · 显示背后窗口与桌面的模糊背景" };
    private C.Button connect = null!, disconnect = null!;
    private Dictionary<string, string[]> nodeGroups = new();
    private Dictionary<string, string> selections = new();
    private readonly NotifyIcon? tray;
    private readonly DispatcherTimer timer = new() { Interval = TimeSpan.FromSeconds(2) };
    private readonly CancellationTokenSource lifetime = new();
    private bool busy, closed, polling;
    private readonly Microsoft.Win32.UserPreferenceChangedEventHandler preferenceChanged;
    private bool Dark => WindowBackdrop.Dark;

    internal SwirlWindow(ProxyProfile? initialProfile = null, bool withTray = true)
    {
        profile = initialProfile ?? ProxyProfile.Load(); controller = new ProxyController(Report);
        Title = "Swirl"; Width = 1160; Height = 790; MinWidth = 930; MinHeight = 650;
        WindowStartupLocation = W.WindowStartupLocation.CenterScreen; WindowStyle = W.WindowStyle.None;
        FontFamily = new M.FontFamily("Microsoft YaHei UI"); FontSize = 13;
        UseLayoutRounding = true; SnapsToDevicePixels = true;
        Resources.MergedDictionaries.Add(new W.ResourceDictionary { Source = new Uri("/Swirl;component/Desktop/Styles.xaml", UriKind.Relative) });
        SetColors(); Icon = ImageSource();
        WindowChrome.SetWindowChrome(this, new WindowChrome { CaptionHeight = 44, ResizeBorderThickness = new W.Thickness(7), GlassFrameThickness = new W.Thickness(-1), CornerRadius = new W.CornerRadius(12), UseAeroCaptionButtons = false });
        var shell = new C.Grid(); shell.RowDefinitions.Add(new C.RowDefinition { Height = new W.GridLength(44) }); shell.RowDefinitions.Add(new C.RowDefinition()); shell.RowDefinitions.Add(new C.RowDefinition { Height = new W.GridLength(32) });
        var caption = new C.Grid { Margin = new W.Thickness(18, 0, 0, 0) }; caption.ColumnDefinitions.Add(new C.ColumnDefinition()); caption.ColumnDefinitions.Add(new C.ColumnDefinition { Width = W.GridLength.Auto });
        caption.Children.Add(Text("Swirl", 13, true));
        var windowButtons = new C.StackPanel { Orientation = C.Orientation.Horizontal };
        foreach (var (symbol, name, action) in new (string, string, Action)[] { ("\uE921", "最小化", () => WindowState = W.WindowState.Minimized), ("\uE922", "最大化或还原", () => WindowState = WindowState == W.WindowState.Maximized ? W.WindowState.Normal : W.WindowState.Maximized), ("\uE8BB", "关闭并恢复代理", Close) })
        {
            var button = Button(symbol, () => { action(); return Task.CompletedTask; }); button.FontFamily = new M.FontFamily("Segoe Fluent Icons"); button.Width = 46; button.Height = 40; button.Margin = new W.Thickness(0); button.Background = M.Brushes.Transparent; button.BorderThickness = new W.Thickness(0); button.ToolTip = name;
            WindowChrome.SetIsHitTestVisibleInChrome(button, true); windowButtons.Children.Add(button);
        }
        C.Grid.SetColumn(windowButtons, 1); caption.Children.Add(windowButtons); shell.Children.Add(caption);
        var workspace = new C.Grid(); workspace.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(214) }); workspace.ColumnDefinitions.Add(new C.ColumnDefinition()); C.Grid.SetRow(workspace, 1); shell.Children.Add(workspace);
        var sidebar = new C.DockPanel { Margin = new W.Thickness(12, 6, 12, 12) };
        var brand = new C.StackPanel { Orientation = C.Orientation.Horizontal, Margin = new W.Thickness(10, 9, 0, 26) };
        brand.Children.Add(new C.Image { Source = Icon, Width = 44, Height = 44, Margin = new W.Thickness(0, 0, 10, 0) }); var brandLabels = new C.StackPanel(); brandLabels.Children.Add(Text("Swirl", 24, true)); brandLabels.Children.Add(Note("让网络轻盈一点", 11)); brand.Children.Add(brandLabels); C.DockPanel.SetDock(brand, C.Dock.Top); sidebar.Children.Add(brand);
        var footer = Note("Swirl 0.7.1\nWindows · Mihomo", 11); footer.Margin = new W.Thickness(16, 10, 0, 0); C.DockPanel.SetDock(footer, C.Dock.Bottom); sidebar.Children.Add(footer);
        var links = new C.StackPanel();
        foreach (var (key, name, glyph) in new[] { ("overview", "概览", "\uE80F"), ("nodes", "代理节点", "\uE839"), ("plugins", "插件中心", "\uE74C"), ("routing", "规则分流", "\uE8AB"), ("https", "HTTPS 解密", "\uE72E"), ("scripts", "脚本任务", "\uE756"), ("sync", "配置同步", "\uE753"), ("logs", "运行记录", "\uE9D9"), ("settings", "偏好设置", "\uE713") })
        {
            var row = new C.StackPanel { Orientation = C.Orientation.Horizontal }; row.Children.Add(new C.TextBlock { Text = glyph, FontFamily = new M.FontFamily("Segoe Fluent Icons"), Width = 30, VerticalAlignment = W.VerticalAlignment.Center }); row.Children.Add(Text(name));
            var button = Button("", () => { SelectPage(key); return Task.CompletedTask; }); button.Content = row; button.HorizontalContentAlignment = W.HorizontalAlignment.Left; button.Margin = new W.Thickness(0, 0, 0, 5); button.Padding = new W.Thickness(15, 12, 10, 12); button.BorderThickness = new W.Thickness(0); links.Children.Add(button); navigation[key] = button;
        }
        sidebar.Children.Add(links); workspace.Children.Add(sidebar);
        viewport.Margin = new W.Thickness(22, 8, 24, 16); C.Grid.SetColumn(viewport, 1); workspace.Children.Add(viewport);
        status.Margin = new W.Thickness(238, 7, 25, 0); status.FontSize = 11; status.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); status.TextTrimming = W.TextTrimming.CharacterEllipsis; status.TextWrapping = W.TextWrapping.NoWrap; C.Grid.SetRow(status, 2); shell.Children.Add(status); Content = shell;
        BuildOverview(); BuildNodes(); BuildPlugins(); BuildRouting(); BuildHttps(); BuildScripts(); BuildSync(); BuildLogs(); BuildSettings(); LoadProfile(); SelectPage("overview");
        status.Text = File.Exists(ProxyController.CorePath) ? "网络核心已就绪 · 尚未连接" : "缺少网络核心，请完整安装 Swirl";
        SourceInitialized += (_, _) => ApplyBackdrop();
        preferenceChanged = (_, _) => { if (!closed) Dispatcher.BeginInvoke(() => { if (!closed) { SetColors(); ApplyBackdrop(); } }); };
        Microsoft.Win32.SystemEvents.UserPreferenceChanged += preferenceChanged;
        if (withTray)
        {
            var menu = new ContextMenuStrip(); menu.Items.Add("打开 Swirl", null, (_, _) => { Show(); WindowState = W.WindowState.Normal; Activate(); }); menu.Items.Add("退出并恢复代理", null, (_, _) => Close());
            tray = new NotifyIcon { Text = "Swirl", Icon = SwirlTheme.CreateIcon(), Visible = true, ContextMenuStrip = menu };
            tray.DoubleClick += (_, _) => { Show(); WindowState = W.WindowState.Normal; Activate(); };
            StateChanged += (_, _) => { if (WindowState == W.WindowState.Minimized) Hide(); };
        }
        timer.Tick += async (_, _) => await PollAsync(); timer.Start();
        Closed += (_, _) => { closed = true; Microsoft.Win32.SystemEvents.UserPreferenceChanged -= preferenceChanged; lifetime.Cancel(); timer.Stop(); controller.Dispose(); tray?.Dispose(); lifetime.Dispose(); };
    }

    private void SetColors()
    {
        M.SolidColorBrush Brush(byte alpha, byte r, byte g, byte b) => new(M.Color.FromArgb(alpha, r, g, b));
        Resources["Ink"] = Dark ? Brush(255, 241, 245, 251) : Brush(255, 27, 40, 62);
        Resources["Muted"] = Dark ? Brush(255, 172, 184, 202) : Brush(255, 92, 108, 133);
        Resources["Card"] = Dark ? Brush(150, 35, 44, 59) : Brush(150, 255, 255, 255);
        Resources["Field"] = Dark ? Brush(190, 45, 55, 73) : Brush(175, 247, 250, 255);
        Resources["PopupSurface"] = Dark ? Brush(255, 40, 48, 63) : Brush(255, 247, 250, 255);
        Resources["Line"] = Dark ? Brush(70, 184, 210, 245) : Brush(65, 150, 167, 194);
        Resources["Selection"] = Dark ? Brush(140, 40, 92, 146) : Brush(180, 223, 239, 255);
        Resources["Accent"] = Brush(255, 33, 123, 226);
    }
    private void ApplyBackdrop() { bool enabled = WindowBackdrop.Apply(this, profile.GlassAppearance); if (profile.GlassAppearance && !enabled) Report("玻璃背景未启用：Windows 透明效果设置或当前系统不支持，已使用清晰背景。"); }
    private static BitmapSource ImageSource()
    {
        using var stream = typeof(SwirlWindow).Assembly.GetManifestResourceStream("Swirl.Icon.png")!;
        var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = stream; image.EndInit(); image.Freeze(); return image;
    }
    private C.TextBlock Text(string text, double size = 13, bool bold = false) => new() { Text = text, FontSize = size, FontWeight = bold ? W.FontWeights.SemiBold : W.FontWeights.Normal, VerticalAlignment = W.VerticalAlignment.Center };
    private C.TextBlock Note(string text, double size = 12) { var label = Text(text, size); label.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); label.Margin = new W.Thickness(0, 6, 0, 12); return label; }
    private C.Button Button(string text, Func<Task> action, bool primary = false)
    {
        var button = new C.Button { Content = text }; if (primary) { button.SetResourceReference(C.Button.BackgroundProperty, "Accent"); button.Foreground = M.Brushes.White; button.BorderThickness = new W.Thickness(0); }
        button.Click += async (_, _) => { try { await action(); } catch (OperationCanceledException) when (closed) { } catch (Exception e) { if (!closed) { Report(e.Message); status.Text = e.Message; W.MessageBox.Show(this, e.Message, "操作未完成", W.MessageBoxButton.OK, W.MessageBoxImage.Information); } } }; return button;
    }
    private static void Row(C.Panel parent, params W.UIElement[] children) { var row = new C.WrapPanel { Margin = new W.Thickness(0, 8, 0, 4) }; foreach (var child in children) row.Children.Add(child); parent.Children.Add(row); }
    private C.StackPanel Page(string key, string title, string note)
    {
        var page = new C.StackPanel(); var label = Text(title, 27, true); label.Margin = new W.Thickness(0, 0, 0, 2); page.Children.Add(label); page.Children.Add(Note(note)); pages[key] = page; return page;
    }
    private C.StackPanel Card(C.Panel page, string title, string description = "")
    {
        var content = new C.StackPanel(); content.Children.Add(Text(title, 16, true)); if (description.Length > 0) content.Children.Add(Note(description));
        var border = new C.Border { Child = content, CornerRadius = new W.CornerRadius(14), Padding = new W.Thickness(20), BorderThickness = new W.Thickness(1), Margin = new W.Thickness(0, 8, 0, 8) }; border.SetResourceReference(C.Border.BackgroundProperty, "Card"); border.SetResourceReference(C.Border.BorderBrushProperty, "Line"); page.Children.Add(border); return content;
    }
    internal void SelectPage(string key) { viewport.Content = pages[key]; viewport.ScrollToTop(); foreach (var item in navigation) item.Value.Background = item.Key == key ? (M.Brush)Resources["Selection"] : M.Brushes.Transparent; }
    private void BuildOverview()
    {
        var page = Page("overview", "概览", "连接状态、当前线路与插件，一眼可见。");
        var hero = Card(page, "网络连接"); headline.FontSize = 28; headline.FontWeight = W.FontWeights.SemiBold; headline.Margin = new W.Thickness(0, 10, 0, 4); hero.Children.Add(headline); detail.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); hero.Children.Add(detail);
        connect = Button("连接网络", StartAsync, true); disconnect = Button("断开", () => { Stop(); return Task.CompletedTask; }); disconnect.IsEnabled = false; Row(hero, connect, disconnect, Button("检测连接", ProbeAsync));
        var metrics = new C.Grid { Margin = new W.Thickness(0, 8, 0, 8) };
        for (int i = 0; i < 3; i++) metrics.ColumnDefinitions.Add(new C.ColumnDefinition());
        int index = 0; foreach (var (label, value) in new[] { ("下载流量", downloadMetric), ("上传流量", uploadMetric), ("启用插件", pluginMetric) }) { var box = new C.StackPanel(); box.Children.Add(Note(label)); value.FontSize = 23; value.FontWeight = W.FontWeights.SemiBold; box.Children.Add(value); var border = new C.Border { Child = box, Padding = new W.Thickness(18), CornerRadius = new W.CornerRadius(12), Margin = new W.Thickness(0, 0, index < 2 ? 10 : 0, 0) }; border.SetResourceReference(C.Border.BackgroundProperty, "Card"); C.Grid.SetColumn(border, index++); metrics.Children.Add(border); } page.Children.Add(metrics);
        var columns = new C.Grid(); columns.ColumnDefinitions.Add(new C.ColumnDefinition()); columns.ColumnDefinitions.Add(new C.ColumnDefinition());
        var left = new C.StackPanel { Margin = new W.Thickness(0, 0, 10, 0) }; var right = new C.StackPanel(); C.Grid.SetColumn(right, 1); columns.Children.Add(left); columns.Children.Add(right); page.Children.Add(columns);
        var route = Card(left, "当前策略", "核心的实际线路选择"); route.Children.Add(routeMetric); Row(route, Button("选择节点", () => { SelectPage("nodes"); return Task.CompletedTask; }), Button("接管方式", () => { SelectPage("settings"); return Task.CompletedTask; }));
        var health = Card(right, "连接检查"); diagnostic.LineHeight = 22; health.Children.Add(diagnostic);
        Row(health, Button("添加去广告插件", () => { SelectPage("plugins"); return Task.CompletedTask; }), Button("查看记录", () => { SelectPage("logs"); return Task.CompletedTask; }));
    }
    private void BuildNodes()
    {
        var page = Page("nodes", "代理节点", "支持 Clash / Mihomo 订阅，保留原有节点组与规则。");
        var input = Card(page, "订阅与配置"); input.Children.Add(Note("订阅地址（在本机加密保存）")); input.Children.Add(subscription); subscriptionShown.Visibility = W.Visibility.Collapsed; input.Children.Add(subscriptionShown);
        subscriptionClient.ItemsSource = new[] { "Mihomo / Clash Meta", "Clash 兼容", "浏览器请求" }; Row(input, Text("请求类型"), subscriptionClient); subscriptionRoute.ItemsSource = new[] { "自动 · 先直连，再尝试当前系统代理", "直连 · 不经过系统代理", "当前系统代理 · 每次读取最新设置", "Swirl 代理 · 保持连接下载" }; Row(input, Text("下载链路"), subscriptionRoute); input.Children.Add(Note("下载链路与代理流量模式独立。更新时保持当前连接，新配置在重新连接后生效。"));
        Row(input, Button("更新订阅", UpdateSubscriptionAsync, true), Button("本地 YAML", () => Mutate(async () => { using var dialog = new OpenFileDialog { Filter = "Clash / Mihomo|*.yaml;*.yml" }; if (dialog.ShowDialog(OwnerHandle) != System.Windows.Forms.DialogResult.OK) return; if (new FileInfo(dialog.FileName).Length > 4 * 1024 * 1024) throw new InvalidOperationException("配置超过 4 MB。"); profile.ProtectedYaml = ProxyProfile.Protect(MihomoConfig.ParseSubscription(await File.ReadAllTextAsync(dialog.FileName))); profile.Save(); status.Text = "本地配置已导入。"; })), Button("显示 / 隐藏地址", () => { bool show = subscriptionShown.Visibility != W.Visibility.Visible; if (show) subscriptionShown.Text = subscription.Password; else subscription.Password = subscriptionShown.Text; subscriptionShown.Visibility = show ? W.Visibility.Visible : W.Visibility.Collapsed; subscription.Visibility = show ? W.Visibility.Collapsed : W.Visibility.Visible; return Task.CompletedTask; }), Button("检查配置", () => Mutate(async () => { SaveFlags(); await controller.ValidateAsync(profile); status.Text = "配置检查通过。"; })));
        var select = Card(page, "策略组与线路", "选中线路后点击“应用线路”。检测连接会检查当前实际代理路径。"); select.Children.Add(groups); nodes.Height = 200; select.Children.Add(nodes);
        groups.SelectionChanged += (_, _) => FillNodes();
        Row(select, Button("应用线路", async () => { if (!controller.Running || groups.SelectedItem is not string group || nodes.SelectedItem is not string node) throw new InvalidOperationException("请先连接并选择线路。"); await controller.SelectAsync(group, node); await LoadGroupsAsync(); status.Text = "线路已应用；正在检测…"; await ProbeAsync(); }, true), Button("测试延迟", async () => { if (!controller.Running || nodes.SelectedItem is not string node) throw new InvalidOperationException("请先连接并选择线路。"); status.Text = node + " · " + await controller.DelayAsync(node) + " ms"; }), Button("连接网络", StartAsync));
    }
    private void BuildPlugins()
    {
        var page = Page("plugins", "插件中心", "使用 Loon 明文插件处理规则、重写与脚本。"); var input = Card(page, "添加插件", "支持插件原作者链接、loon://import 链接及可莉公开目录。"); input.Children.Add(pluginUrl);
        Row(input, Button("链接导入", () => Mutate(async () => { string url = LoonPlugin.ResolveImportUrl(pluginUrl.Text.Trim()); if (new Uri(url).Host.Equals("hub.kelee.one", StringComparison.OrdinalIgnoreCase)) { url = await PluginCatalog.ChooseAsync(OwnerHandle) ?? ""; if (url.Length == 0) return; } await ImportPluginAsync(url); }), true), Button("可莉插件目录", () => Mutate(async () => { var url = await PluginCatalog.ChooseAsync(OwnerHandle); if (url != null) await ImportPluginAsync(url); })), Button("本地文件", () => Mutate(async () => { using var dialog = new OpenFileDialog { Filter = "Loon 明文插件|*.lpx;*.plugin;*.conf" }; if (dialog.ShowDialog(OwnerHandle) != System.Windows.Forms.DialogResult.OK) return; var plugin = LoonPlugin.Parse(await File.ReadAllTextAsync(dialog.FileName), "本地文件"); await plugin.DownloadScriptsAsync(); profile.Plugins.Add(plugin); profile.Save(); RefreshPlugins(); })));
        var library = Card(page, "已安装插件", "导入后需启用；HTTPS 脚本还需打开 HTTPS 解密并信任本机证书。"); plugins.Height = 160; library.Children.Add(plugins); plugins.SelectionChanged += (_, _) => ShowPlugin();
        Row(library, Button("启用 / 停用", () => Mutate(() => { if (plugins.SelectedItem is LoonPlugin plugin) { if (plugin.Unsupported.Count > 0) throw new InvalidOperationException("插件包含不兼容项，请查看下方说明。"); plugin.Enabled = !plugin.Enabled; profile.Save(); RefreshPlugins(plugin.Id); } return Task.CompletedTask; }), true), Button("更新", () => Mutate(async () => { if (plugins.SelectedItem is not LoonPlugin old || !old.Source.StartsWith("https://")) return; var updated = LoonPlugin.Parse(await NetworkFetch.TextAsync(old.Source), old.Source); await updated.DownloadScriptsAsync(); updated.Id = old.Id; updated.Argument = old.Argument; updated.ProtectedParameterValues = old.ProtectedParameterValues; updated.ProxyPolicy = old.ProxyPolicy; updated.Enabled = false; profile.Plugins[profile.Plugins.IndexOf(old)] = updated; profile.Save(); RefreshPlugins(updated.Id); })), Button("移除", () => Mutate(() => { if (plugins.SelectedItem is LoonPlugin plugin) { profile.Plugins.Remove(plugin); profile.Save(); RefreshPlugins(); } return Task.CompletedTask; })));
        pluginInfo.Margin = new W.Thickness(0, 12, 0, 0); pluginInfo.LineHeight = 22; library.Children.Add(pluginInfo);
        var parameters = Card(page, "参数与策略"); parameters.Children.Add(Note("脚本 $argument")); parameters.Children.Add(argument); parameters.Children.Add(Note("代理策略组（可留空）")); parameters.Children.Add(pluginPolicy);
        Row(parameters, Button("作者参数控件", () => Mutate(() => { if (plugins.SelectedItem is LoonPlugin plugin && PluginParameterEditor.Edit(OwnerHandle, plugin)) profile.Save(); return Task.CompletedTask; })), Button("保存参数", () => Mutate(() => { if (plugins.SelectedItem is LoonPlugin plugin) { plugin.Argument = argument.Text; plugin.ProxyPolicy = pluginPolicy.Text.Trim(); profile.Save(); status.Text = "参数已保存，下次连接时生效。"; } return Task.CompletedTask; }), true));
    }
    private void BuildRouting()
    {
        var page = Page("routing", "规则分流", "按域名、IP、URL 和 Wi-Fi 条件选择策略。"); var list = Card(page, "自定义规则"); rules.Height = 155; list.Children.Add(rules);
        Row(list, Button("启用 / 停用", () => Mutate(() => { if (rules.SelectedItem is UserRoutingRule rule) { rule.Enabled = !rule.Enabled; SaveRules(); } return Task.CompletedTask; })), Button("上移", () => Mutate(() => MoveRule(-1))), Button("下移", () => Mutate(() => MoveRule(1))), Button("移除", () => Mutate(() => { if (rules.SelectedItem is UserRoutingRule rule) { profile.UserRules.Remove(rule); SaveRules(); } return Task.CompletedTask; })));
        var edit = Card(page, "编辑规则", "DIRECT 为直连，REJECT 为拦截。URL 路径规则需指定解密域名。"); ruleKind.ItemsSource = new[] { "DOMAIN-SUFFIX", "DOMAIN", "IP-CIDR", "IP-CIDR6", "URL-REGEX", "SSID" }; ruleKind.SelectedIndex = 0; Row(edit, ruleKind, rulePolicy);
        edit.Children.Add(Note("域名 / 网段 / URL 正则 / Wi-Fi 名称")); edit.Children.Add(ruleValue); edit.Children.Add(Note("限定 Wi-Fi 名称（可留空）")); edit.Children.Add(ruleSsid); edit.Children.Add(Note("HTTPS URL 解密域名（英文逗号分隔）")); edit.Children.Add(ruleHosts);
        ruleKind.SelectionChanged += (_, _) => { ruleHosts.IsEnabled = (string?)ruleKind.SelectedItem == "URL-REGEX"; ruleSsid.IsEnabled = (string?)ruleKind.SelectedItem != "SSID"; };
        rules.SelectionChanged += (_, _) => { if (rules.SelectedItem is not UserRoutingRule rule) return; ruleKind.SelectedItem = rule.Kind; ruleValue.Text = rule.Value; ruleSsid.Text = rule.Ssid; ruleHosts.Text = rule.HttpsHosts; rulePolicy.SelectedItem = rule.Policy; };
        Row(edit, Button("添加规则", () => Mutate(() => { profile.UserRules.Add(EditedRule()); SaveRules(); return Task.CompletedTask; }), true), Button("保存修改", () => Mutate(() => { if (rules.SelectedItem is UserRoutingRule old) { var rule = EditedRule(); rule.Id = old.Id; rule.Enabled = old.Enabled; profile.UserRules[profile.UserRules.IndexOf(old)] = rule; SaveRules(); } return Task.CompletedTask; })));
        list.Children.Add(Note("Wi-Fi 条件在连接时读取，更换网络后请重新连接。"));
    }
    private void BuildHttps()
    {
        var page = Page("https", "HTTPS 解密", "解密范围来自启用的插件与 HTTPS URL 规则。"); var setup = Card(page, "证书与开关"); setup.Children.Add(mitm);
        Row(setup, Button("信任本机证书", () => Mutate(() => { UserRouting.Prepare(profile); var effective = UserRouting.EffectivePlugins(profile).ToArray(); string hosts = string.Join("、", effective.Where(p => p.Enabled && p.Unsupported.Count == 0).SelectMany(p => p.Hosts).Distinct()); if (hosts.Length == 0) throw new InvalidOperationException("请先启用包含 MITM 域名的插件。"); if (W.MessageBox.Show(this, "HTTPS 插件会读取这些域名的解密流量：\n\n" + hosts + "\n\n是否信任本机生成的证书？", "HTTPS 解密范围", W.MessageBoxButton.YesNo, W.MessageBoxImage.Question) == W.MessageBoxResult.Yes) { using var proxy = new PluginProxy(effective, true, Report); proxy.TrustCertificate(); status.Text = "证书已信任，请保存 HTTPS 开关。"; } return Task.CompletedTask; }), true), Button("保存开关", () => Mutate(() => { SaveFlags(); status.Text = "HTTPS 设置已保存，下次连接时生效。"; return Task.CompletedTask; })), Button("移除证书", () => Mutate(() => { using var proxy = new PluginProxy(Array.Empty<LoonPlugin>(), false, Report); proxy.RemoveCertificate(); mitm.IsChecked = profile.Mitm = false; profile.Save(); status.Text = "证书已移除。"; return Task.CompletedTask; })));
        var hostsCard = Card(page, "当前解密域名"); scope.LineHeight = 24; hostsCard.Children.Add(scope);
        Card(page, "TUN 与 HTTPS 可以同时启用", "支持 HTTP/2；正文脚本处理 2 MB 内且长度明确的请求或响应。视频流会原样转发。应用若固定证书，可能拒绝本机解密证书；插件实际效果可在运行记录查看。");
    }
    private void BuildScripts()
    {
        var page = Page("scripts", "脚本任务", "运行作者声明的通用脚本，查看执行结果。"); var manual = Card(page, "手动运行"); Row(manual, scriptPlugins, tasks); scriptPlugins.SelectionChanged += (_, _) => { tasks.ItemsSource = (scriptPlugins.SelectedItem as LoonPlugin)?.Scripts.Where(s => s.Phase == "generic").ToArray(); tasks.SelectedIndex = 0; };
        Row(manual, Button("运行任务", async () => { if (scriptPlugins.SelectedItem is LoonPlugin plugin && tasks.SelectedItem is LoonScript script) { await controller.RunTaskAsync(plugin, script); status.Text = "任务已完成，详情见运行记录。"; } }, true), Button("运行记录", () => { SelectPage("logs"); return Task.CompletedTask; }));
        Card(page, "后台任务", "Cron 和网络变化脚本在连接运行且所属插件启用时触发。断开连接会取消任务，同一任务不会重叠执行。");
    }
    private void BuildSync()
    {
        var page = Page("sync", "配置同步", "在 Windows 设备间共享加密配置。"); var card = Card(page, "加密同步目录", "选择云盘或共享文件夹；密码至少 12 个字符，不会保存。"); card.Children.Add(syncFolder); card.Children.Add(syncPassword);
        Row(card, Button("选择目录", () => { using var dialog = new FolderBrowserDialog(); if (dialog.ShowDialog(OwnerHandle) == System.Windows.Forms.DialogResult.OK) syncFolder.Text = dialog.SelectedPath; return Task.CompletedTask; }), Button("查看状态", () => { syncStatus.Text = ConfigurationSync.GetStatus(profile, syncFolder.Text.Trim()).Message; return Task.CompletedTask; }));
        Row(card, Button("上传配置", () => Mutate(async () => { try { string password = syncPassword.Password, folder = syncFolder.Text.Trim(); var result = await Task.Run(() => ConfigurationSync.Upload(profile, folder, password)); profile.Save(); syncStatus.Text = result.Message; } finally { syncPassword.Clear(); } }), true), Button("下载并检查", () => Mutate(async () => { try { string password = syncPassword.Password, folder = syncFolder.Text.Trim(); ApplyIncoming(await Task.Run(() => ConfigurationSync.Download(folder, password))); } finally { syncPassword.Clear(); } })), Button("备份并替换", () => Mutate(async () => { if (W.MessageBox.Show(this, "以本机配置替换所选目录的共享配置？替换前会保留加密备份。", "替换共享配置", W.MessageBoxButton.YesNo) != W.MessageBoxResult.Yes) return; try { string password = syncPassword.Password, folder = syncFolder.Text.Trim(); syncStatus.Text = (await Task.Run(() => ConfigurationSync.Upload(profile, folder, password, true))).Message; profile.Save(); } finally { syncPassword.Clear(); } })));
        syncStatus.Margin = new W.Thickness(0, 12, 0, 0); card.Children.Add(syncStatus); var backup = Card(page, "便携备份", "导入前显示摘要；导入后插件、TUN 和 HTTPS 保持停用，供你检查。");
        Row(backup, Button("导出 .swirl", () => Mutate(async () => { using var dialog = new SaveFileDialog { Filter = "Swirl 加密配置|*.swirl", FileName = "Swirl-config.swirl" }; if (dialog.ShowDialog(OwnerHandle) != System.Windows.Forms.DialogResult.OK) return; try { string password = syncPassword.Password; await Task.Run(() => ConfigurationSync.Export(profile, dialog.FileName, password)); syncStatus.Text = "加密备份已导出。"; } finally { syncPassword.Clear(); } })), Button("导入并检查", () => Mutate(async () => { using var dialog = new OpenFileDialog { Filter = "Swirl 加密配置|*.swirl" }; if (dialog.ShowDialog(OwnerHandle) != System.Windows.Forms.DialogResult.OK) return; try { string password = syncPassword.Password; ApplyIncoming(await Task.Run(() => ConfigurationSync.Import(dialog.FileName, password))); } finally { syncPassword.Clear(); } })));
    }
    private void BuildLogs()
    {
        var page = Page("logs", "运行记录", "连接检查与插件执行结果，不记录订阅地址或节点凭据。"); var card = Card(page, "本机活动"); log.IsReadOnly = true; log.AcceptsReturn = true; log.TextWrapping = W.TextWrapping.Wrap; log.VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto; log.Height = 450; log.FontFamily = new M.FontFamily("Cascadia Mono, Microsoft YaHei UI"); card.Children.Add(log); Row(card, Button("清空记录", () => { log.Clear(); return Task.CompletedTask; }));
    }
    private void BuildSettings()
    {
        var page = Page("settings", "偏好设置", "选择流量接管方式与窗口外观。"); var capture = Card(page, "连接方式", "连接时会检查 Windows 代理是否生效。TUN 需要管理员权限。"); capture.Children.Add(systemProxy); capture.Children.Add(tun); mode.ItemsSource = new[] { "规则分流", "全局代理", "全部直连" }; capture.Children.Add(mode);
        Row(capture, Button("保存连接设置", () => Mutate(() => { SaveFlags(); status.Text = "设置已保存，下次连接时生效。"; return Task.CompletedTask; }), true));
        var appearance = Card(page, "外观", "原生 Windows 11 Acrylic 背景，遵循系统透明效果设置。高对比度或不支持的系统会使用清晰背景。"); appearance.Children.Add(glass); glass.Click += (_, _) => { profile.GlassAppearance = glass.IsChecked == true; profile.Save(); ApplyBackdrop(); };
        var about = Card(page, "Swirl 0.7.1", "为 Windows 设计。部分 Loon 语法和脚本接口已兼容，插件导入后显示具体不兼容项。"); Row(about, Button("打开数据目录", () => { Directory.CreateDirectory(ProxyProfile.DirectoryPath); Process.Start(new ProcessStartInfo(ProxyProfile.DirectoryPath) { UseShellExecute = true }); return Task.CompletedTask; }));
    }
    private async Task StartAsync()
    {
        if (busy || controller.Running) return; busy = true; connect.IsEnabled = false; headline.Text = "正在建立连接"; status.Text = "正在检查配置与接管方式…";
        try { SaveFlags(); if (!profile.UseSystemProxy && !profile.Tun) throw new InvalidOperationException("请在偏好设置启用系统代理或 TUN，否则应用流量不会自动进入 Swirl。"); activeProfile = JsonSerializer.Deserialize<ProxyProfile>(JsonSerializer.Serialize(profile))!; await controller.StartAsync(activeProfile, profile.UseSystemProxy); if (closed) return; disconnect.IsEnabled = true; await LoadGroupsAsync(); RefreshSummary(); await ProbeAsync(); }
        catch { controller.Stop(); RefreshSummary(); throw; }
        finally { busy = false; if (!closed) { connect.IsEnabled = !controller.Running; disconnect.IsEnabled = controller.Running; } }
    }
    private Task UpdateSubscriptionAsync() => Mutate(async () =>
    {
        string source = subscriptionShown.Visibility == W.Visibility.Visible ? subscriptionShown.Text : subscription.Password;
        var selectedRoute = (SubscriptionDownloadRoute)subscriptionRoute.SelectedIndex;
        var selectedClient = (SubscriptionClientProfile)subscriptionClient.SelectedIndex;
        if (selectedRoute == SubscriptionDownloadRoute.Swirl && !controller.Running)
            throw new InvalidOperationException("请先保持 Swirl 连接，再通过 Swirl 代理更新订阅；首次导入请选择自动或当前系统代理。");
        var downloaded = await SubscriptionImport.DownloadRoutedAsync(source,
            selectedClient, selectedRoute, lifetime.Token,
            message => { if (!closed) { status.Text = message; Report(message); } });
        string yaml = MihomoConfig.ParseSubscription(downloaded.Content);
        profile.ProtectedYaml = ProxyProfile.Protect(yaml);
        profile.ProtectedSubscription = ProxyProfile.Protect(downloaded.NormalizedSource);
        profile.SubscriptionClient = selectedClient;
        profile.SubscriptionRoute = selectedRoute;
        profile.Save(); subscription.Password = downloaded.NormalizedSource; subscriptionShown.Text = downloaded.NormalizedSource;
        status.Text = controller.Running ? "新订阅已保存；当前连接保持原配置，重新连接后生效。" : "订阅已导入，请连接后选择节点。";
    }, allowConnected: true);
    private void Stop() { controller.Stop(); disconnect.IsEnabled = false; connect.IsEnabled = true; nodes.ItemsSource = null; groups.ItemsSource = null; selections.Clear(); RefreshSummary(); status.Text = "已断开连接，已尝试恢复原代理设置。"; }
    private async Task Mutate(Func<Task> action, bool allowConnected = false)
    {
        if (busy) return; if (controller.Running && !allowConnected) throw new InvalidOperationException("请先断开连接，再修改配置或插件。"); busy = true;
        try { await action(); RefreshSummary(); } finally { busy = false; }
    }
    private void SaveFlags() { profile.UseSystemProxy = systemProxy.IsChecked == true; profile.Tun = tun.IsChecked == true; profile.Mitm = mitm.IsChecked == true; profile.Mode = mode.SelectedIndex == 1 ? "global" : mode.SelectedIndex == 2 ? "direct" : "rule"; profile.BasicAds = false; profile.Save(); }
    private void LoadProfile()
    {
        try { subscription.Password = profile.Subscription; } catch { Report("保存的订阅地址无法解密，请重新导入。"); }
        subscriptionClient.SelectedIndex = (int)profile.SubscriptionClient; subscriptionRoute.SelectedIndex = (int)profile.SubscriptionRoute; systemProxy.IsChecked = profile.UseSystemProxy; tun.IsChecked = profile.Tun; mitm.IsChecked = profile.Mitm; glass.IsChecked = profile.GlassAppearance;
        mode.SelectedIndex = profile.Mode == "global" ? 1 : profile.Mode == "direct" ? 2 : 0; syncFolder.Text = profile.SyncFolder; RefreshPlugins(); SaveRules(false); RefreshSummary();
    }
    private async Task LoadGroupsAsync()
    {
        string? selected = groups.SelectedItem as string; nodeGroups = await controller.GroupsAsync(); selections = await controller.SelectionsAsync(); groups.ItemsSource = nodeGroups.Keys.ToArray(); groups.SelectedItem = selected != null && nodeGroups.ContainsKey(selected) ? selected : nodeGroups.Keys.FirstOrDefault(); FillNodes(); RefreshRoute();
    }
    private void FillNodes() { if (groups.SelectedItem is not string group || !nodeGroups.TryGetValue(group, out var values)) { nodes.ItemsSource = null; return; } nodes.ItemsSource = values; nodes.SelectedItem = selections.GetValueOrDefault(group); }
    private void RefreshRoute() { routeMetric.Text = !controller.Running ? "尚未连接" : selections.Count == 0 ? "没有可手动选择的策略组" : string.Join("\n", selections.Where(s => nodeGroups.ContainsKey(s.Key)).Take(3).Select(s => s.Key + "  →  " + s.Value)); }
    private async Task ProbeAsync()
    {
        if (!controller.Running) throw new InvalidOperationException("请先连接网络。"); diagnostic.Text = CaptureSummary() + "\n正在检测两个 HTTPS 地址…"; status.Text = "正在检测实际代理入口…";
        var results = await ConnectionHealth.ProbeAsync(lifetime.Token); if (closed || !controller.Running) return;
        int success = results.Count(r => r.Success); headline.Text = success > 0 ? "代理入口检测通过" : "核心运行中，网络检测未通过";
        detail.Text = success > 0 ? "检测地址可访问；其他应用的接管情况可在下方查看。" : "请检查当前线路、流量模式和接管方式，再重新检测。";
        diagnostic.Text = CaptureSummary() + "\n" + string.Join("\n", results.Select(r => r.Name + "  ·  " + r.Detail + (r.Success ? "  ·  " + r.Milliseconds + " ms" : ""))) + "\n" + PluginSummary();
        foreach (var result in results) Report("网络检查：" + result.Name + " · " + result.Detail); status.Text = success + "/2 个 HTTPS 检测地址可访问";
    }
    private string CaptureSummary()
    {
        string capture; try { capture = profile.UseSystemProxy ? WindowsSystemProxy.IsEnabled ? "Windows 系统代理：已确认生效" : "Windows 系统代理：未生效（可能被其他软件替换）" : "Windows 系统代理：未启用"; } catch { capture = "Windows 代理状态：无法读取"; }
        return "网络核心：" + (controller.Running ? "运行中" : "已停止") + "\n" + capture + "\n流量模式：" + (profile.Mode == "direct" ? "全部直连（不会通过代理节点）" : profile.Mode == "global" ? "全局代理" : "按订阅规则分流") + (profile.Tun ? " · TUN 已请求开启" : "");
    }
    private string PluginSummary() { int enabled = profile.Plugins.Count(p => p.Enabled && p.Unsupported.Count == 0); return enabled == 0 ? "去广告：没有启用插件，请到插件中心添加并启用。" : "插件：" + enabled + " 个已启用 · HTTPS 解密" + (profile.Mitm ? "已开启，实际命中见运行记录" : "未开启，HTTPS 重写脚本不会处理加密正文"); }
    private void RefreshSummary()
    {
        var summaryProfile = controller.Running ? activeProfile ?? profile : profile;
        pluginMetric.Text = profile.Plugins.Count(p => p.Enabled && p.Unsupported.Count == 0) + " / " + profile.Plugins.Count;
        if (!controller.Running) { headline.Text = "准备好，轻盈出发"; detail.Text = profile.ProtectedYaml.Length == 0 ? "先导入订阅，再连接网络。" : "已导入配置，连接后可查看实际线路与检测结果。"; diagnostic.Text = "网络核心：尚未连接\n" + PluginSummary(); uploadMetric.Text = downloadMetric.Text = "—"; }
        RefreshRoute(); string[] hosts; try { UserRouting.Prepare(summaryProfile); hosts = UserRouting.EffectivePlugins(summaryProfile).Where(p => p.Enabled && p.Unsupported.Count == 0).SelectMany(p => p.Hosts).Distinct().ToArray(); } catch { hosts = Array.Empty<string>(); }
        scope.Text = hosts.Length == 0 ? "尚无解密域名。启用含 MITM 设置的插件后显示。" : string.Join("\n", hosts);
    }
    private async Task PollAsync()
    {
        if (closed || polling || !controller.Running) { if (!closed && disconnect.IsEnabled && !busy && !controller.Running) { disconnect.IsEnabled = false; connect.IsEnabled = true; RefreshSummary(); headline.Text = "连接已停止"; } return; }
        polling = true; try { var traffic = await controller.TrafficAsync(); if (!closed) { uploadMetric.Text = FormatBytes(traffic.Upload); downloadMetric.Text = FormatBytes(traffic.Download); if (profile.UseSystemProxy && !WindowsSystemProxy.IsEnabled) { headline.Text = "Windows 代理被替换"; detail.Text = "请检查其他代理软件，断开后重新连接 Swirl。"; } } } catch { } finally { polling = false; }
    }
    private static string FormatBytes(long value) => value >= 1024 * 1024 * 1024 ? (value / 1073741824d).ToString("0.0") + " GB" : value >= 1024 * 1024 ? (value / 1048576d).ToString("0.0") + " MB" : (value / 1024d).ToString("0.0") + " KB";
    private async Task ImportPluginAsync(string address) { var plugin = LoonPlugin.Parse(await NetworkFetch.TextAsync(address), address); await plugin.DownloadScriptsAsync(); profile.Plugins.Add(plugin); profile.Save(); RefreshPlugins(plugin.Id); status.Text = "插件已导入，请查看兼容性并启用。"; }
    private void RefreshPlugins(string? selected = null) { plugins.ItemsSource = null; plugins.ItemsSource = profile.Plugins; plugins.SelectedItem = profile.Plugins.FirstOrDefault(p => p.Id == selected) ?? profile.Plugins.FirstOrDefault(); scriptPlugins.ItemsSource = null; scriptPlugins.ItemsSource = profile.Plugins; scriptPlugins.SelectedIndex = 0; ShowPlugin(); RefreshSummary(); }
    private void ShowPlugin() { if (plugins.SelectedItem is not LoonPlugin plugin) { pluginInfo.Text = "尚未安装插件。网络连接成功后，还需添加对应应用的插件才能处理广告。"; argument.Clear(); pluginPolicy.Clear(); return; } argument.Text = plugin.Argument; pluginPolicy.Text = plugin.ProxyPolicy; pluginInfo.Text = plugin.Name + " · " + (plugin.Enabled ? "已启用" : "未启用") + "\n规则 " + plugin.Rules.Count + " · 重写 " + plugin.Rewrites.Count + " · 脚本 " + plugin.Scripts.Count + "\nHTTPS 域名：" + string.Join(", ", plugin.Hosts) + "\n" + (plugin.Unsupported.Count > 0 ? string.Join("\n", plugin.Unsupported) : "语法可解析；实际目标应用效果以规则命中为准。"); }
    private UserRoutingRule EditedRule() { var rule = new UserRoutingRule { Kind = (string?)ruleKind.SelectedItem ?? "DOMAIN-SUFFIX", Policy = (string?)rulePolicy.SelectedItem ?? "DIRECT", Value = ruleValue.Text, Ssid = ruleSsid.IsEnabled ? ruleSsid.Text : "", HttpsHosts = ruleHosts.IsEnabled ? ruleHosts.Text : "" }; rule.Validate(); return rule; }
    private void SaveRules(bool save = true) { profile.RoutingSnapshot = null; if (save) profile.Save(); rules.ItemsSource = null; rules.ItemsSource = profile.UserRules; rulePolicy.ItemsSource = UserRouting.Policies(profile); rulePolicy.SelectedIndex = 0; RefreshSummary(); }
    private Task MoveRule(int direction) { int old = rules.SelectedIndex, next = old + direction; if (old >= 0 && next >= 0 && next < profile.UserRules.Count) { var rule = profile.UserRules[old]; profile.UserRules.RemoveAt(old); profile.UserRules.Insert(next, rule); SaveRules(); rules.SelectedItem = rule; } return Task.CompletedTask; }
    private void ApplyIncoming(ProxyProfile incoming) { if (W.MessageBox.Show(this, ConfigurationSync.Summary(incoming) + "\n\n替换本机配置？", "检查导入配置", W.MessageBoxButton.YesNo) != W.MessageBoxResult.Yes) return; string current = Path.Combine(ProxyProfile.DirectoryPath, "profile.json"); if (File.Exists(current)) File.Copy(current, Path.Combine(ProxyProfile.DirectoryPath, "profile-before-import-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + ".json")); ConfigurationSync.Apply(profile, incoming); profile.Save(); LoadProfile(); syncStatus.Text = "配置已导入，请检查插件与 HTTPS 设置。"; }
    private void Report(string text) { if (closed) return; if (!Dispatcher.CheckAccess()) { Dispatcher.BeginInvoke(() => Report(text)); return; } if (log.Text.Length > 40000) log.Text = log.Text[^20000..]; log.AppendText(DateTime.Now.ToString("HH:mm:ss") + "  " + text.Replace("AdShield", "Swirl", StringComparison.Ordinal) + Environment.NewLine); log.ScrollToEnd(); }
    private System.Windows.Forms.IWin32Window OwnerHandle => new WindowOwner(new WindowInteropHelper(this).Handle);
    private sealed record WindowOwner(IntPtr Handle) : System.Windows.Forms.IWin32Window;
}
