param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [switch]$PrepareOnly,
    [switch]$GitHubEnvironment
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if ($env:VSCMD_ARG_TGT_ARCH -notin @('x64','amd64')) { throw 'Enter the x64 MSVC developer environment before building the TLS runtime.' }
# Select native Strawberry Perl explicitly; MSYS/Git Perl must not change the
# recipe. NASM is prepared from a pinned official ZIP, not assumed preinstalled.
foreach ($directory in @('C:/Strawberry/perl/bin')) {
    if (Test-Path -LiteralPath $directory -PathType Container) { $env:PATH=$directory+';'+$env:PATH }
}
$perl=(Get-Command perl.exe -ErrorAction Stop).Source
$perlKind=(& $perl -e 'print $^O').Trim()
if ($LASTEXITCODE -ne 0 -or $perlKind -ne 'MSWin32') { throw 'The TLS runtime requires native Windows Perl for VC-WIN64A.' }
$env:PERL=$perl
$nasm=& (Join-Path $PSScriptRoot 'Prepare-Nasm.ps1') -OutputDirectory ($OutputDirectory+'-tools/nasm')
$env:PATH=[IO.Path]::GetDirectoryName($nasm)+';'+$env:PATH
$tools=@('cl.exe','nmake.exe','nasm.exe','perl.exe') | ForEach-Object {
    $path=(Get-Command $_ -ErrorAction Stop).Source
    [ordered]@{name=$_;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$identity=$tools | ConvertTo-Json -Compress
$digest=[Security.Cryptography.SHA256]::Create()
try { $key=([BitConverter]::ToString($digest.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity)))).Replace('-','').ToLowerInvariant() }
finally { $digest.Dispose() }
if ($GitHubEnvironment) {
    if (-not $env:GITHUB_ENV -or -not $env:GITHUB_PATH -or -not $env:GITHUB_OUTPUT) { throw 'GitHub environment files are unavailable.' }
    foreach ($directory in @([IO.Path]::GetDirectoryName($perl),[IO.Path]::GetDirectoryName((Get-Command nasm.exe).Source))) {
        $directory >> $env:GITHUB_PATH
    }
    "PERL=$perl" >> $env:GITHUB_ENV
    "identity=$key" >> $env:GITHUB_OUTPUT
}
if ($PrepareOnly) { Write-Host "Verified native TLS build tools: $key"; return }
& python (Join-Path $repo 'tools/Build-OpenSslRuntime.py') --output $OutputDirectory --target VC-WIN64A
if ($LASTEXITCODE -ne 0) { throw 'Pinned OpenSSL source build or cache verification failed.' }
$runtime=(Resolve-Path -LiteralPath $OutputDirectory).Path
if ($GitHubEnvironment) { "SWIRL_OPENSSL_ROOT=$runtime" >> $env:GITHUB_ENV }
Write-Host "Verified OpenSSL runtime: $runtime"
