using System.Net;
using System.Net.Http;
using System.Text;

namespace AdShield.Network;

internal enum SubscriptionClientProfile { Mihomo, Clash, Browser }

internal sealed record SubscriptionDownload(string Content, string NormalizedSource);

/// <summary>
/// Subscription fetching has its own client identity. Plugin/script downloads
/// continue using NetworkFetch and never inherit an airport compatibility UA.
/// </summary>
internal static class SubscriptionImport
{
    internal const int SizeLimit = 4 * 1024 * 1024;
    private const int AddressLimit = 32 * 1024;
    private const int RedirectLimit = 5;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);

    internal static string UserAgent(SubscriptionClientProfile clientProfile) => clientProfile switch
    {
        // The official MetaCubeX dashboard uses this identity for subscription import.
        SubscriptionClientProfile.Mihomo => "clash.meta",
        SubscriptionClientProfile.Clash => "clash",
        SubscriptionClientProfile.Browser => "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        _ => throw new InvalidOperationException("请选择有效的订阅下载方式。")
    };

    internal static Uri ParseAddress(string raw)
    {
        if (raw == null) throw InvalidAddress();
        string address = raw.Trim();
        ValidateAddressText(address);
        address = DecodeWholeAddress(address);
        if (!Uri.TryCreate(address, UriKind.Absolute, out var candidate)) throw InvalidAddress();

        if (IsInstallScheme(candidate.Scheme))
        {
            if (!candidate.Host.Equals("install-config", StringComparison.OrdinalIgnoreCase)
                || candidate.AbsolutePath is not ("" or "/") || candidate.UserInfo.Length != 0
                || !candidate.IsDefaultPort || candidate.Fragment.Length != 0) throw InvalidAddress();
            string? wrapped = null;
            foreach (string part in candidate.Query.TrimStart('?').Split('&'))
            {
                int separator = part.IndexOf('=');
                if (separator < 0) continue;
                string key = DecodePercent(part[..separator]);
                if (!key.Equals("url", StringComparison.OrdinalIgnoreCase)) continue;
                if (wrapped != null) throw InvalidAddress();
                // Decode the wrapper layer once when encoded. An unencoded
                // HTTPS target already has its own token/query escaping.
                string value = part[(separator + 1)..];
                wrapped = value.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
                    || value.StartsWith("http://", StringComparison.OrdinalIgnoreCase) ? value : DecodePercent(value);
            }
            if (string.IsNullOrWhiteSpace(wrapped)) throw InvalidAddress();
            ValidateAddressText(wrapped);
            address = DecodeWholeAddress(wrapped);
        }
        return RequireHttps(address);
    }

    internal static async Task<SubscriptionDownload> DownloadAsync(string raw,
        SubscriptionClientProfile clientProfile = SubscriptionClientProfile.Mihomo,
        CancellationToken cancellationToken = default)
    {
        using var transport = new HttpClientHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate | DecompressionMethods.Brotli
        };
        return await DownloadAsync(raw, clientProfile, transport, cancellationToken);
    }

    // Tests can inject an HTTPS-aware fake/loopback adapter. This does not relax
    // address validation or TLS checking in the production transport above.
    internal static async Task<SubscriptionDownload> DownloadAsync(string raw,
        SubscriptionClientProfile clientProfile, HttpMessageHandler transport,
        CancellationToken cancellationToken = default)
    {
        Uri source = ParseAddress(raw);
        string userAgent = UserAgent(clientProfile);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        using var client = new HttpClient(transport, disposeHandler: false) { Timeout = Timeout.InfiniteTimeSpan };
        try
        {
            Uri current = source;
            for (int redirects = 0; ; redirects++)
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, current);
                request.Headers.UserAgent.ParseAdd(userAgent);
                request.Headers.Accept.ParseAdd("application/yaml, application/x-yaml, text/yaml, text/x-yaml, text/plain;q=0.9, */*;q=0.1");
                using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, timeout.Token);
                if (IsRedirect(response.StatusCode))
                {
                    if (redirects >= RedirectLimit) throw new InvalidOperationException("订阅地址重定向过多，请检查地址后重试。");
                    var location = response.Headers.Location;
                    if (location == null) throw new InvalidOperationException("订阅服务器返回了无效的重定向。");
                    try { current = RequireHttps(new Uri(current, location).AbsoluteUri); }
                    catch { throw new InvalidOperationException("订阅服务器的重定向地址无效；仅支持 HTTPS 地址。"); }
                    continue;
                }
                if (!response.IsSuccessStatusCode) throw HttpError(response.StatusCode);
                if (response.Content.Headers.ContentLength > SizeLimit) throw TooLarge();
                string? mediaType = response.Content.Headers.ContentType?.MediaType;
                if (mediaType?.Equals("text/html", StringComparison.OrdinalIgnoreCase) == true
                    || mediaType?.Equals("application/xhtml+xml", StringComparison.OrdinalIgnoreCase) == true) throw HtmlResponse();

                using var input = await response.Content.ReadAsStreamAsync(timeout.Token);
                using var output = new MemoryStream();
                byte[] buffer = new byte[8192];
                int read;
                while ((read = await input.ReadAsync(buffer, timeout.Token)) > 0)
                {
                    if (output.Length + read > SizeLimit) throw TooLarge();
                    output.Write(buffer, 0, read);
                }
                string text;
                try { text = StrictUtf8.GetString(output.GetBuffer(), 0, (int)output.Length).TrimStart('\uFEFF'); }
                catch (DecoderFallbackException) { throw new InvalidOperationException("订阅内容不是有效的 UTF-8 配置，请从服务商获取 Clash/Mihomo YAML 地址。"); }
                if (string.IsNullOrWhiteSpace(text)) throw new InvalidOperationException("订阅服务器返回了空内容，请检查订阅状态或改用本地 YAML 导入。");
                string beginning = text.AsSpan(0, Math.Min(text.Length, 512)).TrimStart().ToString();
                if (beginning.StartsWith("<!doctype html", StringComparison.OrdinalIgnoreCase)
                    || beginning.StartsWith("<html", StringComparison.OrdinalIgnoreCase)
                    || beginning.StartsWith("<head", StringComparison.OrdinalIgnoreCase)
                    || beginning.StartsWith("<body", StringComparison.OrdinalIgnoreCase)) throw HtmlResponse();
                return new(text, source.AbsoluteUri);
            }
        }
        catch (OperationCanceledException)
        {
            if (cancellationToken.IsCancellationRequested)
                throw new OperationCanceledException("订阅下载已取消。", cancellationToken);
            throw new InvalidOperationException("下载订阅超时（30 秒），请检查网络后重试。");
        }
        catch (HttpRequestException)
        {
            // HttpClient exceptions may include the complete private subscription
            // URI. Never attach the exception or its message to UI/log failures.
            throw new InvalidOperationException("无法连接订阅服务器，请检查网络、系统代理和服务器证书后重试。");
        }
        catch (IOException)
        {
            throw new InvalidOperationException("订阅下载中断，请检查网络后重试。");
        }
    }

    private static bool IsInstallScheme(string scheme) => scheme is "clash" or "clash-verge" or "mihomo";
    private static bool IsRedirect(HttpStatusCode status) => status is HttpStatusCode.MovedPermanently
        or HttpStatusCode.Redirect or HttpStatusCode.SeeOther or HttpStatusCode.TemporaryRedirect or HttpStatusCode.PermanentRedirect;

    private static Uri RequireHttps(string address)
    {
        ValidateAddressText(address);
        if (!Uri.TryCreate(address, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps
            || !address.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
            || uri.Host.Length == 0 || uri.HostNameType == UriHostNameType.Unknown
            || uri.UserInfo.Length != 0 || uri.Fragment.Length != 0) throw InvalidAddress();
        return uri;
    }

    private static string DecodeWholeAddress(string address)
    {
        for (int layer = 0; layer < 2; layer++)
        {
            if (address.StartsWith("https://", StringComparison.OrdinalIgnoreCase)
                || address.StartsWith("http://", StringComparison.OrdinalIgnoreCase)
                || Uri.TryCreate(address, UriKind.Absolute, out var uri) && IsInstallScheme(uri.Scheme)) break;
            if (!address.Contains('%')) break;
            string decoded = DecodePercent(address);
            if (decoded == address) break;
            address = decoded;
            ValidateAddressText(address);
        }
        return address;
    }

    private static void ValidateAddressText(string address)
    {
        if (address.Length is 0 or > AddressLimit || address.Any(char.IsControl) || address.Contains('\\')) throw InvalidAddress();
        for (int i = 0; i < address.Length; i++)
        {
            if (address[i] != '%') continue;
            if (i + 2 >= address.Length || !Uri.IsHexDigit(address[i + 1]) || !Uri.IsHexDigit(address[i + 2])) throw InvalidAddress();
            int value = Convert.ToInt32(address.Substring(i + 1, 2), 16);
            if (value < 32 || value == 127) throw InvalidAddress();
            i += 2;
        }
    }

    private static string DecodePercent(string value)
    {
        // Do not use form decoding: '+' is a valid literal in subscription tokens.
        ValidateAddressText(value);
        try { return Uri.UnescapeDataString(value); }
        catch { throw InvalidAddress(); }
    }

    private static InvalidOperationException InvalidAddress() => new("请粘贴完整的 HTTPS 订阅地址，或 Clash / Clash Verge / Mihomo 的 install-config 链接；地址不能含登录信息、控制字符或片段。");
    private static InvalidOperationException TooLarge() => new("订阅配置超过 4 MB，无法导入。");
    private static InvalidOperationException HtmlResponse() => new("订阅服务器返回了网页，而不是 Clash/Mihomo 配置。可切换 Clash / 浏览器下载方式后重试，或在浏览器下载 YAML 后本地导入。");
    private static InvalidOperationException HttpError(HttpStatusCode status) => new(status switch
    {
        HttpStatusCode.Forbidden => "订阅服务器拒绝了请求（HTTP 403）。可切换 Clash / 浏览器下载方式后重试；仍失败时，请从可用的 Clash 客户端导出 YAML 后本地导入。",
        HttpStatusCode.Unauthorized => "订阅服务器要求有效授权（HTTP 401）。请检查订阅状态并重新复制完整地址。",
        HttpStatusCode.NotFound => "订阅地址不存在（HTTP 404）。请从服务商重新复制 Clash/Mihomo 订阅地址。",
        _ => "订阅下载失败（HTTP " + (int)status + "），请检查订阅状态或在浏览器下载 YAML 后本地导入。"
    });
}
