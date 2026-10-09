namespace AdShield;

internal static class Store
{
    internal static readonly string Dir = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Swirl");
    internal static readonly string LogFile = System.IO.Path.Combine(Dir, "events.log");
    internal static void MigrateLegacyNetwork()
    {
        string legacy = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AdShield", "network");
        string destination = Path.GetFullPath(Path.Combine(Dir, "network"));
        if (Directory.Exists(destination) || !Directory.Exists(legacy)) return;
        string pending = Path.GetFullPath(Path.Combine(Dir, "network-migration-" + Guid.NewGuid().ToString("N")));
        string root = Path.GetFullPath(Dir) + Path.DirectorySeparatorChar;
        if (!pending.StartsWith(root, StringComparison.OrdinalIgnoreCase) || !destination.StartsWith(root, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("配置迁移路径无效。");
        try
        {
            Directory.CreateDirectory(pending);
            foreach (string source in Directory.EnumerateFiles(legacy, "*", SearchOption.AllDirectories))
            {
                string target = Path.GetFullPath(Path.Combine(pending, Path.GetRelativePath(legacy, source)));
                if (!target.StartsWith(pending + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)) continue;
                Directory.CreateDirectory(Path.GetDirectoryName(target)!); File.Copy(source, target, false);
            }
            Directory.Move(pending, destination);
        }
        catch { Log("Legacy configuration migration failed; original data retained."); }
    }
    internal static void Log(string message)
    {
        try
        {
            Directory.CreateDirectory(Dir);
            File.AppendAllText(LogFile, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + message.Replace("\r", " ").Replace("\n", " ") + Environment.NewLine);
        }
        catch { /* Logs are optional. */ }
    }
}
