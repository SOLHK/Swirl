using System.Collections.Concurrent;
using System.Net.NetworkInformation;

namespace AdShield.Network;

internal sealed class PluginCron
{
    private readonly HashSet<int>[] fields;
    private readonly bool anyDay, anyWeek;
    internal bool HasSeconds { get; }
    internal PluginCron(string expression)
    {
        var pieces = expression.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (pieces.Length is not (5 or 6)) throw new InvalidOperationException("Cron 需要五段或六段。");
        HasSeconds = pieces.Length == 6;
        if (!HasSeconds) pieces = new[] { "0" }.Concat(pieces).ToArray();
        int[] minima = { 0, 0, 0, 1, 1, 0 }, maxima = { 59, 59, 23, 31, 12, 7 };
        fields = pieces.Select((p, i) => Field(p, minima[i], maxima[i])).ToArray();
        if (fields[5].Remove(7)) fields[5].Add(0);
        anyDay = pieces[3] == "*"; anyWeek = pieces[5] == "*";
    }
    private static HashSet<int> Field(string field, int min, int max)
    {
        var result = new HashSet<int>();
        foreach (string part in field.Split(','))
        {
            var stepParts = part.Split('/');
            if (stepParts.Length > 2 || !int.TryParse(stepParts.Length == 2 ? stepParts[1] : "1", out int step) || step <= 0 || step > max + 1) throw new InvalidOperationException("Cron 步长无效。");
            var range = stepParts[0].Split('-');
            int start, end;
            if (range[0] == "*") { start = min; end = max; }
            else
            {
                if (!int.TryParse(range[0], out start)) throw new InvalidOperationException("Cron 字段无效。");
                if (range.Length == 2) { if (!int.TryParse(range[1], out end)) throw new InvalidOperationException("Cron 范围无效。"); }
                else end = stepParts.Length == 2 ? max : start;
            }
            if (range.Length > 2 || start < min || end > max || end < start) throw new InvalidOperationException("Cron 范围无效。");
            for (int n = start; n <= end; n += step) result.Add(n);
        }
        return result;
    }
    internal bool Matches(DateTime now)
    {
        bool day = fields[3].Contains(now.Day), week = fields[5].Contains((int)now.DayOfWeek);
        return fields[0].Contains(now.Second) && fields[1].Contains(now.Minute) && fields[2].Contains(now.Hour) && fields[4].Contains(now.Month) &&
            (anyDay ? week : anyWeek ? day : day || week);
    }
}

internal sealed class PluginTasks : IDisposable
{
    private readonly LoonPlugin[] plugins;
    private readonly Action<string> report;
    private readonly CancellationTokenSource stop = new();
    private readonly ConcurrentDictionary<string, byte> running = new();
    private readonly SemaphoreSlim slots = new(4);
    private readonly ConcurrentDictionary<string, Task> work = new();
    private readonly ConcurrentDictionary<string, long> cronSlots = new();
    private Task? loop;
    private DateTime networkChanged = DateTime.MinValue;
    private readonly object networkGate = new();
    internal PluginTasks(IEnumerable<LoonPlugin> plugins, Action<string> report) { this.plugins = plugins.Where(p => p.Enabled && p.Unsupported.Count == 0).ToArray(); this.report = report; }
    internal void Start()
    {
        NetworkChange.NetworkAddressChanged += OnNetworkChanged;
        loop = Task.Run(async () =>
        {
            using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(250));
            try
            {
                while (await timer.WaitForNextTickAsync(stop.Token))
                {
                    var now = DateTime.Now;
                    foreach (var plugin in plugins)
                        foreach (var script in plugin.Scripts.Where(s => s.Phase == "cron"))
                        {
                            var settings = ScriptSettings.For(plugin, script);
                            string key = plugin.Id + ":" + plugin.Scripts.IndexOf(script);
                            if (!settings.Enabled || !new PluginCron(settings.Cron).Matches(now)) continue;
                            long slot = now.Ticks / TimeSpan.TicksPerSecond;
                            if (cronSlots.TryGetValue(key, out var previous) && previous == slot) continue;
                            cronSlots[key] = slot; _ = ExecuteAsync(plugin, script);
                        }
                    bool changed;
                    lock (networkGate) { changed = networkChanged != DateTime.MinValue && DateTime.UtcNow - networkChanged >= TimeSpan.FromSeconds(2); if (changed) networkChanged = DateTime.MinValue; }
                    if (changed)
                        foreach (var plugin in plugins)
                            foreach (var script in plugin.Scripts.Where(s => s.Phase == "network-changed")) _ = ExecuteAsync(plugin, script);
                }
            }
            catch (OperationCanceledException) { }
            catch { report("脚本调度异常，已停止本次调度。"); }
        });
    }
    private void OnNetworkChanged(object? sender, EventArgs e) { lock (networkGate) networkChanged = DateTime.UtcNow; }
    internal Task ExecuteAsync(LoonPlugin plugin, LoonScript script)
    {
        if (!plugins.Contains(plugin) || script.Phase is not ("generic" or "cron" or "network-changed")) throw new InvalidOperationException("只能运行已启用插件的非 HTTP 脚本。");
        string key = plugin.Id + ":" + plugin.Scripts.IndexOf(script);
        if (stop.IsCancellationRequested || !running.TryAdd(key, 0)) return Task.CompletedTask;
        var task = RunAsync(); work[key] = task; return task;
        async Task RunAsync()
        {
            bool acquired = false;
            try
            {
                await slots.WaitAsync(stop.Token); acquired = true;
                var settings = ScriptSettings.For(plugin, script);
                if (!settings.Enabled) return;
                await Task.Run(() => PluginScriptRunner.Run(plugin, script, null, null, stop.Token), stop.Token);
                report("任务执行：" + plugin.Name + " / " + settings.Tag);
            }
            catch (OperationCanceledException) { }
            catch { report("任务脚本失败：" + plugin.Name); }
            finally { if (acquired) slots.Release(); running.TryRemove(key, out _); work.TryRemove(key, out _); }
        }
    }
    public void Dispose()
    {
        NetworkChange.NetworkAddressChanged -= OnNetworkChanged;
        stop.Cancel();
        try { Task.WhenAll(work.Values.Append(loop ?? Task.CompletedTask)).Wait(TimeSpan.FromSeconds(4)); } catch { }
        // Cancellation primitives stay alive until outstanding jobs have observed cancellation.
    }
}
