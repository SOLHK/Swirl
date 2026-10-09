using System.Net;
using Titanium.Web.Proxy;
using Titanium.Web.Proxy.EventArguments;
using Titanium.Web.Proxy.Http;
using Titanium.Web.Proxy.Models;
using Microsoft.Extensions.Logging;

namespace AdShield.Network;

internal sealed class PluginProxy : IDisposable
{
    private readonly ProxyServer server = new(false, false, false);
    private readonly LoonPlugin[] plugins;
    private readonly bool mitm;
    private readonly Action<string> report;
    private readonly bool requireTrustedRoot;
    private readonly ProxyProfile? profile;
    private readonly LoonPlugin? independentRoutingHosts;
    private readonly CancellationTokenSource stop = new();
    private sealed class SessionState
    {
        internal bool RequestBodyRewrite, ResponseBodyRewrite, Synthetic;
        internal ScriptMessage? OriginalResponse;
        internal TaskCompletionSource<bool>? RequestCompletion;
    }
    private static SessionState State(SessionEventArgs e)
    {
        if (e.UserData is SessionState state) return state;
        state = new(); e.UserData = state; return state;
    }
    internal PluginProxy(IEnumerable<LoonPlugin> plugins, bool mitm, Action<string> report, bool requireTrustedRoot = true, string? pinnedTestOrigin = null, ProxyProfile? profile = null)
    {
        this.plugins = plugins.Where(plugin => plugin.Enabled && plugin.Unsupported.Count == 0).ToArray();
        this.mitm = mitm;
        this.report = report;
        this.requireTrustedRoot = requireTrustedRoot;
        this.profile = profile;
        if (profile != null && UserRouting.Snapshot(profile).Mode == "rule")
            independentRoutingHosts = new LoonPlugin { Hosts = UserRouting.Snapshot(profile).Rules.Where(r => r.Kind == "URL-REGEX").SelectMany(r => r.MitmHosts()).Distinct(StringComparer.OrdinalIgnoreCase).ToList() };
        server.Logging = new() { LoggerFactory = new SafeProxyLog(report), EnableConsole = false, EnableFile = false, MinimumLevel = LogLevel.Error };
        // The loopback integration harness can pin its self-signed origin and
        // trust the generated proxy root in its own client, without changing OS trust.
        if (pinnedTestOrigin != null)
            server.ServerCertificateValidationCallback += (_, e) =>
            {
                e.IsValid = e.IsValid || e.Certificate?.GetCertHashString() == pinnedTestOrigin;
                return Task.CompletedTask;
            };
        var upstream = new ExternalProxy("127.0.0.1", MihomoConfig.MixedPort) { BypassLocalhost = false };
        server.UpStreamHttpProxy = upstream;
        server.UpStreamHttpsProxy = upstream;
        server.ForwardToUpstreamGateway = false;
        server.EnableHttp2 = true;
        server.EnableHttpInterception = true;
        server.MaxBufferedBodyBytes = PluginScriptRunner.MaxBody;
        if (profile != null) server.GetCustomUpStreamProxyFunc = session =>
        {
            var route = UserRouting.ResolveUrlRoute(profile, session.HttpClient.Request.Url);
            return Task.FromResult<IExternalProxy?>(new ExternalProxy("127.0.0.1", route is { Reject: false } ? route.Port : MihomoConfig.MixedPort) { BypassLocalhost = false });
        };
        server.CertificateManager.RootCertificateName = "Swirl Plugin CA";
        server.CertificateManager.RootCertificateIssuerName = "Swirl Local Plugins";
        Directory.CreateDirectory(ProxyProfile.DirectoryPath);
        server.CertificateManager.PfxFilePath = Path.Combine(ProxyProfile.DirectoryPath, "plugin-root.pfx");
        string passwordFile = Path.Combine(ProxyProfile.DirectoryPath, "certificate-password.dat");
        if (!File.Exists(passwordFile)) File.WriteAllText(passwordFile, ProxyProfile.Protect(Convert.ToHexString(System.Security.Cryptography.RandomNumberGenerator.GetBytes(24))));
        server.CertificateManager.PfxPassword = ProxyProfile.Unprotect(File.ReadAllText(passwordFile));
        server.CertificateManager.SaveFakeCertificates = false;
    }

