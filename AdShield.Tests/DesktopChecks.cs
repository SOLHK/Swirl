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
                var underlay = new W.Window { WindowStyle = W.WindowStyle.None, WindowStartupLocation = W.WindowStartupLocation.CenterScreen, Width = 1230, Height = 850, ShowInTaskbar = false, Background = new M.LinearGradientBrush(M.Color.FromRgb(23, 99, 188), M.Color.FromRgb(242, 129, 59), 24) };
                var stripes = new C.Grid(); for (int i = 0; i < 5; i++) stripes.ColumnDefinitions.Add(new C.ColumnDefinition());
                for (int i = 0; i < 5; i++) { var stripe = new C.Border { Background = i % 2 == 0 ? new M.SolidColorBrush(M.Color.FromArgb(95, 0, 130, 230)) : new M.SolidColorBrush(M.Color.FromArgb(95, 235, 121, 61)) }; C.Grid.SetColumn(stripe, i); stripes.Children.Add(stripe); }
                underlay.Topmost = true; underlay.Content = stripes; underlay.Show(); var window = new SwirlWindow(new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(NodeSelectionChecks.Fixture) }, false) { Topmost = true }; window.Show(); window.Activate();
                T Field<T>(string name) => (T)typeof(SwirlWindow).GetField(name, System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.GetValue(window)!;
                var nodes = Field<C.ListBox>("nodes"); var groups = Field<C.ListBox>("groups"); var target = Field<C.ComboBox>("nodeTargetGroup");
                check(nodes.Items.Count == 2 && groups.Items.Count == 3, "desktop import populates nodes and strategy pages without starting the core");
                target.SelectedItem = target.Items.Cast<ProxyGroup>().Single(g => g.Name == "Proxy"); nodes.SelectedItem = "SG";
                var apply = (Task)typeof(SwirlWindow).GetMethod("ApplySelectionAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!.Invoke(window, ["Proxy", "SG"])!;
                apply.GetAwaiter().GetResult();
                check(Field<ProxyProfile>("profile").SelectedProxies["Proxy"] == "SG" && nodes.SelectedItem as string == "SG", "desktop applies and saves a preselected node while disconnected");
                var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(400) }; int page = 0; bool dropdownPending = false, compactPending = false; string[] keys = ["overview", "groups", "nodes", "subscriptions", "plugins", "routing", "https", "scripts", "sync", "logs", "settings"];
                timer.Tick += (_, _) =>
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
                        if (page == keys.Length) { timer.Stop(); window.Close(); underlay.Close(); application.Shutdown(); return; }
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
