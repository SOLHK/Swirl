# 智能字体系统：Windows 实机交接

当前 W1-B 智能宽度交接使用 **`work/vf-smart-width-w1`**，没有合并到
`work/core-completion-20261017`。准确的验收提交、Windows CI 通过/失败/跳过
数量、量化问题修正和未完成清单见
[W1-B 验证记录](FONT_SMART_WIDTH_W1B_VALIDATION.md)。以前集成分支的测试
与 Core 独立状态仍保留在 [历史验证记录](FONT_AUTOMATION_VALIDATION.md)，
不能用旧提交的成功替代本次 W1-B 实机检查。

云端没有访问或更新你的 `D:\Codex`，字体 CI 的证据包也不包含安装包。
以下命令须在 Windows 本机执行；本文件本身不是已经执行过的实机报告。
源码、隔离构建和本轮输出均保存在 `D:\Codex`，原始 TTC 保持不变。

## 1. 确认现有源码、工具链和 EXE

在 `D:\Codex` 内的 W1 专用 Swirl 仓库根目录打开 PowerShell，检查：

```powershell
git branch --show-current
git status --short
git rev-parse HEAD
```

分支必须是上面的 W1 专用分支；有未提交修改时先保留它们，不使用强制重置。
若源码尚未更新，在该分支的干净工作区执行
`git pull --ff-only origin work/vf-smart-width-w1`，并重新记录完整 SHA。
后续新提交的 CI 结论须与其实际 SHA 对应。
若另一个窗口正在使用集成分支，不切换或覆盖那个工作区；可在尚不存在的
独立目录执行 `git clone --branch work/vf-smart-width-w1 https://github.com/SOLHK/Swirl.git D:\Codex\Swirl-W1B`。
目录已存在时先检查其中的分支、HEAD 和未提交修改，不重复克隆到已有目录。

W1 本机检查优先覆盖受约束单行按钮/导航、下拉框、列表/卡片名称、表头、
对话框及窗口标题；同时观察正文、输入和数值显示仍保持原排版。宽度不足
但已到安全压缩限度时，应继续使用该组件原有的省略规则。专门打开 Gateway
菜单并连续 resize；该 popup 的具体开关状态不在 W1-B 针对性 QML 测试内。
保留自动/手动切换、换字体、同窗实际 DPI 变化和弹窗反复开关的原始观察。

已有同一源码的可运行测试构建时可直接进入第 2 步。需要重建时，使用现有
Qt **6.10.3 的 MSVC 2022 x64 SDK**、VS 2022 C++ 工具链和 CMake；
不要将 MinGW Qt 与 MSVC 混用。在能调用这些现有工具的 PowerShell 中运行：

```powershell
$ErrorActionPreference = 'Stop'
if ((& qmake.exe -query QT_VERSION).Trim() -ne '6.10.3') { throw 'Qt 版本不匹配' }
if ((& qmake.exe -query QMAKE_XSPEC).Trim() -ne 'win32-msvc') { throw '需要 MSVC Qt SDK' }
$swirlQt = (& qmake.exe -query QT_INSTALL_PREFIX).Trim()
$swirlSource = [IO.Path]::GetFullPath((git rev-parse --show-toplevel).Trim())
$swirlRevision = (git rev-parse HEAD).Trim()
$swirlBuild = Join-Path 'D:\Codex' ('Swirl-font-build-' + $swirlRevision.Substring(0, 12))
New-Item -ItemType Directory -Path "$swirlBuild\tmp" -Force | Out-Null
$env:TEMP = $env:TMP = $env:TMPDIR = "$swirlBuild\tmp"
cmake -S "$swirlSource\src\Swirl.Quick" -B $swirlBuild `
    -G 'Visual Studio 17 2022' -A x64 "-DCMAKE_PREFIX_PATH=$swirlQt" `
    -DSWIRL_BUILD_UI_TESTS=ON -DSWIRL_USE_RUST_CORE=OFF
if ($LASTEXITCODE -ne 0) { throw 'CMake 配置失败，保留原错误' }
Get-Content (Join-Path $swirlBuild 'font-toolchain.txt')
cmake --build $swirlBuild --config Release --parallel 2 `
    --target Swirl SwirlFontTests SwirlFontAxisPolicyTests
