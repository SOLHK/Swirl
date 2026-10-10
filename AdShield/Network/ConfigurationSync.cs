using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AdShield.Network;

internal sealed class ConfigurationSyncStatus
{
    public bool HasRemote { get; init; }
    public bool Conflict { get; init; }
    public bool LocalChanged { get; init; }
    public string Revision { get; init; } = "";
    public int ConflictCopies { get; init; }
    public DateTimeOffset? WrittenUtc { get; init; }
    public string Message { get; init; } = "";
}

internal sealed class SyncConflictException : InvalidOperationException
{
    internal SyncConflictException(string message) : base(message) { }
}

internal sealed class PortableProfile
{
    public ProxyProfile Profile { get; set; } = new();
    public string Yaml { get; set; } = "";
    public string Subscription { get; set; } = "";
    public Dictionary<string, string> ParameterValues { get; set; } = new();
}

internal sealed class SyncEnvelope
{
    public string Format { get; set; } = "Swirl-Encrypted-Config";
    public int Version { get; set; } = 1;
    public string Revision { get; set; } = "";
    public string ParentRevision { get; set; } = "";
    public string WrittenUtc { get; set; } = "";
    public string Kdf { get; set; } = "PBKDF2-SHA256";
    public int Iterations { get; set; } = 600_000;
    public string Cipher { get; set; } = "AES-256-GCM";
    public string Salt { get; set; } = "";
    public string Nonce { get; set; } = "";
    public string Tag { get; set; } = "";
    public string Data { get; set; } = "";

    internal byte[] AuthenticatedMetadata() => JsonSerializer.SerializeToUtf8Bytes(new
    {
        Format, Version, Revision, ParentRevision, WrittenUtc, Kdf, Iterations, Cipher, Salt, Nonce
    });

    internal void Validate()
    {
        if (Format != "Swirl-Encrypted-Config" || Version != 1 || Kdf != "PBKDF2-SHA256" || Cipher != "AES-256-GCM" || Iterations != 600_000 || !Guid.TryParseExact(Revision, "N", out _) || ParentRevision != "" && !Guid.TryParseExact(ParentRevision, "N", out _) || !DateTimeOffset.TryParse(WrittenUtc, out _))
            throw new InvalidOperationException("不支持或已损坏的 Swirl 加密配置文件。");
        if (Salt == null || Nonce == null || Tag == null || Data == null || Convert.FromBase64String(Salt).Length != 16 || Convert.FromBase64String(Nonce).Length != 12 || Convert.FromBase64String(Tag).Length != 16 || Data.Length > ConfigurationSync.MaxFileSize)
            throw new InvalidOperationException("加密配置参数无效。");
    }
}

internal static class ConfigurationSync
{
    internal const string SyncFileName = "Swirl-config.swirl";
    internal const int MaxFileSize = 24 * 1024 * 1024;
    private const int MaxPlaintextSize = 16 * 1024 * 1024;

    // No password, node secret or plaintext profile is written to the sync
    // folder. CA certificates/keys, runtime files and script persistent stores
    // deliberately remain local to their Windows user.
    internal static void Export(ProxyProfile profile, string path, string password)
    {
        ValidatePassword(password);
        string target = Path.GetFullPath(path);
        var envelope = Encrypt(profile, password, "");
        if (File.Exists(target)) Backup(target);
        WriteAtomic(target, JsonSerializer.SerializeToUtf8Bytes(envelope));
    }

    // Reading returns a reviewable profile and never modifies the active one.
    // Network interception and all imported scripts stay disabled until the
    // user explicitly reviews and enables them on this Windows installation.
    internal static ProxyProfile Import(string path, string password)
    {
        var bytes = ReadBounded(Path.GetFullPath(path));
        return Decrypt(ParseEnvelope(bytes), password);
    }

