param(
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][string]$ReferenceExecutable,
    [Parameter(Mandatory)][string]$EvidenceDirectory,
    [string]$RepositoryRoot = '.',
    [switch]$RestoreOriginalGeneratedQtMetadata
)

$ErrorActionPreference = 'Stop'
$sourceSha = '7015f1744117a8e144b7bce03c413c5c7bf990b6'
$headSha = '3d0b2b4593bc83a6372f0a0628cb06e6aa55b327'
$runId = 42819555991
$artifactId = 13771546754
$archiveSha = '43a9954947b41d16d27ccb92d02051b51fa0e93d1a7fb36c4cb12b3397b7f8a7'
$exeSha = '0a888fbd933ecb86c4c1acf24e6b526f9e729120ae8ecd7205e1cddea68c08cf'
$qmlSha = '66d291c47770c366627cfd68f3e050e30dbb6f1747639f32c6ea812803ad1cb3'
$rustSha = 'a7924d6d64e12a94344693281c669a2bfbec75368fa813e8d0aa571dea04cae6'
$api = 'https://api.github.com/repos/SOLHK/Swirl'

function Get-Sha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-Json([string]$Path) {
    Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
}

function New-PathIndex($Rows) {
    $index = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach ($row in $Rows) { $index.Add($row.path, $row) }
    return ,$index
}

