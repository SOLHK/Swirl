# Windows 系统代理兼容性续接记录 — 2026-11-02

## 结论与证据边界

本记录续接 [原验收记录](WINDOWS_PROXY_COMPAT_20261102.md)，不改写其历史结果。最近更新为 **2026-11-02 15:42 UTC**，保留此前 15:20 的中间快照。本轮已证实并修复 SOCKS5 失败分类缺陷，补充原生代理恢复、WinHTTP 不变性和敏感断言输出保护，并为策略表单补上无需下一轮事件循环的 viewport 回归。固定本地候选的 1800 秒持续流已完成并通过。`4048565` Rust 三平台 workspace 已通过，但 Windows 后续 Qt 协议夹具暴露旧错误码断言，**该完整 Rust workflow 为 FAILURE，不能记作通过**。最终候选的完整 Windows Qt 应用、生产包与实机 Codex 验收尚未完成。

只有 `work/windows-proxy-compat-20261102` 可提交；继续使用 [PR #50](https://github.com/SOLHK/Swirl/pull/50)，目标为 `test`。当前保持 **Draft，未合并**。同设备、同订阅、同节点的 Windows 11 Clash/Swirl A/B 为 **NOT_RUN**：执行环境没有已登录 Codex 的真实 Windows 11 桌面。受控 loopback、Windows Actions runner 和 Linux Qt Quick Test 都不能替代此门禁。

本轮公开证据位于 [final-continuation](evidence/windows-proxy-compat-20261102/final-continuation/index.json)。索引记录每个文件的大小、SHA-256、来源与适用范围；不包含自身或本文的自引用 hash。原始日志按字节复制，汇总明确标记为派生快照；没有复制私有下载 URL、完整 workflow 环境日志或大型二进制。

## 一、重新核对源码身份和真实 CI

| 源码阶段 | 分支 HEAD | Actions 实际 checkout | 源码 tree |
| --- | --- | --- | --- |
| 本窗口开始时重新读取 | `1327cb4d587eddc60563c926672f67a6da5c16ce` | `139f8d5d4e0d4cad8f7502389719c606eb2636f2` | `7a028adbb3bc6d6ba5bf35d50a13604160742b5b` |
| 本轮已推送的诊断/协议提交 | `40485650ef72a41967b81cde72cb0600ce5b2538` | `8762af6086f5b04249f94d7a97d7773cf3805858` | `cf1d0dd56ccc22f572aaf93e16f95f34d836d0bf` |
| 后续本地修正 | 基于 `4048565`，尚未绑定最终 commit | **PENDING** | Rust `core/` 子树固定为 `f4dbcd2bd4c565f92c0aae836fa7504fcd43efde`；不是整个仓库 tree |

两个 Actions checkout 都是 PR 合并引用，目标基线为 `63dde8812f85839aa6024cbba6c498c96cae022d`。已核对对应分支与合并引用的源码 tree 一致；不能把 PR 的 head SHA 和运行时实际 checkout SHA 混写。后续提交必须重新核对。

交接中的 [Rust 41405385253](https://github.com/SOLHK/Swirl/actions/runs/41405385253) 与 [Qt 41405385271](https://github.com/SOLHK/Swirl/actions/runs/41405385271) 属于更早历史。开始时实际最新的 `1327cb4` 结果为：

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| Rust Linux / macOS / Windows | 816 / 816 / 817 passed，各 0 failed、0 ignored；各执行 6 项独立 V2 网络测试 | [41456316660](https://github.com/SOLHK/Swirl/actions/runs/41456316660)，[核验摘要](evidence/windows-proxy-compat-20261102/final-continuation/ci/verified1327-summary.json) |
| 完整 Qt 6.12 | critical UI 9/9、critical network/security 10/10；后续完整回归 21/22，`swirl-policy-ui` 失败，无跳过 | [41456316644](https://github.com/SOLHK/Swirl/actions/runs/41456316644)，[原始 JUnit](evidence/windows-proxy-compat-20261102/final-continuation/qml/1327-full-regression.xml) |
| 独立 policy form | 通过旧四项几何用例 | [41456316592](https://github.com/SOLHK/Swirl/actions/runs/41456316592)；不能覆盖完整应用失败 |
| Qt 生产构建与安装包 | Release、启动检查、NSIS 已产出；重新解包并核对 1519 个文件 hash | 仅证明 `1327cb4` 对应包，不能替代后续候选 |

`4048565` 的 [source guards 41467700974](https://github.com/SOLHK/Swirl/actions/runs/41467700974) 和 [独立 policy form 41467700966](https://github.com/SOLHK/Swirl/actions/runs/41467700966) 已成功。该独立 workflow 尚未包含后续新增的同步 viewport 用例。[15:20 进度快照](evidence/windows-proxy-compat-20261102/final-continuation/ci/progress-snapshot.json) 保留当时尚待收齐的结果；**15:35 已确认 [Rust 41467700964](https://github.com/SOLHK/Swirl/actions/runs/41467700964) 整体失败**：Linux/macOS workspace 各 822/0/0，Windows workspace 823/0/0，但 Windows 后续 Qt persisted REALITY + Vision + Chrome133 阶段失败。具体原因和原始证据见第三节。后续 Windows 公网 Qt 测试和完整 native application 构建因此未执行，不能借前序 workspace 成功计为完成。[完整 Qt 41467701293](https://github.com/SOLHK/Swirl/actions/runs/41467701293) 仍在构建。

## 二、`swirl-policy-ui`：已证实的缺陷与仍待闭合的因果链

`1327cb4` 对应 [完整应用原始报告](evidence/windows-proxy-compat-20261102/final-continuation/qml/1327-full-app-policy-ui.json) 真实执行了 527 项检查，仅失败于 `Keyboard focus reveals the last advanced field at minimum window size`。不是缺失提交：该报告 source SHA 指向 `139f8d5…`，源码 tree 与 `1327cb4` 一致；构建日志确认 QML cache 重新生成。

最小窗口为 **760×672**。报告显示实际 `Flickable.height` 从 543 降为 499，`contentHeight` 与表单 body 均为 644，焦点仍在 `policyProbeTolerance`。经过原 120 毫秒等待（实际 124.1596 毫秒），`contentY` 仍为 81；字段 scene y=593、height=32，而 viewport 下边界为 587，连字段中心都被真实 `clip` 祖先裁剪。以同一字段底部 618 和既有 6px 留白计算，新 viewport 需要 `contentY=125`；81 是旧高度 543 的计算结果。

独立测试和完整应用的差异已经具体化：独立 Qt Quick Test 使用展示用 Theme/Motion 替身，几何变化后能继续处理队列；完整应用有真实 Dialog、ColumnLayout、Loader、窗口最小尺寸、编译 QML 和 render/polish 时序。Linux 下复现相同 Dialog/布局以及 `QTimer` 回调内的嵌套 `qWait` 均能通过，故不能仅凭“异步”“AOT”或“flaky”给 Windows 失败下结论。

已可确定的生产缺陷是：`1327cb4` 只在实际 viewport 的 `heightChanged` 中排队 `Qt.callLater(revealFocus)`。**几何更新已经完成时，现有焦点仍可能被裁剪，必须等下一轮事件处理才能修正。** 候选在同一个 viewport signal 中立即执行现有 `revealFocus()`，并保留 deferred pass 处理后续布局变化；没有扩大窗口、增加生产超时或取消焦点条件。

新增 `test_viewportResizeRevealsBeforeReturningToEventLoop`：先让原焦点和 `contentY=81` 稳定，再同步增加 `bottomPadding=44`；不等待下一轮事件，立即断言 viewport=499、外层高度=543、contentHeight=644、焦点未变、整个字段连同原留白可见且 contentY=125。旧四项焦点、外部焦点、手工滚动和延后布局检查全部保留。负对照固定为 `1327cb4`，只允许这个新增用例失败。

本地使用 **PySide6 提供的 Qt 6.12 Quick Test 入口**，Linux offscreen/software renderer，执行生成的真实 QML 用例：旧 `1327cb4` 为 6 passed / 1 failed，唯一失败为新增用例；当前候选 7 passed / 0 failed / 0 skipped。计数包含 init/cleanup，业务用例分别为旧四项通过、新项失败，以及候选五项全通过。见 [结果](evidence/windows-proxy-compat-20261102/final-continuation/qml/local-result.json)、[旧实现 JUnit](evidence/windows-proxy-compat-20261102/final-continuation/qml/local-baseline/junit.xml)、[候选 JUnit](evidence/windows-proxy-compat-20261102/final-continuation/qml/local-candidate/junit.xml)。这不是 Windows 完整应用的通过证明。

`PolicyUiChecks.cpp` 的后续候选保留原 120ms 等待和原失败断言，另在真实页面用可恢复的 QML Binding 单独缩小 viewport 44dp；用完整字段边界逐层核对 clip，并以信号断言外层几何、内容范围和焦点没有变化。报告补充几何/焦点/contentY 时间线及实际 QML 资源 hash，观察器使用窗口的有效 QML context。**还必须从 Windows 完整应用报告确认真正的事件先后及原失败断言通过，当前文档不把独立回归的机制证明升级为已定位的 Windows 唯一根因。**

## 三、Rust SOCKS5 失败语义与诊断修正

本轮保留原先已验证的 DNS 多候选和 DIRECT 规则边界、建立隧道前协议回复、HTTP CONNECT 全部合法 2xx / 有界 1xx / TLS 字节保留及半关闭修复。没有重写正确的转发路径。

新的真实失败是错误回复分类过粗：策略拒绝、DNS 无地址、上游协议拒绝等会被报告为 SOCKS5 `REP=5`（连接拒绝）；不支持的 ATYP 在解析阶段直接 EOF；普通握手超时不应声称 TTL expired。候选保留上游失败类别，按 [RFC 1928 §6](https://www.rfc-editor.org/rfc/rfc1928#section-6) 分别返回规则拒绝 2、网络不可达 3、主机/DNS 不可达 4、已证实 TCP 拒绝 5、地址类型不支持 8，无法精确归类的失败返回 1。

继续审查发现 `HostUnreachable` 原先与 `NetworkUnreachable` 合并，仍会错误回复 3，并使多地址 host/network 混合失败被误判为单一原因。后续候选为 host 增加固定脱敏分类 `UpstreamHostUnreachable`，回复 4；混合类别保持通用失败，结果不依赖完成顺序。同步更新 Rust stage、Qt 展示及 Python 验证器的封闭白名单，不回显原 OS 错误文字。

| 旧生产代码负对照 | 真实失败 | 复放范围 |
| --- | --- | --- |
| [V2 wire](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-socks5-wire.log) | 3 failed：DNS 回复 5 而应为 4；ATYP 直接 EOF；上游拒绝回复 5 而应为 1 | `1327cb4` V2/protocol 生产代码加新测试，原文件 hash 见 `baseline-source.json` |
| [V2 路由拒绝](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-socks5-route-denial.log) | 1 failed：回复 5 而应为 2 | 同一聚焦负对照 |
| [V1 路由/DNS](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-legacy-socks5-fresh.log) | 2 failed | V1 生产代码与 `1327cb4` 字节一致；更大工作树已包含 V2 修复，不能称整个历史 checkout |
| [host/network 分类](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-host-unreachable-complete.log) | 3 failed：typed、混合类别、真实 wire 回复 | `4048565` dial/classifier/mapper 加新回归 |
| [Python 封闭白名单](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-host-diagnostic-allowlist.log) | 1 个新增 subtest 报错 `DiagnosticOutputInvalid` | `4048565` 诊断脚本加 host 分类测试 |

V1/V2 路由、DNS、ATYP、认证节点和 HTTP 407 用真实独立 loopback peer。host/network/permission 用具类型的 `std::io::ErrorKind` 结果注入**真实产品 `dial_addresses` 调度器**，再经 TCP 发送并读取真实 SOCKS5 回复；没有改变主机路由/权限来强迫 OS 产生错误。这些是聚焦旧生产实现的负对照，不是整个历史 workspace 的失败总数。

本地后续候选的 [完整结果](evidence/windows-proxy-compat-20261102/final-continuation/rust/amended-validation-summary.json) 为：Rust workspace **822 passed / 0 failed / 0 ignored**，40 个结果段；`cargo fmt --check`、严格 Clippy `-D warnings`、workspace test、Release build 全部退出 0；独立 V2 网络 **6/0/0**，联网诊断 **23/0/0**。测试二进制绑定到固定 `core/` 子树，实际 `swirl-api` SHA-256 为 `5cc28d77b90e86863f2dbdad90e403fce2200be47eed2111124df39f918f76f3`。提交字段仍为空，不能把这些结果记到另一个 commit。

六项 V2 网络测试重新覆盖：真实 TLS 证书验证、CONNECT 与同包 ClientHello、HTTP/2 三请求复用、WSS upgrade/分片/ping/关闭、分块 SSE 跨握手期限、TCP 半关闭尾部、客户端取消与 core stop 后释放。见 [原始日志](evidence/windows-proxy-compat-20261102/final-continuation/rust/amended-v2-network.log)。它们证明受控协议行为，不能证明实际 Codex/VS Code 账号会话和公网节点可用。

### 完整 Windows CI 随后暴露的旧夹具契约

`4048565` 的 Windows job `125352826267` 在 `Qt persisted REALITY + Vision + Chrome133 through full Xray to HTTP and HTTPS` 失败。测试源码、EXE 和 Rust binary identity 已从实际 artifact 核对，见 [失败摘要](evidence/windows-proxy-compat-20261102/final-continuation/ci/4048565-windows-qt-failure-summary.json)。[原始 tests.log](evidence/windows-proxy-compat-20261102/final-continuation/ci/4048565-windows-qt-failure/tests.log) 为 **5 个顶层方法，4 次 failure incident，0 error、0 skip**：bad short-id/public-key/servername 三个子场景，加一个 policy-reject 方法失败。不能把 unittest 子测试计数简写成“五项仅一项通过”；导入、TLS1.2、取消三个顶层方法均通过。

失败直接指向 `RustCoreTests.cpp` 的 `frontend_response_valid`。该 C++ 夹具硬编码只接受 SOCKS5 成功 `05 00 …` 或任意失败 `05 05 …`；Python lifecycle 验证器和合成报告夹具也把策略拒绝、认证失败的回复固定为 5。结合生产源码与本轮 wire 回归，规则拒绝应为 2、上游认证/握手失败应为 1，可以定位旧夹具错误契约。原 CI 报告只保留 invalid/status=-1，没有保留实际 REP 字节，因此确切原生回复仍须重建后的报告确认。真实报告同时显示 HTTP 502 负对照正确，HTTP/SOCKS DIRECT 正对照成功，stop/listener release 成功；这些局部结果不改变整个 workflow 的失败状态。

后续候选已修正 `RustCoreTests.cpp`、`test_reality_runtime.py`、`test_qt_reality_lifecycle.py` 三层精确期望：规则拒绝为完整 10 字节 REP=2，上游握手拒绝为 REP=1；对规范回复保留数值 REP 便于诊断，但仍要求完整字节和阶段语义同时正确。新增两个验证器回归逐项拒绝旧 REP=5、相互错置的 1/2 以及其余错误状态。完整矩阵、禁止成功隧道和 origin/spare 不可达断言保留，不接受任意非零回复充当正确失败。

用 `4048565` 原 Python 验证器复放当前测试，10 个方法出现 4 次预期 failure incident；修正后 **10 passed / 0 failed / 0 skipped**。见 [旧验证器原始日志](evidence/windows-proxy-compat-20261102/final-continuation/rust/baseline-4048565-qt-lifecycle-validator.log)、[候选日志](evidence/windows-proxy-compat-20261102/final-continuation/rust/amended-qt-lifecycle-validator.log) 和 [三个文件的前后 hash](evidence/windows-proxy-compat-20261102/final-continuation/rust/qt-lifecycle-validator-source.json)。Windows Rust workflow 已在真实 Chrome133+Vision 链之前强制执行该验证器套件，相关 CI guard 本地 1/1 通过；[修正摘要](evidence/windows-proxy-compat-20261102/final-continuation/rust/qt-lifecycle-reply-fix-summary.json) 保存退出码和文件身份。**本节不记修正后原生通过，须由最终源码的 Windows CI 复验。** 该修正不涉及 Rust Core；第五节已经完成的 1800 秒测试始终使用固定 `f4dbcd2…` 子树的同一二进制。因前序失败导致公网证据目录不存在的 artifact upload 错误是派生结果，不另归因为产品协议故障。

## 四、Windows 原生系统代理与敏感证据

`SystemProxySession.cpp` 的现有生产实现经逐项审查：WinINet per-connection options 与 HKCU 四项 registry 原始存在性/类型/字节双向读回；设置变更与 refresh 通知；DPAPI journal；guard 就绪后接管；正常退出与异常退出恢复；PID/创建时间与 applied snapshot 所有权核验；外部修改后放弃写回；生产路径无 WinHTTP 修改。`EngineController` 在接管前验证实际 loopback listener、Rust 运行状态及已提交配置的 port/PID/generation，并在异步完成前重验。启用 capture 时必须绑定实际 Swirl 管理的中继端口，不能使用过期配置端口。

原 `1327cb4` critical-network 实际执行了 `swirl-system-proxy-state`、`swirl-system-proxy-recovery` 并通过，但旧 CTest 汇总没有逐个 QTest 断言，不能只靠测试文件存在宣称新增验收项已覆盖。本轮补充：

- `SystemProxyTests.cpp` 新增 **PAC-only** 和 **manual+PAC** 两行，使用非空合成 PAC 和自定义 bypass，接管与释放前后精确比较 WinINet/registry；验证 DPAPI journal 和诊断输出无 fixture PAC/bypass 原文，失败路径也恢复一次性 runner 原状态。
- 每个原生测试的 init/cleanup 都只读调用 `WinHttpGetDefaultProxyConfiguration`，精确比较 machine default 的类型、字符串及 nullness；PAC 用例另在接管中比较。测试仅链接 `winhttp`，无写入调用。这个范围不应扩称为所有 WinHTTP advanced/per-user 设置的验收。
- 保留所有原恢复、崩溃、外部修改、registry-only 修改、旧 journal、guard 竞态与取消用例，以及原 5 秒恢复预算。将含真实 snapshot 的 `QCOMPARE` 改为相同严格程度的布尔相等断言，避免失败时把 PAC、proxy 凭据或 registry 原文自动写进 QTest XML；`SystemProxyStateTests.cpp` 的 live snapshot 比较也同步保护。
- CMake/完整 Qt workflow 为 state 和 recovery 保留独立 XML，清理缓存中的旧证据，并强制检查必需用例/PAC 数据行确实执行、无失败、无跳过后才接受门禁。

新增原生用例的 **Windows 执行证据仍待当前完整 Qt 收齐**。原生恢复套件使用真实 Windows API 和 TCP fixture；策略 UI/真实 Rust 控制器集成使用每实例内存代理适配器。两类证据各有范围，不能拼接成已完成真实 Windows 11 桌面到公网的端到端验收。

## 五、持续流与 Windows 生产包身份

历史 30 分钟摘要被原样保留为 [historical-1800s-summary.json](evidence/windows-proxy-compat-20261102/final-continuation/soak/historical-1800s-summary.json)：8 连接、1800.026379 秒、每连接 1801 个事件，共 14408 个；客户端/origin 摘要一致，最终 active=0、failed=0、8 条 ended，listener 已关闭。其记录的 binary SHA 为 `458f7e3067f61476dafd96001f53ac9906e9f58773ccfd9e68bf6535b98bc5e0`，早于 `86b73d3` 提交。**本轮找不到其原始逐秒 JSON**，只能重新核对 surviving summary；记录的 raw SHA `c47df0a47a24fbfc4cc6e251d67cffc87468dc5b2a1b31ec3e875a72ba964dda` 没有被重新计算。见 [复核边界](evidence/windows-proxy-compat-20261102/final-continuation/soak/historical-recheck.json)。

本轮新的 **1800 秒 × 8 连接** soak 于 15:12:05 UTC 启动、15:42:06 UTC 完成，退出 0，**PASS**。实际持续 **1800.004075 秒**，8×1801=**14408** 个 SSE 事件；每个连接的客户端、origin 和按序重算的期望 SHA-256 三方一致，所有 peer 均记录 TLS close_notify 与 TCP EOF。最终 active=0、failed=0、accepted=8、ended=8，listener 已关闭；累计上传 13,800、下载 1,198,958 字节。1800 个资源样本观察到 FD 恒为 23、RSS 为 6888–6912 KiB；这个有限负载和时段的观察不能证明不存在泄漏，也不覆盖 NAT 空闲、休眠或网络切换。

完整 [原始逐秒 JSON](evidence/windows-proxy-compat-20261102/final-continuation/soak/amended-soak-1800.json) 已复制并独立重算 SHA-256：`b4469c9adcaa82726bda10e6b219d4eb71634e7dbed1292c0c082e609f9fe875`。见 [复核摘要](evidence/windows-proxy-compat-20261102/final-continuation/soak/amended-soak-1800-summary.json)、[运行元数据](evidence/windows-proxy-compat-20261102/final-continuation/soak/amended-soak-1800-run.json) 和 [harness 身份](evidence/windows-proxy-compat-20261102/final-continuation/soak/amended-soak-harness-identity.json)。实际源码固定为 `core/` 子树 `f4dbcd2bd4c565f92c0aae836fa7504fcd43efde`、`swirl-api` SHA-256 `5cc28d77b90e86863f2dbdad90e403fce2200be47eed2111124df39f918f76f3`；结束时 HEAD 仍为 `4048565`，host/network 修正尚未提交，故元数据的 source commit 正确保留为 null。后续最终 commit 应单独核对该 `core/` 子树等价性，不能把本地结果追记成 `4048565` 原代码通过。入口及六个本地递归 imports 与 run-start 基线逐字节一致；harness hash 实际在 15:38 捕获，未伪称为开始时采集，期间修改的 Qt lifecycle 脚本不在该 import 图中。

本轮 soak 的范围是 **Linux 受控 V2 HTTP CONNECT → 认证 SOCKS5 节点 → 验证 TLS → SSE**，没有真实公网 provider 或 Windows 桌面。先前针对 `4048565` 的 soak 因发现 host/network 缺陷而中止，不计通过。`1327cb4` 三平台 120 秒原始产物已重新核对；`4048565` 的 Linux/macOS/Windows 120 秒产物和六组 Qt 6.10/6.11 security XML 已核对，见 [部分产物摘要](evidence/windows-proxy-compat-20261102/final-continuation/ci/4048565-partial-verified-artifacts.json)。旧版本 Qt security matrix 不能替代 Qt 6.12 全应用。

本轮重新下载、解包并核对的 **历史 `1327cb4` Windows 包**：NSIS 79,148,595 字节，SHA-256 `8b2e3f49bfb9fa90613ef72b1f394597d272c391eb9ad6816d3450117333a232`；实际解包 1519 文件全部与嵌入 manifest 一致。manifest SHA 为 `4fd2dc483ad9add0f7ed9094c9c9dce811f5a221ab1ef0e4badf26c2cdc14006`，包 source 为 `139f8d5…`，Rust build ID 为 `d448b09823344a34fc6a2ce45fcc9d1cc625b85d482affee8e05b0448c603e26`。`Swirl.exe`、`swirl_api.dll`、Qt6Core、OpenSSL DLL 的逐文件 hash 见 [核验摘要](evidence/windows-proxy-compat-20261102/final-continuation/ci/verified1327-summary.json)。**后续候选必须重新产包并核对；不能交付该历史包作为本轮修复结果。**

## 六、未完成门禁

| 门禁 | 当前状态与真实原因 |
| --- | --- |
| 完整应用原最小窗口断言及新增同步 viewport 断言 | **PENDING**：等待后续候选的 Windows Qt 6.12 全应用运行及时间线，不接受独立通过替代 |
| 最终候选 Rust 三平台、严格静态检查和 Release | **PENDING CI**：本地 822/6/23 已通过；`4048565` 三平台 workspace 822/822/823 通过，但后续 Windows Qt 夹具失败使完整 workflow 为 **FAILURE**，修正后须重跑 |
| 新 PAC/bypass、WinHTTP invariance 和恢复 XML | **PENDING**：检查 Windows 原生真实执行、数据行、零跳过与清理证据 |
| 当前候选 NSIS、EXE/DLL、manifest、Qt/OpenSSL、冷/热启动及退出 | **PENDING**：最终源码身份下重新构建与验证 |
| 当前候选 30 分钟持续流 | **PASS（Linux 受控协议范围）**：1800.004075 秒、8 连接、14408 事件，完整 raw 已复核；不是 Windows 11/provider 验收 |
| Windows 11 Codex 工作空间、新建/多轮对话、已有项目、真实 WS/SSE、VS Code、Git/GitHub、PowerShell/curl、退出恢复 | **NOT_RUN**：没有相同设备、订阅、节点及已登录桌面；节点协议、DNS、IPv6、出口 IP 和传输一致性也尚无实机读数 |
| 合并 `test` | **禁止进入合并步骤**：完整 CI、当前生产包和真实 Windows 11 验收缺一不可；PR #50 保持 Draft，`main` 未修改 |

后续更新应追加确切 commit、checkout/tree、Actions、原始报告和包身份，并明确哪些状态被新证据取代。发现失败继续按原断言修复；不能把本记录中的 `PENDING` 或 `NOT_RUN` 改成推测通过。

## 七、已完成的 `24af583` 检查点与原生正常退出补验 — 16:43 UTC

以上 15:42 UTC 及更早段落保留为当时的历史快照。**2026-11-02 16:40 UTC 重新查询时，`24af583` 的五个 Actions workflow 均已完成并为 SUCCESS。** 以下结果只属于这个固定源码检查点，不自动覆盖后来推进的分支。精简核验摘要和原始报告保存于 [检查点索引](evidence/windows-proxy-compat-20261102/native-exit-followup/checkpoint-24af583/index.json)：10 个证据文件共 214,087 字节，逐字节复制，保留原始 CRLF/LF；索引记录来源、大小及 SHA-256，未复制二进制、完整环境日志或临时签名下载 URL。

| 身份 | 已核对值 |
| --- | --- |
| 开发提交 | `24af5838e39b4612321a7ee2b1be11d78fb9b6dd` |
| 实际 CI checkout | `ceafbef537b9f9f30a0bc13b1dc24f7ff16addfd` |
| 两者相同的仓库 tree | `13a24de79dbab26098059286a1c74b291ed23084` |
| Rust `core/` tree | `f4dbcd2bd4c565f92c0aae836fa7504fcd43efde` |

| Workflow | 此检查点的实际结果 |
| --- | --- |
| [Rust 41475106020](https://github.com/SOLHK/Swirl/actions/runs/41475106020) | **SUCCESS**；Linux/macOS/Windows workspace 为 **822/822/823 passed**，各 0 failed、0 ignored；fmt、严格 Clippy、Release 和 Windows 最终完整 Swirl 应用构建通过 |
| [完整 Qt 41475106009](https://github.com/SOLHK/Swirl/actions/runs/41475106009) | **SUCCESS**；critical UI 9/9、network 10/10、remaining 22/22，41 项 CTest 均无失败、跳过或 disabled；另 3 项注册检查以已部署 `Swirl.exe` 的 overview-input、all-pages、capture 入口执行成功，**44 项配置清单全部有对应执行** |
| [Qt HTTP security 41475106022](https://github.com/SOLHK/Swirl/actions/runs/41475106022) | **7 个 job 全部 SUCCESS**；六组 Qt 6.10.3/6.11.3 各原 11 项均通过且无跳过；原生 Qt 6.12 的 policy/subscription/telemetry 为 11/5/34 个 pass 结果，完整产品 capture 亦通过。macOS 首次无 runner、无执行步骤的容量失败保留为失败记录；同源码第二次执行通过 |
| [独立策略回归 41475106061](https://github.com/SOLHK/Swirl/actions/runs/41475106061) | **SUCCESS**；候选 7/7，固定 `1327cb4` 负对照只失败新增的同步 viewport 用例 |
| [源码守卫 41475106025](https://github.com/SOLHK/Swirl/actions/runs/41475106025) | **SUCCESS**；9、7、3 项测试套件全部通过 |

Rust 的 workspace 零 ignored 不表示整个 workflow 零跳过。常规 Qt bridge 是 95 pass/10 个 fixture skip；后续显式 native harness 覆盖其中九项，独立 QUIC 等原有可选范围未在这个 workflow 执行，macOS 公网步骤也因原 Linux-only 条件跳过。完整边界见检查点中的 `rust-validated-summary.json`。最终 Windows 原生报告已核对真实回复：上游握手失败为 **REP=1**，DOMAIN/MATCH 拒绝为 **REP=2**；8 次 lifecycle 调用的 22 项前端检查正确，公网 A/B×HTTP/SOCKS5×HTTP/TLS1.3 共 8 次成功。这些仍不是用户 provider 或 Codex 会话验收。

### 完整策略页原断言与新增几何断言已经通过

[完整应用原始 policy-ui.json](evidence/windows-proxy-compat-20261102/native-exit-followup/checkpoint-24af583/policy-ui.json) 记录 **537/537 checks、0 failures**，CTest 耗时 59.1586 秒。真实最小窗口仍为 **760×672**，本用例实际 DPR=1；原请求等待仍为 **120ms**，实际 136.501ms。运行时嵌入 QML 的 SHA-256 为 `875bd9b43c832e64c3ae66386a4cc2b62e4e42f7917b764531961cf9f0316eaf`，与提交和 checkout 的生产文件一致。

候选时间线实际观察到外层 form 先从 543 变为 499，而 viewport 短暂仍为 543；随后 viewport=499 时 `contentY` 从 81 同步变为 125，原焦点断言通过。新增 viewport-only 用例保持窗口、外层高度 499、contentHeight 644、内容内字段几何和焦点不变，只把实际 viewport **499→455**；`contentY` **125→169**，在下一轮事件前完整 32px 字段已通过全部 clip 边界检查，恢复也成功。Activity 的 DPR 1/1.25/1.5/1.75/2 模拟另分别通过 465/467/468/467/467 checks，不扩称为策略页五个 DPR 或物理显示验收。

诊断提交 `4048565` 的完整 Qt 最终确实失败于观察器的 **SEGFAULT**，不是一次成功取得的原焦点失败时间线。`24af583` 已修正有效 QML context 并完成以上实际复验；候选的时间戳不能被倒用来宣称已经测得旧实现 deferred callback 的精确停顿原因。

### 原生恢复已验证；持有代理时的正常进程退出仍需补验

检查点保存的原生 state/recovery XML 分别是 **34/15 个 QTest pass incident**，包含数据行和 init/cleanup，不是单个 `QVERIFY` 的计数；两行非空 PAC/bypass、异常 owner/engine 退出、外部修改和 registry 原始字节恢复均实际执行，无失败或跳过。WinHTTP 证据限定为只读 `WinHttpGetDefaultProxyConfiguration` 返回的 machine default。另有真实 Rust listener 的控制器/UI 集成，但其代理适配器是每实例内存实现。

**显式 `release()` 恢复、异常退出后 guard 恢复，与“真实 Swirl 持有原生系统代理时正常退出整个进程”是不同的执行路径。** `24af583` 的这些成功结果尚未覆盖后一条组合生命周期，源码审查和分别通过的套件不能代替它。新增真实 `Swirl.exe`＋实际 Rust＋原生 WinINet/registry 的正常退出测试、对应 CI 和新包验证目前均为 **PENDING**；这里记录的是证据缺口，不预判产品一定损坏，也不提前记录新测试通过。

### 固定检查点的生产包和持续流身份

独立生产构建关闭 UI tests；实际 SDK、qmake 和 Qt runtime 均为 **6.12.0**，已核对 CMake 的 **C++23 REQUIRED** 契约、原生编译成功及包内 Qt/OpenSSL **3.5.9** 的实际 DLL 身份。冷启动和相同缓存路径的后续启动均完成 **61/61 页面**、exit 0、无 QML warnings/errors。两次 `cacheHitVerified` 均为 **false**，没有观察到 runtime disk-cache 文件；不能把成功热启动写成缓存命中已证明。

[实际 NSIS artifact](https://github.com/SOLHK/Swirl/actions/runs/41475106009/artifacts/13160021695) 已下载、重算 ZIP digest、解包并核对 **1519/1519** 个 manifest 文件。生产 Rust self-test 的 HTTP、CONNECT、SOCKS5、core 启动和 listener 释放全部成功；运行时 source=`ceafbef…`、build ID=`0b285d29579917c4a34a744e06de52a5d05345d244dff991ee498ba2ba3f4bdc` 与实际包 manifest 一致。

| `24af583` 包文件 | SHA-256 |
| --- | --- |
| `Swirl-Setup.exe`，79,148,856 字节 | `082c6e60ffa968d0e6d3d8766a055e7dc49b5a6263de1f66c74352218b6ea84b` |
| `Swirl.exe` | `d7581841f897133b397125da60c2cce228ba8e694bd1983e17f07414db6dea16` |
| `swirl_api.dll` | `4ca6c9c9a1a56b65b1d3ba698fde70777bbf810abc2d9bbbd1b19dfd1d425f6a` |
| `package-manifest.json` | `95e57c627ba3948422075ea22b731dc3bb77e386719e91cbf2450fb6a0758003` |
| GitHub installer ZIP | `1b3974f92455fc86404a0473f44bc497048ebc8603618025df39f864031fcc40` |

30 分钟测试仍绑定上述相同 `core/` tree：**1800.004075 秒、8×1801=14408 事件**，raw SHA=`b4469c9adcaa82726bda10e6b219d4eb71634e7dbed1292c0c082e609f9fe875`，binary SHA=`5cc28d77b90e86863f2dbdad90e403fce2200be47eed2111124df39f918f76f3`。[另一个续接窗口的复核](evidence/windows-proxy-compat-20261102/resume-20261103/soak-1800-recheck.json) 指向的也是这次新测试。本次再次核对其 240,591 字节 raw 在 `24af583`、`2ff3c8` Git blob 及工作树逐字节相同，两个提交的 `core/` tree 均为 `f4dbcd2…`；原执行元数据 `source_commit_sha=null` 未改写。**这不是更早 1800.026379 秒、raw `c47df0…`、binary `458f7e…` 那次测试的原始文件恢复证明**；第五节对旧记录仅存 summary 的边界仍适用于旧记录。新测试的 Linux 受控 TLS/SSE 范围也没有变成 Windows/Codex 实测。

### 后续源码与尚未满足的合并门禁

远端随后另行推进到 `2ff3c853c4df6e3da3760b353eed87dcaf58864a`，增加真实 native→Rust listener 组合测试、生产 NSIS 安装/运行/卸载测试等；相关范围见 [该续接记录](WINDOWS_PROXY_COMPAT_RESUME_20261103.md)。16:43 UTC 查询时，其独立策略和 source guard 已成功，[完整 Qt](https://github.com/SOLHK/Swirl/actions/runs/41481544129) 与 [Rust](https://github.com/SOLHK/Swirl/actions/runs/41481544448) 正在运行，[Qt security](https://github.com/SOLHK/Swirl/actions/runs/41481544469) 尚在队列，不能由 `24af583` 的绿色结果代替。持有原生代理的正常 Swirl 进程退出补验是进一步独立门禁，仍须后续实际证据；新的安装/卸载门禁也不应倒记为本节历史包已执行。

真实 Windows 11 已登录 Codex Desktop 的同设备/订阅/节点 Clash/Swirl A/B 继续为 **NOT_RUN**，Workspace Settings、多轮对话、真实 VS Code/WS/SSE 和退出后的该设备代理恢复均未冒称通过。PR #50 继续保持 Draft；上述检查点本身不满足合并 `test` 的全部条件，`main` 不在修改范围。
