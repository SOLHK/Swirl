using System.Globalization;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace AdShield.Network;

internal sealed class SubscriptionUsage
{
    public long? Upload { get; set; }
    public long? Download { get; set; }
    public long? Total { get; set; }
    public long? Expire { get; set; }
    internal long? Used => Upload.HasValue && Download.HasValue && Upload.Value <= long.MaxValue - Download.Value ? Upload + Download : null;
    internal DateTimeOffset? Expires => Expire is > 0 and <= 253402300799 ? DateTimeOffset.FromUnixTimeSeconds(Expire.Value) : null;
    internal double? Percent => Used.HasValue && Total is > 0 ? Math.Clamp(Used.Value * 100d / Total.Value, 0, 100) : null;
    internal static SubscriptionUsage? Parse(string? header)
    {
        if (string.IsNullOrWhiteSpace(header) || header.Length > 2048) return null;
        var fields = new Dictionary<string, long>(StringComparer.OrdinalIgnoreCase);
        foreach (string item in header.Split(';'))
        {
            var pair = item.Trim().Split('=', 2);
            if (pair.Length == 2 && long.TryParse(pair[1].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out long value) && value >= 0) fields[pair[0].Trim()] = value;
        }
        long? Read(string name) => fields.TryGetValue(name, out var value) ? value : null;
        var usage = new SubscriptionUsage { Upload = Read("upload"), Download = Read("download"), Total = Read("total"), Expire = Read("expire") };
        return usage.Upload == null && usage.Download == null && usage.Total == null && usage.Expire == null ? null : usage;
    }
}

// This whole record list is encrypted at rest. URLs, YAML, choices and policy
// edits never become plaintext fields in profile.json or screenshot fixtures.
internal sealed class SubscriptionEntry
{
    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Name { get; set; } = "我的订阅";
    public string Source { get; set; } = "";
    public string Yaml { get; set; } = "";
    public DateTimeOffset? UpdatedAt { get; set; }
    public SubscriptionUsage? Usage { get; set; }
    public SubscriptionClientProfile Client { get; set; }
    public SubscriptionDownloadRoute Route { get; set; }
    public Dictionary<string, string> Selections { get; set; } = new();
    public List<PolicyGroupSettings> Groups { get; set; } = new();
    internal string Origin => Uri.TryCreate(Source, UriKind.Absolute, out var uri) ? uri.IdnHost : "本地 YAML 文件";
}