function Assert-UnlinkedPath([string]$Path) {
    for ($part = $Path; $part; $part = [IO.Path]::GetDirectoryName($part.TrimEnd('\','/'))) {
        if ((Get-Item -LiteralPath $part -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked recovered runtime path.' }
    }
}

function Get-RuntimeTree([string]$Root) {
    foreach ($item in (Get-ChildItem -LiteralPath $Root -Force -Recurse | Sort-Object FullName)) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked entry in recovered runtime.' }
        if (!$item.PSIsContainer) {
            [ordered]@{
                path = [IO.Path]::GetRelativePath($Root, $item.FullName).Replace('\','/')
                bytes = $item.Length
                sha256 = Get-Sha256 $item.FullName
            }
        }
    }
}

$runtime = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$reference = (Resolve-Path -LiteralPath $ReferenceExecutable).Path
if ((git -C $RepositoryRoot rev-parse HEAD).Trim() -cne $sourceSha -or $LASTEXITCODE -ne 0) { throw 'Wrong recovery checkout.' }
if ((Get-Sha256 $reference) -cne $exeSha) { throw 'Cached Release reference EXE differs from the failed run.' }
Assert-UnlinkedPath $runtime
$evidence = [IO.Path]::GetFullPath($EvidenceDirectory).TrimEnd('\','/')
if ($evidence.Equals($runtime, [StringComparison]::OrdinalIgnoreCase) -or
    $evidence.StartsWith($runtime + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
    (Test-Path -LiteralPath $evidence)) { throw 'Recovery evidence requires a fresh path outside the runtime.' }
New-Item -ItemType Directory -Path $evidence | Out-Null

$token = $env:SWIRL_ARTIFACT_READ_TOKEN
if (!$token) { throw 'The isolated runner requires an Actions artifact read token.' }
$headers = @{ Authorization = "Bearer $token"; Accept = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
$metadata = Invoke-RestMethod -Headers $headers -Uri "$api/actions/artifacts/$artifactId"
if ($metadata.id -ne $artifactId -or $metadata.name -cne 'Swirl-Qt612-Package-Evidence' -or $metadata.expired -or
    $metadata.workflow_run.id -ne $runId -or $metadata.workflow_run.head_sha -cne $headSha -or
    $metadata.size_in_bytes -ne 125663022 -or $metadata.digest -cne "sha256:$archiveSha") {
    throw 'Original package evidence API identity differs from the pinned run.'
}
$archivePath = Join-Path ([IO.Path]::GetTempPath()) ('swirl-pr61-package-evidence-' + [guid]::NewGuid() + '.zip')
$handler = [Net.Http.HttpClientHandler]::new()
$handler.AllowAutoRedirect = $false
$client = [Net.Http.HttpClient]::new($handler)
$client.DefaultRequestHeaders.UserAgent.ParseAdd('Swirl-PR61-Recovery/1.0')
$request = [Net.Http.HttpRequestMessage]::new('GET', "$api/actions/artifacts/$artifactId/zip")
$request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $token)
try {
    $redirect = $client.SendAsync($request, 'ResponseHeadersRead').GetAwaiter().GetResult()
    $location = $redirect.Headers.Location
    if ($redirect.StatusCode -ne 302 -or !$location.IsAbsoluteUri -or $location.Scheme -cne 'https') { throw 'Artifact download did not return an HTTPS redirect.' }
    $download = $client.GetAsync($location, 'ResponseHeadersRead').GetAwaiter().GetResult()
    if (!$download.IsSuccessStatusCode) { throw "Artifact storage returned HTTP $([int]$download.StatusCode)." }
    $stream = [IO.File]::Create($archivePath)
    try { $download.Content.CopyToAsync($stream).GetAwaiter().GetResult() | Out-Null } finally { $stream.Dispose() }
} finally {
    $request.Dispose()
    $client.Dispose()
}
if ((Get-Item -LiteralPath $archivePath).Length -ne $metadata.size_in_bytes -or (Get-Sha256 $archivePath) -cne $archiveSha) {
    throw 'Downloaded original artifact size or hash differs.'
}
$members = [ordered]@{
    'build-evidence/full-motion-release/receipt.json' = 'original-release-receipt.json'
    'build-evidence/full-motion-release/runtime-before.json' = 'original-runtime-before.json'
    'build-evidence/full-motion-release/runtime-after.json' = 'original-runtime-after.json'
    'build-evidence/full-motion-release/rapid/Swirl-diagnostics.txt' = 'original-rapid.log'
    'build-evidence/full-motion-release/ready/Swirl-diagnostics.txt' = 'original-ready.log'
    'installer-bin/package-manifest.json' = 'original-package-manifest.json'
    'out/package-evidence/production-rust-self-test.json' = 'original-rust-self-test.json'
    'build-evidence/qt-product-release-deployment/copy-d3d/receipt.json' = 'original-shader-copy-receipt.json'
    'out/qt-corresponding-source/qt-source-bundle.json' = 'original-qt-source-bundle.json'
}
$archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($member in $members.GetEnumerator()) {
        $entry = $archive.GetEntry($member.Key)
        if (!$entry) { throw "Original artifact entry is missing: $($member.Key)." }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $evidence $member.Value))
    }
} finally { $archive.Dispose() }
[IO.File]::Delete($archivePath)

$original = Read-Json (Join-Path $evidence 'original-release-receipt.json')
$originalBefore = @(Read-Json (Join-Path $evidence 'original-runtime-before.json'))
$originalAfter = @(Read-Json (Join-Path $evidence 'original-runtime-after.json'))
$expected = New-PathIndex $originalBefore
if ($original.run_id -ne $runId -or $original.run_attempt -ne 1 -or $original.source_sha -cne $sourceSha -or
    $original.pr_head_sha -cne $headSha -or $original.expected_flavor -cne 'release' -or !$original.original_runtime_unchanged -or
    $original.exe_sha256 -cne $exeSha -or $original.reference_exe_sha256 -cne $exeSha -or
    $original.rust_api_sha256 -cne $rustSha -or $expected['Swirl.exe'].sha256 -cne $exeSha -or
    $expected['Qt6Qml.dll'].sha256 -cne $qmlSha -or $expected['swirl_api.dll'].sha256 -cne $rustSha -or
    (ConvertTo-Json -InputObject $originalBefore -Compress) -cne (ConvertTo-Json -InputObject $originalAfter -Compress)) {
    throw 'Original failed-run receipt and runtime inventories disagree.'
}
foreach ($mode in @('rapid','ready')) {
    $case = @($original.cases | Where-Object mode -CEQ $mode)
    if ($case.Count -ne 1 -or (Get-Sha256 (Join-Path $evidence "original-$mode.log")) -cne $case[0].log_sha256) {
        throw "Original $mode log and receipt disagree."
    }
}
$oldManifestPath = Join-Path $evidence 'original-package-manifest.json'
if ((Get-Sha256 $oldManifestPath) -cne $expected['package-manifest.json'].sha256 -or
    (Get-Sha256 (Join-Path $evidence 'original-rust-self-test.json')) -cne $expected['rust-self-test.json'].sha256) {
    throw 'Original manifest or Rust self-test report differs from its runtime entry.'
}
$oldManifest = Read-Json $oldManifestPath
$newManifestPath = Join-Path $runtime 'package-manifest.json'
Assert-UnlinkedPath $newManifestPath
$newManifest = Read-Json $newManifestPath
if ($RestoreOriginalGeneratedQtMetadata) {
    # Old source notices were regenerated from verified source archives. Restore
    # only the original archive-reference and shader metadata documents. The
    # selected SDK, executable and DLLs are still verified byte-for-byte below.
    @'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
shader_copy = json.loads((out / 'original-shader-copy-receipt.json').read_text(encoding='utf-8-sig'))
source = json.loads((out / 'original-qt-source-bundle.json').read_text(encoding='utf-8-sig'))
note = {key: source[key] for key in ('schema', 'source_sha', 'qt_version', 'archive', 'runtime_content_id',
                                    'runtime_modules', 'build_only_modules')}
note['qtdeclarative_source_commit'] = source['patched_qml']['source_commit']
note['patch_commit'] = source['patched_qml']['commit']
note['delivery'] = ('Provide this complete source archive together with the installer. '
                    'CI artifact retention is temporary and is not a long-term source offer.')
for name, obj, sorted_keys in (
    ('restored-shader-metadata.json', shader_copy['runtime_shader_metadata']['document'], False),
    ('restored-source-note.json', note, True),
):
    raw = json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=sorted_keys) + '\n'
    (out / name).write_bytes(raw.encode())
'@ | python - $evidence
    if ($LASTEXITCODE -ne 0) { throw 'Could not reconstruct original generated Qt metadata.' }
    $metadataFiles = [ordered]@{
        'qt-shader-runtime.json' = 'restored-shader-metadata.json'
        'licenses/qt/SOURCE-BUNDLE.json' = 'restored-source-note.json'
    }
    $restorations = foreach ($item in $metadataFiles.GetEnumerator()) {
        $target = Join-Path $runtime $item.Key
        $replacement = Join-Path $evidence $item.Value
        Assert-UnlinkedPath $target
        $oldSha = Get-Sha256 $target
        $newSha = Get-Sha256 $replacement
        $entry = @($newManifest.files | Where-Object path -CEQ $item.Key)
        if ($entry.Count -ne 1 -or $entry[0].sha256 -cne $oldSha -or $expected[$item.Key].sha256 -cne $newSha -or
            (Get-Item -LiteralPath $replacement).Length -ne $expected[$item.Key].bytes) {
            throw "Generated Qt metadata does not match its recovered and original manifests: $($item.Key)."
        }
        if ($oldSha -cne $newSha) {
            [IO.File]::Copy($replacement, $target, $true)
            $entry[0].sha256 = $newSha
        }
        [ordered]@{ path = $item.Key; staged_sha256 = $oldSha; original_sha256 = $newSha; bytes_restored = ($oldSha -cne $newSha) }
    }
    if (@($restorations | Where-Object bytes_restored).Count) {
        ConvertTo-Json -InputObject $newManifest -Depth 12 | Set-Content -LiteralPath $newManifestPath -Encoding utf8
    }
    ConvertTo-Json -InputObject @($restorations) | Set-Content -LiteralPath (Join-Path $evidence 'restored-qt-metadata.json') -Encoding utf8
}
$recovered = @(Get-RuntimeTree $runtime)
$actual = New-PathIndex $recovered
ConvertTo-Json -InputObject $recovered -Depth 4 | Set-Content -LiteralPath (Join-Path $evidence 'recovered-runtime-before.json') -Encoding utf8

$rawDifferences = foreach ($name in (@($expected.Keys) + @($actual.Keys) | Sort-Object -CaseSensitive -Unique)) {
    $before = $expected[$name]
    $after = $actual[$name]
    if (!$before -or !$after -or $before.sha256 -cne $after.sha256 -or $before.bytes -ne $after.bytes) {
        # No executable, library, script, QML resource, configuration or data is exempt.
        $allowed = ($name -ceq 'Swirl-diagnostics.txt' -and !$after) -or
            ($name -cin @('package-manifest.json','rust-self-test.json') -and $before -and $after)
        [ordered]@{ path = $name; original = $before; recovered = $after; allowed_metadata = [bool]$allowed }
    }
}
ConvertTo-Json -InputObject @($rawDifferences) -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'raw-differences.json') -Encoding utf8
if (@($rawDifferences | Where-Object { !$_.allowed_metadata }).Count) { throw 'Recovered runtime has forbidden differences. See raw-differences.json.' }

$oldFiles = New-PathIndex $oldManifest.files
$newFiles = New-PathIndex $newManifest.files
if ($oldManifest.source_sha -cne $sourceSha -or $newManifest.source_sha -cne $sourceSha -or
    $oldManifest.schema -ne 1 -or $newManifest.schema -ne 1 -or
    (ConvertTo-Json -InputObject $oldManifest.rust -Compress) -cne (ConvertTo-Json -InputObject $newManifest.rust -Compress) -or
    $oldFiles.Count -ne $expected.Count - 2 -or $newFiles.Count -ne $oldFiles.Count) {
    throw 'Recovered package manifest lost source, Rust identity or package inventory.'
}
foreach ($name in $oldFiles.Keys) {
    if ($name -cin @('package-manifest.json','Swirl-diagnostics.txt') -or !$newFiles.ContainsKey($name) -or
        $oldFiles[$name].sha256 -cne $expected[$name].sha256 -or $newFiles[$name].sha256 -cne $actual[$name].sha256) {
        throw "Package manifest does not bind original and recovered bytes: $name."
    }
}
$selfTest = Read-Json (Join-Path $runtime 'rust-self-test.json')
if (!$selfTest.success -or !$selfTest.http_response_verified -or !$selfTest.socks5_response_verified -or
    !$selfTest.connect_response_verified -or !$selfTest.listener_released) { throw 'Recovered Rust self-test report lacks a mandatory success marker.' }

[ordered]@{
    schema = 1; admitted = $true; run_id = $runId; attempt = 1; artifact_id = $artifactId; archive_sha256 = $archiveSha
    source_sha = $sourceSha; pr_head_sha = $headSha; exe_sha256 = $exeSha; qml_dll_sha256 = $qmlSha; rust_dll_sha256 = $rustSha
    original_file_count = $expected.Count; recovered_file_count = $actual.Count; raw_difference_count = @($rawDifferences).Count
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidence 'admission.json') -Encoding utf8