if ($LASTEXITCODE -ne 0) { throw '实际编译失败' }
$swirlBuiltExe = Join-Path $swirlBuild 'Release\Swirl.exe'
& "$swirlQt\bin\windeployqt.exe" --release --qmldir "$swirlSource\src\Swirl.Quick\qml" $swirlBuiltExe
if ($LASTEXITCODE -ne 0) { throw 'Qt 运行时部署失败' }
$swirlRevision | Set-Content (Join-Path $swirlBuild 'source-commit.txt') -Encoding UTF8
Write-Host "本次构建的 EXE：$swirlBuiltExe"
```

检查 `font-toolchain.txt` 实际为 Qt 6.10.3、MSVC、x64。该独立构建采用
项目默认兼容内核，与字体 CI 一致；它不覆盖已有安装目录或替代 Rust Core
产品验收。无需新建 CI 或配置 App/Secrets。若缺少本机工具，不能把云端
安装成功当成本机已安装。

GUI 输入和帧测试必须编译了 `SWIRL_BUILD_UI_TESTS=ON`。首次打开后在
**设置 → 关于**核对版本末尾的短提交号；此值来自构建时的 Git HEAD。
Windows 文件属性中的固定 `1.0.0.0` 不能证明 EXE 对应哪个源码提交。
GUI 测试入口返回 4 时，应先检查是否缺少上述测试编译选项。

## 2. 填写两个真实路径，准备每轮独立目录

下面只需输入现有 EXE 和合法本机 TTC 的真实路径；路径可以包含空格。
EXE 须位于 `D:\Codex`，因为应用也会在 EXE 旁写诊断文件。
私有基准使用原有 **PingFang UI SC** 三轴 TTC，须确实具备原测试要求的
`wght`、`wdth`、`HGHT` 及其范围；普通 TTF 或其他语义的可变字体不适用
这些私有夹具断言。TTC、隔离状态目录和原始私有图像只留本机，不上传 GitHub。

```powershell
$ErrorActionPreference = 'Stop'
$swirlExe = (Resolve-Path -LiteralPath (Read-Host '现有 Swirl.exe 的完整路径')).Path
$swirlTtc = (Resolve-Path -LiteralPath (Read-Host '合法本机三轴 TTC 的完整路径')).Path
if (!(Test-Path -LiteralPath $swirlExe -PathType Leaf) -or
    !$swirlExe.StartsWith('D:\Codex\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '需要 D:\Codex 内的真实 EXE 文件'
}
if (!(Test-Path -LiteralPath $swirlTtc -PathType Leaf)) { throw 'TTC 文件不存在' }

# 仅清除本 PowerShell 会话的测试覆盖，实际缩放和刷新率由 Windows 设置。
$swirlOverrides = @('QT_QUICK_BACKEND', 'QT_SCALE_FACTOR', 'QT_SCREEN_SCALE_FACTORS',
    'QT_FONT_DPI', 'QT_ENABLE_HIGHDPI_SCALING', 'QT_AUTO_SCREEN_SCALE_FACTOR',
    'QT_USE_PHYSICAL_DPI', 'QT_SCALE_FACTOR_ROUNDING_POLICY',
    'QSG_RHI_PREFER_SOFTWARE_RENDERER', 'QSG_RENDER_LOOP', 'QSG_NO_VSYNC')
foreach ($name in $swirlOverrides) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
Get-ChildItem Env: | Where-Object Name -like 'SWIRL_QUALITY_*' | Remove-Item
$env:QT_QPA_PLATFORM = 'windows:fontengine=freetype'
$env:QSG_RHI_BACKEND = 'd3d11'
$env:QSG_INFO = '1'

function New-SwirlFontRun([string]$kind) {
    $stamp = (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
    $run = Join-Path 'D:\Codex\font-evidence' "$kind-$stamp"
    foreach ($part in @('state', 'tmp', 'cache')) {
        New-Item -ItemType Directory -Path (Join-Path $run $part) -Force | Out-Null
    }
    $env:SWIRL_TEST_ROOT = Join-Path $run 'state' # 必须先创建，且为绝对本地目录
    $env:TEMP = $env:TMP = $env:TMPDIR = Join-Path $run 'tmp'
    $env:QML_DISK_CACHE_PATH = Join-Path $run 'cache'
    $env:QSG_RHI_DISABLE_DISK_CACHE = '1'
    $env:QSG_RHI_PIPELINE_CACHE_SAVE = Join-Path $run 'cache\pipeline.bin'
    Remove-Item Env:QSG_RHI_PIPELINE_CACHE_LOAD -ErrorAction SilentlyContinue
    return $run
}
function Invoke-SwirlFontRun([string]$program, [string[]]$swirlArguments) {
    $started = [DateTime]::UtcNow
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    # Start-Process 会连接 ArgumentList；逐个引用保留 family 和文件路径中的空格。
    $quoted = ($swirlArguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $p = Start-Process -FilePath $program -ArgumentList $quoted `
        -WorkingDirectory (Split-Path -Parent $program) -PassThru -Wait
    $p.Refresh()
    $code = $p.ExitCode
    @{ exitCode = $code; startedUtc = $started.ToString('o') } | ConvertTo-Json |
        Set-Content (Join-Path $swirlRun "$stamp-exit.json") -Encoding UTF8
    if ($program -eq $swirlExe) {
        $diag = Join-Path (Split-Path -Parent $program) 'Swirl-diagnostics.txt'
        if ((Test-Path -LiteralPath $diag) -and (Get-Item -LiteralPath $diag).LastWriteTimeUtc -ge $started) {
            Copy-Item -LiteralPath $diag -Destination (Join-Path $swirlRun "$stamp-diagnostics.txt")
        }
    }
    Write-Host "退出码：$code；本轮目录：$swirlRun"
    if ($null -eq $code -or $code -ne 0) { throw '本轮未通过；检查已保存的退出码、报告和诊断' }
}
```

这些入口顺序运行，不并发启动；每次新建目录保留原结果。GUI 程序的结果
取自进程 `ExitCode`，不使用 `$LASTEXITCODE` 推测。若启动失败、报告缺失、
XML 截断或出现 skip，均按实际状态记录，不能因为目录已创建就记为通过。

## 3. 全界面自动模式与重启观察

```powershell
$swirlRun = New-SwirlFontRun 'automatic-review'
Invoke-SwirlFontRun $swirlExe @('--font-review', '--preview-page=settings',
    "--preview-font-file=$swirlTtc", '--preview-font-family=PingFang UI SC')
```

命令会等到你关闭隔离窗口。参数顺序必须保持：`--font-review` 只导入时
不会应用，后面的 `--preview-font-family` 才选择并确认字体。检查本轮诊断
的 `Font rendering` 家族确实为 `PingFang UI SC`。新状态默认自动；其他
字体的人工观察可使用其真实家族名，但不要套用上述私有三轴基准。

在默认自动模式检查正文/标题层级、按钮、导航、列表、输入、菜单、工具提示
和弹窗；切换明暗主题、字体和应用内缩放，返回已访问页面。窗口仍打开时，
观察同一窗口跨不同 DPI 屏幕、滚动及转场，记录闪字、重影、跳动和裁切。
高级手动模式只在主动启用时测试；确认手动值后切回自动并应用，检查层级恢复。

要验证已确认模式和数值的真实重启，在上述窗口关闭后保留同一个
`$swirlRun` 和 `SWIRL_TEST_ROOT`，执行：

```powershell
Invoke-SwirlFontRun $swirlExe @('--font-review', '--preview-page=settings', '--preview-preserve-settings')
```

重启命令不再传入文件/家族，避免启动参数覆盖刚保存的选择。没有
`--preview-preserve-settings` 的测试启动会清理隔离设置，不能据此判断
配置丢失。隔离导入副本位于本轮状态目录，原始 TTC 不会被修改。

## 4. 原样运行私有字形矩阵和 UI 检查

先在当前真实系统缩放下执行。完整矩阵可能耗时较长；直接运行已有槽，
不使用带离屏设置和 30 秒截止的 `swirl-font-selection` CTest 包装。

```powershell
$swirlFontTests = Join-Path (Split-Path -Parent $swirlExe) 'SwirlFontTests.exe'
if (!(Test-Path -LiteralPath $swirlFontTests -PathType Leaf)) { throw '需要同一构建的 SwirlFontTests.exe' }
$swirlRun = New-SwirlFontRun 'private-matrix'
$env:SWIRL_TEST_TTC = $swirlTtc
$env:SWIRL_FONT_EVIDENCE = $swirlRun
$env:SWIRL_QUALITY_FULL = '1'
$env:SWIRL_QUALITY_HALF_PHASES = '1'
Invoke-SwirlFontRun $swirlFontTests @('importOptionalPingFangUiCollection',
    'optionalVariableAxesAndLivePreview', 'optionalRenderMatrix', 'optionalNativePointSizes',
    'optionalPaintedPreviewAxes', 'optionalRasterQualityMatrix', 'nativeGlyphsHaveNoColourFringes',
    '-o', "$swirlRun\font-private.xml,xml", '-o', "$swirlRun\font-private.txt,txt")

$swirlRun = New-SwirlFontRun 'private-ui'
Invoke-SwirlFontRun $swirlExe @('--font-ui-test', "--font-ui-output=$swirlRun",
    '--preview-page=settings', "--preview-font-file=$swirlTtc", '--preview-font-family=PingFang UI SC')
```

`--font-ui-output` 是**目录**，报告会写入其中的 `font-ui-report.json`。
确认 `failures=0`、各项检查实际完成，并保留原始截图和内存序列。它检查
真实三轴编辑、确认传播、页面与弹窗字体及有限内存压力；测试中主动进入
手动模式和改变 HGHT 是已有压力场景，不是自动模式的轴推荐值。

字形报告包括 `matrix.json`、`native-point-sizes.json` 和
`raster-quality.json`；最后一项仍使用每通道**容差 2**。核对完整 XML、
实际 case 数、`failures`、每例 `pass`、字形/fallback 及首帧变换检查。
保留首次失败；不删除失败图、不改容差、不用后续重跑抹去原结果。

## 5. 实际 DPI 和 60/240 Hz：分别记录

在 Windows **设置 → 系统 → 屏幕**记录当前分辨率、缩放比例，进入
**高级显示**记录实际刷新率。实际改到 125%/200% 后，用新目录重复上面的
观察和矩阵；同一窗口跨屏/缩放切换需要另外观察，不能用每次新开窗口代替。
结束后恢复原显示设置并核对。不要设置 `QT_SCALE_FACTOR` 模拟这一步。

先选实际 60 Hz，执行以下原有帧入口；再在显示器确实支持时选实际 240 Hz，
重新执行同一段，新目录会保留两次结果。保持测试窗口可见，避免最小化。

```powershell
$swirlRun = New-SwirlFontRun 'frames'
Invoke-SwirlFontRun $swirlExe @('--font-frame-test', "--font-frame-output=$swirlRun",
    '--preview-page=settings', "--preview-font-file=$swirlTtc", '--preview-font-family=PingFang UI SC')
$swirlFrames = Get-Content (Join-Path $swirlRun 'font-frame-report.json') -Raw | ConvertFrom-Json
$swirlFrames | Select-Object completed, samePage, dpr, qtRefreshRate
$swirlFrames.phases | Select-Object mode, round, completed, inputWorked,
    @{ Name='queuedPresentP95Ms'; Expression={ $_.queuedPresentIntervalMs.p95 } },
    representedMeasuredInputs, requestedSampleFrames
```

`--font-frame-output` 同样是**目录**。原测试测量静态持续更新、真实 HGHT
滑块和三轴更新各 3 轮，每阶段 30 个预热帧、240 个请求采样帧。
检查 9 个阶段的 `completed`、`inputWorked`、`samePage` 和实际采样数；
没有获得记录的输入不计作已呈现。退出 0 只表示该检查完成，代码没有
以 240 fps 为退出条件。

| 证据 | 能说明的范围 |
| --- | --- |
| `matrix.json` 中的 scale | QImage DPR 模拟；即使全通过，也不是 Windows 系统实际切换缩放。 |
| 原生截图与 `raster-quality.json` 的 DPR | 当前 Qt 窗口及其像素比较；还需系统设置记录、同窗口变化和人眼观察。 |
| `queuedPresentIntervalMs` | 排队呈现间隔；60 Hz 周期约 16.667 ms，240 Hz 约 4.167 ms。比较全部轮次的 p95/p99/max、轴输入覆盖和耗时，不能只看平均值。 |
| `frameSwapped` / `afterFrameEnd` | 分别是排队呈现/提交，不是 GPU 完成、面板扫描或实际光子时间。 |

查看 `font-frame-report.json` 的原始帧、光栅、输入序列及 `limits`，结合
诊断中的真实渲染设备判断，不把请求 D3D11 当作实际硬件设备证明。
不删除动画、降低质量或丢弃轴更新来取得帧率数字。没有 240 Hz 实机执行，
就记录“未执行”；阶段完成或历史 60 Hz 报告都不能补成 240 Hz 通过。

源码入口依据：[main.cpp](../src/Swirl.Quick/main.cpp)、
[StoragePaths.h](../src/Swirl.Quick/app/StoragePaths.h)、
[FontTests.cpp](../src/Swirl.Quick/tests/FontTests.cpp)、
[FontRasterQualityChecks.h](../src/Swirl.Quick/tests/FontRasterQualityChecks.h)、
[FontUiChecks.h](../src/Swirl.Quick/tests/FontUiChecks.h)、
[FontFrameChecks.h](../src/Swirl.Quick/tests/FontFrameChecks.h)。
