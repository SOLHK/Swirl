param(
    [ValidateSet('Install','ValidateUninstall','Uninstall')][string]$Mode,
    [string]$ApplicationDirectory,
    [string]$ExpectedManifest,
    [string]$AppVersion
)
# This file is embedded in the installer, not an unmanaged product payload.
# Dot-sourcing exposes the same transaction functions to the native regression.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'RustProductPackagePolicy.ps1')

# RegistryKey.GetValue/SetValue decode and normalize string terminators. The
# original value may contain a missing terminator, embedded NULs, or raw bytes
# that do not round-trip through that typed representation. Preserve the Win32
# type and exactly the returned bytes, including a present zero-length value.
if (-not ('SwirlIntegration.NativeRegistry' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace SwirlIntegration {
    public sealed class RawRegistryValue {
        public bool Exists;
        public UInt32 Type;
        public byte[] Bytes;
    }
    public static class NativeRegistry {
        public const int MaxValueBytes = 65536;
        private static readonly IntPtr CurrentUser = new IntPtr(unchecked((int)0x80000001));
        private const int QueryValue = 0x0001, SetValue = 0x0002, Registry32 = 0x0200;
        private const int NotFound = 2, PathNotFound = 3, MoreData = 234;
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegOpenKeyExW(IntPtr root, string path, int options, int access, out IntPtr key);
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegCreateKeyExW(IntPtr root, string path, int reserved, string keyClass,
            int options, int access, IntPtr security, out IntPtr key, out int disposition);
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegQueryValueExW(IntPtr key, string name, IntPtr reserved,
            out UInt32 type, [Out] byte[] data, ref UInt32 size);
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegSetValueExW(IntPtr key, string name, int reserved,
            UInt32 type, byte[] data, int size);
        [DllImport("advapi32.dll", CharSet=CharSet.Unicode, ExactSpelling=true)]
        private static extern int RegDeleteValueW(IntPtr key, string name);
        [DllImport("advapi32.dll", ExactSpelling=true)]
        private static extern int RegCloseKey(IntPtr key);

        private static void Check(int error) {
            if (error != 0) throw new Win32Exception(error);
        }
        public static RawRegistryValue Read(string path, string name) {
            IntPtr key;
            int error = RegOpenKeyExW(CurrentUser, path, 0, QueryValue | Registry32, out key);
            if (error == NotFound || error == PathNotFound)
                return new RawRegistryValue { Exists=false, Type=0, Bytes=new byte[0] };
            Check(error);
            try {
                for (int attempt=0; attempt<4; ++attempt) {
                    UInt32 type, size=0;
                    error = RegQueryValueExW(key, name, IntPtr.Zero, out type, null, ref size);
                    if (error == NotFound)
                        return new RawRegistryValue { Exists=false, Type=0, Bytes=new byte[0] };
                    if (error != MoreData) Check(error);
                    if (size > MaxValueBytes) throw new InvalidOperationException("Registry snapshot exceeds its byte bound.");
                    byte[] bytes = new byte[(int)size];
                    error = RegQueryValueExW(key, name, IntPtr.Zero, out type, bytes, ref size);
                    if (error == NotFound)
                        return new RawRegistryValue { Exists=false, Type=0, Bytes=new byte[0] };
                    if (error == MoreData) continue;
                    Check(error);
                    if (size > bytes.Length) throw new InvalidOperationException("Registry read exceeded its buffer.");
                    if (size != bytes.Length) Array.Resize(ref bytes, (int)size);
                    return new RawRegistryValue { Exists=true, Type=type, Bytes=bytes };
                }
                throw new InvalidOperationException("Registry value changed repeatedly while being read.");
            } finally { RegCloseKey(key); }
        }
        public static void Write(string path, string name, UInt32 type, byte[] bytes) {
            if (bytes == null || bytes.Length > MaxValueBytes)
                throw new InvalidOperationException("Registry snapshot exceeds its byte bound.");
            IntPtr key;
            int disposition;
            Check(RegCreateKeyExW(CurrentUser, path, 0, null, 0, SetValue | Registry32,
                                  IntPtr.Zero, out key, out disposition));
            try { Check(RegSetValueExW(key, name, 0, type, bytes, bytes.Length)); }
            finally { RegCloseKey(key); }
        }
        public static void Delete(string path, string name) {
            IntPtr key;
            int error = RegOpenKeyExW(CurrentUser, path, 0, SetValue | Registry32, out key);
            if (error == NotFound || error == PathNotFound) return;
            Check(error);
            try {
                error = RegDeleteValueW(key, name);
                if (error != NotFound) Check(error);
            } finally { RegCloseKey(key); }
        }
    }
}
'@
}

function New-SwirlRegistryValueState {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('String','ExpandString','MultiString','DWord','QWord','Binary','None')][string]$Kind,
        [AllowNull()][AllowEmptyString()][AllowEmptyCollection()][object]$Value
    )
    [uint32]$type = 0
    [byte[]]$bytes = @()
    switch ($Kind) {
        'String' { $type=1; $bytes=[Text.Encoding]::Unicode.GetBytes([string]$Value+[char]0) }
        'ExpandString' { $type=2; $bytes=[Text.Encoding]::Unicode.GetBytes([string]$Value+[char]0) }
        'Binary' { $type=3; $bytes=[byte[]]$Value }
        'None' { $type=0; $bytes=[byte[]]$Value }
        'MultiString' {
            $type=7
            $bytes=[Text.Encoding]::Unicode.GetBytes(([string[]]$Value -join [char]0)+[char]0+[char]0)
        }
        { $_ -in @('DWord','QWord') } {
            $number=[decimal]::Parse([Convert]::ToString($Value,[Globalization.CultureInfo]::InvariantCulture),
                [Globalization.NumberStyles]::Integer,[Globalization.CultureInfo]::InvariantCulture)
            if ($Kind -eq 'DWord') {
                $type=4
                if ($number -lt -2147483648 -or $number -gt 4294967295) { throw 'DWORD value is out of range.' }
                $bytes=if($number -lt 0){[BitConverter]::GetBytes([int]$number)}else{[BitConverter]::GetBytes([uint32]$number)}
            } else {
                $type=11
                if ($number -lt [decimal]'-9223372036854775808' -or $number -gt [decimal]'18446744073709551615') { throw 'QWORD value is out of range.' }
                $bytes=if($number -lt 0){[BitConverter]::GetBytes([long]$number)}else{[BitConverter]::GetBytes([System.UInt64]$number)}
            }
            if (-not [BitConverter]::IsLittleEndian) { [Array]::Reverse($bytes) }
        }
    }
    if ($null -eq $bytes) { $bytes=[byte[]]@() }
    if ($bytes.Length -gt [SwirlIntegration.NativeRegistry]::MaxValueBytes) { throw 'Registry value exceeds its byte bound.' }
    return [ordered]@{exists=$true; type=$type; bytes=[Convert]::ToBase64String($bytes)}
}