    internal static ConfigurationSyncStatus GetStatus(ProxyProfile profile, string folder)
    {
        string path = SyncPath(folder);
        bool localChanged = profile.SyncContentHash.Length == 0 || Fingerprint(profile) != profile.SyncContentHash;
        if (!File.Exists(path)) return new() { LocalChanged = localChanged, Message = "此目录还没有共享配置。上传后，云盘客户端会负责同步文件。" };
        var bytes = ReadBounded(path);
        var remote = ParseEnvelope(bytes);
        int conflictCopies = ConflictCopies(Path.GetDirectoryName(path)!);
        bool conflict = conflictCopies > 0 || !string.Equals(profile.SyncFolder, Path.GetDirectoryName(path), StringComparison.OrdinalIgnoreCase) || profile.SyncRemoteRevision.Length == 0 || remote.Revision != profile.SyncRemoteRevision || Hash(bytes) != profile.SyncRemoteHash;
        return new()
        {
            HasRemote = true, Revision = remote.Revision, WrittenUtc = DateTimeOffset.Parse(remote.WrittenUtc), LocalChanged = localChanged, Conflict = conflict, ConflictCopies = conflictCopies,
            Message = conflictCopies > 0 ? "目录中发现 " + conflictCopies + " 个其他配置副本，可能是云盘冲突文件。请保留并检查，软件不会合并或删除这些文件。" : conflict ? "目录中有未接收的配置。请先下载查看，上传不会自动覆盖。" : localChanged ? "本机配置有变化，可手动上传。" : "本机与所选目录的配置一致。云端传输状态由云盘客户端提供。"
        };
    }

    internal static ConfigurationSyncStatus Upload(ProxyProfile profile, string folder, string password, bool replaceRemote = false)
    {
        ValidatePassword(password);
        string path = SyncPath(folder);
        string directory = Path.GetDirectoryName(path)!;
        Directory.CreateDirectory(directory);
        using var fileLock = LockDirectory(directory);
        if (ConflictCopies(directory) > 0 && !replaceRemote) throw new SyncConflictException("目录中存在其他 Swirl 配置副本，可能是云盘冲突文件。请先检查这些文件；普通上传不会自动覆盖。");
        byte[]? previous = File.Exists(path) ? ReadBounded(path) : null;
        string previousHash = previous == null ? "" : Hash(previous);
        SyncEnvelope? previousEnvelope = previous == null ? null : ParseEnvelope(previous);
        if (previousEnvelope != null)
        {
            // Authentication prevents publishing over a file with a different
            // password or forged revision metadata.
            _ = Decrypt(previousEnvelope, password);
            bool unseen = !string.Equals(profile.SyncFolder, directory, StringComparison.OrdinalIgnoreCase) || previousEnvelope.Revision != profile.SyncRemoteRevision || previousHash != profile.SyncRemoteHash;
            if (unseen && !replaceRemote) throw new SyncConflictException("同步目录存在新的配置，已停止上传。请先下载查看，或明确选择“备份并替换目录配置”。");
        }
        var envelope = Encrypt(profile, password, previousEnvelope?.Revision ?? "");
        var bytes = JsonSerializer.SerializeToUtf8Bytes(envelope);
        // The local lock prevents competing Swirl processes on this machine.
        // A last-moment checksum catches cloud-client replacement while the
        // password was being derived. Cloud providers can still create their
        // own conflict copies, which are retained and reported to the user.
        string currentHash = File.Exists(path) ? Hash(ReadBounded(path)) : "";
        if (currentHash != previousHash) throw new SyncConflictException("上传过程中目录配置发生变化，已停止写入。请重新下载查看。");
        if (previous != null) Backup(path, previous);
        WriteAtomic(path, bytes);
        profile.SyncFolder = directory;
        profile.SyncRemoteRevision = envelope.Revision;
        profile.SyncRemoteHash = Hash(bytes);
        profile.SyncContentHash = Fingerprint(profile);
        return new() { HasRemote = true, Revision = envelope.Revision, WrittenUtc = DateTimeOffset.Parse(envelope.WrittenUtc), Message = "已写入加密配置。请在云盘客户端确认上传完成后，再到另一台 Windows 设备下载。" };
    }

    internal static ProxyProfile Download(string folder, string password)
    {
        string path = SyncPath(folder);
        var bytes = ReadBounded(path);
        var envelope = ParseEnvelope(bytes);
        var profile = Decrypt(envelope, password);
        profile.SyncFolder = Path.GetDirectoryName(path)!;
        profile.SyncRemoteRevision = envelope.Revision;
        profile.SyncRemoteHash = Hash(bytes);
        profile.SyncContentHash = Fingerprint(profile);
        return profile;
    }

    internal static void Apply(ProxyProfile current, ProxyProfile incoming)
    {
        current.ProtectedYaml = incoming.ProtectedYaml;
        current.ProtectedSubscription = incoming.ProtectedSubscription;
        current.SubscriptionClient = Enum.IsDefined(incoming.SubscriptionClient) ? incoming.SubscriptionClient : SubscriptionClientProfile.Mihomo;
        current.SubscriptionRoute = Enum.IsDefined(incoming.SubscriptionRoute) ? incoming.SubscriptionRoute : SubscriptionDownloadRoute.Automatic;
        current.Mode = incoming.Mode;
        current.Tun = false;
        current.Mitm = false;
        current.BasicAds = false;
        current.Plugins = incoming.Plugins;
        current.UserRules = incoming.UserRules;
        current.SyncFolder = incoming.SyncFolder;
        current.SyncRemoteRevision = incoming.SyncRemoteRevision;
        current.SyncRemoteHash = incoming.SyncRemoteHash;
        current.SyncContentHash = incoming.SyncContentHash;
        current.RoutingSnapshot = null;
    }

