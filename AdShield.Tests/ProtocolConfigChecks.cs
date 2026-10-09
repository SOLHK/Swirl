using AdShield.Network;
using System.Diagnostics;
using System.IO;
using System.Text;
using YamlDotNet.Serialization;

internal static class ProtocolConfigChecks
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        string uuid = "00000000-0000-0000-0000-000000000001";
        Dictionary<string, object> Node(string name, string type, int port = 443) => new() { ["name"] = name, ["type"] = type, ["server"] = "192.0.2.1", ["port"] = port };
        var nodes = new List<Dictionary<string, object>>();
        var ss = Node("SS", "ss"); ss["cipher"] = "aes-128-gcm"; ss["password"] = "fixture-password"; nodes.Add(ss);
        var ss2022 = Node("SS2022", "ss"); ss2022["cipher"] = "2022-blake3-aes-128-gcm"; ss2022["password"] = Convert.ToBase64String(Encoding.ASCII.GetBytes("0123456789abcdef")); nodes.Add(ss2022);
        var ssr = Node("SSR", "ssr"); ssr["cipher"] = "aes-128-ctr"; ssr["password"] = "fixture-password"; ssr["protocol"] = "auth_aes128_md5"; ssr["obfs"] = "plain"; nodes.Add(ssr);
        var vmess = Node("VMess", "vmess"); vmess["uuid"] = uuid; vmess["alterId"] = 0; vmess["cipher"] = "auto"; nodes.Add(vmess);
        var vless = Node("VLESS", "vless"); vless["uuid"] = uuid; nodes.Add(vless);
        var trojan = Node("Trojan", "trojan"); trojan["password"] = "fixture-password"; trojan["sni"] = "example.test"; nodes.Add(trojan);
        var hysteria = Node("Hysteria2", "hysteria2"); hysteria["password"] = "fixture-password"; hysteria["sni"] = "example.test"; nodes.Add(hysteria);
        var wg = Node("WireGuard", "wireguard", 51820); wg["ip"] = "10.0.0.2"; wg["private-key"] = Convert.ToBase64String(Enumerable.Repeat((byte)1, 32).ToArray()); wg["public-key"] = Convert.ToBase64String(Enumerable.Repeat((byte)2, 32).ToArray()); nodes.Add(wg);
        var http = Node("HTTP", "http", 8080); nodes.Add(http);
        var https = Node("HTTPS", "http"); https["tls"] = true; https["sni"] = "example.test"; nodes.Add(https);
        var socks = Node("SOCKS5", "socks5", 1080); nodes.Add(socks);
        string directory = Path.GetFullPath(Path.Combine("..", "protocol-validation-" + Guid.NewGuid().ToString("N"))); Directory.CreateDirectory(directory);
        foreach (var node in nodes)
        {
            string yaml = new SerializerBuilder().Build().Serialize(new Dictionary<string, object> { ["proxies"] = new[] { node } });
            var profile = new ProxyProfile { ProtectedYaml = ProxyProfile.Protect(yaml) };
            string file = Path.Combine(directory, "config.yaml"); File.WriteAllText(file, MihomoConfig.Build(profile, "fixture-secret"));
            var start = ProxyController.StartInfo(directory, file); start.ArgumentList.Add("-t");
            using var process = Process.Start(start)!;
            var output = process.StandardOutput.ReadToEndAsync(); var errors = process.StandardError.ReadToEndAsync();
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            try { await process.WaitForExitAsync(timeout.Token); } catch { if (!process.HasExited) process.Kill(true); throw; }
            await Task.WhenAll(output, errors);
            check(process.ExitCode == 0, "bundled core accepts " + node["name"] + " protocol configuration without contacting endpoint");
        }
    }
}
