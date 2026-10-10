using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal sealed record ProxyGroup(string Name, string Type, string[] Members, string? Current, bool PendingProvider = false)
{
    internal bool Selectable => Type is "select" or "Selector";
    public override string ToString() => Name;
}

// Both the offline preview and controller response use the same selection model.
// Only Selector groups accept PUT /proxies; automatic groups remain visible.
internal sealed class ProxyCatalog
{
    internal Dictionary<string, ProxyGroup> Groups { get; } = new(StringComparer.Ordinal);
    internal Dictionary<string, string> Nodes { get; } = new(StringComparer.Ordinal);

    internal static ProxyCatalog FromProfile(ProxyProfile profile)
    {
        var catalog = new ProxyCatalog();
        if (string.IsNullOrWhiteSpace(profile.Yaml)) return catalog;
        var root = MihomoConfig.Parse(MihomoConfig.Build(profile, "preview"));
        static IEnumerable<IDictionary<object, object>> Maps(object? value) => value is IEnumerable<object> items ? items.OfType<IDictionary<object, object>>() : [];
        static string[] Names(object? value) => value is IEnumerable<object> items ? items.Select(x => x.ToString()!).ToArray() : [];
        void AddNodes(object? value) { foreach (var node in Maps(value)) if (node.TryGetValue("name", out var name) && name.ToString() != MihomoConfig.PluginOutbound) catalog.Nodes[name.ToString()!] = node.TryGetValue("type", out var type) ? type.ToString()! : ""; }
        root.TryGetValue("proxies", out var proxies); AddNodes(proxies);
        var providerNodes = new Dictionary<string, string[]>();
        if (root.TryGetValue("proxy-providers", out var providers) && providers is IDictionary<object, object> entries)
            foreach (var entry in entries)
                if (entry.Value is IDictionary<object, object> provider)
                {
                    provider.TryGetValue("payload", out var payload); AddNodes(payload);
                    providerNodes[entry.Key.ToString()!] = Maps(payload).Where(n => n.ContainsKey("name")).Select(n => n["name"].ToString()!).ToArray();
                }
        root.TryGetValue("proxy-groups", out var groups);
        var groupMaps = Maps(groups).ToArray();
        foreach (var map in groupMaps)
        {
            string name = map["name"].ToString()!, type = map["type"].ToString()!;
            map.TryGetValue("proxies", out var members); var names = Names(members).ToList();
            bool Enabled(string key) => map.TryGetValue(key, out var value) && string.Equals(value.ToString(), "true", StringComparison.OrdinalIgnoreCase);
            bool all = Enabled("include-all");
            if (all || Enabled("include-all-proxies")) names.AddRange(catalog.Nodes.Keys);
            if (all || Enabled("include-all-groups")) names.AddRange(groupMaps.Select(g => g["name"].ToString()!).Where(n => n != name));
            map.TryGetValue("use", out var use); var used = Names(use);
            if (all || Enabled("include-all-providers")) used = providerNodes.Keys.ToArray();
            foreach (var provider in used) names.AddRange(providerNodes.GetValueOrDefault(provider) ?? []);
            bool Match(string key, string node) => !map.TryGetValue(key, out var expression) || string.IsNullOrWhiteSpace(expression.ToString()) || Regex.IsMatch(node, expression.ToString()!, RegexOptions.None, TimeSpan.FromMilliseconds(100));
            var filtered = names.Where(n => n != MihomoConfig.PluginOutbound && Match("filter", n) && (!map.ContainsKey("exclude-filter") || string.IsNullOrWhiteSpace(map["exclude-filter"].ToString()) || !Regex.IsMatch(n, map["exclude-filter"].ToString()!, RegexOptions.None, TimeSpan.FromMilliseconds(100)))).Distinct().ToArray();
            catalog.Groups[name] = new(name, type, filtered, null, used.Any(p => !providerNodes.TryGetValue(p, out var list) || list.Length == 0));
        }
        catalog.Groups["GLOBAL"] = new("GLOBAL", "select", catalog.Groups.Keys.Concat(catalog.Nodes.Keys).Concat(["DIRECT", "REJECT"]).Distinct().ToArray(), null);
        return catalog;
    }

    internal static ProxyCatalog FromController(JsonElement root)
    {
        var catalog = new ProxyCatalog();
        foreach (var proxy in root.GetProperty("proxies").EnumerateObject())
        {
            if (proxy.Name == MihomoConfig.PluginOutbound) continue;
            string type = proxy.Value.GetProperty("type").GetString()!;
            if (proxy.Value.TryGetProperty("all", out var all))
                catalog.Groups[proxy.Name] = new(proxy.Name, type, all.EnumerateArray().Select(n => n.GetString()!).Where(n => n != MihomoConfig.PluginOutbound).ToArray(), proxy.Value.TryGetProperty("now", out var current) ? current.GetString() : null);
            else if (type is not ("Direct" or "Reject" or "RejectDrop" or "Pass" or "Compatible")) catalog.Nodes[proxy.Name] = type;
        }
        return catalog;
    }

    internal Dictionary<string, string> InitialSelections(ProxyProfile profile)
    {
        var saved = profile.SelectedProxies;
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        bool ReachesNode(string name, HashSet<string> path)
        {
            if (Nodes.ContainsKey(name)) return true;
            if (!path.Add(name) || !Groups.TryGetValue(name, out var group)) return false;
            if (result.TryGetValue(name, out var planned)) return ReachesNode(planned, path);
            if (saved.TryGetValue(name, out var choice) && group.Members.Contains(choice)) return ReachesNode(choice, path);
            if (!group.Selectable && group.Current != null) return ReachesNode(group.Current, path);
            return group.Members.Any(member => ReachesNode(member, new(path, StringComparer.Ordinal)));
        }
        foreach (var group in Groups.Values.Where(g => g.Selectable))
        {
            if (saved.TryGetValue(group.Name, out var choice) && group.Members.Contains(choice) && Resolve(group.Name, saved) != "策略组循环") { result[group.Name] = choice; continue; }
            string? preferred = group.Name == "GLOBAL" ? MihomoConfig.PreferredGroup(profile) : null;
            // GLOBAL must never point to itself. Prefer the effective rule group,
            // then another group/node with a real upstream, instead of DIRECT.
            if (preferred == "GLOBAL" || preferred == null || !group.Members.Contains(preferred) || !ReachesNode(preferred, new([group.Name], StringComparer.Ordinal)))
                preferred = group.Members.FirstOrDefault(n => ReachesNode(n, new([group.Name], StringComparer.Ordinal)));
            if (preferred != null) result[group.Name] = preferred;
        }
        return result;
    }

    internal string Resolve(string name, IReadOnlyDictionary<string, string> selections)
    {
        var path = new HashSet<string>(StringComparer.Ordinal);
        while (Groups.TryGetValue(name, out var group))
        {
            if (!path.Add(name)) return "策略组循环";
            string? next = selections.GetValueOrDefault(name) ?? group.Current;
            if (string.IsNullOrEmpty(next)) return group.Type is "LoadBalance" or "load-balance" ? "负载均衡 · " + group.Members.Length + " 个候选" : group.PendingProvider ? "等待提供器加载" : "等待核心选择";
            name = next;
        }
        return name == "DIRECT" ? "直连" : name == "REJECT" ? "拒绝连接" : name;
    }
}
