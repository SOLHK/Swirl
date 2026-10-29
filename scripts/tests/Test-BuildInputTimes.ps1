Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../BuildInputTimes.ps1')
$base=[IO.Path]::GetFullPath('D:/Codex/tmp')
$root=Join-Path $base ('swirl-build-input-test-'+[guid]::NewGuid().ToString('N'))
$repo=Join-Path $root 'repo'
$cache=Join-Path $root 'cache'
New-Item -ItemType Directory -Path $repo,$cache -Force | Out-Null
function Assert([bool]$Value,[string]$Message) { if (-not $Value) { throw $Message } }
try {
    & git -C $repo init --quiet
    if ($LASTEXITCODE) { throw 'Fixture git init failed.' }
    $stable=Join-Path $repo 'unchanged.cpp'
    $changed=Join-Path $repo 'changed.cpp'
    $untracked=Join-Path $repo 'untracked.cpp'
    [IO.File]::WriteAllText($stable,'unchanged source')
    [IO.File]::WriteAllText($changed,'old source')
    & git -C $repo add -- unchanged.cpp changed.cpp
    if ($LASTEXITCODE) { throw 'Fixture staging failed.' }
    $saved=[DateTime]::SpecifyKind([DateTime]'2020-01-01',[DateTimeKind]::Utc)
    $fresh=$saved.AddDays(1)
    [IO.File]::SetLastWriteTimeUtc($stable,$saved)
    [IO.File]::SetLastWriteTimeUtc($changed,$saved)
    $null=Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $cache
    [IO.File]::SetLastWriteTimeUtc($stable,$fresh)
    [IO.File]::WriteAllText($changed,'new source')
    [IO.File]::SetLastWriteTimeUtc($changed,$fresh)
    [IO.File]::WriteAllText($untracked,'user file')
    [IO.File]::SetLastWriteTimeUtc($untracked,$fresh)
    # A cache entry for an untracked file cannot expand the current allowlist.
    $manifest=Join-Path $cache 'swirl-input-times.json'
    $data=Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
    $data.files+=@{path='untracked.cpp';sha256=(Get-FileHash $untracked).Hash;utc=$saved.ToString('o')}
    $data | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding utf8
    $count=Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $cache -Restore
    Assert ($count -eq 1) 'Only unchanged tracked input may reuse its timestamp.'
    Assert ([IO.File]::GetLastWriteTimeUtc($stable) -eq $saved) 'Unchanged input cache was missed.'
    Assert ([IO.File]::GetLastWriteTimeUtc($changed) -eq $fresh) 'Changed source incorrectly reused an old timestamp.'
    Assert ([IO.File]::GetLastWriteTimeUtc($untracked) -eq $fresh) 'Untracked user file was modified.'
    Assert ([IO.File]::ReadAllText($changed) -ceq 'new source') 'Source contents changed.'
    $data.source_root='different-root'
    $data | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifest -Encoding utf8
    $rejected=$false
    try { $null=Sync-SwirlBuildInputTimes -RepositoryRoot $repo -BuildDirectory $cache -Restore } catch { $rejected=$true }
    Assert $rejected 'Foreign-checkout cache was accepted.'
    Write-Output 'Build input cache: 6 checks passed; changed source and untracked files preserved.'
} finally {
    $resolved=[IO.Path]::GetFullPath($root)
    if (-not $resolved.StartsWith($base+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe fixture cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
