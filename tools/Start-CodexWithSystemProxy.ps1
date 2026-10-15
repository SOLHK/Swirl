#Requires -Version 7.0
<#
.SYNOPSIS
Launch a new Codex desktop process with the current explicit loopback proxy.
.DESCRIPTION
Reads WinINET and current-user registry settings without changing them. Only
ProcessStartInfo.Environment is changed; user/machine variables, Codex settings,
DNS, certificates and other applications are never modified. Existing desktop
processes must be exited by the user first, so Electron cannot reuse a process
whose environment predates this launch.
.EXAMPLE
pwsh -NoProfile -File ./tools/Start-CodexWithSystemProxy.ps1 -CheckOnly
.EXAMPLE
pwsh -NoProfile -File ./tools/Start-CodexWithSystemProxy.ps1
#>
[CmdletBinding()]
param([string]$CodexPath, [switch]$CheckOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-LoopbackProxyEndpoint {
    param([Parameter(Mandatory)][string]$Server)
    # Windows accepts per-protocol maps. This helper deliberately requires one
    # unambiguous HTTP proxy endpoint for HTTP, HTTPS CONNECT and ALL_PROXY.
    $match = [regex]::Match($Server, '\A(?<host>localhost|[0-9]{1,3}(?:\.[0-9]{1,3}){3}|\[[0-9a-fA-F:]+\]):(?<port>[0-9]{1,5})\z', 'IgnoreCase')
    if (!$match.Success) { throw '需要单一回环 host:port 代理；不接受凭据、协议映射、远程代理或其他 URI 内容。' }
    $port = [int]$match.Groups['port'].Value
    if ($port -lt 1 -or $port -gt 65535) { throw '代理端口须在 1–65535 之间。' }
    $hostName = $match.Groups['host'].Value.Trim('[', ']')
    if ($hostName -ieq 'localhost') { $hostName = '127.0.0.1' }
    $address = $null
    if (![System.Net.IPAddress]::TryParse($hostName, [ref]$address) -or ![System.Net.IPAddress]::IsLoopback($address)) {
        throw '代理地址必须是本机回环 IP。'
    }
    $canonicalHost = $address.ToString()
    if ($address.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) { $canonicalHost = '[' + $canonicalHost + ']' }
    return 'http://' + $canonicalHost + ':' + $port
}

function Assert-ExplicitLoopbackProxy {
    param([Parameter(Mandatory)]$WinInet, [Parameter(Mandatory)]$Registry)
    if (($WinInet.Flags -band 2) -eq 0 -or !$Registry.Enabled) { throw 'Windows 显式系统代理尚未启用。请先在 Swirl 中启用并确认连接。' }
    if (($WinInet.Flags -band 12) -ne 0 -or ![string]::IsNullOrEmpty($WinInet.Pac) -or ![string]::IsNullOrEmpty($Registry.Pac)) {
        throw '检测到 PAC 或自动检测代理；为避免代理路径歧义，本工具不启动 Codex。'
    }
    $endpoint = ConvertTo-LoopbackProxyEndpoint -Server $WinInet.Server
    $registryEndpoint = ConvertTo-LoopbackProxyEndpoint -Server $Registry.Server
    if ($endpoint -ne $registryEndpoint) { throw 'WinINET 与当前用户注册表的代理端点不一致，未启动 Codex。' }
    return $endpoint
}

function Read-WindowsExplicitProxy {
    if (!('SwirlTools.ReadOnlyProxy' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
namespace SwirlTools {
    public sealed class ProxyValues { public uint Flags; public string Server; public string Pac; }
    public static class ReadOnlyProxy {
        [StructLayout(LayoutKind.Explicit, Size = 16)]
        private struct Option {
            [FieldOffset(0)] public uint Kind;
            [FieldOffset(8)] public uint Flags;
            [FieldOffset(8)] public IntPtr Text;
        }
        [StructLayout(LayoutKind.Sequential)]
        private struct OptionList {
            public uint Size; public IntPtr Connection; public uint Count;
            public uint Error; public IntPtr Options;
        }
        [DllImport("wininet.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        private static extern bool InternetQueryOptionW(IntPtr h, uint option, ref OptionList value, ref uint length);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalFree(IntPtr memory);
        private static ProxyValues Query(uint flagKind) {
            var memory = Marshal.AllocHGlobal(48);
            try {
                for (int i = 0; i < 3; ++i) {
                    var value = new Option { Kind = i == 0 ? flagKind : (i == 1 ? 2U : 4U) };
                    Marshal.StructureToPtr(value, IntPtr.Add(memory, i * 16), false);
                }
                var list = new OptionList { Size = (uint)Marshal.SizeOf(typeof(OptionList)), Count = 3, Options = memory };
                uint size = list.Size;
                if (!InternetQueryOptionW(IntPtr.Zero, 75, ref list, ref size)) throw new Win32Exception(Marshal.GetLastWin32Error());
                var flags = Marshal.PtrToStructure<Option>(memory);
                var server = Marshal.PtrToStructure<Option>(IntPtr.Add(memory, 16));
                var pac = Marshal.PtrToStructure<Option>(IntPtr.Add(memory, 32));
                return new ProxyValues { Flags = flags.Flags,
                    Server = server.Text == IntPtr.Zero ? "" : Marshal.PtrToStringUni(server.Text),
                    Pac = pac.Text == IntPtr.Zero ? "" : Marshal.PtrToStringUni(pac.Text) };
            } finally {
                for (int i = 1; i < 3; ++i) {
                    var value = Marshal.PtrToStructure<Option>(IntPtr.Add(memory, i * 16));
                    if (value.Text != IntPtr.Zero) GlobalFree(value.Text);
                }
                Marshal.FreeHGlobal(memory);
            }
        }
        public static ProxyValues Read() {
            if (IntPtr.Size != 8) throw new PlatformNotSupportedException("Use Windows x64 PowerShell 7.");
            try { return Query(10); } catch (Win32Exception) { return Query(1); }
        }
    }
}
'@
    }
    $winInet = [SwirlTools.ReadOnlyProxy]::Read()
    $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Software\Microsoft\Windows\CurrentVersion\Internet Settings', $false)
    if ($null -eq $key) { throw '无法只读访问当前用户的 Windows 代理设置。' }
    try {
        $registry = [pscustomobject]@{
            Enabled = ($key.GetValue('ProxyEnable', 0) -eq 1 -and $key.GetValueKind('ProxyEnable') -eq [Microsoft.Win32.RegistryValueKind]::DWord)
            Server = [string]$key.GetValue('ProxyServer', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
            Pac = [string]$key.GetValue('AutoConfigURL', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        }
    } finally { $key.Dispose() }
    return Assert-ExplicitLoopbackProxy -WinInet $winInet -Registry $registry
}

function Resolve-LocalCodexExecutablePath {
    param([Parameter(Mandatory)][string]$RequestedPath)
    if (![IO.Path]::IsPathFullyQualified($RequestedPath)) { throw 'CodexPath 必须是本机 EXE 的绝对路径。' }
    # Pure string normalization must precede Get-Item. Windows also accepts
    # //server/share UNC paths and //?/ device paths; inspecting those first
    # could access a remote share before the local-path policy is enforced.
    $normalized = [IO.Path]::GetFullPath($RequestedPath)
    if ($normalized.StartsWith('\\') -or $normalized -notmatch '\A[A-Za-z]:\\') {
        throw 'CodexPath 不接受 UNC 网络路径或设备路径前缀；请指定本机驱动器上的桌面 EXE。'
    }
    return $normalized
}

function Resolve-CodexDesktopPath {
    param([string]$RequestedPath)
    if (![string]::IsNullOrWhiteSpace($RequestedPath)) {
        $localPath = Resolve-LocalCodexExecutablePath -RequestedPath $RequestedPath
        $file = Get-Item -LiteralPath $localPath
        if ($file.PSIsContainer -or $file.Name -notmatch '^(ChatGPT|Codex)\.exe$' -or $file.FullName -match '\\OpenAI\\Codex\\bin\\') {
            throw 'CodexPath 必须指向 ChatGPT.exe 或 Codex.exe 桌面程序，不能使用后台 CLI 的 bin/codex.exe。'
        }
        return $file.FullName
    }
    $packages = @(Get-AppxPackage -Name 'OpenAI.Codex' | Sort-Object Version -Descending)
    foreach ($package in $packages) {
        foreach ($relative in @('app\ChatGPT.exe', 'app\Codex.exe')) {
            $candidate = Join-Path $package.InstallLocation $relative
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [IO.Path]::GetFullPath($candidate) }
        }
    }
    throw '没有找到当前用户安装的 OpenAI.Codex 桌面程序。请用 -CodexPath 指定桌面 EXE。'
}

function Test-CodexDesktopIdentity {
    param([string]$ExecutablePath, [string]$LaunchPath)
    return ![string]::IsNullOrEmpty($ExecutablePath) -and (
        $ExecutablePath.Equals($LaunchPath, [StringComparison]::OrdinalIgnoreCase) -or
        $ExecutablePath -match '\\OpenAI\.Codex_[^\\]+\\app\\')
}

function Get-ExistingCodexDesktop {
    param([string]$LaunchPath)
    # No command lines or environment blocks are inspected or printed.
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe' OR Name='Codex.exe'" -Property ProcessId,Name,ExecutablePath)
    foreach ($process in $processes) {
        if ([string]::IsNullOrEmpty($process.ExecutablePath)) { throw '部分 Codex/ChatGPT 进程路径无法验证；请自行退出桌面应用后重试。' }
        if (Test-CodexDesktopIdentity -ExecutablePath $process.ExecutablePath -LaunchPath $LaunchPath) { $process.ProcessId }
    }
}

function New-CodexProxyStartInfo {
    param([Parameter(Mandatory)][string]$ExecutablePath, [Parameter(Mandatory)][string]$ProxyEndpoint)
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $ExecutablePath
    $info.WorkingDirectory = [IO.Path]::GetDirectoryName($ExecutablePath)
    $info.UseShellExecute = $false
    foreach ($name in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')) { $info.Environment[$name] = $ProxyEndpoint }
    # Do not inherit a broad NO_PROXY list that could bypass the selected proxy.
    $info.Environment['NO_PROXY'] = 'localhost,127.0.0.1,::1'
    return $info
}

function Get-DisplayExecutablePath {
    param([string]$Path)
    if ($Path.StartsWith($env:USERPROFILE, [StringComparison]::OrdinalIgnoreCase)) { return '%USERPROFILE%' + $Path.Substring($env:USERPROFILE.Length) }
    return $Path
}

if (!$IsWindows -or ![Environment]::Is64BitProcess) { throw '请使用 Windows x64 PowerShell 7（pwsh）运行。' }
$launchPath = Resolve-CodexDesktopPath -RequestedPath $CodexPath
$proxyEndpoint = Read-WindowsExplicitProxy
$existing = @(Get-ExistingCodexDesktop -LaunchPath $launchPath)
if ($CheckOnly) {
    [pscustomobject]@{
        mode = 'check-only'
        executable = Get-DisplayExecutablePath -Path $launchPath
        proxy = $proxyEndpoint
        existingDesktopProcessCount = $existing.Count
        launchAllowed = $existing.Count -eq 0
        environmentScope = 'new child process only'
    } | ConvertTo-Json
    return
}
if ($existing.Count -gt 0) { throw 'Codex 桌面已经在运行。请保存工作并自行完全退出后再运行此脚本；本工具不会停止进程或中断当前对话。' }
# Check again immediately before starting; the desktop app may have been opened
# during proxy inspection. This is a best-effort check, not an app-owned mutex.
if (@(Get-ExistingCodexDesktop -LaunchPath $launchPath).Count -gt 0) { throw 'Codex 桌面刚刚启动，未创建新进程。请自行完全退出后重试。' }
$startInfo = New-CodexProxyStartInfo -ExecutablePath $launchPath -ProxyEndpoint $proxyEndpoint
$child = [System.Diagnostics.Process]::Start($startInfo)
if ($null -eq $child) { throw 'Windows 没有创建 Codex 桌面进程。' }
[pscustomobject]@{ started = $true; executable = Get-DisplayExecutablePath -Path $launchPath; proxy = $proxyEndpoint; environmentScope = 'new child process only' } | ConvertTo-Json
$child.Dispose()
