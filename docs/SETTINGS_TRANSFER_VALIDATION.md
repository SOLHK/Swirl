# 设置卡片共享转场验证

本记录对应 2026-10-16 的 Windows 本机验证。它覆盖设置九宫格转场与跨窗口输入归属，不代替网络/Codex 验收或 CI 结果。

## 已定位的原因与修复

- 原实现同时淡入原生详情窗口和标题代理面，页面又有独立路由转场，因此出现大块空白面、九宫格与详情同现，以及订阅入口短暂显示旧 DNS 内容。设置宿主现在由单一时钟控制，暂时显示同一份真实缓存内容，完成后才交给不透明原生窗口。详情按终点尺寸排版，边界、圆角与表面颜色插值；不抓取整页纹理来遮盖问题。
- 卡片返回摘要曾跟随动画起点（详情宽度）重排，现保存源卡内容宽度；返回重新测量可见源卡，源卡已隐藏或滚出裁剪区时在当前位置降级消退。
- 减少动态路径在 `QWindow.onClosing` 中递归调用 `close()`，可能留下状态已 Idle 的模态 HWND；现直接隐藏并恢复源卡焦点。
- 设置缓存页跨 `QQuickWindow` 移动后，`Popup` 自身的 `Overlay.overlay` 仍可能指向首次创建的隐藏转场窗口。修复前实际记录是声明页位于活动 `settingsSheet`，订阅表单 overlay 却位于隐藏 `settingsTransfer`，导致 Escape 关闭整张设置窗、旧模态层阻断快捷键。`SwirlDialog` 新增可选声明页 `ownerItem`，迁移页显式提供它；嵌套放弃修改提示跟随外层 overlay。ComboBox、表格菜单和本机文件选择器保持各自声明项的坐标/窗口归属。未迁移调用者保持默认行为。

## 回归验证

`--interaction-test` 在 Windows QPA + software 和 offscreen + software 分别完成 **68 项，0 失败**。覆盖鼠标打开订阅表单、真实 Escape、dirty 确认与取消、缓存返回重开、全局 Ctrl+K、原生窗按钮及脚本实际执行。About 页面测试在缓存页中查找当前可见品牌控件，避免错误命中不可见同名实例。无需通过降低动态或改变 CI 的 QPA 设置跳过问题。

`--hero-test` 最新本机 D3D11 完成 **245 项，0 失败**，证据组为 `settings-ci-fixed`。原 `settings-final4` 的 186 项断言全部保留，另增加明确的正常动态/系统减少动态策略、54 次非空帧采样以及策略恢复检查。专用 Hero 诊断包含本轮完整过程，没有 QML warning/error；`swirl-motion` 本机 CTest 也通过（1/1）。新一轮远端 CI 尚待验证。覆盖内容包括：

- 九个设置入口进入与返回、页面缓存身份、源槽尺寸不变、返回焦点、当前窗口坐标测量。
- 25%/50%/75% 的真实 Escape/关闭按钮中断、反向继续和重复打开；在输入处理边界记录反向前后几何与 reveal，避免将正常输入派发时间误判为跳变。
- 最大化标题栏双击、绿灯全屏/还原、黄灯最小化/还原、resize、源卡隐藏降级、运行中减少动态与转场清理。
- 迁移后 Dialog overlay 与声明页属于同一原生窗；字体许可先滚入实际 viewport 后鼠标点击，配置、脚本、节点导入的真实 modal/ESC；本机文件选择器 `parentWindow` 跟随当前页。

初次截图测试曾在隐藏详情窗调用 `grabWindow()`，同时另一个 `QQuickWindow` 正在渲染，违反 Qt 对隐藏窗口 readback 的前提并触发 QRhi 崩溃。改为信号驱动等待原生交接完成后仅抓取可见窗；不能把该测试 API 误用报告为产品已证实的跨窗场景图崩溃。

两轮 Windows-2022 CI（38791094196、38791176380）的 Hero 均完成并报告 26 项失败；系统报告 `systemReducedMotion=true`。旧测试只将 `Theme.reduceMotion` 设为 false，但实际策略是 Theme 与系统的逻辑 OR，因而测试仍走即时路径，54 次设置业务进入/返回成功却没有任何 moving-window 帧样本。修正后，仅 UI 测试构建提供进程内策略 fixture，明确验证正常动态与系统减少动态两条支路，保留原断言并要求性能帧样本非空；原系统值记录在 JSON，结束及提前退出均恢复。fixture 不修改 Windows 动画/无障碍设置，生产构建不包含注入接口。减少动态 native 就绪还需新的真实帧及 route/section 已落地，避免在延后路由更新前检查旧缓存页。最新本机报告记录原系统策略为 false、正常 fixture 为 0、系统减少 fixture 为 1、恢复结果为 true；54 次动画性能进入/返回均有实际帧样本，没有首帧 -1 或 0 samples。新补丁的 CI 结果需另行验证，不能以本机通过预判。

