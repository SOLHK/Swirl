#Requires -Version 7.0
# Pure validation tests: no registry writes, application launches or network IO.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$launcherPath = Join-Path $PSScriptRoot '..\Start-CodexWithSystemProxy.ps1'
$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($launcherPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw 'Launcher PowerShell syntax failed.' }
$definitions = $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] }, $false)
foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
$script:assertions = 0
function Assert-True([bool]$Condition, [string]$Message) {
    if (!$Condition) { throw $Message }; ++$script:assertions
}
function Assert-Rejected([scriptblock]$Action, [string]$Message) {
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    Assert-True $rejected $Message
}

Assert-True ((ConvertTo-LoopbackProxyEndpoint '127.0.0.1:17988') -eq 'http://127.0.0.1:17988') 'IPv4 loopback failed.'
Assert-True ((ConvertTo-LoopbackProxyEndpoint 'localhost:7897') -eq 'http://127.0.0.1:7897') 'localhost must avoid DNS resolution.'
Assert-True ((ConvertTo-LoopbackProxyEndpoint '[::1]:17988') -eq 'http://[::1]:17988') 'IPv6 loopback failed.'
foreach ($bad in @('127.0.0.1:0','127.0.0.1:65536','127.0.0.999:7897','192.168.0.1:7897','example.com:7897','user:password@127.0.0.1:7897','http=127.0.0.1:7897;https=127.0.0.1:7898','127.0.0.1:7897/path','127.0.0.1:7897?token=secret')) {
    Assert-Rejected { ConvertTo-LoopbackProxyEndpoint $bad } 'Unsafe or ambiguous proxy was accepted.'
}
Assert-Rejected { ConvertTo-LoopbackProxyEndpoint "127.0.0.1:7897`n" } 'Trailing newline must be rejected.'
$native = [pscustomobject]@{Flags=3;Server='127.0.0.1:17988';Pac=''}
$registry = [pscustomobject]@{Enabled=$true;Server='127.0.0.1:17988';Pac=''}
Assert-True ((Assert-ExplicitLoopbackProxy $native $registry) -eq 'http://127.0.0.1:17988') 'Consistent proxy rejected.'
$native.Flags = 11
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'WPAD must be rejected.'
$native.Flags = 3; $registry.Pac = 'https://example.com/private.pac'
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'Registry PAC ambiguity must be rejected.'
$registry.Pac = ''; $native.Pac = 'https://example.com/private.pac'
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'WinINET PAC ambiguity must be rejected.'
$native.Pac = ''; $registry.Server = '127.0.0.1:7897'
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'Mismatched endpoint must be rejected.'
$registry.Server = '127.0.0.1:17988'; $registry.Enabled = $false
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'Disabled registry proxy must be rejected.'
$registry.Enabled = $true; $native.Flags = 1
Assert-Rejected { Assert-ExplicitLoopbackProxy $native $registry } 'Disabled WinINET proxy must be rejected.'

$parentBefore = [Environment]::GetEnvironmentVariable('HTTP_PROXY','Process')
$info = New-CodexProxyStartInfo -ExecutablePath 'C:\Codex\ChatGPT.exe' -ProxyEndpoint 'http://127.0.0.1:17988'
Assert-True (!$info.UseShellExecute) 'Shell activation could lose the process environment.'
Assert-True ($info.ArgumentList.Count -eq 2 -and $info.ArgumentList[0] -eq '--proxy-server=http://127.0.0.1:17988') 'Chromium proxy startup switch missing.'
Assert-True ($info.ArgumentList[1] -eq '--proxy-bypass-list=localhost;127.0.0.1;[::1]') 'Only local callback destinations may bypass the Chromium proxy.'
foreach ($name in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY')) { Assert-True ($info.Environment[$name] -eq 'http://127.0.0.1:17988') 'Child proxy environment missing.' }
Assert-True ($info.Environment['NO_PROXY'] -eq 'localhost,127.0.0.1,::1') 'Child NO_PROXY must not bypass remote destinations.'
Assert-True ([Environment]::GetEnvironmentVariable('HTTP_PROXY','Process') -ceq $parentBefore) 'Parent environment was modified.'
Assert-True (Test-CodexDesktopIdentity 'C:\Program Files\WindowsApps\OpenAI.Codex_1.0_x64__id\app\ChatGPT.exe' 'C:\Codex\ChatGPT.exe') 'Packaged desktop was missed.'
Assert-True (Test-CodexDesktopIdentity 'C:\Codex\ChatGPT.exe' 'C:\Codex\ChatGPT.exe') 'Explicit desktop path was missed.'
Assert-True (!(Test-CodexDesktopIdentity 'C:\Users\example\AppData\Local\OpenAI\Codex\bin\version\codex.exe' 'C:\Codex\ChatGPT.exe')) 'CLI helper must not be treated as desktop.'
Assert-True ((Resolve-LocalCodexExecutablePath 'C:/Codex/app/../ChatGPT.exe') -eq 'C:\Codex\ChatGPT.exe') 'Local path normalization failed.'
foreach ($badPath in @('//example.invalid/share/Codex.exe','\\example.invalid\share\Codex.exe','\\?\C:\Codex\Codex.exe','//?/C:/Codex/Codex.exe','\\.\C:\Codex\Codex.exe','//./C:/Codex/Codex.exe','\\?\UNC\example.invalid\share\Codex.exe','Codex.exe','C:Codex.exe')) {
    Assert-Rejected { Resolve-LocalCodexExecutablePath $badPath } 'Network, device or relative executable path was accepted.'
}
Write-Output "Codex proxy launcher: $script:assertions assertions passed; no applications started or system settings changed."
