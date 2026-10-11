using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed class PolicyGroupSettings
{
    public string Name { get; set; } = "";
    public string Type { get; set; } = "select";
    public List<string> Members { get; set; } = new();
    public List<string> Providers { get; set; } = new();
    public bool AllNodes { get; set; }
    public bool AllProviders { get; set; }
    public string Filter { get; set; } = "";
    public string Url { get; set; } = "https://www.gstatic.com/generate_204";
    public int Interval { get; set; } = 300;
    public int Timeout { get; set; } = 5000;
    public int Tolerance { get; set; } = 50;
    public string Strategy { get; set; } = "consistent-hashing";
    internal void Validate()
    {
        Name = Name.Trim();
        if (Name.Length is 0 or > 100 || Name.Any(c => char.IsControl(c) || c == ',') || Name is "GLOBAL" or "DIRECT" or "REJECT" || Name == MihomoConfig.PluginOutbound) throw new InvalidOperationException("策略组名称需为 1–100 个字符，不能使用内置名称、逗号或换行。");
        if (Type is not ("select" or "url-test" or "fallback" or "load-balance")) throw new InvalidOperationException("请选择手动选择、自动选最快、故障转移或负载均衡。");
        if (Members == null || Providers == null || Members.Count > 2000 || Providers.Count > 200) throw new InvalidOperationException("策略组成员数量超过上限。");
        Members = Members.Distinct(StringComparer.Ordinal).ToList(); Providers = Providers.Distinct(StringComparer.Ordinal).ToList();
        if (Members.Contains(Name) || Members.Contains(MihomoConfig.PluginOutbound)) throw new InvalidOperationException("策略组不能包含自己或内部插件入口。");
        if (Members.Count == 0 && Providers.Count == 0 && !AllNodes && !AllProviders) throw new InvalidOperationException("至少添加一个节点、子策略组或节点提供器。");
        if (Filter.Length > 500) throw new InvalidOperationException("节点筛选条件过长。");
        try { if (Filter.Length > 0) _ = new Regex(Filter, RegexOptions.None, TimeSpan.FromMilliseconds(100)); }
        catch (ArgumentException) { throw new InvalidOperationException("节点筛选表达式无效，请检查括号或直接填写地区关键词。"); }
        if (Type != "select")
        {
            if (!Uri.TryCreate(Url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https") || uri.UserInfo.Length > 0 || Url.Length > 1024) throw new InvalidOperationException("测速地址需为 HTTP 或 HTTPS 地址。");
            if (Interval is < 10 or > 86400 || Timeout is < 500 or > 30000 || Tolerance is < 0 or > 10000) throw new InvalidOperationException("检测间隔应为 10–86400 秒，超时为 500–30000 毫秒，切换容差为 0–10000 毫秒。");
            if (Type == "load-balance" && Strategy is not ("consistent-hashing" or "round-robin" or "sticky-sessions")) throw new InvalidOperationException("负载均衡方式无效。");
        }
    }
}

internal static class UserProxyGroups
{
    internal static Dictionary<string, PolicyGroupSettings> Read(ProxyProfile profile)
    {
        var root = MihomoConfig.Parse(profile.Yaml); Apply(profile, root);
        if (!root.TryGetValue("proxy-groups", out var value) || value is not IEnumerable<object> items) return new();
        var result = new Dictionary<string, PolicyGroupSettings>(StringComparer.Ordinal);
        foreach (var group in items.OfType<IDictionary<object, object>>())
        {
            string Text(string key, string fallback = "") => group.TryGetValue(key, out var field) ? field.ToString()! : fallback;
            int Number(string key, int fallback) => int.TryParse(Text(key), out int number) ? number : fallback;
            bool Enabled(string key) => bool.TryParse(Text(key), out bool enabled) && enabled;
            List<string> Names(string key) => group.TryGetValue(key, out var field) && field is IEnumerable<object> names ? names.Select(n => n.ToString()!).ToList() : [];
            string name = Text("name");
            result[name] = new PolicyGroupSettings { Name = name, Type = Text("type"), Members = Names("proxies"), Providers = Names("use"), AllNodes = Enabled("include-all") || Enabled("include-all-proxies"), AllProviders = Enabled("include-all") || Enabled("include-all-providers"), Filter = Text("filter"), Url = Text("url", "https://www.gstatic.com/generate_204"), Interval = Number("interval", 300), Timeout = Number("timeout", 5000), Tolerance = Number("tolerance", 50), Strategy = Text("strategy", "consistent-hashing") };
        }
        return result;
    }
    internal static void Apply(ProxyProfile profile, Dictionary<string, object> root)
    {
        var edits = profile.GroupSettings; if (edits.Count == 0) return;
        if (edits.Count > 200 || edits.Select(e => e.Name).Distinct().Count() != edits.Count) throw new InvalidOperationException("自建策略组重复或超过 200 个。");
        var groups = root.TryGetValue("proxy-groups", out var value) && value is IEnumerable<object> items ? items.ToList() : new List<object>();
        foreach (var edit in edits)
        {
            edit.Validate();
            var map = groups.OfType<IDictionary<object, object>>().FirstOrDefault(g => g.TryGetValue("name", out var name) && name.ToString() == edit.Name);
            if (map == null) { map = new Dictionary<object, object>(); groups.Add(map); }
            map["name"] = edit.Name; map["type"] = edit.Type;
            foreach (var key in new[] { "proxies", "use", "include-all", "include-all-proxies", "include-all-providers", "filter", "url", "interval", "timeout", "tolerance", "strategy" }) map.Remove(key);
            if (edit.Members.Count > 0) map["proxies"] = edit.Members;
            if (edit.Providers.Count > 0) map["use"] = edit.Providers;
            if (edit.AllNodes) map["include-all-proxies"] = true;
            if (edit.AllProviders) map["include-all-providers"] = true;
            if (edit.Filter.Length > 0) map["filter"] = edit.Filter;
            if (edit.Type != "select") { map["url"] = edit.Url; map["interval"] = edit.Interval; map["timeout"] = edit.Timeout; map["lazy"] = false; }
            if (edit.Type == "url-test") map["tolerance"] = edit.Tolerance;
            if (edit.Type == "load-balance") map["strategy"] = edit.Strategy;
        }
        var names = groups.OfType<IDictionary<object, object>>().Select(g => g["name"].ToString()!).ToHashSet(StringComparer.Ordinal);
        var nodes = root.TryGetValue("proxies", out var proxies) && proxies is IEnumerable<object> raw ? raw.OfType<IDictionary<object, object>>().Where(n => n.ContainsKey("name")).Select(n => n["name"].ToString()!).ToHashSet(StringComparer.Ordinal) : new HashSet<string>();
        var providers = root.TryGetValue("proxy-providers", out var provided) && provided is IDictionary<object, object> entries ? entries.Keys.Select(k => k.ToString()!).ToHashSet(StringComparer.Ordinal) : new HashSet<string>();
        foreach (var edit in edits)
        {
            if (edit.Members.Any(n => !nodes.Contains(n) && !names.Contains(n) && n is not ("DIRECT" or "REJECT")) || edit.Providers.Any(p => !providers.Contains(p))) throw new InvalidOperationException("策略组引用的节点或提供器已不存在，请编辑成员后再连接。");
        }
        bool Cycle(string name, HashSet<string> path)
        {
            if (!path.Add(name)) return true;
            var group = groups.OfType<IDictionary<object, object>>().FirstOrDefault(g => g["name"].ToString() == name);
            return group != null && group.TryGetValue("proxies", out var members) && members is IEnumerable<object> children && children.Select(c => c.ToString()!).Where(names.Contains).Any(n => Cycle(n, new(path, StringComparer.Ordinal)));
        }
        if (edits.Any(e => Cycle(e.Name, new(StringComparer.Ordinal)))) throw new InvalidOperationException("策略组之间形成了循环，请移除互相引用的成员。");
        root["proxy-groups"] = groups;
    }
    internal static void Save(ProxyProfile profile, PolicyGroupSettings settings, bool creating)
    {
        settings.Validate();
        var original = MihomoConfig.Parse(profile.Yaml);
        bool imported = original.TryGetValue("proxy-groups", out var raw) && raw is IEnumerable<object> groups && groups.OfType<IDictionary<object, object>>().Any(g => g["name"].ToString() == settings.Name);
        if (creating && (imported || profile.GroupSettings.Any(g => g.Name == settings.Name) || settings.Name.StartsWith("Swirl 节点", StringComparison.Ordinal))) throw new InvalidOperationException("这个名称已经被使用，请换一个策略组名称。");
        var edits = profile.GroupSettings; edits.RemoveAll(g => g.Name == settings.Name); edits.Add(settings);
        var copy = System.Text.Json.JsonSerializer.Deserialize<ProxyProfile>(System.Text.Json.JsonSerializer.Serialize(profile))!; copy.GroupSettings = edits;
        _ = MihomoConfig.Build(copy, "validate");
        profile.GroupSettings = edits; profile.RoutingSnapshot = null;
    }
    internal static void RemoveEdit(ProxyProfile profile, string name)
    {
        var edits = profile.GroupSettings; edits.RemoveAll(g => g.Name == name);
        var copy = System.Text.Json.JsonSerializer.Deserialize<ProxyProfile>(System.Text.Json.JsonSerializer.Serialize(profile))!; copy.GroupSettings = edits;
        _ = MihomoConfig.Build(copy, "validate");
        if (profile.UserRules.Any(r => r.Enabled && r.Policy == name) && !Read(copy).ContainsKey(name)) throw new InvalidOperationException("分流规则仍在使用这个策略组，请先修改对应规则。");
        profile.GroupSettings = edits;
    }
}
