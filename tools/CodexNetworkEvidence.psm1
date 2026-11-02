# Read-only, bounded evidence helpers. Never return raw proxy strings or errors.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
Set-StrictMode -Version Latest

function ConvertTo-ProxyEndpointEvidence {
    param([AllowEmptyString()][string]$Value, [string]$DefaultScheme='http')
    if ([string]::IsNullOrWhiteSpace($Value)) { return @{configured=$false} }
    $invalid=@{configured=$true;valid=$false}
    if ($Value.Length -gt 4096 -or $Value -match '[\x00-\x20\x7f]') { return $invalid }
    if ($DefaultScheme -notin @('http','socks4')) { return $invalid }
    try {
        $text=if ($Value.Contains('://')) {$Value} else {$DefaultScheme+'://'+$Value}
        $uri=[uri]$text
        $hostName=$uri.IdnHost.Trim('[',']')
        if (!$uri.IsAbsoluteUri -or $uri.Scheme -notin @('http','https','socks','socks4','socks4a','socks5','socks5h') -or
            [string]::IsNullOrEmpty($hostName) -or $hostName -notmatch '\A[0-9A-Za-z.:%_-]+\z') { return $invalid }
        $port=$uri.Port
        if ($port -eq -1 -and $uri.Scheme -like 'socks*') { $port=1080 }
        if ($port -lt 1 -or $port -gt 65535) { return $invalid }
        return @{configured=$true;valid=$true;scheme=$uri.Scheme;host=$hostName;port=$port;
            credentialsPresent=![string]::IsNullOrEmpty($uri.UserInfo);
            extraUriComponentsPresent=($uri.AbsolutePath -notin @('','/') -or !!$uri.Query -or !!$uri.Fragment)}
    } catch { return $invalid }
}

function ConvertTo-ProxyMapEvidence {
    param([AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return @{configured=$false;entries=@()} }
    if ($Value.Length -gt 16384 -or $Value -match '[\x00-\x1f\x7f]') { return @{configured=$true;valid=$false;entries=@()} }
    # Query/userinfo may contain '=', ';' or whitespace. A single URI is parsed
    # intact; only a leading known Windows protocol assignment starts a map.
    $isMap=$Value -match '\A(?:http|https|ftp|socks)='
    if (!$isMap) { return @{configured=$true;entries=@(@{mapping='all';endpoint=(ConvertTo-ProxyEndpointEvidence $Value)})} }
    # Credentials or URI suffixes can themselves contain mapping delimiters.
    # Omit such maps wholesale, so secret text can never become a second host.
    if ($Value -match '[@?#\\]' -or ($Value -replace '[a-z0-9]+://','') -match '/') {
        return @{configured=$true;valid=$false;entries=@();credentialsPresent=$Value.Contains('@')}
    }
    $parts=@($Value -split '[; ]+' | Where-Object {$_})
    if ($parts.Count -gt 32) { return @{configured=$true;valid=$false;entries=@()} }
    $entries=@(foreach ($part in $parts) {
        if ($part -match '\A(http|https|ftp|socks)=(.+)\z') {
            $mapping=$Matches[1].ToLowerInvariant();$endpoint=$Matches[2]
            # Windows socks= without an explicit scheme means SOCKSv4 in Chromium.
            $default=if ($mapping -eq 'socks') {'socks4'} else {'http'}
            @{mapping=$mapping;endpoint=(ConvertTo-ProxyEndpointEvidence $endpoint $default)}
        } else { @{mapping='invalid';endpoint=@{configured=$true;valid=$false}} }
    })
    return @{configured=$true;entries=$entries}
}

function ConvertTo-ProxyBypassEvidence {
    param([AllowEmptyString()][string]$Value)
    if ([string]::IsNullOrEmpty($Value)) { return @{configured=$false;entryCount=0} }
    if ($Value.Length -gt 16384) { return @{configured=$true;bounded=$false} }
    $parts=@($Value -split '[;, ]+' | Where-Object {$_})
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $digest=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant() }
    finally {$sha.Dispose()}
    # A digest allows A/B equality checks without exporting private bypass names.
    return @{configured=$true;entryCount=$parts.Count;sha256=$digest;includesLocal=('<local>' -in $parts)}
}

function ConvertTo-NativeProxyEvidence {
    param($Observation)
    if ($Observation.ErrorCode -ne 0) { return @{available=$false;errorCode=$Observation.ErrorCode} }
    return @{available=$true;flags=$Observation.Flags;accessType=$Observation.AccessType;autoDetect=$Observation.AutoDetect;
        proxy=(ConvertTo-ProxyMapEvidence $Observation.Server);bypass=(ConvertTo-ProxyBypassEvidence $Observation.Bypass);
        pacConfigured=![string]::IsNullOrEmpty($Observation.Pac)}
}

