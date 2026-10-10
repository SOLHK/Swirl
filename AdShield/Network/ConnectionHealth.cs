using System.Diagnostics;
using System.Net;
using System.Net.Http;

namespace AdShield.Network;

internal sealed record ConnectionProbe(string Name, bool Success, int? Status, long Milliseconds, string Detail);
internal static class ConnectionHealth
{
    internal static async Task<ConnectionProbe[]> ProbeAsync(CancellationToken cancellationToken = default)
        => await Task.WhenAll(ProbeAsync("Google 检测", new Uri("https://www.gstatic.com/generate_204"), cancellationToken), ProbeAsync("Cloudflare 检测", new Uri("https://cp.cloudflare.com/generate_204"), cancellationToken));

    internal static async Task<ConnectionProbe> ProbeAsync(string name, Uri uri, CancellationToken token = default, HttpMessageHandler? transport = null)
    {
        using var handler = transport ?? new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.PluginPort), UseProxy = true, AllowAutoRedirect = false };
        using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(8) };
        var watch = Stopwatch.StartNew();
        try
        {
            using var response = await client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, token);
            bool valid = response.StatusCode == HttpStatusCode.NoContent;
            return new(name, valid, (int)response.StatusCode, watch.ElapsedMilliseconds, valid ? "通过应用入口、插件层和 Mihomo 收到有效响应" : "检测地址返回 HTTP " + (int)response.StatusCode);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch (OperationCanceledException) { return new(name, false, null, watch.ElapsedMilliseconds, "检测超时，请检查线路与策略组选择"); }
        catch (HttpRequestException) { return new(name, false, null, watch.ElapsedMilliseconds, "应用入口到目标地址的连接失败，请检查线路和代理设置"); }
    }
}
