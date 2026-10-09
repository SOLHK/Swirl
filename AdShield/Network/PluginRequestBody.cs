using System.Runtime.CompilerServices;
using Titanium.Web.Proxy.EventArguments;
using Titanium.Web.Proxy.Http;

namespace AdShield.Network;

internal static class PluginRequestBody
{
    private static readonly bool PinnedVersion = typeof(Titanium.Web.Proxy.ProxyServer).Assembly.GetName().Version == new Version(7, 0, 19, 0);
    // Titanium 7.0.19's native H2 path defers outbound HEADERS when a
    // BeforeRequest handler buffers the body, but sets Request.Locked before
    // completing that handler. The public SetRequestBody method therefore
    // rejects a valid edit. At this call site we are still in BeforeRequest
    // with a fully buffered body; writing the same body property used by the
    // public method preserves its length/encoding bookkeeping. Keep this
    // narrowly scoped and recheck it when upgrading the pinned dependency.
    internal static void Set(SessionEventArgs session, byte[] body)
    {
        var request = session.HttpClient.Request;
        if (Deferred(request)) SetBufferedBody(request, body);
        else session.SetRequestBody(body);
    }
    internal static void SetString(SessionEventArgs session, string body) => Set(session, session.HttpClient.Request.Encoding.GetBytes(body));

    // The native buffered H2 path retains its short dispatch task rather than
    // the full asynchronous BeforeRequest handler. Explicitly hold forwarding
    // until our handler finishes; otherwise Task.Run/HTTP/jq edits race DATA.
    internal static void Hold(SessionEventArgs session, Task? completion)
    {
        var request = session.HttpClient.Request;
        if (completion != null && Deferred(request)) HandlerTask(request) = completion;
    }
    internal static IDisposable? Mutation(SessionEventArgs session)
    {
        var request = session.HttpClient.Request;
        if (!Deferred(request)) return null;
        bool old = GetLocked(request); SetLocked(request, false);
        return new RestoreLock(request, old);
    }
    private static bool Deferred(Request request) => PinnedVersion && request.HttpVersion == System.Net.HttpVersion.Version20 && request.IsBodyRead && HeadersDeferred(request);

    private sealed class RestoreLock(Request request, bool value) : IDisposable
    {
        public void Dispose() => SetLocked(request, value);
    }

    [UnsafeAccessor(UnsafeAccessorKind.Method, Name = "set_Body")]
    private static extern void SetBufferedBody(RequestResponseBase message, byte[] body);

    [UnsafeAccessor(UnsafeAccessorKind.Field, Name = "Http2HeadersDeferred")]
    private static extern ref bool HeadersDeferred(RequestResponseBase message);
    [UnsafeAccessor(UnsafeAccessorKind.Field, Name = "Http2BeforeHandlerTask")]
    private static extern ref Task? HandlerTask(RequestResponseBase message);
    [UnsafeAccessor(UnsafeAccessorKind.Method, Name = "get_Locked")]
    private static extern bool GetLocked(RequestResponseBase message);
    [UnsafeAccessor(UnsafeAccessorKind.Method, Name = "set_Locked")]
    private static extern void SetLocked(RequestResponseBase message, bool value);
}
