using Jint;
using Jint.Native;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace AdShield.Network;

internal sealed record ScriptMessage(string Url, string Method, Dictionary<string, string> Headers, string Body, int Status = 200, byte[]? BodyBytes = null, Dictionary<string, string>? Trailers = null);
internal sealed record ScriptChange(string? Body, Dictionary<string, string>? Headers, int? Status, string? Url, bool SyntheticResponse = false, bool AbortRequest = false, byte[]? BodyBytes = null);

internal static class PluginScriptRunner
{
    private static readonly ConcurrentDictionary<string, object> StorageLocks = new();
    internal const int MaxBody = 2 * 1024 * 1024;
    internal static ScriptChange? Run(LoonPlugin plugin, LoonScript script, ScriptMessage? request, ScriptMessage? response, CancellationToken cancellation = default)
    {
        var context = new SyntaxContext { Response = response };
        if (request != null) context.Request = request;
        var settings = ScriptSettings.For(plugin, script, context);
        if (!settings.Enabled) return null;
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        deadline.CancelAfter(TimeSpan.FromSeconds(settings.Timeout));
        using var engine = new Engine(options => options.TimeoutInterval(TimeSpan.FromSeconds(settings.Timeout)).CancellationToken(deadline.Token)
            .MaxStatements(300000).LimitMemory(32 * 1024 * 1024).LimitRecursion(64));
        string? done = null;
        bool completed = false;
        var clock = Stopwatch.StartNew();
        var timers = new List<(int Id, JsValue Callback, DateTime Due)>();
        int timerId = 0;
        var cookies = new CookieContainer();
        engine.SetValue("__schedule", new Func<JsValue, int, int>((callback, delay) =>
        {
            if (delay < 0 || delay >= settings.Timeout * 1000 || timers.Count >= 32) throw new InvalidOperationException("脚本定时器超过运行上限。");
            int id = ++timerId;
            timers.Add((id, callback, DateTime.UtcNow.AddMilliseconds(delay)));
            return id;
        }));
        engine.SetValue("__cancel", new Action<int>(id => timers.RemoveAll(timer => timer.Id == id)));
        engine.SetValue("__request", MessageJson(request, settings.BinaryBody));
        engine.SetValue("__response", MessageJson(response, settings.BinaryBody));
        engine.SetValue("__argument", JsonSerializer.Serialize(settings.Argument));
        engine.SetValue("__scriptName", settings.Tag);
        engine.SetValue("__done", new Action<string>(value =>
        {
            if (completed) return;
            completed = true;
            done = value;
        }));
        engine.SetValue("__log", new Action<string>(_ => Store.Log("PLUGIN SCRIPT " + plugin.Name + " emitted a log")));
        engine.SetValue("__read", new Func<string, string?>(key => Storage(plugin.Id, key, null)));
        engine.SetValue("__write", new Func<string?, string, bool>((value, key) => { Storage(plugin.Id, key, value, true); return true; }));
        engine.SetValue("__removeStore", new Action(() => RemoveStorage(plugin.Id)));
        engine.SetValue("__fetch", new Func<string, string>(json =>
        {
            try { return ScriptFetch(json, cookies, deadline.Token); }
            catch (Exception error) { return JsonSerializer.Serialize(new { __swirl_error = error is OperationCanceledException ? "HTTP request timed out or was canceled" : "HTTP request failed (" + error.GetType().Name + ")" }); }
        }));
        engine.SetValue("__binary", new Func<string, string>(json =>
        {
            try { return PluginBinaryApi.Invoke(json); }
            catch (Exception error) { return JsonSerializer.Serialize(new { __swirl_error = "Binary operation failed (" + error.GetType().Name + ")" }); }
        }));
        engine.Execute("""
            function __reviveBody(object) {if(object && object.body && object.body.__swirl_bytes) object.body=new Uint8Array(object.body.__swirl_bytes); return object;}
            function __json(value) {return JSON.stringify(value,function(key,item){return item instanceof Uint8Array ? {__swirl_bytes:Array.from(item)}:item;});}
            var $request = __reviveBody(JSON.parse(__request)) || undefined;
            var $response = __reviveBody(JSON.parse(__response)) || undefined;
            var $argument = JSON.parse(__argument);
            var $loon = 'Windows Swirl 0.6.0 Loon-compatible';
            var $script = {name:__scriptName,startTime:new Date()};
            var $environment = {version:'0.6.0',platform:'Windows',params:{}};
            var $done = function(value){__done(__json(value===undefined?{__adshield_abort:true}:value));};
            var console = {log:function(){__log('log');},warn:function(){__log('warn');},error:function(){__log('error');}};
            var $persistentStore = {read:function(key){return __read(key===undefined?__scriptName:String(key));},write:function(value,key){return __write(value==null?null:String(value),key===undefined?__scriptName:String(key));},remove:function(){__removeStore();}};
            var $notification = {post:function(){__log('notification');}};
            var $httpClient = {};
            ['get','post','put','delete','head','patch','options'].forEach(function(method){
                $httpClient[method] = function(options,callback){
                    var result;
                    try {
                        if(typeof options === 'string') options={url:options};
                        options=Object.assign({},options,{method:method.toUpperCase()});
                        result=__reviveBody(JSON.parse(__fetch(__json(options))));
                    } catch(e) { callback(String(e),null,null);return; }
                    if(result.__swirl_error){callback(result.__swirl_error,null,null);return;}
                    callback(null,{status:result.status,statusCode:result.status,headers:result.headers,h2_trailers:result.h2_trailers},result.body);
                };
            });
            var $task = {fetch:function(options){
                try{if(typeof options==='string')options={url:options};var result=__reviveBody(JSON.parse(__fetch(__json(options))));return result.__swirl_error?Promise.reject(new Error(result.__swirl_error)):Promise.resolve(result);}
                catch(e){return Promise.reject(e);}
            }};
            var setTimeout=function(callback,delay){var args=Array.prototype.slice.call(arguments,2);return __schedule(function(){callback.apply(null,args);},Number(delay)||0);};
            var clearTimeout=function(id){__cancel(Number(id));};
            var setInterval=setTimeout;
            var clearInterval=clearTimeout;
            function __binaryCall(value){var result=JSON.parse(__binary(__json(value)));if(result.__swirl_error)throw new Error(result.__swirl_error);return result;}
            var $utils = {gzip:function(data){return new Uint8Array(__binaryCall({operation:'gzip',data:data}));},ungzip:function(data){return new Uint8Array(__binaryCall({operation:'ungzip',data:data}));}};
            var $crypto={aes:{encrypt:function(data,options){var result=__binaryCall({operation:'encrypt',data:data,options:options});result.ciphertext=new Uint8Array(result.ciphertext);if(result.tag)result.tag=new Uint8Array(result.tag);return result;},decrypt:function(data,options){return new Uint8Array(__binaryCall({operation:'decrypt',data:data,options:options}));}}};
            """);
        engine.Execute(script.Code);
        engine.Advanced.ProcessTasks();
        while (!completed && timers.Count > 0)
        {
            var timer = timers.OrderBy(t => t.Due).First();
            int wait = Math.Max(0, (int)Math.Ceiling((timer.Due - DateTime.UtcNow).TotalMilliseconds));
            if (clock.ElapsedMilliseconds + wait > settings.Timeout * 1000) throw new InvalidOperationException("脚本定时器超时。");
            if (wait > 0 && deadline.Token.WaitHandle.WaitOne(wait)) deadline.Token.ThrowIfCancellationRequested();
            timers.Remove(timer);
            engine.Invoke(timer.Callback);
            engine.Advanced.ProcessTasks();
            if (clock.ElapsedMilliseconds > settings.Timeout * 1000) throw new InvalidOperationException("脚本总运行时间超时。");
        }
        if (!completed) throw new InvalidOperationException("脚本未调用 $done，原始请求保持不变。");
        // A JSON representation of 2 MB of Uint8Array data is larger than 2 MB.
        // The decoded byte limit is enforced separately before applying changes.
        if (done == null || done.Length > 10 * MaxBody) throw new InvalidOperationException("脚本输出无效或过大。");
        using var document = JsonDocument.Parse(done);
        var root = document.RootElement;
        if (root.ValueKind == JsonValueKind.String)
        {
            string value = root.GetString()!;
            if (Encoding.UTF8.GetByteCount(value) > MaxBody) throw new InvalidOperationException("脚本正文超过上限。");
            return new(value, null, null, null);
        }
        if (root.ValueKind != JsonValueKind.Object) return null;
        if (root.TryGetProperty("__adshield_abort", out _) && script.Phase == "http-request") return new(null, null, null, null, AbortRequest: true);
        bool synthetic = root.TryGetProperty("response", out var nested) && nested.ValueKind == JsonValueKind.Object;
        if (synthetic) root = nested;
        Dictionary<string, string>? headers = null;
        if (root.TryGetProperty("headers", out var h) && h.ValueKind == JsonValueKind.Object)
            headers = h.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.ToString(), StringComparer.OrdinalIgnoreCase);
        int? status = null;
        if (root.TryGetProperty("status", out var s) || root.TryGetProperty("statusCode", out s))
        {
            if (int.TryParse(s.ToString(), out int code)) status = code;
            else if (System.Text.RegularExpressions.Regex.Match(s.ToString(), @"\b([1-5][0-9]{2})\b") is { Success: true } match)
                status = int.Parse(match.Groups[1].Value);
        }
        string? changedBody = null; byte[]? changedBytes = null;
        if (root.TryGetProperty("body", out var b))
        {
            if (b.ValueKind == JsonValueKind.Object && b.TryGetProperty("__swirl_bytes", out _)) changedBytes = ReadBytes(b);
            else if (b.ValueKind == JsonValueKind.String) changedBody = b.GetString();
            else throw new InvalidOperationException("脚本 body 必须是字符串或 Uint8Array。");
            if (changedBody != null && Encoding.UTF8.GetByteCount(changedBody) > MaxBody) throw new InvalidOperationException("脚本正文超过上限。");
        }
        return new(changedBody, headers, status, root.TryGetProperty("url", out var u) ? u.GetString() : null, synthetic, BodyBytes: changedBytes);
    }

    private static string MessageJson(ScriptMessage? message, bool binary)
    {
        if (message == null) return "null";
        object body = binary ? new Dictionary<string, object> { ["__swirl_bytes"] = (message.BodyBytes ?? Encoding.UTF8.GetBytes(message.Body)).Select(b => (int)b).ToArray() } : message.Body;
        return JsonSerializer.Serialize(new { url = message.Url, method = message.Method, status = message.Status, statusCode = message.Status, headers = message.Headers, body, h2_trailers = message.Trailers ?? new() });
    }

    internal static byte[] ReadBytes(JsonElement value)
    {
        if (value.ValueKind != JsonValueKind.Object || !value.TryGetProperty("__swirl_bytes", out var array) || array.ValueKind != JsonValueKind.Array || array.GetArrayLength() > MaxBody)
            throw new InvalidOperationException("二进制值必须是有界 Uint8Array。");
        var bytes = new byte[array.GetArrayLength()]; int position = 0;
        foreach (var item in array.EnumerateArray())
            bytes[position++] = item.TryGetInt32(out int number) && number is >= 0 and <= 255 ? (byte)number : throw new InvalidOperationException("二进制字节无效。");
        return bytes;
    }

    private static string? Storage(string id, string key, string? value, bool write = false)
    {
        if (!Guid.TryParseExact(id, "N", out _) || key.Length > 256 || value?.Length > 65536) throw new InvalidOperationException("脚本存储参数无效。");
        lock (StorageLocks.GetOrAdd(id, _ => new object()))
        {
            string folder = Path.Combine(ProxyProfile.DirectoryPath, "script-storage"), path = Path.Combine(folder, id + ".dat");
            var items = File.Exists(path) ? JsonSerializer.Deserialize<Dictionary<string, string>>(ProxyProfile.Unprotect(File.ReadAllText(path)))! : new Dictionary<string, string>();
            if (!write) return items.GetValueOrDefault(key);
            if (value == null) items.Remove(key); else items[key] = value;
            if (items.Count > 300 || JsonSerializer.Serialize(items).Length > 1024 * 1024) throw new InvalidOperationException("脚本存储超过上限。");
            Directory.CreateDirectory(folder);
            File.WriteAllText(path, ProxyProfile.Protect(JsonSerializer.Serialize(items)));
            return value;
        }
    }

    private static void RemoveStorage(string id)
    {
        if (!Guid.TryParseExact(id, "N", out _)) throw new InvalidOperationException("脚本存储标识无效。");
        lock (StorageLocks.GetOrAdd(id, _ => new object()))
        {
            string path = Path.Combine(ProxyProfile.DirectoryPath, "script-storage", id + ".dat");
            if (File.Exists(path)) File.Delete(path);
        }
    }

    private static string ScriptFetch(string json, CookieContainer cookies, CancellationToken cancellation)
    {
        using var document = JsonDocument.Parse(json);
        var options = document.RootElement;
        string url = options.GetProperty("url").GetString() ?? "";
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https")) throw new InvalidOperationException("脚本请求必须使用 HTTP/HTTPS。");
        bool Flag(string key, bool fallback) => options.TryGetProperty(key, out var flag) ? flag.ValueKind is JsonValueKind.True or JsonValueKind.False ? flag.GetBoolean() : throw new InvalidOperationException(key + " 必须是 Boolean。") : fallback;
        if (options.TryGetProperty("node", out var node) && node.GetString() is { Length: > 0 }) throw new InvalidOperationException("此运行环境尚未提供脚本指定节点接口。");
        using var handler = new HttpClientHandler { Proxy = new WebProxy("http://127.0.0.1:" + MihomoConfig.MixedPort), UseProxy = true, AllowAutoRedirect = Flag("auto-redirect", true), CookieContainer = cookies, UseCookies = Flag("auto-cookie", true), AutomaticDecompression = DecompressionMethods.All, MaxAutomaticRedirections = 10 };
        // An imported script can opt into the Loon insecure behavior; ordinary
        // requests retain platform certificate verification by default.
        if (Flag("insecure", false)) handler.ServerCertificateCustomValidationCallback = (_, _, _, _) => true;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        double timeoutMs = options.TryGetProperty("timeout", out var requested) && requested.TryGetDouble(out double milliseconds) ? milliseconds : 5000;
        if (!double.IsFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 300000) throw new InvalidOperationException("HTTP 请求超时必须为 0～300000 毫秒。");
        timeout.CancelAfter(TimeSpan.FromMilliseconds(timeoutMs));
        using var client = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        var method = options.TryGetProperty("method", out var m) ? m.GetString() ?? "GET" : "GET";
        using var request = new HttpRequestMessage(new HttpMethod(method), uri);
        if (options.TryGetProperty("alpn", out var alpn))
        {
            request.Version = alpn.GetString() switch { "h1" => HttpVersion.Version11, "h2" => HttpVersion.Version20, _ => throw new InvalidOperationException("alpn 必须是 h1 或 h2。") };
            request.VersionPolicy = HttpVersionPolicy.RequestVersionExact;
        }
        if (options.TryGetProperty("body", out var body))
        {
            byte[] bytes = body.ValueKind == JsonValueKind.Object ? ReadBytes(body) : body.ValueKind == JsonValueKind.String ? Flag("body-base64", false) ? Convert.FromBase64String(body.GetString()!) : Encoding.UTF8.GetBytes(body.GetString()!) : throw new InvalidOperationException("HTTP body 必须是字符串或 Uint8Array。");
            if (bytes.Length > MaxBody) throw new InvalidOperationException("HTTP 请求正文超过上限。");
            request.Content = new ByteArrayContent(bytes);
        }
        if (options.TryGetProperty("headers", out var headers) && headers.ValueKind == JsonValueKind.Object)
            foreach (var header in headers.EnumerateObject())
            {
                string value = header.Value.ToString();
                if (!System.Text.RegularExpressions.Regex.IsMatch(header.Name, @"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$") || value.Contains('\r') || value.Contains('\n')) throw new InvalidOperationException("HTTP 请求头无效。");
                if (!request.Headers.TryAddWithoutValidation(header.Name, value))
                {
                    request.Content ??= new ByteArrayContent(Array.Empty<byte>());
                    request.Content.Headers.Remove(header.Name);
                    if (!request.Content.Headers.TryAddWithoutValidation(header.Name, value)) throw new InvalidOperationException("HTTP 请求头不能应用。");
                }
            }
        using var response = client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token).GetAwaiter().GetResult();
        if (response.Content.Headers.ContentLength > MaxBody) throw new InvalidOperationException("脚本下载内容过大。");
        using var stream = response.Content.ReadAsStream();
        using var output = new MemoryStream();
        var buffer = new byte[8192];
        int read;
        while ((read = stream.ReadAsync(buffer.AsMemory(), timeout.Token).AsTask().GetAwaiter().GetResult()) > 0)
        {
            if (output.Length + read > MaxBody) throw new InvalidOperationException("脚本下载超过上限。");
            output.Write(buffer, 0, read);
        }
        var responseHeaders = response.Headers.Concat(response.Content.Headers).GroupBy(h => h.Key, StringComparer.OrdinalIgnoreCase).ToDictionary(g => g.Key, g => string.Join(",", g.SelectMany(h => h.Value)), StringComparer.OrdinalIgnoreCase);
        var trailers = response.TrailingHeaders.ToDictionary(h => h.Key, h => string.Join(",", h.Value), StringComparer.OrdinalIgnoreCase);
        byte[] resultBytes = output.ToArray(); object resultBody;
        try { resultBody = Flag("binary-mode", false) ? BinaryJson(resultBytes) : new UTF8Encoding(false, true).GetString(resultBytes); }
        catch (DecoderFallbackException) { resultBody = BinaryJson(resultBytes); }
        return JsonSerializer.Serialize(new { status = (int)response.StatusCode, statusCode = (int)response.StatusCode, headers = responseHeaders, h2_trailers = trailers, body = resultBody });
    }
    private static object BinaryJson(byte[] bytes) => new Dictionary<string, object> { ["__swirl_bytes"] = bytes.Select(b => (int)b).ToArray() };
}
