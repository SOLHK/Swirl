using System.Diagnostics;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;

namespace AdShield.Network;

internal sealed class ProxyController : IDisposable
{
    private Process? core;
    private CoreProcessJob? processJob;
    private readonly object proxySettingsGate = new();
    private PluginProxy? pluginProxy;
    private PluginTasks? pluginTasks;
    private readonly CancellationTokenSource lifetime = new();
    private readonly Action<string> report;
    private string secret = "";
    private bool ownsSystemProxy;
    private bool activeTun;
    internal bool Running => core is { HasExited: false };
    internal ProxyController(Action<string> report) { this.report = report; }
    internal static string CorePath => Path.Combine(AppContext.BaseDirectory, "core", "mihomo.exe");

    internal async Task StartAsync(ProxyProfile profile, bool systemProxy)
    {
        if (Running) throw new InvalidOperationException("代理已经运行，请先停止或应用并重启。");
        if (!File.Exists(CorePath)) throw new InvalidOperationException("缺少随软件提供的 core/mihomo.exe，请完整安装或解压。");
        if (profile.Tun && !new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator))
            throw new InvalidOperationException("TUN 需要管理员权限，请以管理员身份运行 Swirl；普通系统代理模式无需管理员权限。");
        UserRouting.Prepare(profile);
        foreach (int port in new[] { MihomoConfig.MixedPort, MihomoConfig.PluginPort, MihomoConfig.ControllerPort }.Concat(UserRouting.ListenerPorts(profile)))
        {
            using var probe = new TcpListener(System.Net.IPAddress.Loopback, port);
            try { probe.Start(); } catch (SocketException) { throw new InvalidOperationException("本机端口 " + port + " 已占用，请关闭另一份 Swirl 或修改冲突应用。"); }
        }
        secret = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));
        var (runtime, filename) = await PrepareConfigAsync(profile, secret);
        lifetime.Token.ThrowIfCancellationRequested();
        try
        {
            // Have the destination ready before the core installs TUN routes.
            pluginProxy = new PluginProxy(UserRouting.EffectivePlugins(profile), profile.Mitm, report, profile: profile);
            pluginProxy.Start();
            activeTun = profile.Tun;
            var start = StartInfo(runtime, filename);
            core = Process.Start(start) ?? throw new InvalidOperationException("代理核心无法启动。");
            processJob = new CoreProcessJob(core);
            core.EnableRaisingEvents = true;
            core.Exited += (_, _) =>
            {
                lock (proxySettingsGate)
                {
                    try { if (ownsSystemProxy) WindowsSystemProxy.Restore(); } catch { }
                    ownsSystemProxy = false;
                }
                report("Mihomo 核心已退出，系统代理已尝试恢复。");
            };
            // Never print raw core logs: they may include subscription credentials.
            core.OutputDataReceived += (_, _) => { };
            core.ErrorDataReceived += (_, _) => { };
            core.BeginOutputReadLine(); core.BeginErrorReadLine();
            bool ready = false;
            for (int attempt = 0; attempt < 80; attempt++)
            {
                lifetime.Token.ThrowIfCancellationRequested();
                if (core.HasExited) throw new InvalidOperationException("代理核心启动后退出，请检查配置、节点和网络。");
                try { using var result = await RequestAsync(HttpMethod.Get, "/version"); ready = result.IsSuccessStatusCode; } catch (HttpRequestException) { }
                if (ready) break;
                await Task.Delay(200, lifetime.Token);
            }
            if (!ready) throw new InvalidOperationException("代理核心未在规定时间内就绪。");
            lifetime.Token.ThrowIfCancellationRequested();
            if (systemProxy)
            {
                lock (proxySettingsGate)
                {
                    if (core.HasExited) throw new InvalidOperationException("代理核心已经退出，未接管系统代理。");
                    ownsSystemProxy = true;
                    WindowsSystemProxy.Enable();
                    if (!WindowsSystemProxy.IsEnabled) throw new InvalidOperationException("Windows 系统代理没有生效，请检查是否有其他代理软件正在接管网络。");
                }
            }
            report("代理已启动：本机入口 127.0.0.1:" + MihomoConfig.PluginPort + "，模式 " + profile.Mode + (profile.Tun ? "，TUN 已启用" : ""));
            pluginTasks = new PluginTasks(UserRouting.EffectivePlugins(profile), report); pluginTasks.Start();
        }
        catch { Stop(); throw; }
    }

    internal async Task ValidateAsync(ProxyProfile profile)
    {
        if (Running) throw new InvalidOperationException("请先断开连接，再检查配置。");
        await PrepareConfigAsync(profile, Convert.ToHexString(RandomNumberGenerator.GetBytes(24)));
    }
    private async Task<(string Directory, string File)> PrepareConfigAsync(ProxyProfile profile, string controllerSecret)
    {
        if (!File.Exists(CorePath)) throw new InvalidOperationException("缺少随软件提供的 core/mihomo.exe，请完整安装或解压。");
        string runtime = Path.Combine(ProxyProfile.DirectoryPath, "runtime");
        Directory.CreateDirectory(runtime);
        report("正在准备本地分流数据库…");
        int installed = await Task.Run(() => CoreAssets.Prepare(profile, runtime), lifetime.Token);
        if (installed > 0) report("已准备 " + installed + " 份本地分流数据库。");
        string filename = Path.Combine(runtime, "config.yaml");
        File.WriteAllText(filename, MihomoConfig.Build(profile, controllerSecret), new UTF8Encoding(false));
        report("正在检查配置、节点和分流规则…");
        await TestConfigAsync(runtime, filename);
        return (runtime, filename);
    }
    internal static ProcessStartInfo StartInfo(string directory, string filename)
    {
        var start = new ProcessStartInfo(CorePath) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = directory };
        start.ArgumentList.Add("-d"); start.ArgumentList.Add(directory);
        start.ArgumentList.Add("-f"); start.ArgumentList.Add(filename);
        return start;
    }
    internal async Task TestConfigAsync(string directory, string filename)
    {
        var start = StartInfo(directory, filename);
        start.ArgumentList.Add("-t");
        using var process = Process.Start(start) ?? throw new InvalidOperationException("无法检查代理配置。");
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException)
        {
            if (!process.HasExited) process.Kill(true);
            await process.WaitForExitAsync(); await Task.WhenAll(output, errors);
            lifetime.Token.ThrowIfCancellationRequested();
            throw new InvalidOperationException("配置检查超时：默认分流数据库已在本地准备，请检查自定义 GEO 来源或节点 / 规则提供器是否可以下载。");
        }
        await Task.WhenAll(output, errors);
        if (process.ExitCode != 0) throw new InvalidOperationException(CoreDiagnostics.Describe(output.Result + "\n" + errors.Result, process.ExitCode));
    }
    private async Task<HttpResponseMessage> RequestAsync(HttpMethod method, string path, object? data = null)
    {
        using var handler = new HttpClientHandler { UseProxy = false };
        using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(3) };
        using var request = new HttpRequestMessage(method, "http://127.0.0.1:" + MihomoConfig.ControllerPort + path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", secret);
        if (data != null) request.Content = new StringContent(JsonSerializer.Serialize(data), Encoding.UTF8, "application/json");
        return await client.SendAsync(request, lifetime.Token);
    }
    internal async Task<Dictionary<string, string[]>> GroupsAsync()
    {
        using var response = await RequestAsync(HttpMethod.Get, "/proxies");
        response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var groups = new Dictionary<string, string[]>();
        foreach (var proxy in document.RootElement.GetProperty("proxies").EnumerateObject())
            if (proxy.Value.TryGetProperty("type", out var type) && type.GetString() == "Selector" && proxy.Value.TryGetProperty("all", out var all))
                groups[proxy.Name] = all.EnumerateArray().Select(n => n.GetString()!).Where(n => n != MihomoConfig.PluginOutbound).ToArray();
        return groups;
    }
    internal async Task<Dictionary<string, string>> SelectionsAsync()
    {
        using var response = await RequestAsync(HttpMethod.Get, "/proxies"); response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return document.RootElement.GetProperty("proxies").EnumerateObject()
            .Where(p => p.Value.TryGetProperty("now", out var n) && n.ValueKind == JsonValueKind.String)
            .ToDictionary(p => p.Name, p => p.Value.GetProperty("now").GetString()!);
    }
    internal async Task<(long Upload, long Download)> TrafficAsync()
    {
        using var response = await RequestAsync(HttpMethod.Get, "/connections"); response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        var root = document.RootElement; return (root.GetProperty("uploadTotal").GetInt64(), root.GetProperty("downloadTotal").GetInt64());
    }
    internal async Task SelectAsync(string group, string node)
    {
        if (node == MihomoConfig.PluginOutbound) throw new InvalidOperationException("内部插件入口不能作为上游节点。");
        using var response = await RequestAsync(HttpMethod.Put, "/proxies/" + Uri.EscapeDataString(group), new { name = node });
        response.EnsureSuccessStatusCode();
    }
    internal async Task<int> DelayAsync(string node)
    {
        using var response = await RequestAsync(HttpMethod.Get, "/proxies/" + Uri.EscapeDataString(node) + "/delay?timeout=2000&url=" + Uri.EscapeDataString("https://www.gstatic.com/generate_204"));
        response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return document.RootElement.GetProperty("delay").GetInt32();
    }
    internal void Stop()
    {
        pluginTasks?.Dispose(); pluginTasks = null;
        if (activeTun && Running)
        {
            try
            {
                using var handler = new HttpClientHandler { UseProxy = false };
                using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(2) };
                using var request = new HttpRequestMessage(HttpMethod.Patch, "http://127.0.0.1:" + MihomoConfig.ControllerPort + "/configs");
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", secret);
                request.Content = new StringContent("{\"tun\":{\"enable\":false}}", Encoding.UTF8, "application/json");
                using var response = client.Send(request);
                if (!response.IsSuccessStatusCode) report("TUN 关闭请求未成功，正在终止核心释放接口。");
            }
            catch { report("TUN 关闭请求失败，正在终止核心释放接口。"); }
        }
        activeTun = false;
        lock (proxySettingsGate)
        {
            try { if (ownsSystemProxy) WindowsSystemProxy.Restore(); } catch { report("恢复系统代理失败，请在 Windows 设置中关闭 127.0.0.1:" + MihomoConfig.PluginPort); }
            ownsSystemProxy = false;
        }
        pluginProxy?.Dispose(); pluginProxy = null;
        if (core != null)
        {
            try { if (!core.HasExited) { core.Kill(true); core.WaitForExit(3000); } } catch { }
            core.Dispose(); core = null;
        }
        processJob?.Dispose(); processJob = null;
    }
    public void Dispose() { lifetime.Cancel(); Stop(); lifetime.Dispose(); }
    internal Task RunTaskAsync(LoonPlugin plugin, LoonScript script) => pluginTasks?.ExecuteAsync(plugin, script) ?? throw new InvalidOperationException("请先启动代理，再运行任务脚本。");
}
