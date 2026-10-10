using AdShield.Network;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;

internal static class NativeCaptureChecks
{
    [DllImport("wininet.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr InternetOpenW(string agent, int access, string? proxy, string? bypass, int flags);
    [DllImport("wininet.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr InternetOpenUrlW(IntPtr internet, string url, string? headers, int headersLength, int flags, IntPtr context);
    [DllImport("wininet.dll")] private static extern bool InternetReadFile(IntPtr request, byte[] buffer, int size, out int read);
    [DllImport("wininet.dll")] private static extern bool InternetCloseHandle(IntPtr handle);
    [DllImport("wininet.dll")] private static extern bool InternetSetOptionW(IntPtr handle, int option, ref int value, int size);
    internal static async Task RunAsync(Action<bool, string> check)
    {
        var original = NativeProxySettings.Read(); string directory = Path.Combine(Path.GetTempPath(), "Swirl-native-check-" + Guid.NewGuid().ToString("N"));
        string? previousDirectory = ProxyProfile.TestDirectory; ProxyProfile.TestDirectory = directory;
        var listener = new TcpListener(IPAddress.Loopback, MihomoConfig.PluginPort); listener.Start();
        try
        {
            WindowsSystemProxy.Enable(); check(WindowsSystemProxy.IsEnabled, "Native Windows current-connection proxy is enabled and verified");
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            var receive = Task.Run(async () => { using var socket = await listener.AcceptTcpClientAsync(timeout.Token); using var stream = socket.GetStream(); byte[] buffer = new byte[8192]; int count = await stream.ReadAsync(buffer, timeout.Token); string request = Encoding.ASCII.GetString(buffer, 0, count); const string body = "swirl-native-capture-ok"; await stream.WriteAsync(Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n" + body), timeout.Token); return request; });
            string response = await Task.Run(() =>
            {
                IntPtr internet = InternetOpenW("Swirl native verification", 0, null, null, 0); if (internet == IntPtr.Zero) throw new Exception("WinINet initialization failed");
                try { int milliseconds = 6000; InternetSetOptionW(internet, 2, ref milliseconds, 4); InternetSetOptionW(internet, 6, ref milliseconds, 4); IntPtr request = InternetOpenUrlW(internet, "http://swirl-native-capture.invalid/verify", null, 0, unchecked((int)0x84000000), IntPtr.Zero); if (request == IntPtr.Zero) throw new Exception("Native system-proxy request failed: " + Marshal.GetLastWin32Error()); try { var buffer = new byte[256]; if (!InternetReadFile(request, buffer, buffer.Length, out int count)) throw new Exception("WinINet read failed"); return Encoding.ASCII.GetString(buffer, 0, count); } finally { InternetCloseHandle(request); } } finally { InternetCloseHandle(internet); }
            });
            check(response == "swirl-native-capture-ok" && (await receive).Contains("swirl-native-capture.invalid/verify"), "A Windows-native client reaches Swirl without an explicitly supplied proxy");
        }
        finally { listener.Stop(); WindowsSystemProxy.Restore(); ProxyProfile.TestDirectory = previousDirectory; }
        check(NativeProxySettings.Read() == original, "Native Windows proxy flags, PAC, bypass and server restore exactly");
    }
}
