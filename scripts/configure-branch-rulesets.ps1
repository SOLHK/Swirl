<#
.SYNOPSIS
  为 SOLHK/Swirl 创建正式版 main 和测试版 test 的 GitHub Rulesets。
.DESCRIPTION
  默认仅预览，不会更改 GitHub 设置。需在拥有仓库管理员权限的设备上
  使用 gh auth login 登录，显式传入 -Apply 才会创建规则。
  不会推送源码、合并 PR 或发布 Release。
.EXAMPLE
  pwsh -File scripts/configure-branch-rulesets.ps1
  pwsh -File scripts/configure-branch-rulesets.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository = 'SOLHK/Swirl'
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw '请先安装 GitHub CLI（https://cli.github.com/），再执行 gh auth login。'
}

& gh auth status 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    throw '当前 GitHub CLI 尚未登录，请执行 gh auth login。'
}

function Invoke-GitHubApi {
    param(
        [Parameter(Mandatory)][string]$Endpoint,
        [ValidateSet('GET', 'POST', 'PUT')][string]$Method = 'GET',
        [object]$Payload
    )
    $temporaryFile = $null
    try {
        if ($null -ne $Payload) {
            $temporaryFile = Join-Path ([System.IO.Path]::GetTempPath()) ("swirl-ruleset-" + [Guid]::NewGuid().ToString('N') + ".json")
            $json = ConvertTo-Json -InputObject $Payload -Depth 24 -Compress
            [System.IO.File]::WriteAllText($temporaryFile, $json, [System.Text.UTF8Encoding]::new($false))
            $output = & gh api --method $Method -H 'Accept: application/vnd.github+json' --input $temporaryFile $Endpoint
        } else {
            $output = & gh api --method $Method -H 'Accept: application/vnd.github+json' $Endpoint
        }
        if ($LASTEXITCODE -ne 0) { throw "GitHub API $Method $Endpoint 执行失败。请检查管理员权限。" }
        return ($output -join "`n") | ConvertFrom-Json
    } finally {
        if ($temporaryFile -and (Test-Path $temporaryFile)) {
            Remove-Item -LiteralPath $temporaryFile -Force
        }
    }
}

function New-SwirlRuleset {
    param([ValidateSet('main','test')][string]$Branch)
    $checks = @(
        @{ context = 'build' },
        @{ context = 'build-qt-ui' }
    )
    if ($Branch -eq 'main') {
        $checks += @{ context = 'production-gate' }
    }
    return @{
        name        = "Swirl protect $Branch"
        target      = 'branch'
        enforcement = 'active'
        bypass_actors = @()
        conditions  = @{
            ref_name = @{
                include = @("refs/heads/$Branch")
                exclude = @()
            }
        }
        rules = @(
            @{ type = 'deletion' },
            @{ type = 'non_fast_forward' },
            @{
                type = 'pull_request'
                parameters = @{
                    allowed_merge_methods = @('merge', 'squash', 'rebase')
                    dismiss_stale_reviews_on_push = $true
                    require_code_owner_review = $false
                    require_last_push_approval = $false
                    required_approving_review_count = 0
                    required_review_thread_resolution = $true
                }
            },
            @{
                type = 'required_status_checks'
                parameters = @{
                    strict_required_status_checks_policy = $true
                    do_not_enforce_on_create = $false
                    required_status_checks = $checks
                }
            }
        )
    }
}

Write-Host "目标仓库：$Repository" -ForegroundColor Cyan
Write-Host '正式版：必须通过 PR，且 build / build-qt-ui / production-gate 全部成功。'
Write-Host '测试版：必须通过 PR，且 build / build-qt-ui 全部成功。'
Write-Host '规则同时禁止删除和强制推送，不设置任何 bypass 账号。'
Write-Host '注意：GitHub 限制不能凭空验证用户是否说过“推送正式版”；production-gate 的 release-approved 仍需仓库所有者人工授权。'
$existing = @(Invoke-GitHubApi -Endpoint "/repos/$Repository/rulesets")
foreach ($branch in @('main','test')) {
    $desired = New-SwirlRuleset -Branch $branch
    $present = @($existing | Where-Object { $_.name -eq $desired.name })
    if ($present.Count -gt 0) {
        Write-Host "已存在规则：$($desired.name) [id=$($present[0].id)]，为避免覆盖现有管理员设置，本脚本不修改。" -ForegroundColor Yellow
        continue
    }
    if (-not $Apply) {
        Write-Host "【预览】将创建 ACTIVE 规则：$($desired.name)" -ForegroundColor Yellow
        continue
    }
    $created = Invoke-GitHubApi -Endpoint "/repos/$Repository/rulesets" -Method POST -Payload $desired
    Write-Host "已创建规则：$($created.name) [id=$($created.id)]" -ForegroundColor Green
}
if (-not $Apply) {
    Write-Host ''
    Write-Host '未对 GitHub 作任何变更。确认规则后，添加 -Apply 才会创建。' -ForegroundColor Yellow
}
Write-Host "核对页面：https://github.com/$Repository/settings/rules"
