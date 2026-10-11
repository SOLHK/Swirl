using AdShield.Desktop;
using AdShield.Network;
using System.Windows.Interop;
using System.Windows.Threading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;

internal static class DesktopChecks
{
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr window, out RectangleNative rectangle);
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)] private struct RectangleNative { internal int Left, Top, Right, Bottom; }
    internal static void Render(string folder, Action<bool, string> check)
    {
        string? originalDirectory = ProxyProfile.TestDirectory;
        ProxyProfile.TestDirectory = Path.Combine(Path.GetTempPath(), "Swirl-desktop-check-" + Guid.NewGuid().ToString("N"));
        Exception? error = null; var thread = new Thread(() =>
        {
            try
            {
                Directory.CreateDirectory(folder); var application = new W.Application { ShutdownMode = W.ShutdownMode.OnExplicitShutdown };
                var underlay = new W.Window { WindowStyle = W.WindowStyle.None, WindowStartupLocation = W.WindowStartupLocation.CenterScreen, Width = 1230, Height = 850, ShowInTaskbar = false, Background = new M.LinearGradientBrush(M.Color.FromRgb(191, 211, 248), M.Color.FromRgb(237, 211, 226), 24) };
                var stripes = new C.Grid(); for (int i = 0; i < 5; i++) stripes.ColumnDefinitions.Add(new C.ColumnDefinition());
                for (int i = 0; i < 5; i++) { var stripe = new C.Border { Background = i % 2 == 0 ? new M.SolidColorBrush(M.Color.FromArgb(40, 181, 207, 247)) : new M.SolidColorBrush(M.Color.FromArgb(40, 237, 211, 226)) }; C.Grid.SetColumn(stripe, i); stripes.Children.Add(stripe); }
                var fixtureRoot = MihomoConfig.Parse(NodeSelectionChecks.Fixture); var fixtureNodes = ((IEnumerable<object>)fixtureRoot["proxies"]).ToList();
                foreach (string label in new[] { "香港 02 · 示例", "日本 01 · 示例", "日本 02 · 示例", "新加坡 02 · 示例", "美国 01 · 示例", "美国 02 · 示例", "英国 01 · 示例", "德国 01 · 示例", "台湾 01 · 示例", "韩国 01 · 示例" }) fixtureNodes.Add(new Dictionary<string, object> { ["name"] = label, ["type"] = "http", ["server"] = "192.0.2.1", ["port"] = 8080 }); fixtureRoot["proxies"] = fixtureNodes;
                var fixtureGroups = ((IEnumerable<object>)fixtureRoot["proxy-groups"]).ToList(); foreach (string label in new[] { "流媒体", "工作服务", "国内网站" }) fixtureGroups.Add(new Dictionary<string, object> { ["name"] = label, ["type"] = "select", ["proxies"] = new[] { label == "国内网站" ? "DIRECT" : "Proxy", "Auto", "HK", "SG" } }); fixtureRoot["proxy-groups"] = fixtureGroups;
                string yaml = new YamlDotNet.Serialization.SerializerBuilder().Build().Serialize(fixtureRoot);
                var fixtureProfile = new ProxyProfile(); var main = SubscriptionLibrary.Add(fixtureProfile, "日常订阅 · 示例", new(yaml, "https://daily.example.test/sub?token=not-a-real-secret", SubscriptionUsage.Parse("upload=1073741824; download=21474836480; total=107374182400; expire=1893456000")), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic);
                SubscriptionLibrary.Add(fixtureProfile, "备用订阅 · 示例", new(NodeSelectionChecks.Fixture, "https://backup.example.test/sub?token=not-a-real-secret"), SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic);
                underlay.Topmost = true; underlay.Content = stripes; underlay.Show(); var window = new SwirlWindow(fixtureProfile, false) { Topmost = true }; window.Show(); window.Activate();
                T Field<T>(string name) => (T)typeof(SwirlWindow).GetField(name, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.GetValue(window)!;
                var nodes = Field<C.ListBox>("nodes"); var groups = Field<C.ListBox>("groups"); var target = Field<C.ComboBox>("nodeTargetGroup");
                check(nodes.Items.Count >= 2 && groups.Items.Count == 6, "desktop import populates nodes and strategy pages without starting the core");
                check(Field<C.WrapPanel>("subscriptionCards").Children.Count == 2, "desktop renders two subscription cards with active and missing-metadata states");
                target.SelectedItem = target.Items.Cast<ProxyGroup>().Single(g => g.Name == "Proxy"); nodes.SelectedItem = "SG";
                var apply = (Task)typeof(SwirlWindow).GetMethod("ApplySelectionAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.Invoke(window, ["Proxy", "SG"])!;
                apply.GetAwaiter().GetResult();
                check(Field<ProxyProfile>("profile").SelectedProxies["Proxy"] == "SG" && nodes.SelectedItem as string == "SG", "desktop applies and saves a preselected node while disconnected");
                target.SelectedItem = target.Items.Cast<ProxyGroup>().Single(g => g.Name == "Swirl 节点");
                var delays = Field<Dictionary<string, int>>("measuredDelays"); delays["HK"] = 52; delays["SG"] = 71; delays["日本 01 · 示例"] = 88; delays["日本 02 · 示例"] = 0;
                typeof(SwirlWindow).GetMethod("FillNodes", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.Invoke(window, null);
                var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(400) }; int page = 0; bool dropdownPending = false, compactPending = false; string[] keys = ["overview", "groups", "nodes", "subscriptions", "plugins", "routing", "https", "scripts", "sync", "logs", "settings"];
                timer.Tick += async (_, _) =>
                {
                    try
                    {
                        window.Activate();
                        if (dropdownPending)
                        {
                            check(target.IsDropDownOpen && target.ItemContainerGenerator.ContainerFromIndex(0) is C.ComboBoxItem { IsVisible: true }, "strategy dropdown shows selectable entries after native composition");
                            Save(window, Path.Combine(folder, "nodes-dropdown.png")); target.IsDropDownOpen = false; dropdownPending = false;
                            window.Width = 930; window.Height = 650; window.UpdateLayout(); compactPending = true; return;
                        }
                        if (compactPending)
                        {
                            Save(window, Path.Combine(folder, "nodes-compact.png")); window.Width = 1160; window.Height = 790; compactPending = false;
                            window.SelectPage(keys[page++]); window.UpdateLayout(); return;
                        }
                        if (page > 0)
                        {
                            Save(window, Path.Combine(folder, keys[page - 1] + ".png"));
                            if (keys[page - 1] == "nodes")
                            {
                                target.IsDropDownOpen = true; window.UpdateLayout();
                                dropdownPending = true; return;
                            }
                        }
                        if (page == keys.Length)
                        {
                            timer.Stop(); var save = (Task)typeof(SwirlWindow).GetMethod("SavePolicyAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.Invoke(window, [new PolicyGroupSettings { Name = "自建自动选择", Type = "fallback", AllNodes = true }, true])!; await save;
                            check(Field<ProxyProfile>("profile").GroupSettings.Single().Type == "fallback" && Field<C.StackPanel>("policyCards").Children.Count == 7, "desktop policy editing validates with the real core and persists into the active subscription card");
                            var editor = window.CreatePolicyEditor(null); editor.Topmost = true; editor.Show(); editor.UpdateLayout();
                            var editorTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(400) }; editorTimer.Tick += (_, _) => { editorTimer.Stop(); Save(editor, Path.Combine(folder, "policy-editor.png")); editor.Close(); window.Close(); underlay.Close(); application.Shutdown(); }; editorTimer.Start(); return;
                        }
                        window.SelectPage(keys[page++]); window.UpdateLayout();
                    }
                    catch (Exception e) { error = e; timer.Stop(); window.Close(); underlay.Close(); application.Shutdown(); }
                };
                timer.Start(); application.Run();
            }
            catch (Exception e) { error = e; }
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join(); ProxyProfile.TestDirectory = originalDirectory; if (error != null) throw error;
        check(Directory.GetFiles(folder, "*.png").Length >= 11, "All eleven WPF desktop pages initialize and render with populated offline subscription data");
    }
    private static void Save(W.Window window, string filename)
    {
        GetWindowRect(new WindowInteropHelper(window).Handle, out var rect);
        using var image = new System.Drawing.Bitmap(rect.Right - rect.Left, rect.Bottom - rect.Top); using var graphics = System.Drawing.Graphics.FromImage(image); graphics.CopyFromScreen(rect.Left, rect.Top, 0, 0, image.Size); image.Save(filename, System.Drawing.Imaging.ImageFormat.Png);
    }
}
