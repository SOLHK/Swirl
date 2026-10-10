using AdShield.Network;
using System.Net;
using System.Net.Http;

internal static class SubscriptionRouteChecks
{
    private const string Source = "https://converter.example.test/sub?target=clash&url=https%3A%2F%2Fprovider.example.test%2Fsub%3Ftoken%3Dsynthetic-private-token";
    private const string Yaml = "proxies: [{name: Fixture, type: http, server: 192.0.2.1, port: 8080}]\n";
    internal static async Task RunAsync(Action<bool, string> check)
    {
        var previous = HttpClient.DefaultProxy;
        try
        {
            HttpClient.DefaultProxy = new WebProxy("http://127.0.0.1:9");
            using var transport = (SocketsHttpHandler)SubscriptionImport.CreateTransport(SubscriptionDownloadRoute.Direct, new Uri(Source))!;
            check(!transport.UseProxy && transport.Proxy == null, "Direct subscription download ignores cached and environment proxy settings");
        }
        finally { HttpClient.DefaultProxy = previous; }
        var system = SubscriptionImport.SystemProxyFrom(new(3, "http=127.0.0.1:8801;https=127.0.0.1:8802", "", ""), new Uri(Source));
        check(system?.GetProxy(new Uri(Source))?.Port == 8802, "System subscription route selects the current HTTPS proxy endpoint");
        var changed = SubscriptionImport.SystemProxyFrom(new(3, "127.0.0.1:8803", "", ""), new Uri(Source));
        check(changed?.GetProxy(new Uri(Source))?.Port == 8803, "System subscription route reads a changed proxy instead of a cached endpoint");
        check(SubscriptionImport.SystemProxyFrom(new(1, "127.0.0.1:8802", "", ""), new Uri(Source)) == null, "Disabled system proxy is not used for subscription downloads");
        using var self = (SocketsHttpHandler)SubscriptionImport.CreateTransport(SubscriptionDownloadRoute.Swirl, new Uri(Source))!;
        check(self.UseProxy && self.Proxy?.GetProxy(new Uri(Source))?.Port == MihomoConfig.MixedPort, "Self-proxy subscription downloads use the core and bypass plugin rewrites");
        var attempts = new List<SubscriptionDownloadRoute>(); var reports = new List<string>();
        var result = await SubscriptionImport.DownloadRoutedAsync(Source, SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic,
            report: reports.Add, transportFactory: (route, uri) =>
            {
                check(uri.OriginalString == Source, "Download route selection preserves nested private query encoding");
                attempts.Add(route);
                return new Fixture(_ => route == SubscriptionDownloadRoute.Direct
                    ? throw new HttpRequestException(HttpRequestError.ConnectionError, "synthetic-private-token")
                    : new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(Yaml) });
            });
        check(result.Content == Yaml && result.NormalizedSource == Source && attempts.SequenceEqual(new[] { SubscriptionDownloadRoute.Direct, SubscriptionDownloadRoute.SystemProxy }), "Automatic subscription import falls back from failed direct connection to current system proxy");
        check(reports.Count > 0 && reports.All(s => !s.Contains("synthetic-private-token") && !s.Contains("https://")), "Route progress and transport failures cannot expose subscription credentials");
        attempts.Clear(); bool forbidden = false;
        try { await SubscriptionImport.DownloadRoutedAsync(Source, SubscriptionClientProfile.Clash, SubscriptionDownloadRoute.Automatic, transportFactory: (route, _) => { attempts.Add(route); return new Fixture(_ => new(HttpStatusCode.Forbidden)); }); }
        catch (InvalidOperationException e) { forbidden = e.Message.Contains("403"); }
        check(forbidden && attempts.Count == 1, "Server HTTP denial does not trigger a hidden identity or routing retry");
        attempts.Clear(); await SubscriptionImport.DownloadRoutedAsync(Source, SubscriptionClientProfile.Clash, SubscriptionDownloadRoute.SystemProxy, transportFactory: (route, _) => { attempts.Add(route); return new Fixture(_ => new(HttpStatusCode.OK) { Content = new StringContent(Yaml) }); });
        check(attempts.SequenceEqual(new[] { SubscriptionDownloadRoute.SystemProxy }), "Explicit system route never performs an unintended direct request");
        bool missing = false;
        try { await SubscriptionImport.DownloadRoutedAsync(Source, SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.SystemProxy, transportFactory: (_, _) => null); }
        catch (SubscriptionTransportException e) { missing = e.Message.Contains("没有启用"); }
        check(missing, "Unavailable manual system proxy returns an actionable error without silently using direct traffic");
        using var canceled = new CancellationTokenSource(); canceled.Cancel(); bool aborted = false;
        try { await SubscriptionImport.DownloadRoutedAsync(Source, SubscriptionClientProfile.Mihomo, SubscriptionDownloadRoute.Automatic, canceled.Token, transportFactory: (_, _) => throw new Exception("Should not create transport")); }
        catch (OperationCanceledException) { aborted = true; }
        check(aborted, "Canceled import cannot start a fallback request");
    }
    private sealed class Fixture(Func<HttpRequestMessage, HttpResponseMessage> action) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) { token.ThrowIfCancellationRequested(); return Task.FromResult(action(request)); }
    }
}
