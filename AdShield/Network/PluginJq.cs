using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdShield.Network;

internal static class PluginJq
{
    internal static async Task<string> RunAsync(string expression, string body)
    {
        if (expression.Length == 0 || expression.Length > 128 * 1024 || Encoding.UTF8.GetByteCount(body) > 2 * 1024 * 1024)
            throw new InvalidOperationException("jq 输入超限。");
        // No module/file imports or host environment access. jq only gets stdin.
        if (Regex.IsMatch(expression, @"\b(import|include)\b")) throw new InvalidOperationException("jq 外部模块未启用。");
        using var input = JsonDocument.Parse(body);
        string executable = Path.Combine(AppContext.BaseDirectory, "core", "jq.exe");
        if (!File.Exists(executable)) throw new InvalidOperationException("缺少随包提供的 jq.exe。");
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            WorkingDirectory = ProxyProfile.DirectoryPath
        };
        start.Environment.Clear();
        start.ArgumentList.Add("-c"); start.ArgumentList.Add("--"); start.ArgumentList.Add(expression);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("jq 无法启动。");
        using var job = new CoreProcessJob(process, 128 * 1024 * 1024);
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        try
        {
            var output = ReadBounded(process.StandardOutput, timeout.Token);
            var errors = ReadBounded(process.StandardError, timeout.Token);
            await process.StandardInput.WriteAsync(body.AsMemory(), timeout.Token);
            process.StandardInput.Close();
            await Task.WhenAll(process.WaitForExitAsync(timeout.Token), output, errors);
            if (process.ExitCode != 0) throw new InvalidOperationException("jq 执行失败。");
            string changed = output.Result.Trim();
            using var validation = JsonDocument.Parse(changed); // One valid JSON document only.
            return changed;
        }
        finally { if (!process.HasExited) { process.Kill(true); await process.WaitForExitAsync(); } }
    }

    private static async Task<string> ReadBounded(StreamReader source, CancellationToken token)
    {
        var output = new StringBuilder();
        var buffer = new char[4096];
        int read;
        while ((read = await source.ReadAsync(buffer.AsMemory(), token)) > 0)
        {
            if (output.Length + read > 2 * 1024 * 1024) throw new InvalidOperationException("jq 输出超限。");
            output.Append(buffer, 0, read);
        }
        return output.ToString();
    }
}
