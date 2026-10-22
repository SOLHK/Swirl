using AdShield.Network;
using System.Net;
using System.Net.Http;

internal static class ConnectionHealthChecks
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        var good = await ConnectionHealth.ProbeAsync("fixture", new Uri("https://example.invalid/check"), transport: new Fixture(HttpStatusCode.NoContent));
        check(good.Success && good.Status == 204, "Connectivity accepts expected HTTPS 204 response");
        var portal = await ConnectionHealth.ProbeAsync("fixture", new Uri("https://example.invalid/check"), transport: new Fixture(HttpStatusCode.OK));
        check(!portal.Success && portal.Status == 200, "Portal HTML cannot produce a successful connection indicator");
        var redirect = await ConnectionHealth.ProbeAsync("fixture", new Uri("https://example.invalid/check"), transport: new Fixture(HttpStatusCode.Redirect));
        check(!redirect.Success, "Redirect cannot produce a successful connection indicator");
        var failure = await ConnectionHealth.ProbeAsync("fixture", new Uri("https://example.invalid/check"), transport: new Fixture(null));
        check(!failure.Success && !failure.Detail.Contains("private-key"), "Connectivity errors do not expose transport exception secrets");
        using var canceled = new CancellationTokenSource(); canceled.Cancel(); bool propagated = false;
        try { await ConnectionHealth.ProbeAsync("fixture", new Uri("https://example.invalid/check"), canceled.Token, new Fixture(HttpStatusCode.NoContent)); } catch (OperationCanceledException) { propagated = true; }
        check(propagated, "Closing the window cancels connection checks");
    }
    private sealed class Fixture(HttpStatusCode? status) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage message, CancellationToken token)
        {
            token.ThrowIfCancellationRequested(); if (status == null) throw new HttpRequestException("private-key=fixture");
            return Task.FromResult(new HttpResponseMessage(status.Value));
        }
    }
}