## 性能采样方法与结果

以下三轮数据来自最新 `settings-ci-fixed/settings-performance.json`。本机 Qt 报告 DPR 1.5、显示刷新率 240 Hz；测试没有改变 Windows 显示刷新率。性能段连续三轮、每轮九入口进入与返回。仅在转场实际 `moving` 区间被动采集 `frameSwapped`，用信号驱动事件循环等待完成，不截图、不强制 update，不丢弃长帧。所有原始间隔、每次请求到首帧、缓存命中及进程资源保存在 `settings-performance.json`。

| 轮次 | 进入 p95 / p99 / 最大间隔 (ms) | 返回 p95 / p99 / 最大间隔 (ms) |
| --- | --- | --- |
| 1 | 4.531 / 4.716 / 27.608 | 4.900 / 8.219 / 8.719 |
| 2 | 4.538 / 4.716 / 6.071 | 7.891 / 8.333 / 8.838 |
| 3 | 4.487 / 4.653 / 5.027 | 5.409 / 8.477 / 9.434 |

这组 4146 个原始间隔保留首轮通用设置的一次 27.608 ms 长帧；`>16.67 ms` 为 1 次、`>33.33 ms` 为 0。它是 Qt 帧交付时间，**不是硬件 240 FPS 或 Windows 合成器呈现率的证明**。不把旧测试轮询所得间隔当作产品优化前后基线。

通用设置首次构建请求到首帧 **141.38 ms**，首帧 GUI `afterAnimating` 采样的 reveal 为 **0.04477**；其他首次新建入口为 0–0.04477，预置缓存的 DNS 入口为 0.15080。未出现冷启动首个可见帧已经跳到中途的证据。初始创建延迟仍保留在报告中，不用预热数据掩盖它。

第三轮结束缓存为 9 页、6774 个被遍历 QML 对象，第 1–3 轮对象数与 GDI handle（28）稳定。三秒自然 idle 后进程 private bytes 从 538836992 降至 484851712，working set 约 361 MB。过程中未 GC、未 `releaseResources`、未关闭 persistent scene graph，也未据此宣称不存在长期泄漏；private/working-set 不能单独归因于 GPU 或 CPU 堆。

追加 `settings-long` 独立进程的 **12 轮、217 项、0 失败**，转场共 77.151 秒、16881 个原始间隔。首轮通用设置保留一次 24.496 ms 长帧，`>16.67 ms` 合计 1 次、`>33.33 ms` 为 0；长帧没有被过滤。首次访问缓存从 1 页/469 个 QML 对象增至 9 页/6774 个，进程 private bytes 从 224915456 增至 519467008，九页缓存与图形资源的首次成本仍然存在。第 5–12 轮 private bytes 在约 507–516 MiB 波动，第 8–12 轮分别为 507.54、507.50、507.75、508.37、508.68 MiB；working set 后段约 347–348 MiB。每轮完成后缓存页均为 9、QML 对象 6774、GDI 28；USER 后段为 67。自然 idle 后 private bytes 从 533393408 降至 496840704，USER 降至 66。本样本呈平台波动，未复现每轮 12–26 MB 的线性残留；12 轮不能证明小时级运行无泄漏，也不能将这些进程计数直接分摊给 GPU 资源。

## 复现入口

这些入口仅在开启 UI 测试的构建中提供；均使用隔离测试数据。

```powershell
Swirl.exe --interaction-test
Swirl.exe --hero-test --hero-output=<evidence-directory>
Swirl.exe --hero-test --hero-settings-only --hero-settings-rounds=12 --hero-no-recording --hero-output=<long-evidence-directory>
```

默认性能采样仍为 3 轮。长样本附带每轮 private bytes、working set、CPU、GDI/USER handle、缓存页/QML 对象数，以及 3 秒自然 idle 前后读数。

动画 QA 录像继续使用 `settings-final4` 的原始帧；后续修改只涉及测试策略与就绪验证，实际动画逻辑未改变。录像依据每张图片真实单调时间戳编码为 VFR：52 张原始帧，尾帧保持后解码 53 帧，时长约 3.623 秒，编码时间戳最大偏差 0.487 ms。截图 readback 约 67–71 ms 一次，会干扰渲染，不能用该录像估算应用帧率；开场截图在初始 35 ms 检查等待后采集，也不捕获最终 DWM/native region 的裁剪和阴影。最终桌面轮廓应使用本机窗口捕获证据检查。