    internal void Start()
    {
        var endpoint = new ExplicitProxyEndPoint(IPAddress.Loopback, MihomoConfig.PluginPort, mitm);
        endpoint.BeforeTunnelConnectRequest += (_, e) =>
        {
            string host = e.HttpClient.Request.RequestUri.Host;
            e.DecryptSsl = mitm && plugins.Any(p => p.MatchesHost(host));
            if (e.DecryptSsl && independentRoutingHosts?.MatchesHost(host) == true)
            {
                // Native H2 connects one origin before request URLs are known.
                // The H2->H1 bridge opens each stream independently, so distinct
                // paths on one client H2 connection can use distinct policies.
                e.UpstreamHttpProtocol = UpstreamHttpProtocol.Http11;
                e.AllowHttpProtocolTranslation = true;
            }
            return Task.CompletedTask;
        };
        server.BeforeRequest += BeforeRequest;
        server.BeforeResponse += BeforeResponse;
        if (mitm)
        {
            server.CertificateManager.CreateRootCertificate();
            if (requireTrustedRoot && !server.CertificateManager.IsRootCertificateUserTrusted())
                throw new InvalidOperationException("请先点击“信任插件证书”，再启用 HTTPS 插件。");
        }
        server.AddEndPoint(endpoint);
        server.Start(false);
    }

    internal void TrustCertificate()
    {
        server.CertificateManager.CreateRootCertificate();
        server.CertificateManager.TrustRootCertificate(false);
        if (!server.CertificateManager.IsRootCertificateUserTrusted()) throw new InvalidOperationException("证书没有被信任。");
    }
    internal string PrepareRootFingerprint()
    {
        server.CertificateManager.CreateRootCertificate();
        return server.CertificateManager.RootCertificate?.Thumbprint ?? throw new InvalidOperationException("插件证书无法生成。");
    }
    internal System.Security.Cryptography.X509Certificates.X509Certificate2 ExportRootCertificate()
    {
        server.CertificateManager.CreateRootCertificate();
        return System.Security.Cryptography.X509Certificates.X509CertificateLoader.LoadCertificate(server.CertificateManager.RootCertificate!.RawData);
    }
    internal void RemoveCertificate()
    {
        server.CertificateManager.CreateRootCertificate();
        server.CertificateManager.RemoveTrustedRootCertificate(false);
    }

    private async Task BeforeRequest(object sender, SessionEventArgs e)
    {
        var completion = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        State(e).RequestCompletion = completion;
        try { await BeforeRequestCore(e); }
        finally { completion.TrySetResult(true); }
    }
    private async Task BeforeRequestCore(SessionEventArgs e)
    {
        string url = e.HttpClient.Request.Url;
        foreach (var plugin in plugins)
        {
            if (await RunModernRewrites(e, plugin, "http-request")) return;
            foreach (var rewrite in plugin.Rewrites.Where(r => r.Syntax.Length == 0 && r.Phase == "http-request" && LoonPlugin.Matches(r.Pattern, url)))
            {
                if (rewrite.Action.StartsWith("reject"))
                {
                    string body = rewrite.Action == "reject-dict" ? "{}" : rewrite.Action == "reject-array" ? "[]" : "";
                    if (rewrite.Action == "reject-img")
                        e.GenericResponse(Convert.FromBase64String("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII="), HttpStatusCode.OK, new[] { new HttpHeader("Content-Type", "image/png") });
                    else e.GenericResponse(body, rewrite.Action == "reject" ? HttpStatusCode.Forbidden : HttpStatusCode.OK);
                    report("插件拦截：" + plugin.Name);
                    return;
                }
                if (rewrite.Action is "302" or "307" && Uri.TryCreate(System.Text.RegularExpressions.Regex.Replace(url, rewrite.Pattern, rewrite.Target, System.Text.RegularExpressions.RegexOptions.None, TimeSpan.FromMilliseconds(100)), UriKind.Absolute, out var redirect) && redirect.Scheme is "https" or "http")
                {
                    e.GenericResponse("", (HttpStatusCode)int.Parse(rewrite.Action), new[] { new HttpHeader("Location", redirect.AbsoluteUri) });
                    report("插件重定向：" + plugin.Name);
                    return;
                }
                if (rewrite.Action == "header")
                {
                    e.HttpClient.Request.Url = System.Text.RegularExpressions.Regex.Replace(url, rewrite.Pattern, rewrite.Target, System.Text.RegularExpressions.RegexOptions.None, TimeSpan.FromMilliseconds(100));
                    url = e.HttpClient.Request.Url;
                    report("插件替换 URL：" + plugin.Name);
                }
                if (rewrite.Action == "mock-response-body")
                {
                    string type = LoonPlugin.Option(rewrite.Target, "data-type");
                    string contentType = type switch { "json" => "application/json", "html" => "text/html", "css" => "text/css", "javascript" => "application/javascript", _ => "text/plain" };
                    string status = LoonPlugin.Option(rewrite.Target, "status-code");
                    e.GenericResponse(LoonPlugin.Option(rewrite.Target, "data"), (HttpStatusCode)(status.Length == 0 ? 200 : int.Parse(status)), new[] { new HttpHeader("Content-Type", contentType + "; charset=utf-8") });
                    report("插件返回 Mock：" + plugin.Name);
                    return;
                }
            }
        }
        State(e).RequestBodyRewrite |= await RunBodyRewrites(e, "http-request");
        if (!State(e).RequestBodyRewrite) await RunScripts(e, "http-request");
        if (profile != null && !State(e).Synthetic && UserRouting.ResolveUrlRoute(profile, e.HttpClient.Request.Url) is { Reject: true })
        {
            State(e).Synthetic = true; e.GenericResponse("", HttpStatusCode.Forbidden); report("URL 分流规则拦截请求。");
        }
    }
    private async Task BeforeResponse(object sender, SessionEventArgs e)
    {
        var state = State(e);
        state.OriginalResponse = new(e.HttpClient.Request.Url, e.HttpClient.Request.Method, Headers(e.HttpClient.Response.Headers), "", e.HttpClient.Response.StatusCode);
        foreach (var plugin in plugins) await RunModernRewrites(e, plugin, "http-response");
        state.ResponseBodyRewrite |= await RunBodyRewrites(e, "http-response");
        if (!state.ResponseBodyRewrite && !state.Synthetic) await RunScripts(e, "http-response");
    }

