function Assert-SwirlBuildSource {
    param(
        [Parameter(Mandatory)][string]$RepositoryRoot,
        [Parameter(Mandatory)][string]$ExpectedSourceSha
    )
    $actual = (& git -C $RepositoryRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -cne $ExpectedSourceSha) { throw 'Source HEAD changed during the build.' }
    & git -C $RepositoryRoot diff --quiet HEAD --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked source changed during the build.' }
    $untracked = @(& git -C $RepositoryRoot ls-files --others --exclude-standard -- src core scripts tools .github)
    if ($LASTEXITCODE -ne 0 -or $untracked.Count -ne 0) { throw 'Untracked build inputs prevent exact-source packaging.' }
}