    internal static string Summary(ProxyProfile profile) => (profile.Yaml.Length == 0 ? "没有节点配置" : "包含 Clash/Mihomo 节点配置") + "，" + profile.Plugins.Count + " 个插件，" + profile.UserRules.Count + " 条自定义规则。导入后 TUN、HTTPS 与插件执行均关闭，请检查后启用。";

    internal static string Fingerprint(ProxyProfile profile)
    {
        var bytes = Plaintext(profile);
        try { return Hash(bytes); }
        finally { CryptographicOperations.ZeroMemory(bytes); }
    }

    private static byte[] Plaintext(ProxyProfile profile)
    {
        var copy = JsonSerializer.Deserialize<ProxyProfile>(JsonSerializer.Serialize(profile)) ?? throw new InvalidOperationException("无法复制配置。");
        var payload = new PortableProfile { Profile = copy, Yaml = profile.Yaml, Subscription = profile.Subscription };
        copy.ProtectedYaml = ""; copy.ProtectedSubscription = "";
        copy.SyncFolder = ""; copy.SyncRemoteRevision = ""; copy.SyncRemoteHash = ""; copy.SyncContentHash = "";
        foreach (var plugin in copy.Plugins)
        {
            if (plugin.ProtectedParameterValues.Length > 0) payload.ParameterValues.Add(plugin.Id, ProxyProfile.Unprotect(plugin.ProtectedParameterValues));
            plugin.ProtectedParameterValues = "";
        }
        var data = JsonSerializer.SerializeToUtf8Bytes(payload);
        if (data.Length > MaxPlaintextSize) throw new InvalidOperationException("配置与插件缓存合计超过 16 MB，不能导出。");
        return data;
    }

    private static SyncEnvelope Encrypt(ProxyProfile profile, string password, string parentRevision)
    {
        var envelope = new SyncEnvelope { Revision = Guid.NewGuid().ToString("N"), ParentRevision = parentRevision, WrittenUtc = DateTimeOffset.UtcNow.ToString("O"), Salt = Convert.ToBase64String(RandomNumberGenerator.GetBytes(16)), Nonce = Convert.ToBase64String(RandomNumberGenerator.GetBytes(12)) };
        var plaintext = Plaintext(profile);
        byte[] key = Rfc2898DeriveBytes.Pbkdf2(password, Convert.FromBase64String(envelope.Salt), envelope.Iterations, HashAlgorithmName.SHA256, 32);
        try
        {
            var data = new byte[plaintext.Length]; var tag = new byte[16];
            using var cipher = new AesGcm(key, tag.Length);
            cipher.Encrypt(Convert.FromBase64String(envelope.Nonce), plaintext, data, tag, envelope.AuthenticatedMetadata());
            envelope.Data = Convert.ToBase64String(data); envelope.Tag = Convert.ToBase64String(tag);
            return envelope;
        }
        finally { CryptographicOperations.ZeroMemory(key); CryptographicOperations.ZeroMemory(plaintext); }
    }