    private async Task<bool> RunModernRewrites(SessionEventArgs e, LoonPlugin plugin, string phase)
    {
        foreach (var rewrite in plugin.Rewrites.Where(r => r.Syntax.Length > 0 && (phase == "http-request" ? r.Phase == phase || PluginRewriteEngine.IsMock(r) : r.Phase == phase && !PluginRewriteEngine.IsMock(r))))
        {
            try
            {
                var req = e.HttpClient.Request; var resp = e.HttpClient.Response;
                var context = new SyntaxContext { Request = new(req.Url, req.Method, Headers(req.Headers), ""), Response = phase == "http-response" ? new(req.Url, req.Method, Headers(resp.Headers), "", resp.StatusCode) : null };
                var outcome = await PluginRewriteEngine.ApplyAsync(plugin, rewrite, context, async () =>
                {
                    long size = phase == "http-response" ? resp.ContentLength : req.ContentLength;
                    string? type = phase == "http-response" ? resp.ContentType : req.ContentType;
                    if (size < 0 || size > 2 * 1024 * 1024 || type?.StartsWith("video/") == true || type?.StartsWith("text/event-stream") == true) throw new InvalidOperationException("正文不能缓冲。");
                    string body = phase == "http-response" ? await e.GetResponseBodyAsString() : await e.GetRequestBodyAsString();
                    if (phase == "http-request") PluginRequestBody.Hold(e, State(e).RequestCompletion?.Task);
                    return body;
                }, report);
                if (!outcome.Matched) continue;
                if (phase == "http-request") State(e).RequestBodyRewrite |= outcome.BodyMatched;
                else State(e).ResponseBodyRewrite |= outcome.BodyMatched;
                using var mutation = phase == "http-request" ? PluginRequestBody.Mutation(e) : null;
                if (outcome.SyntheticBody != null)
                {
                    State(e).Synthetic = true;
                    e.GenericResponse(outcome.SyntheticBody, (HttpStatusCode)context.Response!.Status, context.Response.Headers.Select(h => new HttpHeader(h.Key, h.Value)));
                    report("新版复写本地响应：" + plugin.Name); return true;
                }
                if (phase == "http-request")
                {
                    req.Url = context.Request.Url; ReplaceHeaders(req.Headers, context.Request.Headers);
                    if (outcome.RequestBytes != null) PluginRequestBody.Set(e, outcome.RequestBytes);
                    else if (outcome.BodyChanged) PluginRequestBody.SetString(e, context.Request.Body);
                }
                else
                {
                    ReplaceHeaders(resp.Headers, context.Response!.Headers);
                    if (outcome.BodyChanged) e.SetResponseBodyString(context.Response.Body);
                }
                report("新版复写执行：" + plugin.Name);
            }
            catch { report("新版复写失败，保留原始流量：" + plugin.Name); }
        }
        return false;
    }