internal static class SubscriptionLibrary
{
    internal static List<SubscriptionEntry> Read(ProxyProfile profile)
        => string.IsNullOrEmpty(profile.ProtectedLibrary) ? [] : JsonSerializer.Deserialize<List<SubscriptionEntry>>(ProxyProfile.Unprotect(profile.ProtectedLibrary)) ?? [];
    internal static void Write(ProxyProfile profile, List<SubscriptionEntry> entries)
    {
        if (entries.Count > 20 || entries.Sum(e => (long)Encoding.UTF8.GetByteCount(e.Yaml)) > 12 * 1024 * 1024) throw new InvalidOperationException("最多保存 20 份配置，配置内容合计不能超过 12 MB。请移除不用的订阅后再添加。");
        profile.ProtectedLibrary = entries.Count == 0 ? "" : ProxyProfile.Protect(JsonSerializer.Serialize(entries));
    }
    internal static void Ensure(ProxyProfile profile)
    {
        if (profile.ProtectedLibrary.Length > 0 || profile.ProtectedYaml.Length == 0) return;
        var entry = new SubscriptionEntry { Name = profile.ProtectedSubscription.Length > 0 ? "我的订阅" : "本地配置", Source = profile.Subscription, Yaml = profile.Yaml, Client = profile.SubscriptionClient, Route = profile.SubscriptionRoute, Selections = profile.SelectedProxies, Groups = profile.GroupSettings };
        Write(profile, [entry]); profile.ActiveSubscriptionId = entry.Id;
    }
    internal static void CaptureActive(ProxyProfile profile)
    {
        var entries = Read(profile); var active = entries.FirstOrDefault(e => e.Id == profile.ActiveSubscriptionId);
        if (active == null) return;
        string before = JsonSerializer.Serialize(active);
        active.Yaml = profile.Yaml; active.Source = profile.Subscription; active.Client = profile.SubscriptionClient; active.Route = profile.SubscriptionRoute;
        active.Selections = profile.SelectedProxies; active.Groups = profile.GroupSettings;
        if (before != JsonSerializer.Serialize(active)) Write(profile, entries);
    }
    internal static SubscriptionEntry Add(ProxyProfile profile, string name, SubscriptionDownload download, SubscriptionClientProfile client, SubscriptionDownloadRoute route, string? replaceId = null)
    {
        string yaml = MihomoConfig.ParseSubscription(download.Content);
        Ensure(profile); CaptureActive(profile); var entries = Read(profile);
        var entry = replaceId != null ? entries.FirstOrDefault(e => e.Id == replaceId) ?? throw new InvalidOperationException("这份配置已经移除，请刷新后再导入。") : download.NormalizedSource.Length > 0 ? entries.FirstOrDefault(e => e.Source == download.NormalizedSource) : null;
        bool first = entries.Count == 0;
        entry ??= new SubscriptionEntry();
        if (entry.Groups.Count > 0)
        {
            var candidate = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(yaml), GroupSettings = entry.Groups };
            try { UserProxyGroups.Apply(candidate, MihomoConfig.Parse(yaml)); }
            catch (InvalidOperationException) { throw new InvalidOperationException("更新后的节点与自定义策略组不匹配。旧配置已保留，请先调整策略组成员，再更新订阅。"); }
        }
        entry.Name = CleanName(name.Length > 0 ? name : entry.Name); entry.Source = download.NormalizedSource;
        entry.Yaml = yaml; entry.UpdatedAt = DateTimeOffset.UtcNow; entry.Usage = download.Usage; entry.Client = client; entry.Route = route;
        if (!entries.Any(e => e.Id == entry.Id)) entries.Add(entry);
        Write(profile, entries);
        if (first || profile.ActiveSubscriptionId == entry.Id) Apply(profile, entry);
        return entry;
    }
    internal static void Activate(ProxyProfile profile, string id)
    {
        Ensure(profile); CaptureActive(profile);
        var entry = Read(profile).FirstOrDefault(e => e.Id == id) ?? throw new InvalidOperationException("这份配置已经移除，请刷新列表。");
        Apply(profile, entry);
    }
    private static void Apply(ProxyProfile profile, SubscriptionEntry entry)
    {
        profile.ActiveSubscriptionId = entry.Id; profile.ProtectedYaml = ProxyProfile.Protect(entry.Yaml); profile.ProtectedSubscription = ProxyProfile.Protect(entry.Source);
        profile.SubscriptionClient = entry.Client; profile.SubscriptionRoute = entry.Route; profile.SelectedProxies = entry.Selections; profile.GroupSettings = entry.Groups; profile.RoutingSnapshot = null;
    }
    internal static void Rename(ProxyProfile profile, string id, string name)
    {
        var entries = Read(profile); var entry = entries.FirstOrDefault(e => e.Id == id) ?? throw new InvalidOperationException("没有找到这份配置。");
        entry.Name = CleanName(name); Write(profile, entries);
    }
    internal static void Configure(ProxyProfile profile, string id, SubscriptionClientProfile client, SubscriptionDownloadRoute route)
    {
        if (!Enum.IsDefined(client) || !Enum.IsDefined(route)) throw new InvalidOperationException("下载选项无效。");
        var entries = Read(profile); var entry = entries.FirstOrDefault(e => e.Id == id) ?? throw new InvalidOperationException("这份配置已移除。");
        entry.Client = client; entry.Route = route; Write(profile, entries);
        if (profile.ActiveSubscriptionId == id) { profile.SubscriptionClient = client; profile.SubscriptionRoute = route; }
    }
    internal static void Remove(ProxyProfile profile, string id)
    {
        var entries = Read(profile); entries.RemoveAll(e => e.Id == id); Write(profile, entries);
        if (profile.ActiveSubscriptionId != id) return;
        if (entries.Count > 0) Apply(profile, entries[0]);
        else { profile.ActiveSubscriptionId = ""; profile.ProtectedYaml = profile.ProtectedSubscription = profile.ProtectedSelections = profile.ProtectedGroups = ""; profile.RoutingSnapshot = null; }
    }
    internal static string CleanName(string value)
    {
        string name = value.Trim();
        if (name.Length is 0 or > 80 || name.Any(char.IsControl)) throw new InvalidOperationException("名称请填写 1–80 个字符。");
        return name;
    }
}
