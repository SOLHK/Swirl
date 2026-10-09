using Microsoft.Win32;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace AdShield.Network;

internal sealed record ProxyRegistryValue(string Name, string? Value, bool Exists, bool Integer);
internal static class WindowsSystemProxy
{
    internal static string? TestRegistryPath { get; set; }
    private static string KeyPath => TestRegistryPath ?? @"Software\Microsoft\Windows\CurrentVersion\Internet Settings";
    private static string Backup => Path.Combine(ProxyProfile.DirectoryPath, "system-proxy-backup.dat");
    private static string Address => "127.0.0.1:" + MihomoConfig.PluginPort;
    [DllImport("wininet.dll")] private static extern bool InternetSetOption(IntPtr internet, int option, IntPtr buffer, int size);
    private static void Refresh() { InternetSetOption(IntPtr.Zero, 39, IntPtr.Zero, 0); InternetSetOption(IntPtr.Zero, 37, IntPtr.Zero, 0); }

    internal static void Enable()
    {
        if (File.Exists(Backup)) Restore();
        using var key = Registry.CurrentUser.OpenSubKey(KeyPath, true) ?? throw new InvalidOperationException("无法打开当前用户代理设置。");
        var values = new List<ProxyRegistryValue>();
        foreach (string name in new[] { "ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL", "AutoDetect" })
        {
            var value = key.GetValue(name);
            values.Add(new(name, value?.ToString(), value != null, value is int));
        }
        Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        File.WriteAllText(Backup, ProxyProfile.Protect(JsonSerializer.Serialize(values)));
        key.SetValue("ProxyEnable", 1, RegistryValueKind.DWord);
        key.SetValue("ProxyServer", Address);
        key.SetValue("ProxyOverride", "<local>;localhost;127.*;[::1]");
        key.DeleteValue("AutoConfigURL", false);
        key.SetValue("AutoDetect", 0, RegistryValueKind.DWord);
        Refresh();
    }

    internal static bool Owns(string? address, int enabled) => enabled == 1 && address == Address;
    internal static void Restore()
    {
        if (!File.Exists(Backup)) return;
        using var key = Registry.CurrentUser.OpenSubKey(KeyPath, true);
        if (key == null) return;
        if (Owns(key.GetValue("ProxyServer") as string, (int)(key.GetValue("ProxyEnable") ?? 0)))
        {
            var values = JsonSerializer.Deserialize<List<ProxyRegistryValue>>(ProxyProfile.Unprotect(File.ReadAllText(Backup))) ?? throw new InvalidOperationException("代理备份无法读取。");
            foreach (var value in values)
                if (!value.Exists) key.DeleteValue(value.Name, false);
                else if (value.Integer) key.SetValue(value.Name, int.Parse(value.Value!), RegistryValueKind.DWord);
                else key.SetValue(value.Name, value.Value ?? "");
            Refresh();
        }
        // Preserve changes made by another proxy app or the user after AdShield started.
        File.Delete(Backup);
    }
}