    private async Task<bool> RunBodyRewrites(SessionEventArgs e, string phase)
    {
        bool applied = false;
        foreach (var plugin in plugins)
            foreach (var rewrite in plugin.Rewrites.Where(r => r.Syntax.Length == 0 && r.Phase == phase && r.Action == "json-jq" && LoonPlugin.Matches(r.Pattern, e.HttpClient.Request.Url)))
                try
                {
                    long size = phase == "http-response" ? e.HttpClient.Response.ContentLength : e.HttpClient.Request.ContentLength;
                    string? type = phase == "http-response" ? e.HttpClient.Response.ContentType : e.HttpClient.Request.ContentType;
                    if (size < 0 || size > 2 * 1024 * 1024 || type?.StartsWith("video/") == true || type?.StartsWith("text/event-stream") == true)
                        throw new InvalidOperationException("不缓冲流式或超限正文。");
                    string body = phase == "http-response" ? await e.GetResponseBodyAsString() : await e.GetRequestBodyAsString();
                    if (phase == "http-request") PluginRequestBody.Hold(e, State(e).RequestCompletion?.Task);
                    string changed = await PluginJq.RunAsync(rewrite.Target, body);
                    if (phase == "http-response") e.SetResponseBodyString(changed); else PluginRequestBody.SetString(e, changed);
                    applied = true;
                    report("jq 复写执行：" + plugin.Name);
                }
                catch { report("jq 复写失败，保留原正文：" + plugin.Name); }
        return applied;
    }

