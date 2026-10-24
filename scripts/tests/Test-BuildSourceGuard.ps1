Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../Assert-BuildSource.ps1')
$base=[IO.Path]::GetFullPath('D:/Codex/tmp')
$root=Join-Path $base ('swirl-build-source-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $root 'src') -Force | Out-Null
function Expect-Rejection([string]$Sha,[string]$Message) {
    $rejected=$false
    try { Assert-SwirlBuildSource -RepositoryRoot $root -ExpectedSourceSha $Sha } catch { $rejected=$true }
    if (-not $rejected) { throw $Message }
}
try {
    & git -C $root init --quiet
    [IO.File]::WriteAllText((Join-Path $root 'src/source.cpp'),'first source')
    [IO.File]::WriteAllText((Join-Path $root '.gitignore'),'work/')
    & git -C $root add -- .
    & git -C $root -c user.name=Fixture -c user.email=fixture@example.invalid commit --quiet -m fixture
    if ($LASTEXITCODE) { throw 'Fixture commit failed.' }
    $sha=(& git -C $root rev-parse HEAD).Trim()
    Assert-SwirlBuildSource -RepositoryRoot $root -ExpectedSourceSha $sha
    $new=Join-Path $root 'src/new-header.h'
    [IO.File]::WriteAllText($new,'untracked input')
    Expect-Rejection $sha 'Untracked build input was accepted.'
    Remove-Item -LiteralPath $new
    [IO.File]::WriteAllText((Join-Path $root 'src/source.cpp'),'changed source')
    Expect-Rejection $sha 'Modified tracked source was accepted.'
    & git -C $root add -- src/source.cpp
    Expect-Rejection $sha 'Staged source modification was accepted.'
    & git -C $root -c user.name=Fixture -c user.email=fixture@example.invalid commit --quiet -m changed
    if ($LASTEXITCODE) { throw 'Fixture second commit failed.' }
    Expect-Rejection $sha 'Changed HEAD was accepted.'
    $current=(& git -C $root rev-parse HEAD).Trim()
    New-Item -ItemType Directory -Path (Join-Path $root 'work') | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'work/build.log'),'ignored output')
    Assert-SwirlBuildSource -RepositoryRoot $root -ExpectedSourceSha $current
    Write-Output 'Build source guard: 6 checks passed; untracked, staged, modified and changed-HEAD inputs rejected.'
} finally {
    $resolved=[IO.Path]::GetFullPath($root)
    if (-not $resolved.StartsWith($base+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe fixture cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
