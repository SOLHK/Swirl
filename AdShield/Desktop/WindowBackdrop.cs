using System.Runtime.InteropServices;
using Microsoft.Win32;
using W = System.Windows;
using M = System.Windows.Media;
using System.Windows.Interop;

namespace AdShield.Desktop;

internal static class WindowBackdrop
{
    [StructLayout(LayoutKind.Sequential)] private struct Margins { internal int Left, Right, Top, Bottom; }
    [DllImport("dwmapi.dll")] private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
    [DllImport("dwmapi.dll")] private static extern int DwmExtendFrameIntoClientArea(IntPtr window, ref Margins margins);
    internal static bool Dark
    {
        get { using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"); return key?.GetValue("AppsUseLightTheme") is int value && value == 0; }
    }
    internal static bool Apply(W.Window window, bool requested)
    {
        IntPtr handle = new WindowInteropHelper(window).Handle; if (handle == IntPtr.Zero) return false;
        int dark = Dark ? 1 : 0, corners = 2;
        DwmSetWindowAttribute(handle, 20, ref dark, 4); DwmSetWindowAttribute(handle, 33, ref corners, 4);
        using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        bool enabled = requested && !W.SystemParameters.HighContrast && key?.GetValue("EnableTransparency") is not 0;
        enabled &= OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22621);
        int backdrop = enabled ? 3 : 1;
        enabled &= DwmSetWindowAttribute(handle, 38, ref backdrop, 4) == 0;
        var margins = new Margins { Left = enabled ? -1 : 0, Right = enabled ? -1 : 0, Top = enabled ? -1 : 0, Bottom = enabled ? -1 : 0 };
        DwmExtendFrameIntoClientArea(handle, ref margins);
        if (HwndSource.FromHwnd(handle)?.CompositionTarget is { } target) target.BackgroundColor = enabled ? M.Colors.Transparent : Dark ? M.Color.FromRgb(29, 34, 43) : M.Color.FromRgb(239, 243, 249);
        window.Background = enabled ? M.Brushes.Transparent : new M.SolidColorBrush(Dark ? M.Color.FromRgb(29, 34, 43) : M.Color.FromRgb(239, 243, 249));
        return enabled;
    }
}