function Get-WindowsNativeProxyEvidence {
    if ($env:OS -ne 'Windows_NT') { return @{available=$false;reason='not-windows'} }
    if (!('SwirlEvidence.NativeProxy' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace SwirlEvidence {
    public sealed class ProxyObservation {
        public int ErrorCode; public uint Flags; public uint AccessType; public bool AutoDetect;
        public string Server = "", Bypass = "", Pac = "";
    }
    public static class NativeProxy {
        [StructLayout(LayoutKind.Explicit)] private struct OptionValue {
            [FieldOffset(0)] public uint Flags;
            [FieldOffset(0)] public IntPtr Text;
            [FieldOffset(0)] public System.Runtime.InteropServices.ComTypes.FILETIME Time;
        }
        [StructLayout(LayoutKind.Sequential)] private struct Option { public uint Kind; public OptionValue Value; }
        [StructLayout(LayoutKind.Sequential)] private struct OptionList {
            public uint Size; public IntPtr Connection; public uint Count; public uint Error; public IntPtr Options;
        }
        [StructLayout(LayoutKind.Sequential)] private struct DefaultProxy { public uint AccessType; public IntPtr Server, Bypass; }
        [StructLayout(LayoutKind.Sequential)] private struct UserProxy {
            [MarshalAs(UnmanagedType.Bool)] public bool AutoDetect; public IntPtr Pac, Server, Bypass;
        }
        [DllImport("wininet.dll", SetLastError=true, CharSet=CharSet.Unicode)]
        [return: MarshalAs(UnmanagedType.Bool)] private static extern bool InternetQueryOptionW(IntPtr h, uint option, ref OptionList list, ref uint length);
        [DllImport("winhttp.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WinHttpGetDefaultProxyConfiguration(out DefaultProxy proxy);
        [DllImport("winhttp.dll", SetLastError=true)]
        [return: MarshalAs(UnmanagedType.Bool)] private static extern bool WinHttpGetIEProxyConfigForCurrentUser(out UserProxy proxy);
        [DllImport("kernel32.dll")] private static extern IntPtr GlobalFree(IntPtr memory);
        private static string Text(IntPtr p) { return p == IntPtr.Zero ? "" : Marshal.PtrToStringUni(p); }
        private static void Free(IntPtr p) { if (p != IntPtr.Zero) GlobalFree(p); }
        private static ProxyObservation QueryWinInet(uint flagKind) {
            int stride = Marshal.SizeOf(typeof(Option)); IntPtr memory = Marshal.AllocHGlobal(stride * 4);
            for (int i=0;i<4;++i) Marshal.StructureToPtr(new Option { Kind = i == 0 ? flagKind : (uint)(i+1) }, IntPtr.Add(memory,i*stride), false);
            try {
                var list = new OptionList { Size=(uint)Marshal.SizeOf(typeof(OptionList)), Count=4, Options=memory };
                uint length=list.Size;
                if (!InternetQueryOptionW(IntPtr.Zero,75,ref list,ref length)) return new ProxyObservation { ErrorCode=Marshal.GetLastWin32Error() };
                var flags=(Option)Marshal.PtrToStructure(memory,typeof(Option));
                var server=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,stride),typeof(Option));
                var bypass=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,2*stride),typeof(Option));
                var pac=(Option)Marshal.PtrToStructure(IntPtr.Add(memory,3*stride),typeof(Option));
                return new ProxyObservation { Flags=flags.Value.Flags, AutoDetect=(flags.Value.Flags & 8)!=0, Server=Text(server.Value.Text), Bypass=Text(bypass.Value.Text), Pac=Text(pac.Value.Text) };
            } finally {
                for (int i=1;i<4;++i) Free(((Option)Marshal.PtrToStructure(IntPtr.Add(memory,i*stride),typeof(Option))).Value.Text);
                Marshal.FreeHGlobal(memory);
            }
        }
        public static ProxyObservation WinInet() { var r=QueryWinInet(10); return r.ErrorCode == 0 ? r : QueryWinInet(1); }
        public static ProxyObservation WinHttpDefault() {
            DefaultProxy p; bool ok=WinHttpGetDefaultProxyConfiguration(out p); int error=ok ? 0 : Marshal.GetLastWin32Error();
            try { return new ProxyObservation { ErrorCode=error, AccessType=p.AccessType, Server=ok ? Text(p.Server) : "", Bypass=ok ? Text(p.Bypass) : "" }; }
            finally { Free(p.Server); Free(p.Bypass); }
        }
        public static ProxyObservation WinHttpCurrentUser() {
            UserProxy p; bool ok=WinHttpGetIEProxyConfigForCurrentUser(out p); int error=ok ? 0 : Marshal.GetLastWin32Error();
            try { return new ProxyObservation { ErrorCode=error, AutoDetect=p.AutoDetect, Server=ok ? Text(p.Server) : "", Bypass=ok ? Text(p.Bypass) : "", Pac=ok ? Text(p.Pac) : "" }; }
            finally { Free(p.Pac); Free(p.Server); Free(p.Bypass); }
        }
    }
}
'@
    }
    try {
        return @{available=$true;winInet=(ConvertTo-NativeProxyEvidence ([SwirlEvidence.NativeProxy]::WinInet()));
            winHttpDefault=(ConvertTo-NativeProxyEvidence ([SwirlEvidence.NativeProxy]::WinHttpDefault()));
            winHttpCurrentUser=(ConvertTo-NativeProxyEvidence ([SwirlEvidence.NativeProxy]::WinHttpCurrentUser()));
            scope='Static read-only snapshots; no PAC resolution, target request, or process-effective route is tested.'}
    } catch { return @{available=$false;reason='native-query-failed'} }
}

