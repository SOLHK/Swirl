param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'Copy-VerifiedMsvcRuntime.ps1')
$lock = Get-Content -LiteralPath (Join-Path $repo 'tools/qt612-product-sdk.lock.json') -Raw | ConvertFrom-Json
$report = [ordered]@{schema=1;success=$false;errors=@();source_sha=$env:GITHUB_SHA}
function Identity([string]$Path) {
    $file = Get-Item -LiteralPath $Path
    return [ordered]@{path=$file.FullName;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
try {
    if (-not $IsWindows -or $env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_ENVIRONMENT -cne 'github-hosted' -or
        $env:GITHUB_REPOSITORY -cne 'SOLHK/Swirl' -or $env:VSCMD_ARG_TGT_ARCH -cne 'x64') { throw 'Hosted x64 MSVC producer required.' }
    $cl = (Get-Command cl.exe -ErrorAction Stop).Source
    $link = (Get-Command link.exe -ErrorAction Stop).Source
    $clInfo = (Get-Item -LiteralPath $cl).VersionInfo
    $linkInfo = (Get-Item -LiteralPath $link).VersionInfo
    $compilerVersion = [version]::new($clInfo.FileMajorPart,$clInfo.FileMinorPart,$clInfo.FileBuildPart,$clInfo.FilePrivatePart)
    $linkerVersion = [version]::new($linkInfo.FileMajorPart,$linkInfo.FileMinorPart,$linkInfo.FileBuildPart,$linkInfo.FilePrivatePart)
    $previous = [version]$lock.content.producer_compiler.CMAKE_CXX_COMPILER_VERSION
    $report.compiler = [ordered]@{
        binary=(Identity $cl);linker=(Identity $link)
        metadata=[ordered]@{compiler_id='MSVC';compiler_version=$compilerVersion.ToString();linker_version=$linkerVersion.ToString();
            msvc_architecture='x64';msvc_tools_version=$env:VCToolsVersion;windows_sdk_version=$env:WindowsSDKVersion}
    }
    $report.previous_qml_compiler = [ordered]@{binary=$lock.content.producer_compiler_binary;metadata=$lock.content.producer_compiler}
    $report.compatibility = [ordered]@{
        source='https://learn.microsoft.com/en-us/cpp/porting/binary-compat-2015-2017'
        policy='MSVC 19.44 x64 maintenance update at least as new as the recorded QML producer; matching current linker. New fresh object files; only Qt dynamic libraries and import libraries are reused.'
        original_qml_provenance_preserved=$true
    }
    if ($compilerVersion.Major -ne 19 -or $compilerVersion.Minor -ne 44 -or $compilerVersion -lt $previous -or
        $linkerVersion.Major -ne 14 -or $linkerVersion.Minor -ne 44 -or
        $linkerVersion.Build -ne $compilerVersion.Build -or $linkerVersion.Revision -ne $compilerVersion.Revision -or
        (Split-Path $cl) -ine (Split-Path $link)) { throw 'MSVC maintenance toolchain is outside the explicitly admitted compiler/linker range.' }
    $compilerPath = Resolve-SwirlMsvcPath $cl
    if ($compilerPath -notmatch '^(?<vs>.+)[\\/]VC[\\/]Tools[\\/]MSVC[\\/](?<toolset>[0-9.]+)[\\/]bin[\\/]Hostx64[\\/]x64[\\/]cl\.exe$') { throw 'Compiler does not identify its installed VS toolchain.' }
    $vs = $Matches['vs']; $toolset = [version]$Matches['toolset']
    $redistRoot = Resolve-SwirlMsvcPath (Join-Path $vs 'VC/Redist/MSVC')
    $candidates = @(Get-ChildItem -LiteralPath $redistRoot -Directory | Where-Object {$_.Name -match '^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?$'} | Sort-Object @{Expression={[version]$_.Name};Descending=$true})
    $crtDirectory = $null
    foreach ($candidate in $candidates) {
        $x64 = Join-Path $candidate.FullName 'x64'
        if (-not (Test-Path -LiteralPath $x64 -PathType Container)) { continue }
        $directories = @(Get-ChildItem -LiteralPath $x64 -Directory | Where-Object {$_.Name -match '^Microsoft\.VC[0-9]+\.CRT$'})
        if ($directories.Count -gt 1) { throw 'Ambiguous same-VS CRT directory.' }
        if ($directories.Count -eq 1) { $crtDirectory = Resolve-SwirlMsvcPath $directories[0].FullName; break }
    }
    if ($null -eq $crtDirectory) { throw 'Same-VS current x64 CRT directory missing.' }
    $crtFiles = [ordered]@{}
    $report.compiler.crt = [ordered]@{directory=$crtDirectory;files=$crtFiles;minimum_toolset=$toolset.ToString();
        policy='Latest installed same-VS redist, exact Microsoft-signed AMD64 files; numerical minimum is the existing installed toolset contract, not the compiler/linker servicing build number.'}
    foreach ($file in Get-ChildItem -LiteralPath $crtDirectory -Filter '*.dll' -File) {
        $path = Resolve-SwirlMsvcPath $file.FullName
        $version = [version]::new($file.VersionInfo.FileMajorPart,$file.VersionInfo.FileMinorPart,$file.VersionInfo.FileBuildPart,$file.VersionInfo.FilePrivatePart)
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        $machine = [SwirlMsvcPackage.PeImage]::Read($path).Machine
        $crtFiles[$file.Name.ToLowerInvariant()] = [ordered]@{bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant();
            version=$version.ToString();machine=$machine;signature_status=$signature.Status.ToString();
            signer_subject=if($null -ne $signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null}}
        if ($machine -cne '0x8664' -or $version -lt $toolset -or $signature.Status -ne 'Valid' -or
            $null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)O=Microsoft Corporation(?:,|$)') {
            throw ('Same-VS CRT identity, signature or minimum toolset validation failed: '+$file.Name)
        }
    }
    if ($crtFiles.Count -eq 0) { throw 'Current MSVC redistributable files are unavailable.' }
    $report.success=$true
} catch {
    $report.errors += $_.Exception.Message
} finally {
    $parent = Split-Path -Parent ([IO.Path]::GetFullPath($Output))
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $Output -Encoding utf8
}
if (-not $report.success) { throw ($report.errors -join '; ') }
Write-Host ('Admitted MSVC '+$report.compiler.metadata.compiler_version+' / linker '+$report.compiler.metadata.linker_version)
