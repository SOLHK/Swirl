# Ninja uses timestamps; only restore old input times after content verification.
function Sync-SwirlBuildInputTimes {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$BuildDirectory,
        [switch]$Restore
    )
    $manifestPath = Join-Path $BuildDirectory 'swirl-input-times.json'
    $previous = @{}
    if ($Restore -and (Test-Path -LiteralPath $manifestPath)) {
        $saved = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        if ($saved.source_root -cne $RepositoryRoot) { throw 'Cached source timestamps belong to another checkout.' }
        foreach ($entry in $saved.files) { $previous[[string]$entry.path] = $entry }
    }
    $entries = @()
    $restored = 0
    # Current git-tracked paths are the allowlist. Cache data cannot nominate
    # other paths; changed contents, untracked files and links are never reused.
    $tracked = @(& git -C $RepositoryRoot ls-files)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate tracked build inputs.' }
    foreach ($relative in $tracked) {
        $path = Join-Path $RepositoryRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
        $file = Get-Item -LiteralPath $path
        if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Linked source inputs cannot reuse cached timestamps.' }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
        if ($Restore -and $previous.ContainsKey($relative) -and $previous[$relative].sha256 -ceq $hash) {
            $file.LastWriteTimeUtc = [DateTime]::Parse($previous[$relative].utc,[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind)
            $restored++
        }
        if (-not $Restore) { $entries += @{path=$relative; sha256=$hash; utc=$file.LastWriteTimeUtc.ToString('o')} }
    }
    if (-not $Restore) {
        New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
        @{source_root=$RepositoryRoot; files=$entries} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
    }
    return $restored
}
