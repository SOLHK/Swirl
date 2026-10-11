using AdShield.Network;
using System.Globalization;
using System.Windows.Data;
using Binding = System.Windows.Data.Binding;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;

namespace AdShield.Desktop;

internal sealed partial class SwirlWindow
{
    private readonly C.TextBlock selectedRoute = new();
    private void BuildNodeWorkspace()
    {
        var page = Page("nodes", "节点", "选一个服务器，让指定策略组通过它上网。打勾的是已经使用或预选的节点。");
        var layout = new C.Grid(); for (int i = 0; i < 6; i++) layout.RowDefinitions.Add(new C.RowDefinition { Height = i == 4 ? new W.GridLength(1, W.GridUnitType.Star) : W.GridLength.Auto });
        void Place(W.UIElement child, int row) { C.Grid.SetRow(child, row); layout.Children.Add(child); } Place(page, 0);
        var current = new C.StackPanel(); current.Children.Add(Text("这条策略使用的线路", 12)); selectedRoute.FontSize = 20; selectedRoute.FontWeight = W.FontWeights.SemiBold; selectedRoute.SetResourceReference(C.TextBlock.ForegroundProperty, "Ink"); selectedRoute.Margin = new W.Thickness(0, 8, 0, 4); current.Children.Add(selectedRoute); nodesSummary.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); current.Children.Add(nodesSummary); Place(Surface(current, 15), 1);
        var filters = new C.Grid(); filters.ColumnDefinitions.Add(new C.ColumnDefinition()); filters.ColumnDefinitions.Add(new C.ColumnDefinition());
        var target = new C.StackPanel { Margin = new W.Thickness(0, 0, 12, 0) }; target.Children.Add(Note("为哪个策略组选节点")); target.Children.Add(nodeTargetGroup);
        var search = new C.StackPanel(); search.Children.Add(Note("搜索地区或节点名称")); search.Children.Add(nodeSearch); C.Grid.SetColumn(search, 1); filters.Children.Add(target); filters.Children.Add(search); Place(filters, 2);
        nodeSearch.TextChanged += (_, _) => FillNodes(); nodeTargetGroup.SelectionChanged += (_, _) => FillNodes();
        nodeSort.ItemsSource = new[] { "订阅原顺序", "延迟从低到高", "按名称排列" }; nodeSort.SelectedIndex = 0; nodeSort.SelectionChanged += (_, _) => FillNodes();
        var tools = new C.StackPanel(); Row(tools, nodeSort, SmallButton("测试当前列表", TestVisibleNodesAsync), SmallButton("刷新节点", RefreshCatalogAsync), SmallButton("连接网络", StartAsync)); Place(tools, 3);
        nodes.Height = double.NaN; nodes.MinHeight = 0; nodes.MaxHeight = double.PositiveInfinity; nodes.BorderThickness = new W.Thickness(0); nodes.Margin = new W.Thickness(0, 8, 0, 8);
        var panel = new W.FrameworkElementFactory(typeof(C.WrapPanel)); nodes.ItemsPanel = new C.ItemsPanelTemplate(panel);
        var itemStyle = new W.Style(typeof(C.ListBoxItem), (W.Style)FindResource(typeof(C.ListBoxItem))); itemStyle.Setters.Add(new W.Setter(C.Control.PaddingProperty, new W.Thickness(16))); itemStyle.Setters.Add(new W.Setter(W.FrameworkElement.MarginProperty, new W.Thickness(0, 0, 10, 10))); itemStyle.Setters.Add(new W.Setter(C.Control.BackgroundProperty, new W.DynamicResourceExtension("Card"))); nodes.ItemContainerStyle = itemStyle;
        var template = new W.DataTemplate(); var body = new W.FrameworkElementFactory(typeof(C.StackPanel));
        var name = new W.FrameworkElementFactory(typeof(C.TextBlock)); name.SetBinding(C.TextBlock.TextProperty, new Binding()); name.SetValue(C.TextBlock.FontWeightProperty, W.FontWeights.SemiBold); name.SetValue(C.TextBlock.FontSizeProperty, 14d); name.SetValue(C.TextBlock.TextTrimmingProperty, W.TextTrimming.CharacterEllipsis); name.SetValue(C.TextBlock.TextWrappingProperty, W.TextWrapping.NoWrap); body.AppendChild(name);
        var protocol = new W.FrameworkElementFactory(typeof(C.TextBlock)); protocol.SetBinding(C.TextBlock.TextProperty, new Binding { Converter = new NodeLabel(this, "protocol") }); protocol.SetValue(W.FrameworkElement.MarginProperty, new W.Thickness(0, 9, 0, 6)); protocol.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); protocol.SetValue(C.TextBlock.FontSizeProperty, 11d); body.AppendChild(protocol);
        var latency = new W.FrameworkElementFactory(typeof(C.TextBlock)); latency.SetBinding(C.TextBlock.TextProperty, new Binding { Converter = new NodeLabel(this, "status") }); latency.SetBinding(C.TextBlock.ForegroundProperty, new Binding { Converter = new NodeLabel(this, "color") }); latency.SetValue(C.TextBlock.FontSizeProperty, 12d); body.AppendChild(latency); template.VisualTree = body; nodes.ItemTemplate = template;
        nodes.SizeChanged += (_, _) => ResizeNodeCards(); nodes.SelectionChanged += (_, _) => { if (nodes.SelectedItem is string candidate) nodeInfo.Text = "已点选“" + candidate + "”，点下方按钮使用它。"; }; Place(nodes, 4);
        var footer = new C.StackPanel(); nodeInfo.SetResourceReference(C.TextBlock.ForegroundProperty, "Muted"); footer.Children.Add(nodeInfo);
        Row(footer, Button("使用选中节点", async () => { if (nodeTargetGroup.SelectedItem is not ProxyGroup group || nodes.SelectedItem is not string node) throw new InvalidOperationException("先点选一个节点，再使用它。"); await ApplySelectionAsync(group.Name, node); }, true), SmallButton("只测选中节点", async () => { if (nodes.SelectedItem is not string node) throw new InvalidOperationException("先点选一个节点。"); await TestNodesAsync([node]); }), SmallButton("管理订阅", () => { SelectPage("subscriptions"); return Task.CompletedTask; })); Place(footer, 5); pages["nodes"] = layout;
    }
    private sealed class NodeLabel(SwirlWindow owner, string field) : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        {
            string name = value as string ?? "";
            bool known = owner.measuredDelays.TryGetValue(name, out int delay) || owner.catalog.Delays.TryGetValue(name, out delay);
            bool selected = owner.nodeTargetGroup.SelectedItem is ProxyGroup group && owner.selections.GetValueOrDefault(group.Name) == name;
            if (field == "protocol") return "协议 · " + ProtocolName(owner.catalog.Nodes.GetValueOrDefault(name) ?? "");
            if (field == "color") return selected ? owner.Resources["Accent"] : known && delay > 0 ? owner.Resources["Success"] : known ? owner.Resources["Danger"] : owner.Resources["Muted"];
            return (selected ? "✓ " + (owner.controller.Running ? "正在使用" : "已预选") + " · " : "") + (known ? delay > 0 ? delay + " ms" : "暂不可用" : owner.controller.Running ? "尚未测速" : "连接后可测速");
        }
        public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
    }
    private static string ProtocolName(string type) => type.ToLowerInvariant() switch { "ss" or "shadowsocks" => "Shadowsocks", "ssr" or "shadowsocksr" => "ShadowsocksR", "http" => "HTTP / HTTPS", "socks5" or "socks" => "SOCKS5", "vmess" => "VMess", "vless" => "VLESS", "trojan" => "Trojan", "hysteria2" => "Hysteria2", "wireguard" => "WireGuard", _ => type };
    private void ResizeNodeCards()
    {
        double available = nodes.ActualWidth - 40; if (available <= 0) return;
        int columns = Math.Max(1, (int)(available / 230)); double width = available / columns - 10;
        for (int i = 0; i < nodes.Items.Count; i++) if (nodes.ItemContainerGenerator.ContainerFromIndex(i) is C.ListBoxItem item) item.Width = width;
    }
    private void RefreshNodeHeader()
    {
        var group = nodeTargetGroup.SelectedItem as ProxyGroup;
        selectedRoute.Text = group == null ? "先添加订阅，再选择线路" : catalog.Resolve(group.Name, selections);
        nodesSummary.Text = group == null ? "这里会显示你的服务器节点" : group.Name + " · " + (controller.Running ? "已连接，可立即切换" : "预选后，连接时会自动使用") + (PendingConfiguration ? " · 订阅有更新，重新连接后生效" : "");
    }
    private Task TestVisibleNodesAsync() => TestNodesAsync(nodes.Items.Cast<string>().ToArray());
    private async Task TestNodesAsync(string[] candidates)
    {
        if (!controller.Running) throw new InvalidOperationException("先连接网络，才能检测节点实际延迟。");
        if (testingNodes || candidates.Length == 0) return; testingNodes = true; int done = 0;
        using var slots = new SemaphoreSlim(4);
        try
        {
            await Task.WhenAll(candidates.Select(async node => { await slots.WaitAsync(lifetime.Token); try { if (!controller.Running) return; try { measuredDelays[node] = await controller.DelayAsync(node); } catch (Exception) when (!closed) { if (controller.Running) measuredDelays[node] = 0; } done++; status.Text = "测速中 " + done + " / " + candidates.Length; } finally { slots.Release(); } }));
            status.Text = controller.Running ? "测速完成。延迟越低，通常响应越快；可切换排序查看。" : "连接已断开，测速停止。";
        }
        finally { testingNodes = false; FillNodes(); RefreshPolicyCards(); }
    }
}
