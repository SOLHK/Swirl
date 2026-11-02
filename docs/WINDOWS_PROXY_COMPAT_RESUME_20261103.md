# Windows 系统代理中断续接 — 2026-11-03

本次重新从 GitHub 读取 [PR #50](https://github.com/SOLHK/Swirl/pull/50)，分支实际 HEAD 已是 `24af5838e39b4612321a7ee2b1be11d78fb9b6dd`，不是交接中的 `4048565`。PR 保持 Draft，目标 `test`，尚未合并；`main` 不在本次操作范围。本文记录新提交前取得的证据与本次修改，后续完整 CI 结果以 PR 的固定 Actions 链接和原始 artifact 为准。

## 1. 已恢复的源代码与测试身份

| 身份 | 核实值 |
| --- | --- |
| 开发 HEAD | `24af5838e39b4612321a7ee2b1be11d78fb9b6dd` |
| 对应 Actions PR checkout | `ceafbef537b9f9f30a0bc13b1dc24f7ff16addfd` |
| 两者仓库 tree | `13a24de79dbab26098059286a1c74b291ed23084` |
| `core/` tree | `f4dbcd2bd4c565f92c0aae836fa7504fcd43efde` |
| PR merge 的 test 父提交 | `63dde8812f85839aa6024cbba6c498c96cae022d` |

`24af583` 已提交 viewport 实际高度变化时的同步 `revealFocus()`，保留 deferred 布局复查。完整应用中原 120ms 等待和原可视性断言没有删除或放松，另有即时 viewport 缩小与全部 clip 边界检查。

旧 [404 完整 Qt run 41467701293](https://github.com/SOLHK/Swirl/actions/runs/41467701293) 实际以失败结束：剩余回归的 `swirl-policy-ui` 发生段错误。它的 native proxy、生产构建和安装包局部成功不能覆盖该失败。旧 [404 Rust run 41467700964](https://github.com/SOLHK/Swirl/actions/runs/41467700964) 的 Windows workspace 本身通过，但后续 Qt REALITY 夹具沿用旧 SOCKS5 REP=5 期望而失败，修正在 `24af583` 中。

## 2. 策略页段错误的可复现诊断

旧诊断代码从 C++ 创建的 ScrollView/Flickable 取 `qmlContext(viewport)`，该上下文可以为空。使用 Qt 6.12.0 原生对象做独立复现，旧 `QQmlExpression` 构造使子进程以 `-11`（SIGSEGV）退出；使用实际 QML 根对象的有效上下文后，构造、订阅与求值成功，进程退出 0。`24af583` 已改用 window 的有效上下文并检查表达式错误。

复现脚本、原始 stdout/stderr、Qt 库与程序 SHA-256 见 [原始证据目录](evidence/windows-proxy-compat-20261102/resume-20261103/qml-null-context/result.json)。这是 Linux Qt 构造路径的因果复现，不单独证明 Windows 完整应用通过。完整 Windows `Swirl.exe --policy-self-test` 仍必须执行原断言，并以报告中的嵌入 QML 摘要核对源码。

对诊断回调的生命周期另行审查：geometry、focus、frame 信号均绑定局部 QObject context，它在被引用的 timeline 与 clock 数据之前销毁并断开连接，未发现 window 长期持有局部引用的问题。

本次把同一个完整应用 `swirl-policy-ui` CTest 提前到 critical UI 阶段，在构建安装包前执行，并强制要求其 JUnit 用例存在且没有 failure/error/skipped。仅调整执行顺序，后续剩余阶段排除这项已执行用例；生产断言、窗口、等待和超时均未改变。

## 3. 补齐原生 Windows 设置到真实 Rust 的自动化证据

现有原生 `SystemProxyTests` 使用 QTcpServer 占位代理端口，真实 Rust HTTP/CONNECT/SOCKS5 则在其他套件单独执行。两组通过不足以直接证明同一原生接管会话的端口确实由 Rust 提供服务。

本次在原生恢复套件增加 `takeoverUsesActualRustCoreListenerAndRestoresExactly`：

1. 启动实际 `RustCoreEngine` V2 DLL 和独立 loopback HTTP origin。
2. 通过原生 `SystemProxySession` 接管，读取 WinINet 地址并与注册表及真实 Rust listener 身份核对。
3. 使用读回的端口发送 HTTP 和 SOCKS5 请求，验证 origin 正文、请求数、Rust 实际流量计数与结束记录。
4. 检查 WinHTTP machine default 未变化，精确恢复 WinINet/registry 原始值，清理 DPAPI journal/guard 文件并释放 Rust listener。
5. 在完整 Qt CI 的原生 XML 门禁中强制要求该用例实际 PASS。

用例只在明确 opt-in 的一次性 Windows runner 执行；失败路径也恢复原始快照。保持原 45 秒套件时间上限和既有恢复、安全检查。由于本地目标是 loopback，会命中 Windows 的本地 bypass，客户端显式采用读回的原生代理地址，避免把 DIRECT 请求当作代理成功。这验证原生端口绑定与真实 Rust 数据平面，不声称完成普通应用的自动系统代理发现或 Codex 会话验收。

## 4. macOS CI 排队原因与恢复

[24af Qt 安全 run 41475106022](https://github.com/SOLHK/Swirl/actions/runs/41475106022) 的两个 macOS 15 job 在尚未分配 runner、没有任何测试步骤时取消。GitHub 原始 annotations 明确记载 hosted runner 多次获取失败与 macOS ARM64 容量约束。这是基础设施失败，不登记为测试通过。第二次尝试随后于 2026-11-02 16:21:37 UTC 取得 runner 并转为执行中。

同一候选的 Rust macOS job 已在 `macos-26-arm64` 镜像 `20261026.0455.2`、macOS 26.6.2、aarch64 Rust 1.99.1 上成功，[GitHub 官方 runner 清单](https://github.com/actions/runner-images) 也确认该镜像可用。但既有 Qt macOS 15 队列现已释放，本次保留原矩阵，不把临时容量约束视为源码缺陷。两个 Qt 版本（6.10.3/6.11.3）、原 ARM64 环境、全部安全断言及 Windows Qt 6.12 产品 job 均保留。

## 5. 已完成的 30 分钟持续流独立复核

新的 30 分钟原始结果已从上一窗口工作目录和 Git blob 恢复，重新核对 302 个核心源文件、7 个 harness 源文件及归档索引的 50 个文件大小与摘要，均一致。现存实测二进制也重新计算摘要。详见 [复核结果](evidence/windows-proxy-compat-20261102/resume-20261103/soak-1800-recheck.json)。

| 指标 | 原始结果 |
| --- | --- |
| 实际时长 | 1800.004075 秒 |
| 连接与事件 | 8 条连接，每条 1801 个，共 14408 个 |
| 数据完整性 | 每连接 client、origin、独立按序重建预期 SHA-256 全部一致 |
| 结束 | 8 条均有 TLS close_notify 与 TCP EOF，无重连 |
| 最终状态 | active=0、failed=0、accepted=8、ended=8，listener 已关闭 |
| 资源采样 | 1800 次；FD 恒 23，RSS 6888–6912 KiB |
| 实测 binary SHA-256 | `5cc28d77b90e86863f2dbdad90e403fce2200be47eed2111124df39f918f76f3` |
| raw JSON SHA-256 | `b4469c9adcaa82726bda10e6b219d4eb71634e7dbed1292c0c082e609f9fe875` |

运行当时 host/network 分类修正尚未提交，原元数据 `source_commit_sha=null` 原样保留；随后通过完全相同的 `core/` tree 及逐文件摘要建立与 `24af583` 的关联，未伪造执行时的 commit。当前提交不改变核心子树。范围是 Linux 受控 V2 CONNECT → 认证 SOCKS5 上游 → 验证 TLS → SSE；有限时段 RSS/FD 平稳不能证明不存在所有泄漏，也不能替代 Windows/Codex/provider 测试。

24af 对应三平台 120 秒 × 8 连接的原始 CI ZIP 也逐个核对官方 artifact digest 与内部事件摘要，均通过：[三平台复核](evidence/windows-proxy-compat-20261102/resume-20261103/current-ci-soak-recheck.json)。Windows 实际 120.02914 秒，Linux 120.003424 秒，macOS 120.190268 秒，每条 121 事件。新提交仍须收齐其自身 CI，不能以这个快照代替。

## 6. 补齐实际生产安装器执行

既有流程验证 NSIS 构建、manifest 和生产目录启动；历史 S4 安装器测试使用合成 payload。它们不能单独证明本次完整安装包安装、运行和卸载成功。本次增加 `scripts/tests/Test-WindowsProductionInstaller.ps1`，由完整 Qt workflow 在产出 NSIS 后强制执行：

- 仅在显式 opt-in 的 GitHub hosted Windows 上运行，沿用现有 `/S /ISOLATED` 和唯一 `D:\Codex\tmp\s4\<GUID>\install` 目录，不改变安装器路径安全策略。
- 核对安装包 SHA-256、当前 checkout、实际安装后的所有 manifest 文件及精确库存。
- 运行实际已安装的 EXE：验证配对 Rust DLL 的 HTTP/CONNECT/SOCKS5 与 listener 清理、Qt/OpenSSL 运行时、全部 UI routes 和正常退出。
- 执行本次真实卸载程序，核对安装目录消失、无残留本轮进程，并比较 registry/快捷方式原状态；失败和超时均保留证据并清理专用 fixture。
- 把真实安装/运行/卸载退出码、源码与二进制摘要写入 `build-evidence/installer-lifecycle/lifecycle.json`，随 package evidence 上传。未实际成功不得登记 PASS。

这是 Windows Server runner 上的完整生产包隔离生命周期；普通用户安装路径、快捷方式创建和真实 Windows 11 桌面仍需单独验收。

## 7. 合并门禁

当前环境没有已登录 Codex Desktop 的真实 Windows 11 设备、用户订阅与节点配置，故最终 Clash/Swirl A/B 为 **NOT_RUN**。Windows Server CI、受控 loopback、真实 Rust DLL 测试和 macOS/Linux 协议测试不能替代这一条件。

只有新提交三平台 Rust、Qt 6.12 完整应用/策略页、原生恢复、同源码生产包身份与 Windows 11 Codex 实机 A/B 全部通过，才可合并 `test`。在此之前 PR #50 必须保持 Draft。最终 CI、安装包 SHA-256 与实际剩余阻塞将更新到现有 PR 和交付报告，不把未执行项目写成 PASS。

## 8. 恢复后发现的 CI 覆盖缺口

`2ff3c853c4df6e3da3760b353eed87dcaf58864a` 已提交上述真实 Rust listener 与生产安装器门禁。继续逐项审查 Rust workflow 的实际日志时，确认前期因未生成 Qt 二进制而跳过的多数用例会在后续 Windows 步骤实际执行，但仍有两个适用入口没有执行：`singBoxQuicProductChainAgainstIndependentPeer` 和 `test_offline_cpp_import_and_existing_store_protection`。因此不能把原来的 suite success 概括成所有适用 Qt 用例都已通过。

后续补齐仅修改 Windows CI 编排：复用本次生成的 Qt 6.12 测试程序和配对 Rust DLL，按既有锁文件下载并验证独立 Hysteria2/TUIC 服务端，驱动现有六个 TCP、UDP、错误认证用例；强制检查每份 XML 的实际 PASS、Qt 版本，以及 JSON 中的源码、程序和 DLL 身份，并保存原始报告。另用已构建的 C++ inspector 执行离线导入和既有加密存储保护用例。生产 Rust、原测试断言和子进程时间上限保持不变，执行结果必须以这次补齐后的新 HEAD 的 CI 为准。

安装器测试还补充失败路径的诊断保全：即使已安装的程序在正常报告复制前失败，也先复制其实际 `Swirl-diagnostics.txt`，再进入独立的进程与专用目录清理流程。保全失败会使门禁失败，但不会阻断清理。该修改不改变生产安装器或运行时行为。

## 9. 真实安装器发现并复现的空目录残留

`2ff3c85` 的完整 Qt run [41481544129](https://github.com/SOLHK/Swirl/actions/runs/41481544129) 在新安装器门禁中实际失败：安装退出 0、1519 个文件摘要和库存一致，已安装 EXE 的 Rust HTTP/CONNECT/SOCKS5、TLS 和 61 个页面检查通过；卸载退出 0，但安装目录仍存在。该 run 整体为 FAIL，不能因为此前 UI/native 阶段成功而称完整 Qt 通过。

随后用固定 SHA-256 的 `24af583` 历史完整生产包做独立 Windows 诊断 [41486232873](https://github.com/SOLHK/Swirl/actions/runs/41486232873)。诊断明确记录 `diagnostic_only=true`、历史 package checkout 和当前 probe 脚本身份，不计作新 HEAD 验收。真实安装目录包含 10 个空叶目录；卸载后残余 17 项，全部为目录、0 个文件，与实际 NSIS 压缩 header 中 11 个没有 manifest 文件后代的目录创建指令及其祖先完全对应。进程清理、用户 registry/快捷方式不变性、专用 fixture 最终清理均通过。原始 envelope、目录清单和退出报告见 [installer-cleanup 证据索引](evidence/windows-proxy-compat-20261102/resume-20261103/installer-cleanup/index.json)。

原因是 Qt 部署生成的空目录被 NSIS `File /r` 一并创建，而文件 manifest 及按已删除文件祖先修剪的卸载逻辑没有这些空目录的拥有关系。修复仅在 `Stage-WindowsRustProduct.ps1` 已确认不存在、由本次构建新建的 staging 目录中清除空目录，然后再运行原有真实 EXE/TLS 验证。删除必须拒绝链接并逐层非递归执行，有文件的目录及用户安装目录保护规则保持有效。安装器验收同时检查 manifest 推导的目录集合，阻止相同问题再次进入生产包。新生产包仍须以修复后的完整 CI 实际安装和卸载结果确认。

## 10. 保留远端新增的完整应用正常退出回归

续接过程中远端增加 `3054b1c002eeac78b84f713ad125845b05adbaa2`，父提交为本轮 `77a366c`，已完整保留并同步。新增 `SystemProxyExitFixture` / `SystemProxyExitTests` 使用完整 Swirl、真实 Rust listener 与原生 WinINet 会话，在 PAC-only、manual+PAC 及两种后续外部修改情形下，通过生产 ShutdownCoordinator 正常关闭窗口。门禁要求代理恢复发生时 Rust 仍健康存活，最终 journal、guard 标记与 listener 清理完成，WinHTTP 不变，且三阶段回执都属于实际 checkout。

这些回归与显式 `requestDisable` 的原生恢复用例分别登记；它们只编译入 UI 测试配置。最新提交下的四个数据行必须实际通过后，才可登记完整应用的原生代理正常退出 PASS。它们仍不能代替真实 Windows 11 Codex Desktop 的同设备 A/B 验收。