function Get-EvidenceLocalFile {
    param([string]$Path)
    # Reject remote/device/relative paths before even probing their existence.
    if ($Path -notmatch '\A[A-Za-z]:[\\/]' -or $Path.Substring(2).Contains(':')) { throw 'LocalFileRequired' }
    $full=[IO.Path]::GetFullPath($Path)
    $current=$full
    while ($current) {
        $item=Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'LinkedFileRejected' }
        $current=[IO.Path]::GetDirectoryName($current)
    }
    $file=Get-Item -LiteralPath $full -Force -ErrorAction Stop
    if ($file.PSIsContainer -or $file.Length -gt 536870912) { throw 'FileBounds' }
    return $file
}

function Get-EvidenceFileVersion {
    param([string]$Path)
    try {
        $file=Get-EvidenceLocalFile $Path
        $version=[Diagnostics.FileVersionInfo]::GetVersionInfo($file.FullName).FileVersion
        if ($version -match '\A[0-9]+(?:\.[0-9]+){1,3}(?:[+-][0-9A-Za-z.-]+)?\z') { return $version }
    } catch {}
    return $null
}

function Get-SwirlPackageEvidence {
    param([string]$ExecutablePath)
    $result=@{available=$false;sourceIdentityVerified=$false}
    try {
        $exe=Get-EvidenceLocalFile $ExecutablePath
        if ($exe.Name -ine 'Swirl.exe') { throw 'UnexpectedExecutable' }
        $result.available=$true;$result.fileVersion=Get-EvidenceFileVersion $exe.FullName
        $result.executableSha256=(Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $manifestFile=Get-EvidenceLocalFile (Join-Path $exe.DirectoryName 'package-manifest.json')
        if ($manifestFile.Length -gt 1048576) { throw 'ManifestBounds' }
        $manifest=Get-Content -LiteralPath $manifestFile.FullName -Raw | ConvertFrom-Json
        if ($manifest.schema -ne 1 -or $manifest.source_sha -isnot [string] -or $manifest.source_sha -notmatch '\A[0-9a-f]{40}\z' -or
            $manifest.rust.source_sha -isnot [string] -or $manifest.rust.source_sha -notmatch '\A[0-9a-f]{40}\z') { throw 'InvalidManifest' }
        $result.claimedSourceSha=$manifest.source_sha;$result.claimedRustSourceSha=$manifest.rust.source_sha
        $receiptFile=Get-EvidenceLocalFile (Join-Path $exe.DirectoryName 'swirl-rust-build.json')
        if ($receiptFile.Length -gt 65536) { throw 'BuildReceiptBounds' }
        $receipt=Get-Content -LiteralPath $receiptFile.FullName -Raw | ConvertFrom-Json
        if ($receipt.source_sha -isnot [string] -or $receipt.source_sha -notmatch '\A[0-9a-f]{40}\z') { throw 'InvalidBuildReceipt' }
        $result.buildReceiptClaimedSourceSha=$receipt.source_sha
        $result.buildReceiptSourcesAgree=$receipt.source_sha -ceq $manifest.rust.source_sha
        # Only fixed product paths are opened; arbitrary manifest paths are never followed.
        # These names are the actual Stage-WindowsRustProduct.ps1 product layout.
        $files=@(foreach ($name in @('Swirl.exe','swirl_api.dll','swirl-rust-build.json')) {
            $entries=@($manifest.files | Where-Object {$_.path -ceq $name})
            $entry=@{file=$name;digestMatches=$false}
            if ($entries.Count -eq 1 -and $entries[0].sha256 -match '\A[0-9a-fA-F]{64}\z') {
                try {
                    $file=Get-EvidenceLocalFile (Join-Path $exe.DirectoryName $name)
                    $entry.actualSha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                    $entry.digestMatches=$entry.actualSha256 -ieq $entries[0].sha256
                } catch { $entry.readable=$false }
            }
            $entry
        })
        $result.files=$files
        $result.identityFilesMatchManifest=(@($files | Where-Object {!$_.digestMatches}).Count -eq 0)
        $result.manifestSourcesAgree=$manifest.source_sha -ceq $manifest.rust.source_sha
        $result.scope='On-disk hashes and manifest claims only; no executable launch, loaded-DLL identity, build provenance or full-package verification.'
    } catch { $result.reason='package-metadata-unavailable-or-invalid' }
    return $result
}

Export-ModuleMember -Function ConvertTo-ProxyEndpointEvidence,ConvertTo-ProxyMapEvidence,ConvertTo-ProxyBypassEvidence,Get-WindowsNativeProxyEvidence,Get-EvidenceFileVersion,Get-SwirlPackageEvidence
