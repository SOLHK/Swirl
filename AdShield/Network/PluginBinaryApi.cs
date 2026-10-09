using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;

namespace AdShield.Network;

// Byte-only implementations avoid lossy text conversions for protobuf, gzip
// and plugin crypto helpers. The JS boundary never exposes CLR objects.
internal static class PluginBinaryApi
{
    internal static string Invoke(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        string operation = root.GetProperty("operation").GetString()!;
        byte[] data = PluginScriptRunner.ReadBytes(root.GetProperty("data"));
        if (operation is "gzip" or "ungzip")
        {
            using var output = new MemoryStream();
            if (operation == "gzip")
            {
                using (var gzip = new GZipStream(output, CompressionLevel.Optimal, true)) gzip.Write(data);
                if (output.Length > PluginScriptRunner.MaxBody) throw new InvalidOperationException("gzip 输出超过上限。");
            }
            else
            {
                using var input = new MemoryStream(data);
                using var gzip = new GZipStream(input, CompressionMode.Decompress);
                byte[] buffer = new byte[8192]; int count;
                while ((count = gzip.Read(buffer)) > 0)
                {
                    if (output.Length + count > PluginScriptRunner.MaxBody) throw new InvalidOperationException("gzip 解压超过上限。");
                    output.Write(buffer, 0, count);
                }
            }
            return Bytes(output.ToArray());
        }
        var options = root.GetProperty("options");
        string mode = options.GetProperty("mode").GetString()?.ToLowerInvariant() ?? "";
        byte[] key = PluginScriptRunner.ReadBytes(options.GetProperty("key"));
        if (key.Length is not (16 or 24 or 32)) throw new InvalidOperationException("AES key 必须为 16、24 或 32 字节。");
        byte[]? iv = options.TryGetProperty("iv", out var nonce) ? PluginScriptRunner.ReadBytes(nonce) : null;
        bool encrypt = operation == "encrypt";
        if (!encrypt && operation != "decrypt") throw new InvalidOperationException("未知二进制操作。");
        byte[] changed; byte[]? tag = null;
        if (mode == "gcm")
        {
            if (iv?.Length != 12) throw new InvalidOperationException("AES-GCM nonce 必须为 12 字节。");
            byte[]? aad = options.TryGetProperty("aad", out var associated) ? PluginScriptRunner.ReadBytes(associated) : null;
            changed = new byte[data.Length];
            using var aes = new AesGcm(key, 16);
            if (encrypt) { tag = new byte[16]; aes.Encrypt(iv, data, changed, tag, aad); }
            else
            {
                byte[] expected = PluginScriptRunner.ReadBytes(options.GetProperty("tag"));
                if (expected.Length != 16) throw new InvalidOperationException("AES-GCM tag 必须为 16 字节。");
                aes.Decrypt(iv, data, expected, changed, aad);
            }
        }
        else if (mode == "ctr")
        {
            if (iv?.Length != 16) throw new InvalidOperationException("AES-CTR IV 必须为 16 字节。");
            using var aes = Aes.Create(); aes.Key = key; aes.Mode = CipherMode.ECB; aes.Padding = PaddingMode.None;
            using var transform = aes.CreateEncryptor();
            var counter = (byte[])iv.Clone(); changed = new byte[data.Length]; var block = new byte[16];
            for (int offset = 0; offset < data.Length; offset += 16)
            {
                transform.TransformBlock(counter, 0, 16, block, 0);
                for (int i = 0; i < Math.Min(16, data.Length - offset); i++) changed[offset + i] = (byte)(data[offset + i] ^ block[i]);
                for (int i = 15; i >= 0 && ++counter[i] == 0; i--) { }
            }
        }
        else if (mode is "ecb" or "cbc")
        {
            if (mode == "ecb" && iv != null || mode == "cbc" && iv?.Length != 16) throw new InvalidOperationException("AES IV 与模式不匹配。");
            string padding = options.TryGetProperty("padding", out var specified) ? specified.GetString()?.ToLowerInvariant() ?? "" : "pkcs7";
            using var aes = Aes.Create(); aes.Key = key; aes.Mode = mode == "cbc" ? CipherMode.CBC : CipherMode.ECB;
            aes.Padding = padding switch { "pkcs7" => PaddingMode.PKCS7, "none" => PaddingMode.None, _ => throw new InvalidOperationException("AES padding 必须为 pkcs7 或 none。") };
            if (iv != null) aes.IV = iv;
            using var transform = encrypt ? aes.CreateEncryptor() : aes.CreateDecryptor();
            changed = transform.TransformFinalBlock(data, 0, data.Length);
        }
        else throw new InvalidOperationException("AES mode 必须为 ecb、cbc、ctr 或 gcm。");
        if (changed.Length > PluginScriptRunner.MaxBody) throw new InvalidOperationException("AES 输出超过上限。");
        return encrypt ? JsonSerializer.Serialize(new { ciphertext = changed.Select(b => (int)b).ToArray(), tag = tag?.Select(b => (int)b).ToArray() }) : Bytes(changed);
    }
    private static string Bytes(byte[] data) => JsonSerializer.Serialize(data.Select(b => (int)b).ToArray());
}
