using System.Diagnostics;

namespace AdShield.Network;

internal sealed class ProxyPanel : UserControl
{
    private ProxyProfile profile = ProxyProfile.Load();
    private readonly ProxyController controller;
    private readonly Panel content = new() { Dock = DockStyle.Fill, BackColor = SwirlTheme.Canvas };
    private readonly Panel pageHost = new() { Dock = DockStyle.Fill, BackColor = SwirlTheme.Canvas };
    private readonly Dictionary<string, FlowLayoutPanel> pages = new();
    private readonly Dictionary<string, SwirlNav> navigation = new();
    private readonly TextBox subscription = new() { Width = 620, UseSystemPasswordChar = true, PlaceholderText = "HTTPS 订阅地址或 Clash 一键导入链接" };
    private readonly ComboBox subscriptionClient = new() { Width = 320, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox pluginUrl = new() { Width = 620, PlaceholderText = "插件原作者链接，或 loon://import?plugin=…" };
    private readonly ComboBox mode = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 200 };
    private readonly ComboBox groups = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 260 };
    private readonly ComboBox nodes = new() { DropDownStyle = ComboBoxStyle.DropDownList, Width = 340 };
    private Dictionary<string, string[]> nodeGroups = new();
    private readonly CheckBox systemProxy = new() { Text = "系统代理", AutoSize = true, Checked = true };
    private readonly CheckBox tun = new() { Text = "TUN · 接管应用网络", AutoSize = true };
    private readonly CheckBox mitm = new() { Text = "HTTPS 解密 · 仅插件指定域名", AutoSize = true };
    private readonly ListBox pluginList = new() { Width = 620, Height = 188, BorderStyle = BorderStyle.None, DrawMode = DrawMode.OwnerDrawFixed, ItemHeight = 48 };
    private readonly TextBox pluginInfo = new() { Width = 620, Height = 142, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical };
    private readonly TextBox argument = new() { Width = 620, PlaceholderText = "脚本 $argument，可留空" };
    private readonly TextBox pluginPolicy = new() { Width = 320, PlaceholderText = "默认节点组，或填写策略组名称" };
    private readonly ComboBox scriptPlugins = new() { Width = 260, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox tasks = new() { Width = 330, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox log = new() { Width = 620, Height = 430, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false };
    private readonly Label status = new() { Dock = DockStyle.Bottom, Height = 36, Padding = new Padding(32, 9, 12, 0), ForeColor = SwirlTheme.Muted, BackColor = SwirlTheme.Canvas, AutoEllipsis = true };
    private readonly SwirlButton start = new() { Text = "连接网络", Primary = true };
    private readonly SwirlButton stop = new() { Text = "断开连接", Enabled = false };
    private readonly Label connectionTitle = new() { AutoSize = true, Font = SwirlTheme.Font(24, FontStyle.Bold), Text = "准备好，轻盈出发", BackColor = Color.Transparent };
    private readonly Label connectionDetail = new() { AutoSize = true, Text = "导入订阅与插件，开启属于你的网络。", ForeColor = SwirlTheme.Muted, BackColor = Color.Transparent };
    private readonly Label pluginCount = new() { AutoSize = true, BackColor = Color.Transparent };
    private readonly Label hostCount = new() { AutoSize = true, BackColor = Color.Transparent };
    private readonly Label configSummary = new() { AutoSize = true, BackColor = Color.Transparent };
    private readonly Label protocolSummary = new() { AutoSize = true, BackColor = Color.Transparent };
    private readonly Label hosts = new() { AutoSize = true, MaximumSize = new Size(620, 0), BackColor = Color.Transparent };
    private readonly ListBox routingRules = new() { Width = 620, Height = 165, BorderStyle = BorderStyle.None, HorizontalScrollbar = true };
    private readonly ComboBox ruleKind = new() { Width = 240, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly ComboBox rulePolicy = new() { Width = 300, DropDownStyle = ComboBoxStyle.DropDownList };
    private readonly TextBox ruleValue = new() { Width = 620, PlaceholderText = "域名、IP 网段、URL 正则，或准确的 Wi-Fi 名称" };
    private readonly TextBox ruleSsid = new() { Width = 620, PlaceholderText = "仅在此 Wi-Fi 下生效，可留空" };
    private readonly TextBox ruleHttpsHosts = new() { Width = 620, PlaceholderText = "HTTPS URL 规则的解密域名，用英文逗号分隔" };
    private readonly Label wifiStatus = new() { AutoSize = true };
    private readonly TextBox syncFolder = new() { Width = 620, PlaceholderText = "云盘同步目录，或你选择的共享文件夹" };
    private readonly TextBox syncPassword = new() { Width = 620, UseSystemPasswordChar = true, PlaceholderText = "至少 12 个字符的加密密码，不会保存在配置中" };
    private readonly Label syncStatus = new() { AutoSize = true, MaximumSize = new Size(620, 0) };
    private bool busy, disposed;

    internal ProxyPanel()
    {
        AutoScaleMode = AutoScaleMode.Dpi; AutoScaleDimensions = new SizeF(96, 96);
        Dock = DockStyle.Fill; BackColor = SwirlTheme.Canvas; Font = SwirlTheme.Font(); ForeColor = SwirlTheme.Ink;
        controller = new ProxyController(Report);
        var sidebar = new Panel { Dock = DockStyle.Left, Width = 232, BackColor = SwirlTheme.Sidebar };
        var links = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(16, 15, 16, 0), BackColor = SwirlTheme.Sidebar };
        var sidebarLayout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, ColumnCount = 1, BackColor = SwirlTheme.Sidebar, Margin = Padding.Empty, Padding = Padding.Empty };
        sidebarLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); sidebarLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 66));
        sidebarLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); links.Margin = Padding.Empty;
        sidebar.Controls.Add(sidebarLayout); sidebarLayout.Controls.Add(links, 0, 0);
        links.Controls.Add(new SwirlBrand());
        links.Controls.Add(new Label { Text = "工作空间", Font = SwirlTheme.Font(8), ForeColor = SwirlTheme.Muted, AutoSize = true, Margin = new Padding(13, 12, 0, 8) });
        foreach (var (key, name, symbol) in new[] { ("overview", "概览", "◈"), ("nodes", "代理节点", "◎"), ("plugins", "插件中心", "◇"), ("routing", "规则分流", "⇄"), ("https", "HTTPS 解密", "♧"), ("scripts", "脚本任务", "⌘"), ("sync", "配置同步", "☁"), ("logs", "运行记录", "≡"), ("settings", "偏好设置", "⚙") })
        {
            var nav = new SwirlNav { Text = name, Symbol = symbol, AccessibleName = name };
            navigation.Add(key, nav); nav.Click += (_, _) => SelectPage(key); links.Controls.Add(nav);
        }
        var footer = new Label { Text = "SWIRL  0.6.1\nWindows · Mihomo", ForeColor = SwirlTheme.Muted, Font = SwirlTheme.Font(8), Dock = DockStyle.Fill, Padding = new Padding(28, 16, 0, 0), BackColor = SwirlTheme.Sidebar, Margin = Padding.Empty };
        sidebarLayout.Controls.Add(footer, 0, 1);
        Controls.Add(content); Controls.Add(sidebar);
        var contentLayout = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 2, ColumnCount = 1, BackColor = SwirlTheme.Canvas, Padding = Padding.Empty, Margin = Padding.Empty };
        contentLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); contentLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 36)); contentLayout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        pageHost.Margin = Padding.Empty; status.Dock = DockStyle.Fill; status.Margin = Padding.Empty;
        content.Controls.Add(contentLayout); contentLayout.Controls.Add(pageHost, 0, 0); contentLayout.Controls.Add(status, 0, 1);
        BuildOverview(); BuildNodes(); BuildPlugins(); BuildRouting(); BuildHttps(); BuildScripts(); BuildSync(); BuildLogs(); BuildSettings();
        foreach (Control control in new Control[] { subscription, subscriptionClient, pluginUrl, mode, groups, nodes, systemProxy, tun, mitm, pluginList, pluginInfo, argument, pluginPolicy, scriptPlugins, tasks, log, routingRules, ruleKind, rulePolicy, ruleValue, ruleSsid, ruleHttpsHosts, wifiStatus, syncFolder, syncPassword, syncStatus }) SwirlTheme.Prepare(control);
        foreach (var field in new[] { subscription, pluginUrl, pluginInfo, argument, pluginPolicy, log, ruleValue, ruleSsid, ruleHttpsHosts, syncFolder, syncPassword }) WrapField(field);
        log.Font = new Font("Cascadia Mono", 9); log.BackColor = Color.FromArgb(251, 252, 255);
        mode.Items.AddRange(new object[] { "规则分流", "全局代理", "全部直连" });
        groups.SelectedIndexChanged += (_, _) => { nodes.Items.Clear(); if (groups.SelectedItem is string group && nodeGroups.TryGetValue(group, out var values)) nodes.Items.AddRange(values); if (nodes.Items.Count > 0) nodes.SelectedIndex = 0; };
        pluginList.DrawItem += DrawPlugin;
        pluginList.SelectedIndexChanged += (_, _) => ShowPlugin();
        scriptPlugins.SelectedIndexChanged += (_, _) => { tasks.Items.Clear(); if (scriptPlugins.SelectedItem is LoonPlugin plugin) tasks.Items.AddRange(plugin.Scripts.Where(s => s.Phase == "generic").Cast<object>().ToArray()); if (tasks.Items.Count > 0) tasks.SelectedIndex = 0; };
        start.Click += async (_, _) => await StartAsync();
        stop.Click += (_, _) => Stop();
        LoadProfile(); SelectPage("overview");
        status.Text = File.Exists(ProxyController.CorePath) ? "Mihomo 核心已就绪 · 尚未连接" : "请完整安装 Swirl，以加载网络核心。";
        AutoScaleDimensions = new SizeF(96, 96);
        PerformAutoScale();
    }

    private void BuildOverview()
    {
        var page = Page("overview", "概览", "把连接、分流与插件，放在同一处。 ");
        var hero = new SwirlHero();
        connectionTitle.Location = new Point(26, 35); connectionDetail.Location = new Point(28, 89);
        start.Location = new Point(28, 132); stop.Location = new Point(155, 132);
        hero.Controls.AddRange(new Control[] { connectionTitle, connectionDetail, start, stop }); page.Controls.Add(hero);
        var summary = Card(page, "你的工作空间", "所有信息来自当前配置。连接后，在代理节点中选择实际使用的线路。");
        pluginCount.Font = SwirlTheme.Font(13, FontStyle.Bold); hostCount.Font = SwirlTheme.Font(11); configSummary.Font = SwirlTheme.Font(11);
        summary.Controls.Add(pluginCount); summary.Controls.Add(hostCount); summary.Controls.Add(configSummary);
        Row(summary, Button("导入订阅", () => { SelectPage("nodes"); return Task.CompletedTask; }), Button("添加插件", () => { SelectPage("plugins"); return Task.CompletedTask; }));
        var routes = Card(page, "一条完整的处理链", "应用网络 → 规则分流 → 插件与 HTTPS 解密 → 代理节点");
        Note(routes, "TUN 与 HTTPS 可以同时开启。网络去广告通过插件处理请求和响应；你可以随时查看域名范围、规则与脚本。");
    }
    private void BuildNodes()
    {
        var page = Page("nodes", "代理节点", "导入自己的订阅，选择适合当前网络的线路。");
        var input = Card(page, "订阅与配置", "支持 Clash / Mihomo YAML，地址在本机加密保存。");
        input.Controls.Add(subscription);
        subscriptionClient.Items.AddRange(new object[] { "Mihomo / Clash Meta（推荐）", "Clash 兼容", "浏览器请求" });
        Row(input, new Label { Text = "订阅请求类型", AutoSize = true, Padding = new Padding(0, 7, 8, 0) }, subscriptionClient);
        Note(input, "若相同链接能在其他 Clash 客户端导入，可切换请求类型再更新。支持完整 HTTPS 链接和 Clash 一键导入链接。");
        Row(input, Button("更新订阅", async () => await Mutate(async () =>
        {
            var clientProfile = subscriptionClient.SelectedIndex switch { 1 => SubscriptionClientProfile.Clash, 2 => SubscriptionClientProfile.Browser, _ => SubscriptionClientProfile.Mihomo };
            status.Text = "正在下载并检查订阅…";
            var downloaded = await SubscriptionImport.DownloadAsync(subscription.Text, clientProfile);
            string yaml = MihomoConfig.ParseSubscription(downloaded.Content);
            profile.ProtectedYaml = ProxyProfile.Protect(yaml); profile.ProtectedSubscription = ProxyProfile.Protect(downloaded.NormalizedSource); profile.SubscriptionClient = clientProfile;
            profile.Save(); subscription.Text = downloaded.NormalizedSource; RefreshSummary(); status.Text = "订阅已导入，可以连接并选择节点。";
        }), true), Button("导入配置文件", async () => await Mutate(async () =>
        {
            using var dialog = new OpenFileDialog { Filter = "Clash / Mihomo 配置|*.yaml;*.yml|所有文件|*.*" };
            if (dialog.ShowDialog(this) != DialogResult.OK) return;
            if (new FileInfo(dialog.FileName).Length > 4 * 1024 * 1024) throw new InvalidOperationException("配置文件超过 4 MB。");
            string yaml = MihomoConfig.ParseSubscription(await File.ReadAllTextAsync(dialog.FileName)); profile.ProtectedYaml = ProxyProfile.Protect(yaml); profile.Save(); RefreshSummary(); status.Text = "配置已导入，原有节点组与分流规则会保留。";
        })), Button("显示地址", () => { subscription.UseSystemPasswordChar = !subscription.UseSystemPasswordChar; return Task.CompletedTask; }));
        var selection = Card(page, "策略组与节点", "连接后加载节点。测速反映当前网络的响应时间。");
        Row(selection, groups, nodes);
        Row(selection, Button("切换节点", async () =>
        {
            if (!controller.Running) { status.Text = "请先连接网络，再选择节点。"; return; }
            if (groups.SelectedItem is not string group || nodes.SelectedItem is not string node) return;
            try { await controller.SelectAsync(group, node); status.Text = "已切换至 " + node; } catch { status.Text = "切换失败，请确认核心仍在运行。"; }
        }, true), Button("测试延迟", async () =>
        {
            if (!controller.Running || nodes.SelectedItem is not string node) { status.Text = "请先连接并选择节点。"; return; }
            try { status.Text = node + " · " + await controller.DelayAsync(node) + " ms"; } catch { status.Text = "测速失败或超时。"; }
        }), Button("连接网络", StartAsync));
        var protocol = Card(page, "多种协议，一份配置", "Mihomo 提供协议支持，节点与凭据使用你的订阅配置。");
        Note(protocol, "SS / SS2022 / SSR · VMess / VLESS · Trojan\nHysteria 2 · WireGuard · HTTP(S) / SOCKS5");
        protocol.Controls.Add(protocolSummary);
    }
    private void BuildPlugins()
    {
        var page = Page("plugins", "插件中心", "按需启用插件，让网络更清爽。");
        var input = Card(page, "添加插件", "从原作者链接、可莉目录或本地文件导入。"); input.Controls.Add(pluginUrl);
        Row(input, Button("链接导入", async () => await Mutate(async () =>
        {
            string address = LoonPlugin.ResolveImportUrl(pluginUrl.Text.Trim());
            if (new Uri(address).Host.Equals("hub.kelee.one", StringComparison.OrdinalIgnoreCase)) { var selected = await PluginCatalog.ChooseAsync(this); if (selected == null) return; address = selected; }
            await ImportPluginAsync(address);
        }), true), Button("浏览可莉目录", async () => await Mutate(async () => { var address = await PluginCatalog.ChooseAsync(this); if (address != null) await ImportPluginAsync(address); })), Button("本地文件", async () => await Mutate(async () =>
        {
            using var dialog = new OpenFileDialog { Filter = "Loon 明文插件|*.lpx;*.plugin;*.conf|所有文件|*.*" }; if (dialog.ShowDialog(this) != DialogResult.OK) return;
            var plugin = LoonPlugin.Parse(await File.ReadAllTextAsync(dialog.FileName), "本地文件"); await plugin.DownloadScriptsAsync(); profile.Plugins.Add(plugin); profile.Save(); RefreshPlugins();
        })));
        var library = Card(page, "已安装", "导入后默认停用。先查看兼容性与 HTTPS 域名，再决定是否启用。");
        library.Controls.Add(pluginList);
        Row(library, Button("启用 / 停用", async () => await Mutate(() =>
        {
            if (pluginList.SelectedItem is LoonPlugin plugin) { if (plugin.Unsupported.Count > 0) throw new InvalidOperationException("此插件含不支持的语法，请查看下方兼容性信息。"); plugin.Enabled = !plugin.Enabled; profile.Save(); RefreshPlugins(plugin.Id); }
            return Task.CompletedTask;
        }), true), Button("更新插件", async () => await Mutate(async () =>
        {
            if (pluginList.SelectedItem is not LoonPlugin old || !old.Source.StartsWith("https://")) return;
            var updated = LoonPlugin.Parse(await NetworkFetch.TextAsync(old.Source), old.Source); await updated.DownloadScriptsAsync(); updated.Id = old.Id; updated.Argument = old.Argument; updated.ProtectedParameterValues = old.ProtectedParameterValues; updated.ProxyPolicy = old.ProxyPolicy; updated.Enabled = false;
            profile.Plugins[profile.Plugins.IndexOf(old)] = updated; profile.Save(); RefreshPlugins(updated.Id);
        })), Button("移除", async () => await Mutate(() => { if (pluginList.SelectedItem is LoonPlugin plugin) { profile.Plugins.Remove(plugin); profile.Save(); RefreshPlugins(); } return Task.CompletedTask; })));
        library.Controls.Add(pluginInfo);
        var parameters = Card(page, "插件参数", "保留作者提供的参数控件，也可以设置脚本参数与代理策略。");
        parameters.Controls.Add(argument);
        Row(parameters, Button("参数控件", async () => await Mutate(() => { if (pluginList.SelectedItem is LoonPlugin plugin && PluginParameterEditor.Edit(this, plugin)) { profile.Save(); status.Text = "插件参数已保存。"; } return Task.CompletedTask; })), pluginPolicy);
        Row(parameters, Button("保存参数", async () => await Mutate(() => { if (pluginList.SelectedItem is LoonPlugin plugin) { plugin.Argument = argument.Text; plugin.ProxyPolicy = pluginPolicy.Text.Trim(); profile.Save(); status.Text = "参数与策略已保存，下次连接时生效。"; } return Task.CompletedTask; }), true));
    }
    private void BuildHttps()
    {
        var page = Page("https", "HTTPS 解密", "只处理你启用的插件指定的域名。");
        var setup = Card(page, "证书与开关", "首次使用 HTTPS 脚本，需要信任本机生成的插件证书。"); setup.Controls.Add(mitm);
        Row(setup, Button("信任插件证书", async () => await Mutate(() =>
        {
            UserRouting.Prepare(profile);
            var effective = UserRouting.EffectivePlugins(profile).ToArray();
            string scope = string.Join("、", effective.Where(p => p.Enabled && p.Unsupported.Count == 0).SelectMany(p => p.Hosts).Distinct());
            if (scope.Length == 0) throw new InvalidOperationException("请先启用包含 MITM hostname 的插件。");
            if (MessageBox.Show(this, "HTTPS 插件将读取这些域名的解密流量：\n\n" + scope + "\n\n是否信任 Swirl 本机插件证书？", "信任插件证书", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return Task.CompletedTask;
            using var proxy = new PluginProxy(effective, true, Report); proxy.TrustCertificate(); status.Text = "证书已信任，可以开启 HTTPS 解密。"; return Task.CompletedTask;
        }), true), Button("移除证书", async () => await Mutate(() => { using var proxy = new PluginProxy(Array.Empty<LoonPlugin>(), false, Report); proxy.RemoveCertificate(); mitm.Checked = false; profile.Mitm = false; profile.Save(); status.Text = "插件证书已移除。"; return Task.CompletedTask; })));
        var scopeCard = Card(page, "当前域名范围", "范围随启用的插件更新，排除规则由所属插件控制。"); scopeCard.Controls.Add(hosts);
        var note = Card(page, "与 TUN 协同", "TUN 接管的 HTTP(S) 流量也经过插件入口。");
        Note(note, "支持 HTTP/2 解密与插件处理。正文脚本处理 2 MB 内且长度明确的请求和响应，视频与流式内容原样转发。存在证书固定的应用可能不接受本机证书。");
    }
    private void BuildScripts()
    {
        var page = Page("scripts", "脚本任务", "查看插件任务，按需运行手动脚本。");
        var manual = Card(page, "手动运行", "选择插件，再选择作者声明的通用脚本。"); Row(manual, scriptPlugins, tasks);
        Row(manual, Button("运行脚本", async () =>
        {
            if (scriptPlugins.SelectedItem is not LoonPlugin plugin || tasks.SelectedItem is not LoonScript script) { status.Text = "当前插件没有可手动运行的脚本。"; return; }
            try { await controller.RunTaskAsync(plugin, script); status.Text = "脚本已完成，详情见运行记录。"; } catch (Exception e) { status.Text = e.Message; }
        }, true), Button("查看运行记录", () => { SelectPage("logs"); return Task.CompletedTask; }));
        var scheduled = Card(page, "后台任务", "Cron 与网络变化脚本在代理运行、所属插件启用时触发。");
        Note(scheduled, "停止连接会取消后台任务。同一任务不会重叠执行，最多同时运行 4 个；插件参数可以控制条件、超时与脚本对象参数。");
    }
    private void BuildLogs()
    {
        var page = Page("logs", "运行记录", "查看连接状态、插件处理结果与脚本通知。");
        var card = Card(page, "活动记录", "仅本机显示。订阅地址、节点凭据和原始核心输出不会写入这里。");
        Row(card, Button("清空记录", () => { log.Clear(); return Task.CompletedTask; })); card.Controls.Add(log);
    }
    private void BuildSettings()
    {
        var page = Page("settings", "偏好设置", "决定 Swirl 如何接管和处理你的网络。");
        var capture = Card(page, "连接方式", "TUN 需要管理员权限；系统代理适用于遵循 Windows 代理设置的应用。");
        capture.Controls.Add(systemProxy); capture.Controls.Add(tun); Row(capture, new Label { Text = "流量模式", AutoSize = true, Margin = new Padding(0, 9, 15, 0) }, mode);
        Row(capture, Button("保存设置", async () => await Mutate(() => { SaveFlags(); status.Text = "设置已保存，下次连接时生效。"; return Task.CompletedTask; }), true));
        var about = Card(page, "Swirl 0.6.1", "为 Windows 设计的代理与插件工作空间。");
        Note(about, "使用 Mihomo 网络核心与本机插件处理器。当前兼容部分 Loon 插件语法和脚本接口；导入时会显示具体不兼容项。");
        Row(about, Button("打开数据目录", () => { Directory.CreateDirectory(ProxyProfile.DirectoryPath); Process.Start(new ProcessStartInfo(ProxyProfile.DirectoryPath) { UseShellExecute = true }); return Task.CompletedTask; }), Button("作者插件中心", () => { Process.Start(new ProcessStartInfo("https://hub.kelee.one/") { UseShellExecute = true }); return Task.CompletedTask; }));
    }
    private void BuildRouting()
    {
        var page = Page("routing", "规则分流", "按域名、地址、URL 与 Wi-Fi 网络决定流量去向。");
        var list = Card(page, "自定义规则", "URL 规则优先匹配；域名、IP 与 SSID 规则按列表顺序匹配。");
        list.Controls.Add(wifiStatus); list.Controls.Add(routingRules);
        Row(list, Button("启用 / 停用", async () => await Mutate(() =>
        {
            if (routingRules.SelectedItem is UserRoutingRule rule) { rule.Enabled = !rule.Enabled; SaveRules(rule.Id); }
            return Task.CompletedTask;
        })), Button("上移", async () => await Mutate(() => MoveRule(-1))), Button("下移", async () => await Mutate(() => MoveRule(1))), Button("移除", async () => await Mutate(() =>
        {
            if (routingRules.SelectedItem is UserRoutingRule rule) { profile.UserRules.Remove(rule); SaveRules(); } return Task.CompletedTask;
        })));
        var editor = Card(page, "编辑规则", "域名与 IP 在核心分流；HTTPS URL 路径需解密域名、证书与 HTTPS 开关。");
        Note(editor, "DIRECT 为直连，REJECT 为拦截；PROXY 使用 Swirl 节点，也可选择订阅中的策略组。");
        ruleKind.Items.AddRange(new object[] { "DOMAIN-SUFFIX", "DOMAIN", "IP-CIDR", "IP-CIDR6", "URL-REGEX", "SSID" }); ruleKind.SelectedIndex = 0;
        Row(editor, ruleKind, rulePolicy); editor.Controls.Add(ruleValue); editor.Controls.Add(ruleSsid); editor.Controls.Add(ruleHttpsHosts);
        Row(editor, Button("添加规则", async () => await Mutate(() =>
        {
            var rule = EditedRule(); profile.UserRules.Add(rule); SaveRules(rule.Id); return Task.CompletedTask;
        }), true), Button("保存修改", async () => await Mutate(() =>
        {
            if (routingRules.SelectedItem is not UserRoutingRule old) return Task.CompletedTask;
            var rule = EditedRule(); rule.Id = old.Id; rule.Enabled = old.Enabled; profile.UserRules[profile.UserRules.IndexOf(old)] = rule; SaveRules(rule.Id); return Task.CompletedTask;
        })));
        routingRules.SelectedIndexChanged += (_, _) =>
        {
            if (routingRules.SelectedItem is not UserRoutingRule rule) return;
            ruleKind.SelectedItem = rule.Kind; ruleValue.Text = rule.Value; ruleSsid.Text = rule.Ssid; ruleHttpsHosts.Text = rule.HttpsHosts;
            if (!rulePolicy.Items.Contains(rule.Policy)) rulePolicy.Items.Add(rule.Policy); rulePolicy.SelectedItem = rule.Policy;
        };
        ruleKind.SelectedIndexChanged += (_, _) => { ruleHttpsHosts.Enabled = ruleKind.SelectedItem?.ToString() == "URL-REGEX"; ruleSsid.Enabled = ruleKind.SelectedItem?.ToString() != "SSID"; };
        ruleHttpsHosts.Enabled = false;
        var note = Card(page, "Wi-Fi 条件", "SSID 规则匹配当前主连接的准确 Wi-Fi 名称。");
        Note(note, "网络条件在连接时读取。更换 Wi-Fi 后，请重新连接以应用新条件；无法读取 Wi-Fi 名称时不会匹配对应规则。URL 规则选中的策略优先于核心中的域名与插件分流规则。");
    }
    private void BuildSync()
    {
        var page = Page("sync", "配置同步", "加密备份订阅、规则与插件，在你的 Windows 设备间共享。");
        var card = Card(page, "加密同步", "使用你选择的文件夹或云盘同步目录，密码不会保存在配置中。");
        card.Controls.Add(syncFolder);
        Row(card, Button("选择目录", () =>
        {
            using var dialog = new FolderBrowserDialog { Description = "选择你的云盘同步目录或共享文件夹", UseDescriptionForTitle = true };
            if (dialog.ShowDialog(this) == DialogResult.OK) syncFolder.Text = dialog.SelectedPath;
            return Task.CompletedTask;
        }), Button("查看状态", () => { try { syncStatus.Text = ConfigurationSync.GetStatus(profile, syncFolder.Text.Trim()).Message; } catch (Exception e) { syncStatus.Text = e.Message; } return Task.CompletedTask; }));
        card.Controls.Add(syncPassword);
        Row(card, Button("上传到目录", async () => await Mutate(async () =>
        {
            string password = syncPassword.Text; string folder = syncFolder.Text.Trim();
            try { var result = await Task.Run(() => ConfigurationSync.Upload(profile, folder, password)); profile.Save(); syncStatus.Text = result.Message; }
            finally { syncPassword.Clear(); }
        }), true), Button("下载并检查", async () => await Mutate(async () =>
        {
            string password = syncPassword.Text; string folder = syncFolder.Text.Trim();
            try { var incoming = await Task.Run(() => ConfigurationSync.Download(folder, password)); ApplyIncoming(incoming); }
            finally { syncPassword.Clear(); }
        })));
        card.Controls.Add(syncStatus);
        Row(card, Button("备份并替换目录配置", async () => await Mutate(async () =>
        {
            string folder = syncFolder.Text.Trim();
            if (MessageBox.Show(this, "将以本机当前配置替换这个目录里的共享配置：\n\n" + folder + "\n\n替换前会保存上一份加密文件。其他设备需要重新下载。", "替换共享配置", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
            string password = syncPassword.Text;
            try { var result = await Task.Run(() => ConfigurationSync.Upload(profile, folder, password, true)); profile.Save(); syncStatus.Text = result.Message; }
            finally { syncPassword.Clear(); }
        })));
        var backup = Card(page, "便携备份", "导出加密 .swirl 文件，或在另一台 Windows 设备导入。");
        Row(backup, Button("导出加密配置", async () => await Mutate(async () =>
        {
            using var dialog = new SaveFileDialog { Filter = "Swirl 加密配置|*.swirl", FileName = "Swirl-config.swirl" }; if (dialog.ShowDialog(this) != DialogResult.OK) return;
            string password = syncPassword.Text;
            try { await Task.Run(() => ConfigurationSync.Export(profile, dialog.FileName, password)); syncStatus.Text = "已导出加密配置。请妥善保存密码。"; }
            finally { syncPassword.Clear(); }
        })), Button("导入并检查", async () => await Mutate(async () =>
        {
            using var dialog = new OpenFileDialog { Filter = "Swirl 加密配置|*.swirl|所有文件|*.*" }; if (dialog.ShowDialog(this) != DialogResult.OK) return;
            string password = syncPassword.Text;
            try { var incoming = await Task.Run(() => ConfigurationSync.Import(dialog.FileName, password)); ApplyIncoming(incoming); }
            finally { syncPassword.Clear(); }
        })));
        Note(backup, "同步由你手动上传与下载，云端传输由云盘客户端完成。导入前显示配置摘要；导入后 TUN、HTTPS 与插件均保持停用，待你检查后再启用。");
    }

    private UserRoutingRule EditedRule()
    {
        var rule = new UserRoutingRule { Kind = ruleKind.SelectedItem?.ToString() ?? "DOMAIN-SUFFIX", Value = ruleValue.Text, Policy = rulePolicy.SelectedItem?.ToString() ?? "DIRECT", Ssid = ruleSsid.Enabled ? ruleSsid.Text : "", HttpsHosts = ruleHttpsHosts.Enabled ? ruleHttpsHosts.Text.Trim() : "" };
        rule.Validate(); return rule;
    }
    private Task MoveRule(int direction)
    {
        int index = routingRules.SelectedIndex; int next = index + direction;
        if (index >= 0 && next >= 0 && next < profile.UserRules.Count) { var rule = profile.UserRules[index]; profile.UserRules.RemoveAt(index); profile.UserRules.Insert(next, rule); SaveRules(rule.Id); }
        return Task.CompletedTask;
    }
    private void SaveRules(string? selected = null) { profile.RoutingSnapshot = null; profile.Save(); RefreshRules(selected); RefreshSummary(); status.Text = "规则已保存，下次连接时生效。"; }
    private void RefreshRules(string? selected = null)
    {
        rulePolicy.Items.Clear(); rulePolicy.Items.AddRange(UserRouting.Policies(profile)); if (rulePolicy.Items.Count > 0) rulePolicy.SelectedIndex = 0;
        routingRules.Items.Clear(); foreach (var rule in profile.UserRules) routingRules.Items.Add(rule);
        if (routingRules.Items.Count > 0) routingRules.SelectedIndex = Math.Max(0, profile.UserRules.FindIndex(r => r.Id == selected));
        string ssid = UserRouting.ReadCurrentSsid(); wifiStatus.Text = ssid.Length == 0 ? "当前 Wi-Fi：未连接或名称不可用" : "当前 Wi-Fi：" + ssid;
    }
    private void ApplyIncoming(ProxyProfile incoming)
    {
        if (MessageBox.Show(this, ConfigurationSync.Summary(incoming) + "\n\n是否替换本机当前配置？", "检查导入配置", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
        Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        string current = Path.Combine(ProxyProfile.DirectoryPath, "profile.json");
        if (File.Exists(current)) File.Copy(current, Path.Combine(ProxyProfile.DirectoryPath, "profile-before-import-" + DateTime.Now.ToString("yyyyMMdd-HHmmss-fff") + ".json"));
        ConfigurationSync.Apply(profile, incoming); profile.Save(); LoadProfile(); syncStatus.Text = "已导入配置。请在插件、规则与 HTTPS 页面检查后启用。"; status.Text = syncStatus.Text;
    }

    private async Task ImportPluginAsync(string address)
    {
        var plugin = LoonPlugin.Parse(await NetworkFetch.TextAsync(address), address); await plugin.DownloadScriptsAsync(); profile.Plugins.Add(plugin); profile.Save(); pluginUrl.Text = address; RefreshPlugins(plugin.Id); status.Text = "插件已导入，请查看兼容性后启用。";
    }
    private void LoadProfile()
    {
        try { subscription.Text = profile.Subscription; } catch { status.Text = "订阅无法解密，请重新导入。"; }
        subscriptionClient.SelectedIndex = profile.SubscriptionClient switch { SubscriptionClientProfile.Clash => 1, SubscriptionClientProfile.Browser => 2, _ => 0 };
        mode.SelectedIndex = profile.Mode == "global" ? 1 : profile.Mode == "direct" ? 2 : 0;
        tun.Checked = profile.Tun; mitm.Checked = profile.Mitm; syncFolder.Text = profile.SyncFolder; RefreshPlugins(); RefreshRules();
    }
    private void SaveFlags() { profile.Mode = mode.SelectedIndex == 1 ? "global" : mode.SelectedIndex == 2 ? "direct" : "rule"; profile.Tun = tun.Checked; profile.Mitm = mitm.Checked; profile.BasicAds = false; profile.Save(); }
    private async Task StartAsync()
    {
        if (busy || controller.Running) return; busy = true; start.Enabled = false; status.Text = "正在建立连接…";
        try
        {
            SaveFlags(); await controller.StartAsync(profile, systemProxy.Checked); if (disposed) return;
            stop.Enabled = true; nodeGroups = await controller.GroupsAsync(); groups.Items.Clear(); groups.Items.AddRange(nodeGroups.Keys.Cast<object>().ToArray());
            if (groups.Items.Count > 0) { string? preferred = MihomoConfig.PreferredGroup(profile); int index = preferred == null ? -1 : groups.Items.IndexOf(preferred); groups.SelectedIndex = Math.Max(0, index); }
            connectionTitle.Text = "已连接，自由流动"; connectionDetail.Text = (profile.Tun ? "TUN 已接管" : "系统代理已启用") + (profile.Mitm ? " · HTTPS 插件已开启" : " · HTTPS 解密未开启");
            status.Text = "连接已建立 · 可在代理节点中选择线路";
        }
        catch (Exception e) { if (!disposed) status.Text = e.Message; }
        finally { busy = false; if (!disposed) { start.Enabled = !controller.Running; RefreshSummary(); } }
    }
    private void Stop()
    {
        controller.Stop(); start.Enabled = true; stop.Enabled = false; connectionTitle.Text = "准备好，轻盈出发"; connectionDetail.Text = "连接已断开，接管的系统设置已恢复。"; status.Text = "已断开连接 · 系统代理已尝试恢复"; RefreshSummary();
    }
    private async Task Mutate(Func<Task> action)
    {
        if (busy) return;
        if (controller.Running) { MessageBox.Show(this, "请先断开连接，再修改配置或插件。", "连接正在运行"); return; }
        busy = true; start.Enabled = false;
        try { await action(); } catch (Exception e) { if (!disposed) { status.Text = "操作未完成，请查看提示后重试。"; MessageBox.Show(this, e.Message, "操作未完成"); } }
        finally { busy = false; if (!disposed) { start.Enabled = true; RefreshSummary(); } }
    }
    private void RefreshPlugins(string? selected = null)
    {
        pluginList.Items.Clear(); scriptPlugins.Items.Clear(); foreach (var plugin in profile.Plugins) { pluginList.Items.Add(plugin); scriptPlugins.Items.Add(plugin); }
        if (pluginList.Items.Count > 0) { int index = profile.Plugins.FindIndex(p => p.Id == selected); pluginList.SelectedIndex = Math.Max(0, index); scriptPlugins.SelectedIndex = Math.Max(0, index); }
        else { pluginInfo.Text = "尚未添加插件。可以从作者目录中选择，或粘贴插件链接。"; argument.Clear(); pluginPolicy.Clear(); tasks.Items.Clear(); }
        RefreshSummary();
    }
    private void ShowPlugin()
    {
        if (pluginList.SelectedItem is not LoonPlugin plugin) return;
        argument.Text = plugin.Argument; pluginPolicy.Text = plugin.ProxyPolicy;
        pluginInfo.Text = $"{plugin.Name}\r\n来源：{plugin.Source}\r\n规则 {plugin.Rules.Count} · URL 重写 {plugin.Rewrites.Count} · 脚本 {plugin.Scripts.Count} · 远程规则集 {plugin.RemoteRules.Count}\r\nMITM：{string.Join(", ", plugin.Hosts)}\r\n" +
            (plugin.Unsupported.Count == 0 ? "当前语法可解析；目标应用效果以实际命中规则为准。" : "不兼容项：\r\n" + string.Join("\r\n", plugin.Unsupported));
    }
    private void DrawPlugin(object? sender, DrawItemEventArgs e)
    {
        if (e.Index < 0 || pluginList.Items[e.Index] is not LoonPlugin plugin) return;
        float scale = DeviceDpi / 96f;
        bool selected = (e.State & DrawItemState.Selected) != 0;
        using var brush = new SolidBrush(selected ? Color.FromArgb(242, 240, 255) : Color.White); e.Graphics.FillRectangle(brush, e.Bounds);
        using var dot = new SolidBrush(plugin.Enabled ? Color.FromArgb(69, 179, 145) : Color.FromArgb(196, 201, 215)); e.Graphics.FillEllipse(dot, e.Bounds.X + 12 * scale, e.Bounds.Y + 17 * scale, 10 * scale, 10 * scale);
        using var titleFont = SwirlTheme.Font(10, FontStyle.Bold);
        using var noteFont = SwirlTheme.Font(8);
        TextRenderer.DrawText(e.Graphics, plugin.Name, titleFont, new Rectangle(e.Bounds.X + (int)(36 * scale), e.Bounds.Y + (int)(3 * scale), e.Bounds.Width - (int)(44 * scale), (int)(24 * scale)), SwirlTheme.Ink, TextFormatFlags.EndEllipsis | TextFormatFlags.VerticalCenter);
        TextRenderer.DrawText(e.Graphics, plugin.Unsupported.Count > 0 ? "不兼容 · 请查看说明" : plugin.Enabled ? "已启用" : "未启用", noteFont, new Rectangle(e.Bounds.X + (int)(36 * scale), e.Bounds.Y + (int)(25 * scale), e.Bounds.Width - (int)(44 * scale), (int)(20 * scale)), SwirlTheme.Muted);
    }
    private void RefreshSummary()
    {
        int enabled = profile.Plugins.Count(p => p.Enabled); pluginCount.Text = $"{enabled} 个插件已启用  ·  共 {profile.Plugins.Count} 个";
        string[] scope;
        try { UserRouting.Prepare(profile); scope = UserRouting.EffectivePlugins(profile).Where(p => p.Enabled && p.Unsupported.Count == 0).SelectMany(p => p.Hosts).Distinct().ToArray(); }
        catch { scope = profile.Plugins.Where(p => p.Enabled && p.Unsupported.Count == 0).SelectMany(p => p.Hosts).Distinct().ToArray(); }
        hostCount.Text = $"{scope.Length} 个 HTTPS 域名范围"; hosts.Text = scope.Length == 0 ? "尚无域名。启用含 MITM 设置的插件或添加 HTTPS URL 规则后会在这里显示。" : string.Join("\n", scope);
        configSummary.Text = string.IsNullOrEmpty(profile.ProtectedYaml) ? "尚未导入节点订阅" : "已导入网络配置 · " + (profile.Mode == "global" ? "全局代理" : profile.Mode == "direct" ? "全部直连" : "规则分流");
        try { var configured = ProxyProtocols.Configured(profile); protocolSummary.Text = configured.Count == 0 ? "当前没有静态节点；订阅提供的节点会在连接后加载。" : "已配置：" + string.Join(" · ", configured.Select(p => p.Name + " " + p.NodeCount + " 个")); }
        catch { protocolSummary.Text = "配置中的协议统计暂不可用。"; }
    }
    private void Report(string text)
    {
        if (disposed || IsDisposed || !IsHandleCreated) return;
        if (InvokeRequired) { try { BeginInvoke(new Action(() => Report(text))); } catch (InvalidOperationException) { } return; }
        if (log.TextLength > 40000) log.Text = log.Text[^20000..]; log.AppendText(DateTime.Now.ToString("HH:mm:ss") + "  " + text.Replace("AdShield", "Swirl", StringComparison.Ordinal) + Environment.NewLine);
        if (!controller.Running && stop.Enabled) { start.Enabled = true; stop.Enabled = false; connectionTitle.Text = "连接已断开"; connectionDetail.Text = "网络核心已停止，请查看运行记录。"; }
    }
    internal void SelectPage(string key)
    {
        if (!pages.TryGetValue(key, out var page)) throw new ArgumentException("未知页面：" + key);
        foreach (var item in pages) item.Value.Visible = item.Key == key;
        foreach (var item in navigation) { item.Value.Selected = item.Key == key; item.Value.Invalidate(); }
        page.BringToFront(); Fit(page);
    }
    private FlowLayoutPanel Page(string key, string title, string description)
    {
        var page = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, BackColor = SwirlTheme.Canvas, Padding = new Padding(32, 26, 25, 24), Visible = false };
        pages.Add(key, page); pageHost.Controls.Add(page); page.Resize += (_, _) => Fit(page);
        page.Controls.Add(new Label { Text = title, AutoSize = true, Font = SwirlTheme.Font(27, FontStyle.Bold), ForeColor = SwirlTheme.Ink, Margin = new Padding(0, 0, 0, 5) });
        page.Controls.Add(new Label { Text = description, AutoSize = true, ForeColor = SwirlTheme.Muted, Margin = new Padding(2, 0, 0, 24) }); return page;
    }
    private static SwirlCard Card(FlowLayoutPanel page, string title, string description)
    {
        var card = new SwirlCard { Width = 700, MinimumSize = new Size(700, 0), MaximumSize = new Size(700, 0) };
        card.Controls.Add(new Label { Text = title, AutoSize = true, Font = SwirlTheme.Font(13, FontStyle.Bold), Margin = new Padding(0, 0, 0, 9), BackColor = Color.Transparent });
        Note(card, description); page.Controls.Add(card); return card;
    }
    private static void Note(Control parent, string text) => parent.Controls.Add(new Label { Text = text, AutoSize = true, MaximumSize = new Size(620, 0), ForeColor = SwirlTheme.Muted, Margin = new Padding(0, 0, 0, 14), BackColor = Color.Transparent });
    private static void Row(Control parent, params Control[] controls)
    {
        var row = new FlowLayoutPanel { AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, MaximumSize = new Size(660, 0), BackColor = Color.Transparent, Margin = new Padding(0, 6, 0, 4), WrapContents = true };
        row.Controls.AddRange(controls); parent.Controls.Add(row);
    }
    private static SwirlButton Button(string text, Func<Task> action, bool primary = false)
    {
        var button = new SwirlButton { Text = text, Primary = primary }; button.Click += async (_, _) => await action(); return button;
    }
    private static void WrapField(TextBox field)
    {
        var parent = field.Parent; if (parent == null) return;
        int index = parent.Controls.GetChildIndex(field); parent.Controls.Remove(field);
        var wrapper = new SwirlField(field); parent.Controls.Add(wrapper); parent.Controls.SetChildIndex(wrapper, index);
    }
    private static void Fit(FlowLayoutPanel page)
    {
        if (page.ClientSize.Width < 350) return;
        int width = Math.Max((int)(640 * page.DeviceDpi / 96f), page.ClientSize.Width - page.Padding.Horizontal - (int)(18 * page.DeviceDpi / 96f));
        foreach (Control child in page.Controls)
        {
            if (child is SwirlCard card)
            {
                card.MinimumSize = new Size(width, 0); card.MaximumSize = new Size(width, 0); card.Width = width;
                foreach (Control nested in card.Controls)
                {
                    int inner = width - card.Padding.Horizontal;
                    if (nested is FlowLayoutPanel row) { row.MaximumSize = new Size(inner, 0); foreach (Control field in row.Controls) if (field is TextBox or SwirlField) field.Width = Math.Min(field.Width, inner); }
                    else if (nested is TextBox or SwirlField or ListBox or DataGridView) nested.Width = inner;
                    else if (nested is Label label) label.MaximumSize = new Size(inner, 0);
                }
            }
            else if (child is SwirlHero hero) hero.Width = width;
            else if (child is Label label) label.MaximumSize = new Size(width, 0);
        }
    }
    protected override void OnDpiChangedAfterParent(EventArgs e)
    {
        base.OnDpiChangedAfterParent(e);
        pluginList.ItemHeight = (int)(48 * DeviceDpi / 96f);
        foreach (var page in pages.Values) Fit(page);
    }
    protected override void Dispose(bool disposing) { if (disposing && !disposed) { disposed = true; controller.Dispose(); } base.Dispose(disposing); }
}