    private async Task RunScripts(SessionEventArgs e, string phase)
    {
        var request = e.HttpClient.Request;
        var response = e.HttpClient.Response;
        var selection = new SyntaxContext { Request = new(request.Url, request.Method, Headers(request.Headers), ""), Response = State(e).OriginalResponse };
        var candidates = plugins.SelectMany(plugin => plugin.Scripts.Select(script => (plugin, script)))
            .Where(pair => pair.script.Phase == phase && MatchesScript(pair.plugin, pair.script, selection)).Take(1).ToArray();
        foreach (var (plugin, script) in candidates)
        {
            try
            {
                var settings = ScriptSettings.For(plugin, script, selection);
                // Do not buffer arbitrary video streams, SSE, websocket or unbounded responses.
                if (settings.NeedsBody && (phase == "http-response" ? response.ContentLength : request.ContentLength) > 2 * 1024 * 1024)
                    throw new InvalidOperationException("匹配内容超过 2 MB，未执行脚本。");
                if (settings.NeedsBody && (phase == "http-response" ? response.HasBody && response.ContentLength < 0 : request.HasBody && request.ContentLength < 0))
                    throw new InvalidOperationException("未知长度正文不缓冲，原始流量保持不变。");
                if (settings.NeedsBody && phase == "http-response" && (response.ContentType?.StartsWith("video/") == true || response.ContentType?.StartsWith("text/event-stream") == true))
                    throw new InvalidOperationException("流式内容不执行正文脚本。");
                byte[]? requestBytes = settings.NeedsBody && settings.BinaryBody && phase == "http-request" && request.HasBody ? await e.GetRequestBody() : null;
                byte[]? responseBytes = settings.NeedsBody && settings.BinaryBody && phase == "http-response" && response.HasBody ? await e.GetResponseBody() : null;
                string requestBody = settings.NeedsBody && !settings.BinaryBody && phase == "http-request" && request.HasBody ? await e.GetRequestBodyAsString() : "";
                string responseBody = settings.NeedsBody && !settings.BinaryBody && phase == "http-response" && response.HasBody ? await e.GetResponseBodyAsString() : "";
                if (phase == "http-request") PluginRequestBody.Hold(e, State(e).RequestCompletion?.Task);
                if (requestBody.Length > 2 * 1024 * 1024 || responseBody.Length > 2 * 1024 * 1024) throw new InvalidOperationException("正文超过脚本上限。");
                if (requestBytes?.Length > PluginScriptRunner.MaxBody || responseBytes?.Length > PluginScriptRunner.MaxBody) throw new InvalidOperationException("二进制正文超过脚本上限。");
                var req = new ScriptMessage(request.Url, request.Method, Headers(request.Headers), requestBody, BodyBytes: requestBytes, Trailers: Headers(request.TrailingHeaders));
                var resp = phase == "http-response" ? new ScriptMessage(request.Url, request.Method, Headers(response.Headers), responseBody, response.StatusCode, responseBytes, Headers(response.TrailingHeaders)) : null;
                var change = await Task.Run(() => PluginScriptRunner.Run(plugin, script, req, resp, stop.Token));
                if (change == null) continue;
                using var mutation = phase == "http-request" ? PluginRequestBody.Mutation(e) : null;
                if (change.AbortRequest) { State(e).Synthetic = true; e.GenericResponse("", HttpStatusCode.Forbidden); report("请求脚本阻断：" + plugin.Name); return; }
                var targetHeaders = phase == "http-response" ? response.Headers : request.Headers;
                if (change.Headers != null && change.Headers.Any(h => !System.Text.RegularExpressions.Regex.IsMatch(h.Key, @"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$") || h.Value.Contains('\r') || h.Value.Contains('\n')))
                    throw new InvalidOperationException("脚本返回了无效头部，未应用变更。");
                if (phase == "http-request" && change.SyntheticResponse)
                {
                    State(e).Synthetic = true;
                    var headers = change.Headers?.Select(h => new HttpHeader(h.Key, h.Value)) ?? Array.Empty<HttpHeader>();
                    if (change.BodyBytes != null) e.GenericResponse(change.BodyBytes, (HttpStatusCode)(change.Status is >= 100 and <= 599 ? change.Status.Value : 200), headers);
                    else e.GenericResponse(change.Body ?? "", (HttpStatusCode)(change.Status is >= 100 and <= 599 ? change.Status.Value : 200), headers);
                    report("请求脚本返回本地响应：" + plugin.Name);
                    return;
                }
                if (change.Headers != null) ReplaceHeaders(targetHeaders, change.Headers);
                if (change.BodyBytes != null)
                {
                    if (phase == "http-response") e.SetResponseBody(change.BodyBytes); else PluginRequestBody.Set(e, change.BodyBytes);
                }
                else if (change.Body != null)
                {
                    if (phase == "http-response") e.SetResponseBodyString(change.Body); else PluginRequestBody.SetString(e, change.Body);
                }
                if (phase == "http-response" && change.Status is >= 100 and <= 599) response.StatusCode = change.Status.Value;
                if (phase == "http-request" && change.Url != null && Uri.TryCreate(change.Url, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https") request.Url = uri.AbsoluteUri;
                report("脚本执行：" + plugin.Name);
            }
            catch (Exception error) { report("脚本失败，保留原始请求/响应（" + error.GetType().Name + "）：" + plugin.Name); }
        }
    }
    private bool MatchesScript(LoonPlugin plugin, LoonScript script, SyntaxContext context)
    {
        try { return ScriptSettings.Matches(plugin, script, context); }
        catch { report("脚本条件失败，跳过本条：" + plugin.Name); return false; }
    }
    private static Dictionary<string, string> Headers(HeaderCollection headers) => headers.GetAllHeaders().GroupBy(h => h.Name, StringComparer.OrdinalIgnoreCase).ToDictionary(g => g.Key, g => string.Join(",", g.Select(h => h.Value)), StringComparer.OrdinalIgnoreCase);
    private static void ReplaceHeaders(HeaderCollection target, Dictionary<string, string> headers)
    {
        target.Clear();
        foreach (var header in headers)
            if (!header.Key.Contains('\r') && !header.Key.Contains('\n') && !header.Value.Contains('\r') && !header.Value.Contains('\n')) target.AddHeader(header.Key, header.Value);
    }
    public void Dispose() { stop.Cancel(); if (server.ProxyRunning) server.Stop(); server.Dispose(); }

    // Library diagnostics may include URLs and headers. Keep only an anonymous
    // failure notice so scripts cannot leak tokens through the app's log panel.
    private sealed class SafeProxyLog(Action<string> report) : ILoggerFactory, ILogger
    {
        public ILogger CreateLogger(string categoryName) => this;
        public void AddProvider(ILoggerProvider provider) { }
        public void Dispose() { }
        public bool IsEnabled(LogLevel logLevel) => logLevel >= LogLevel.Error;
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (IsEnabled(logLevel)) report("代理连接异常，未记录请求内容。");
        }
    }
}
