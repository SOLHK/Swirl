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
        Exception? error = null; var thread = new Thread(() =>
        {
            try
            {
                Directory.CreateDirectory(folder); var application = new W.Application { ShutdownMode = W.ShutdownMode.OnExplicitShutdown };
                var underlay = new W.Window { WindowStyle = W.WindowStyle.None, WindowStartupLocation = W.WindowStartupLocation.CenterScreen, Width = 1230, Height = 850, ShowInTaskbar = false, Background = new M.LinearGradientBrush(M.Color.FromRgb(23, 99, 188), M.Color.FromRgb(242, 129, 59), 24) };
                var stripes = new C.Grid(); for (int i = 0; i < 5; i++) stripes.ColumnDefinitions.Add(new C.ColumnDefinition());
                for (int i = 0; i < 5; i++) { var stripe = new C.Border { Background = i % 2 == 0 ? new M.SolidColorBrush(M.Color.FromArgb(95, 0, 130, 230)) : new M.SolidColorBrush(M.Color.FromArgb(95, 235, 121, 61)) }; C.Grid.SetColumn(stripe, i); stripes.Children.Add(stripe); }
                underlay.Topmost = true; underlay.Content = stripes; underlay.Show(); var window = new SwirlWindow(new ProxyProfile(), false) { Topmost = true }; window.Show(); window.Activate();
                var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(400) }; int page = 0; string[] keys = ["overview", "nodes", "plugins", "routing", "https", "scripts", "sync", "logs", "settings"];
                timer.Tick += (_, _) =>
                {
                    try
                    {
                        window.Activate();
                        if (page > 0) Save(window, Path.Combine(folder, keys[page - 1] + ".png"));
                        if (page == keys.Length) { timer.Stop(); window.Close(); underlay.Close(); application.Shutdown(); return; }
                        window.SelectPage(keys[page++]); window.UpdateLayout();
                    }
                    catch (Exception e) { error = e; timer.Stop(); window.Close(); underlay.Close(); application.Shutdown(); }
                };
                timer.Start(); application.Run();
            }
            catch (Exception e) { error = e; }
        });
        thread.SetApartmentState(ApartmentState.STA); thread.Start(); thread.Join(); if (error != null) throw error;
        check(Directory.GetFiles(folder, "*.png").Length >= 9, "All nine WPF desktop pages initialize and render with the native compositor");
    }
    private static void Save(W.Window window, string filename)
    {
        GetWindowRect(new WindowInteropHelper(window).Handle, out var rect);
        using var image = new System.Drawing.Bitmap(rect.Right - rect.Left, rect.Bottom - rect.Top); using var graphics = System.Drawing.Graphics.FromImage(image); graphics.CopyFromScreen(rect.Left, rect.Top, 0, 0, image.Size); image.Save(filename, System.Drawing.Imaging.ImageFormat.Png);
    }
}