function Get-SwirlIntegrationHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}

function Assert-SwirlIntegrationPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^[A-Za-z]:\\' -or $full.Length -le 3) {
        throw 'User integration requires an absolute local path, not a UNC or device path.'
    }
    Assert-SwirlPathWithoutLinks $full
    return $full.TrimEnd('\')
}

function ConvertTo-SwirlIntegrationJson([object]$Value) {
    return (ConvertTo-Json -InputObject $Value -Depth 24 -Compress)
}

function Test-SwirlIntegrationState([object]$Left,[object]$Right) {
    return (ConvertTo-SwirlIntegrationJson $Left) -ceq (ConvertTo-SwirlIntegrationJson $Right)
}

function New-SwirlIntegrationContext([string]$ApplicationDirectory,[string]$ExpectedManifest,[string]$AppVersion) {
    $root = Assert-SwirlIntegrationPath $ApplicationDirectory
    $manifestPath = Assert-SwirlIntegrationPath $ExpectedManifest
    if ((Get-Item -LiteralPath $manifestPath).Length -gt 16777216) { throw 'Integration manifest exceeds its bound.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.source_sha -notmatch '^[0-9a-f]{40}$' -or
        $manifest.rust.source_sha -cne $manifest.source_sha) { throw 'Invalid integration package identity.' }
    if ($AppVersion -and $AppVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid integration product version.' }
    $options = [Environment+SpecialFolderOption]::DoNotVerify
    $desktop = Assert-SwirlIntegrationPath ([Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory,$options))
    $programs = Assert-SwirlIntegrationPath ([Environment]::GetFolderPath([Environment+SpecialFolder]::Programs,$options))
    $roaming = Assert-SwirlIntegrationPath ([Environment]::GetFolderPath([Environment+SpecialFolder]::ApplicationData,$options))
    $menu = Join-Path $programs 'Swirl'
    $targets = @{}
    $keys = @('Software\Swirl','Software\Microsoft\Windows\CurrentVersion\Uninstall\Swirl')
    $values = @(
        @('install-directory',$keys[0],'InstallDir'),
        @('display-name',$keys[1],'DisplayName'), @('display-version',$keys[1],'DisplayVersion'),
        @('install-location',$keys[1],'InstallLocation'), @('uninstall-command',$keys[1],'UninstallString'),
        @('display-icon',$keys[1],'DisplayIcon'), @('publisher',$keys[1],'Publisher'),
        @('no-modify',$keys[1],'NoModify'), @('no-repair',$keys[1],'NoRepair')
    )
    foreach ($value in $values) { $targets[$value[0]] = @{kind='registry'; key=$value[1]; name=$value[2]} }
    $targets['desktop'] = @{kind='shortcut'; path=(Join-Path $desktop 'Swirl.lnk')}
    $targets['start-menu'] = @{kind='shortcut'; path=(Join-Path $menu 'Swirl.lnk')}
    $targets['codex-start-menu'] = @{kind='shortcut'; path=(Join-Path $menu '通过 Swirl 启动 Codex.lnk')}
    $targets['owned-pin'] = @{kind='shortcut'; path=(Join-Path $roaming 'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar/Swirl.lnk')}
    foreach ($target in $targets.Values) {
        if ($target.kind -eq 'shortcut') { $null = Assert-SwirlIntegrationPath $target.path }
    }
    return [pscustomobject]@{
        Root=$root; Receipt=(Join-Path $root '.swirl-user-integration.json'); Targets=$targets; Keys=$keys
        Menu=$menu; Source=[string]$manifest.source_sha; ManifestHash=(Get-SwirlIntegrationHash $manifestPath)
        UserSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        HelperHash=(Get-SwirlIntegrationHash (Join-Path $PSScriptRoot 'WindowsUserIntegration.ps1'))
        Version=$AppVersion; RegistryView='Registry32'
    }
}

function Open-SwirlIntegrationHive {
    # NSIS is a 32-bit process. Explicit view keeps the x64 policy runner and
    # the actual x86 Windows PowerShell installer helper on the same registry.
    return [Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
}

function Get-SwirlIntegrationState([object]$Context,[string]$Id) {
    if (-not $Context.Targets.ContainsKey($Id)) { throw 'Unknown integration target.' }
    $target = $Context.Targets[$Id]
    if ($target.kind -eq 'shortcut') {
        $path = Assert-SwirlIntegrationPath $target.path
        if (-not (Test-Path -LiteralPath $path)) { return [ordered]@{exists=$false} }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -gt 262144) {
            throw 'A shortcut snapshot is not a bounded regular file.'
        }
        return [ordered]@{exists=$true; bytes=[Convert]::ToBase64String([IO.File]::ReadAllBytes($path))}
    }
    $raw = [SwirlIntegration.NativeRegistry]::Read($target.key,$target.name)
    if (-not $raw.Exists) { return [ordered]@{exists=$false} }
    return [ordered]@{exists=$true; type=$raw.Type; bytes=[Convert]::ToBase64String($raw.Bytes)}
}

function Assert-SwirlIntegrationState([object]$Context,[string]$Id,[object]$State) {
    if (-not $Context.Targets.ContainsKey($Id) -or $State.exists -isnot [bool]) { throw 'Invalid integration state.' }
    $names = if ($State -is [Collections.IDictionary]) { @($State.Keys) } else { @($State.PSObject.Properties.Name) }
    if (-not $State.exists) {
        if (@($names | Where-Object { $_ -ne 'exists' }).Count) { throw 'Unexpected absent integration state fields.' }
        return
    }
    if ($Context.Targets[$Id].kind -eq 'shortcut') {
        if (@($names | Where-Object { $_ -notin @('exists','bytes') }).Count -or $State.bytes -isnot [string]) { throw 'Invalid shortcut snapshot fields.' }
        if ([Convert]::FromBase64String([string]$State.bytes).Length -gt 262144) { throw 'Shortcut snapshot exceeds its bound.' }
    } else {
        if (@($names | Where-Object { $_ -notin @('exists','type','bytes') }).Count -or $State.bytes -isnot [string] -or
            ($State.type -isnot [int] -and $State.type -isnot [uint32] -and $State.type -isnot [long] -and $State.type -isnot [System.UInt64]) -or
            [decimal]$State.type -lt 0 -or [decimal]$State.type -gt 4294967295) { throw 'Invalid raw registry snapshot.' }
        if ([Convert]::FromBase64String($State.bytes).Length -gt [SwirlIntegration.NativeRegistry]::MaxValueBytes) { throw 'Registry snapshot exceeds its byte bound.' }
    }
}

function Write-SwirlIntegrationFile([string]$Path,[byte[]]$Bytes) {
    $full = Assert-SwirlIntegrationPath $Path
    $parent = [IO.Path]::GetDirectoryName($full)
    $null = [IO.Directory]::CreateDirectory($parent)
    $temporary = Join-Path $parent ('.swirl-integration-' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllBytes($temporary,$Bytes)
        $null = Assert-SwirlIntegrationPath $full
        if ([IO.File]::Exists($full)) {
            # The .NET backup argument needs a real null. PowerShell converts
            # ordinary $null to an invalid empty string for string parameters.
            [IO.File]::Replace($temporary,$full,[System.Management.Automation.Language.NullString]::Value)
        }
        else { [IO.File]::Move($temporary,$full) }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function Set-SwirlIntegrationState([object]$Context,[string]$Id,[object]$State) {
    Assert-SwirlIntegrationState $Context $Id $State
    $target = $Context.Targets[$Id]
    if ($target.kind -eq 'shortcut') {
        $path = Assert-SwirlIntegrationPath $target.path
        if ($State.exists) { Write-SwirlIntegrationFile $path ([Convert]::FromBase64String([string]$State.bytes)) }
        elseif ([IO.File]::Exists($path)) { [IO.File]::Delete($path) }
        return
    }
    if ($State.exists) {
        [SwirlIntegration.NativeRegistry]::Write($target.key,$target.name,[uint32]$State.type,[Convert]::FromBase64String($State.bytes))
    } else { [SwirlIntegration.NativeRegistry]::Delete($target.key,$target.name) }
}

function Get-SwirlIntegrationContainers([object]$Context) {
    $keys = @{}
    $hive = Open-SwirlIntegrationHive
    try {
        foreach ($name in $Context.Keys) {
            $key = $hive.OpenSubKey($name,$false)
            $keys[$name] = $null -ne $key
            if ($null -ne $key) { $key.Dispose() }
        }
    } finally { $hive.Dispose() }
    return [ordered]@{keys=$keys; menu_existed=[IO.Directory]::Exists($Context.Menu)}
}

function Remove-SwirlEmptyIntegrationContainers([object]$Context,[object]$Before) {
    $hive = Open-SwirlIntegrationHive
    try {
        foreach ($name in $Context.Keys) {
            $existed = if ($Before.keys -is [Collections.IDictionary]) { $Before.keys[$name] } else { $Before.keys.PSObject.Properties[$name].Value }
            if ($existed) { continue }
            $key = $hive.OpenSubKey($name,$false)
            if ($null -eq $key) { continue }
            try { $empty = $key.ValueCount -eq 0 -and $key.SubKeyCount -eq 0 }
            finally { $key.Dispose() }
            # DeleteSubKey is deliberately nonrecursive; user-added values or
            # subkeys, including edits made after installation, are preserved.
            if ($empty) { $hive.DeleteSubKey($name,$false) }
        }
    } finally { $hive.Dispose() }
    $null = Assert-SwirlIntegrationPath $Context.Menu
    if (-not $Before.menu_existed -and [IO.Directory]::Exists($Context.Menu) -and
        @(Get-ChildItem -LiteralPath $Context.Menu -Force).Count -eq 0) {
        [IO.Directory]::Delete($Context.Menu,$false)
    }
}

function Write-SwirlIntegrationReceipt([object]$Context,[object]$Receipt) {
    $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes((ConvertTo-SwirlIntegrationJson $Receipt))
    if ($bytes.Length -gt 8388608) { throw 'Integration receipt exceeds its bound.' }
    Write-SwirlIntegrationFile $Context.Receipt $bytes
}

function Assert-SwirlIntegrationReceipt([object]$Context,[object]$Receipt) {
    if ($Receipt.schema -ne 1 -or $Receipt.application_directory -ine $Context.Root -or
        $Receipt.user_sid -cne $Context.UserSid -or $Receipt.registry_view -cne 'Registry32' -or
        $Receipt.source_sha -notmatch '^[0-9a-f]{40}$' -or $Receipt.manifest_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $Receipt.helper_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $Receipt.phase -notin @('committed','uninstalled','pending')) { throw 'Integration receipt owner or schema mismatch.' }
    $seen = @{}
    foreach ($entry in @($Receipt.entries)) {
        if (-not $Context.Targets.ContainsKey([string]$entry.id) -or $seen.ContainsKey([string]$entry.id)) { throw 'Invalid duplicate integration target.' }
        $seen[[string]$entry.id] = $true
        Assert-SwirlIntegrationState $Context $entry.id $entry.before
        Assert-SwirlIntegrationState $Context $entry.id $entry.after
    }
    foreach ($name in $Context.Keys) {
        $value = if ($Receipt.containers.keys -is [Collections.IDictionary]) { $Receipt.containers.keys[$name] } else { $Receipt.containers.keys.PSObject.Properties[$name].Value }
        if ($value -isnot [bool]) { throw 'Invalid original registry-key ownership.' }
    }
    if ($Receipt.containers.menu_existed -isnot [bool]) { throw 'Invalid original menu ownership.' }
    if ($Receipt.phase -eq 'pending') {
        foreach ($name in $Context.Keys) {
            $value = if ($Receipt.transaction_containers.keys -is [Collections.IDictionary]) { $Receipt.transaction_containers.keys[$name] } else { $Receipt.transaction_containers.keys.PSObject.Properties[$name].Value }
            if ($value -isnot [bool]) { throw 'Invalid transaction registry-key ownership.' }
        }
        if ($Receipt.transaction_containers.menu_existed -isnot [bool]) { throw 'Invalid transaction menu ownership.' }
        if (@($Receipt.operations).Count -gt $Context.Targets.Count) { throw 'Too many integration operations.' }
        $operations = @{}
        foreach ($op in @($Receipt.operations)) {
            if ($operations.ContainsKey([string]$op.id)) { throw 'Duplicate integration operation.' }
            $operations[[string]$op.id] = $true
            Assert-SwirlIntegrationState $Context $op.id $op.before
            Assert-SwirlIntegrationState $Context $op.id $op.after
        }
        if ($null -ne $Receipt.previous_receipt) {
            $previousBytes = [Convert]::FromBase64String([string]$Receipt.previous_receipt)
            if ($previousBytes.Length -gt 8388608) { throw 'Saved integration receipt exceeds its bound.' }
            $previous = [Text.Encoding]::UTF8.GetString($previousBytes) | ConvertFrom-Json
            if ($previous.phase -eq 'pending') { throw 'Nested unfinished integration transaction.' }
            Assert-SwirlIntegrationReceipt $Context $previous
        }
    }
}

function Read-SwirlIntegrationReceipt([object]$Context) {
    $null = Assert-SwirlIntegrationPath $Context.Receipt
    if (-not (Test-Path -LiteralPath $Context.Receipt)) { return $null }
    if (-not (Test-Path -LiteralPath $Context.Receipt -PathType Leaf) -or
        (Get-Item -LiteralPath $Context.Receipt).Length -gt 8388608) { throw 'Invalid integration receipt file.' }
    $receipt = Get-Content -LiteralPath $Context.Receipt -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-SwirlIntegrationReceipt $Context $receipt
    return $receipt
}

function Restore-SwirlIntegrationTransaction([object]$Context,[object]$Pending) {
    Assert-SwirlIntegrationReceipt $Context $Pending
    $operations = @($Pending.operations)
    $failures = New-Object 'System.Collections.Generic.List[string]'
    for ($index = $operations.Count - 1; $index -ge 0; $index--) {
        $op = $operations[$index]
        try {
            if (Test-SwirlIntegrationState (Get-SwirlIntegrationState $Context $op.id) $op.after) {
                Set-SwirlIntegrationState $Context $op.id $op.before
            }
        } catch { $failures.Add([string]$op.id + ': ' + $_.Exception.Message) }
    }
    try { Remove-SwirlEmptyIntegrationContainers $Context $Pending.transaction_containers }
    catch { $failures.Add('containers: ' + $_.Exception.Message) }
    if ($failures.Count) { throw ('Integration recovery remains retryable: ' + ($failures -join '; ')) }
    if ($null -eq $Pending.previous_receipt) { [IO.File]::Delete($Context.Receipt) }
    else { Write-SwirlIntegrationFile $Context.Receipt ([Convert]::FromBase64String([string]$Pending.previous_receipt)) }
}

function Invoke-SwirlIntegrationTransaction([object]$Context,[object]$FinalReceipt,[object[]]$Operations) {
    $priorBytes = if ([IO.File]::Exists($Context.Receipt)) { [Convert]::ToBase64String([IO.File]::ReadAllBytes($Context.Receipt)) } else { $null }
    $pending = [ordered]@{
        schema=1; application_directory=$Context.Root; user_sid=$Context.UserSid; registry_view='Registry32'
        source_sha=$Context.Source; manifest_sha256=$Context.ManifestHash; helper_sha256=$Context.HelperHash
        phase='pending'; entries=$FinalReceipt.entries; containers=$FinalReceipt.containers
        transaction_containers=(Get-SwirlIntegrationContainers $Context); operations=@($Operations); previous_receipt=$priorBytes
    }
    # The complete compare/restore plan is durable before the first registry
    # or shortcut mutation. A later user edit is never adopted as our output.
    Write-SwirlIntegrationReceipt $Context $pending
    try {
        foreach ($op in $Operations) {
            if (-not (Test-SwirlIntegrationState (Get-SwirlIntegrationState $Context $op.id) $op.before)) { throw 'Integration changed while installation was preparing.' }
            Set-SwirlIntegrationState $Context $op.id $op.after
            if (-not (Test-SwirlIntegrationState (Get-SwirlIntegrationState $Context $op.id) $op.after)) { throw 'Integration write verification failed.' }
        }
        if ($FinalReceipt.phase -eq 'uninstalled') { Remove-SwirlEmptyIntegrationContainers $Context $FinalReceipt.containers }
        Write-SwirlIntegrationReceipt $Context $FinalReceipt
    } catch {
        $failure = $_
        # If restoration itself fails, leave the pending journal for recovery.
        Restore-SwirlIntegrationTransaction $Context (Read-SwirlIntegrationReceipt $Context)
        throw $failure
    }
}

function New-SwirlIntegrationReceipt([object]$Context,[object]$Containers,[object[]]$Entries,[string]$Phase) {
    return [ordered]@{schema=1; application_directory=$Context.Root; user_sid=$Context.UserSid; registry_view='Registry32'
        source_sha=$Context.Source; manifest_sha256=$Context.ManifestHash; helper_sha256=$Context.HelperHash
        phase=$Phase; entries=@($Entries); containers=$Containers}
}

function Install-SwirlUserIntegration([object]$Context,[hashtable]$Desired) {
    $previous = Read-SwirlIntegrationReceipt $Context
    if ($null -ne $previous -and $previous.phase -eq 'pending') {
        Restore-SwirlIntegrationTransaction $Context $previous
        $previous = Read-SwirlIntegrationReceipt $Context
    }
    $before = Get-SwirlIntegrationContainers $Context
    $owned = @{}
    if ($null -ne $previous -and $previous.phase -eq 'committed') {
        $before = $previous.containers
        foreach ($entry in @($previous.entries)) { $owned[[string]$entry.id] = $entry }
    }
    $entries = New-Object 'Collections.Generic.List[object]'
    $operations = New-Object 'Collections.Generic.List[object]'
    $preserved = 0
    foreach ($id in @(@($Desired.Keys) + @($owned.Keys) | Sort-Object -Unique)) {
        if (-not $Context.Targets.ContainsKey($id)) { throw 'Unexpected integration destination.' }
        $current = Get-SwirlIntegrationState $Context $id
        if ($owned.ContainsKey($id) -and -not (Test-SwirlIntegrationState $current $owned[$id].after)) {
            $entries.Add($owned[$id]); $preserved++; continue
        }
        $baseline = if ($owned.ContainsKey($id)) { $owned[$id].before } else { $current }
        $after = if ($Desired.ContainsKey($id)) { $Desired[$id] } else { $baseline }
        Assert-SwirlIntegrationState $Context $id $after
        if ($Desired.ContainsKey($id)) { $entries.Add([ordered]@{id=$id; before=$baseline; after=$after}) }
        if (-not (Test-SwirlIntegrationState $current $after)) { $operations.Add([ordered]@{id=$id; before=$current; after=$after}) }
    }
    $final = New-SwirlIntegrationReceipt $Context $before $entries.ToArray() 'committed'
    Invoke-SwirlIntegrationTransaction $Context $final $operations.ToArray()
    return [ordered]@{mode='Install'; changed=$operations.Count; user_edits_preserved=$preserved; success=$true}
}

function Assert-SwirlIntegrationUninstall([object]$Context,[switch]$CheckInstalledManifest) {
    if ($CheckInstalledManifest) {
        $installed = Assert-SwirlIntegrationPath (Join-Path $Context.Root 'package-manifest.json')
        if (-not [IO.File]::Exists($installed) -or (Get-SwirlIntegrationHash $installed) -cne $Context.ManifestHash) {
            throw 'Installed package identity does not match this integration uninstaller.'
        }
    }
    $receipt = Read-SwirlIntegrationReceipt $Context
    if ($null -ne $receipt -and $receipt.phase -eq 'pending') {
        if (-not $CheckInstalledManifest) { throw 'Pending integration transaction requires verified recovery.' }
        Restore-SwirlIntegrationTransaction $Context $receipt
        $receipt = Read-SwirlIntegrationReceipt $Context
    }
    if ($null -ne $receipt -and ($receipt.source_sha -cne $Context.Source -or $receipt.manifest_sha256 -cne $Context.ManifestHash -or
        $receipt.helper_sha256 -cne $Context.HelperHash)) {
        throw 'Integration receipt belongs to another installed package.'
    }
    return $receipt
}

function Uninstall-SwirlUserIntegration([object]$Context) {
    $receipt = Assert-SwirlIntegrationUninstall $Context
    if ($null -eq $receipt -or $receipt.phase -eq 'uninstalled') {
        # Old installations have no trustworthy shortcut/registry receipt.
        # Unknown integration is preserved; absence never authorizes deletion.
        return [ordered]@{mode='Uninstall'; changed=0; legacy_integration_preserved=($null -eq $receipt); success=$true}
    }
    $operations = New-Object 'Collections.Generic.List[object]'
    $preserved = 0
    foreach ($entry in @($receipt.entries)) {
        $current = Get-SwirlIntegrationState $Context $entry.id
        if (-not (Test-SwirlIntegrationState $current $entry.after)) { $preserved++; continue }
        if (-not (Test-SwirlIntegrationState $current $entry.before)) {
            $operations.Add([ordered]@{id=$entry.id; before=$current; after=$entry.before})
        }
    }
    $final = New-SwirlIntegrationReceipt $Context $receipt.containers @() 'uninstalled'
    Invoke-SwirlIntegrationTransaction $Context $final $operations.ToArray()
    return [ordered]@{mode='Uninstall'; changed=$operations.Count; user_edits_preserved=$preserved; success=$true}
}

function New-SwirlDesiredUserIntegration([object]$Context) {
    if (-not $Context.Version) { throw 'Installation requires a product version.' }
    $exe = Join-Path $Context.Root 'Swirl.exe'
    $icon = Join-Path $Context.Root 'Swirl-brand-0217-optical.ico'
    $guard = Join-Path $Context.Root 'SwirlProxyGuard.exe'
    foreach ($file in @($exe,$icon,$guard)) {
        $null = Assert-SwirlIntegrationPath $file
        if (-not [IO.File]::Exists($file)) { throw 'Verified shortcut inputs are missing.' }
    }
    $desired = @{}
    $strings = @{'install-directory'=$Context.Root; 'display-name'='Swirl'; 'display-version'=($Context.Version+'.0')
        'install-location'=$Context.Root; 'uninstall-command'=('"'+(Join-Path $Context.Root '卸载 Swirl.exe')+'"')
        'display-icon'=$icon; 'publisher'='Swirl'}
    foreach ($id in $strings.Keys) { $desired[$id] = New-SwirlRegistryValueState -Kind String -Value ([string]$strings[$id]) }
    foreach ($id in @('no-modify','no-repair')) { $desired[$id] = New-SwirlRegistryValueState -Kind DWord -Value 1 }
    $stage = Join-Path ([IO.Path]::GetTempPath()) ('swirl-integration-' + [guid]::NewGuid().ToString('N'))
    $null = Assert-SwirlIntegrationPath $stage
    $null = [IO.Directory]::CreateDirectory($stage)
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcuts = @{'desktop'=$exe; 'start-menu'=$exe}
        $codex = Join-Path $Context.Root 'SwirlCodexLauncher.exe'
        if ([IO.File]::Exists($codex)) { $shortcuts['codex-start-menu'] = $codex }
        foreach ($id in $shortcuts.Keys) {
            $staged = Join-Path $stage 'Swirl.lnk'
            $link = $shell.CreateShortcut($staged)
            try { $link.TargetPath=$shortcuts[$id]; $link.IconLocation=$icon+',0'; $link.Save() }
            finally { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($link) }
            if ($id -ne 'codex-start-menu') {
                & $guard --repair-shortcut $staged $exe $icon | Out-Null
                if ($LASTEXITCODE -ne 0) { throw 'Verified shortcut AppID repair failed.' }
            }
            $desired[$id] = [ordered]@{exists=$true; bytes=[Convert]::ToBase64String([IO.File]::ReadAllBytes($staged))}
            [IO.File]::Delete($staged)
        }
        $pin = $Context.Targets['owned-pin'].path
        if ([IO.File]::Exists($pin)) {
            $link = $shell.CreateShortcut($pin)
            try { $target = [string]$link.TargetPath }
            finally { $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($link) }
            if ($target -and [IO.Path]::GetFullPath($target) -ieq [IO.Path]::GetFullPath($exe)) {
                $staged = Join-Path $stage 'Swirl.lnk'
                [IO.File]::Copy($pin,$staged,$false)
                & $guard --repair-shortcut $staged $exe $icon | Out-Null
                if ($LASTEXITCODE -ne 0) { throw 'Owned pinned shortcut repair failed.' }
                $desired['owned-pin'] = [ordered]@{exists=$true; bytes=[Convert]::ToBase64String([IO.File]::ReadAllBytes($staged))}
                [IO.File]::Delete($staged)
            }
        }
    } finally {
        $null = [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
        foreach ($entry in @(Get-ChildItem -LiteralPath $stage -File -Force)) { [IO.File]::Delete($entry.FullName) }
        [IO.Directory]::Delete($stage,$false)
    }
    return $desired
}

if ($Mode) {
    if (-not $ApplicationDirectory -or -not $ExpectedManifest) { throw 'Integration identity arguments are required.' }
    $context = New-SwirlIntegrationContext $ApplicationDirectory $ExpectedManifest $AppVersion
    $mutex = New-Object Threading.Mutex($false,('Local\SwirlUserIntegration-' + $context.UserSid))
    $held = $false
    try {
        try { $held = $mutex.WaitOne(30000) } catch [Threading.AbandonedMutexException] { $held=$true }
        if (-not $held) { throw 'Another user-integration transaction is still running.' }
        if ($Mode -eq 'Install') { $result = Install-SwirlUserIntegration $context (New-SwirlDesiredUserIntegration $context) }
        elseif ($Mode -eq 'ValidateUninstall') {
            $null = Assert-SwirlIntegrationUninstall $context -CheckInstalledManifest
            $result = @{mode=$Mode; success=$true}
        } else { $result = Uninstall-SwirlUserIntegration $context }
        $result | ConvertTo-Json -Compress | Write-Output
    } finally { if ($held) { $mutex.ReleaseMutex() }; $mutex.Dispose() }
}
