# Shared by production staging and independent package-policy regression tests.
# Historical license text is not an executable core; the exception is exact and
# directory-scoped, never a blanket exclusion of the licenses directory.
function Test-SwirlForbiddenProductPath {
    param([Parameter(Mandatory=$true)][string]$RelativePath)
    $path = $RelativePath.Replace('\','/')
    $name = ($path -split '/')[-1]
    if ($path -ieq 'licenses/mihomo-GPL-3.0.txt') { return $false }
    return ($name -match '^(mihomo|clash|xray|sing-box)([.-]|$)' -or
        $name -match '(Tests|Fixture)\.(exe|dll)$' -or
        $name -match '^swirl_loader_fixture_[0-9]+\.(dll|so|dylib)$' -or
        $name -match '\.(private|dpapi)$')
}

function Get-SwirlForbiddenProductFiles {
    param([Parameter(Mandatory=$true)][string]$ApplicationDirectory)
    $root = (Resolve-Path -LiteralPath $ApplicationDirectory -ErrorAction Stop).Path.TrimEnd('\','/')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'Product directory is not a directory.' }
    foreach ($file in (Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction Stop)) {
        $relative = $file.FullName.Substring($root.Length + 1).Replace('\','/')
        if (Test-SwirlForbiddenProductPath -RelativePath $relative) { $relative }
    }
}