    private static ProxyProfile Decrypt(SyncEnvelope envelope, string password)
    {
        ValidatePassword(password);
        envelope.Validate();
        byte[] data = Convert.FromBase64String(envelope.Data);
        if (data.Length > MaxPlaintextSize) throw new InvalidOperationException("配置大小超过上限。");
        var plaintext = new byte[data.Length];
        byte[] key = Rfc2898DeriveBytes.Pbkdf2(password, Convert.FromBase64String(envelope.Salt), envelope.Iterations, HashAlgorithmName.SHA256, 32);
        try
        {
            using var cipher = new AesGcm(key, 16);
            cipher.Decrypt(Convert.FromBase64String(envelope.Nonce), data, Convert.FromBase64String(envelope.Tag), plaintext, envelope.AuthenticatedMetadata());
            var payload = JsonSerializer.Deserialize<PortableProfile>(plaintext) ?? throw new InvalidOperationException("配置内容为空。");
            var profile = payload.Profile ?? throw new InvalidOperationException("配置内容缺少配置项。");
            if (profile.Mode is not ("rule" or "global" or "direct") || profile.Plugins == null || profile.UserRules == null || profile.Plugins.Count > 500 || profile.UserRules.Count > 500 || payload.Yaml == null || payload.Subscription == null || payload.ParameterValues == null)
                throw new InvalidOperationException("配置内容无效。");
            if (payload.Yaml.Length > 0) MihomoConfig.Parse(payload.Yaml);
            if (payload.Subscription.Length > 0 && (!Uri.TryCreate(payload.Subscription, UriKind.Absolute, out var subscription) || subscription.Scheme != "https" || subscription.UserInfo.Length > 0))
                throw new InvalidOperationException("配置中的订阅链接无效。");
            profile.ProtectedYaml = ProxyProfile.Protect(payload.Yaml);
            profile.ProtectedSubscription = ProxyProfile.Protect(payload.Subscription);
            profile.Tun = false; profile.Mitm = false; profile.BasicAds = false;
            profile.SyncFolder = ""; profile.SyncRemoteRevision = ""; profile.SyncRemoteHash = ""; profile.SyncContentHash = "";
            foreach (var plugin in profile.Plugins)
            {
                plugin.Enabled = false;
                plugin.ProtectedParameterValues = payload.ParameterValues.TryGetValue(plugin.Id, out string? parameters) ? ProxyProfile.Protect(parameters) : "";
            }
            profile.ReparsePlugins();
            foreach (var plugin in profile.Plugins) _ = plugin.EffectiveParameters();
            foreach (var rule in profile.UserRules) rule.Validate();
            return profile;
        }
        catch (CryptographicException) { throw new InvalidOperationException("密码不正确，或配置文件已被修改。没有导入任何配置。"); }
        catch (JsonException) { throw new InvalidOperationException("加密文件中的配置内容无效。没有导入任何配置。"); }
        finally { CryptographicOperations.ZeroMemory(key); CryptographicOperations.ZeroMemory(plaintext); }
    }

    private static SyncEnvelope ParseEnvelope(byte[] bytes)
    {
        try
        {
            var result = JsonSerializer.Deserialize<SyncEnvelope>(bytes) ?? throw new InvalidOperationException("配置文件为空。");
            result.Validate();
            return result;
        }
        catch (Exception ex) when (ex is JsonException or FormatException or ArgumentNullException)
        { throw new InvalidOperationException("不是有效的 Swirl 加密配置文件。"); }
    }

    private static void ValidatePassword(string password)
    {
        if (password == null || password.Length < 12 || password.Length > 1024) throw new InvalidOperationException("请使用至少 12 个字符的配置密码，并妥善保存；软件不会保存此密码。");
    }

    private static string SyncPath(string folder)
    {
        if (string.IsNullOrWhiteSpace(folder)) throw new InvalidOperationException("请先选择本机的 iCloud Drive、OneDrive 或其他云盘同步目录。");
        return Path.Combine(Path.GetFullPath(folder), SyncFileName);
    }

    private static byte[] ReadBounded(string path)
    {
        using var source = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (source.Length > MaxFileSize) throw new InvalidOperationException("配置文件超过 24 MB。");
        var data = new byte[checked((int)source.Length)];
        source.ReadExactly(data);
        return data;
    }

    private static FileStream LockDirectory(string directory)
    {
        try { return new FileStream(Path.Combine(directory, ".Swirl-config.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        catch (IOException) { throw new SyncConflictException("另一项同步操作正在使用此目录，请稍后重试。"); }
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));

    private static int ConflictCopies(string directory) => Directory.EnumerateFiles(directory, "Swirl-config*.swirl", SearchOption.TopDirectoryOnly).Count(file => !string.Equals(Path.GetFileName(file), SyncFileName, StringComparison.OrdinalIgnoreCase));

    private static void Backup(string path, byte[]? bytes = null)
    {
        string directory = Path.Combine(Path.GetDirectoryName(path)!, "Swirl-config-history");
        Directory.CreateDirectory(directory);
        string backup = Path.Combine(directory, Path.GetFileNameWithoutExtension(path) + "-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8] + ".swirl");
        WriteAtomic(backup, bytes ?? ReadBounded(path));
    }

    internal static void WriteAtomic(string path, byte[] bytes)
    {
        string directory = Path.GetDirectoryName(Path.GetFullPath(path))!;
        Directory.CreateDirectory(directory);
        string temporary = Path.Combine(directory, "." + Path.GetFileName(path) + "." + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None, 8192, FileOptions.WriteThrough)) { stream.Write(bytes); stream.Flush(true); }
            File.Move(temporary, path, true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
