using System.Security.Cryptography;
using System.Text.Json;

namespace AdShield.Network;

internal static class CoreAssets
{
    internal sealed record Asset(string Source, string File, string Key, string Sha256);
    private sealed record Manifest(string Revision, string LicenseRevision, Asset[] Assets);
    internal static readonly Asset[] Assets = ReadManifest();
    private static Asset[] ReadManifest()
    {
        using var stream = typeof(CoreAssets).Assembly.GetManifestResourceStream("Swirl.GeoData.json")!;
        return JsonSerializer.Deserialize<Manifest>(stream, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!.Assets;
    }

    internal static int Prepare(ProxyProfile profile, string directory, string? sourceDirectory = null)
    {
        sourceDirectory ??= Path.Combine(AppContext.BaseDirectory, "core", "geodata");
        var root = string.IsNullOrWhiteSpace(profile.Yaml) ? new() : MihomoConfig.Parse(profile.Yaml);
        root.TryGetValue("geox-url", out var urls);
        Directory.CreateDirectory(directory);
        int copied = 0;
        foreach (var asset in Assets)
        {
            // A user-specified dataset can contain different categories. Do not
            // replace it with the default database merely to pass validation.
            if (urls is IDictionary<object, object> map && map.TryGetValue(asset.Key, out var value) && value is string url && !string.IsNullOrWhiteSpace(url)
                && url != "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/" + asset.Source) continue;
            var aliases = asset.Key == "mmdb" ? new[] { asset.File, "Country.mmdb", "geoip.db" } : new[] { asset.File };
            if (aliases.Any(file => File.Exists(Path.Combine(directory, file)))) continue;
            string source = Path.Combine(sourceDirectory, asset.File);
            if (!File.Exists(source)) throw new InvalidOperationException("安装包缺少 " + asset.File + " 分流数据库，请完整安装新版 Swirl。");
            using (var input = File.OpenRead(source))
                if (!Convert.ToHexString(SHA256.HashData(input)).Equals(asset.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException(asset.File + " 分流数据库校验失败，请重新安装 Swirl。");
            // No overwrite: keep caches refreshed by the core or supplied by the user.
            string target = Path.Combine(directory, asset.File);
            string staging = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try { File.Copy(source, staging); File.Move(staging, target, false); copied++; }
            finally { if (File.Exists(staging)) File.Delete(staging); }
        }
        return copied;
    }
}
