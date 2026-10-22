# Rust 原生策略、SOCKS4 导入与 WebSocket 关闭阶段验收

日期：2026-10-17。唯一开发分支：`work/core-completion-20261017`。
接续基线：`0bf2666e118134d25071cd93e743702cba672f83`。
本阶段实际修改并运行原生 Rust 源码，未改 main、QML 界面、系统代理或系统 DNS，也未访问私有订阅。
本文区分实现、执行证据和具体门禁；旧提交的 CI 成功不作为本阶段通过证据。

源码实现已推送为 [`58969bc`](https://github.com/SOLHK/Swirl/commit/58969bce15f9995573f15661bbd1ca75530938af)。
GitHub 工具生成的源码树 `9a5dd9e15f897d08073609ed6d18d28292ae1151` 与本地验收暂存树逐字节一致。
既有 App 随后提交 [`5dbe762`](https://github.com/SOLHK/Swirl/commit/5dbe762d4b85543939d8ca476451f137e210a559)，
唯一改动是 `rust-core.yml` 增加 9 行，Rust/Qt/Python 实现与前一提交完全相同。

## 本阶段交付

### 原生自动组接入

原有候选 `policy.rs` / `probe.rs` 现在实际进入 crate 模块树，并连接 typed IR、规则解析、
原生 HTTP/HTTPS 探测、运行时调度、控制 API 和不可变会话视图。
支持嵌套手动组、`url_test`、`fallback`、按新会话轮询的 `load_balance`。
探测通过所选原生出口执行，HTTPS 可在已经认证的 TLS 代理连接内再认证源站 TLS。
不调用外部完整代理内核，不重放失败应用请求，不在全部不健康时静默直连。

资源边界、健康过期、迟滞与 schema 字段详见 [原生策略组](RUST_NATIVE_POLICIES.md)。
跨配置代共享四个探测名额；准入和网络操作共用一次绝对期限；完整配置替换及 stop 取消旧任务。
HTTP 探测校验完整最终响应头和精确状态码，限制总头部、字段与临时响应数量，不跟随重定向。
探测不污染应用会话流量和错误计数。

**会话视图在 listener accept 时固定。** 已接收连接即使稍后才握手，也使用接收时的健康视图；
接受前尚无健康节点的预连接不会因之后探测成功而自动刷新。
已接受会话、既有 TCP 和 UDP 关联保留原配置与出口；新接收会话使用新视图。
健康快照读取不消费轮询，应用真正使用组时才消费相应轮次。
Qt 现有组转换仍只支持有限手动组；自动组与嵌套组目前通过 Rust IR/API 使用。

### SOCKS4/4a 从订阅候选进入 Qt 原生路径

复用既有 Rust SOCKS4 握手，增加 URI、Base64、Swirl `proxies` YAML/JSON 容器及
sing-box `type: socks` / `version: "4"` 或 `"4a"` 的离线 inspector 和 Qt 转换。
这里的 YAML/JSON 容器支持不表示 Clash 或 Mihomo 自身实现了 SOCKS4。
SOCKS4 使用本地 DNS；SOCKS4a 传递域名；USERID 按 URI 百分号编码读取，
不把它当成 SOCKS5 的 Base64 用户名密码。
非空密码、未知/冲突扩展、TLS、UDP、TFO 和非 TCP 请求保持明确拒绝或保留报告。

Rust 专用 Qt 构建允许已校验的 SOCKS4 导入；兼容构建维持拒绝，未增加协议下拉项或修改 QML。
新增 Qt 槽同时覆盖合法转换、未知字段/认证拒绝和与独立对端的实际数据转发。

### WebSocket 从关闭意图开始计时

修复背压下 Close 排队、旧数据帧写入或 flush 尚未完成时，原有关闭计时器无法启动的问题。
经过校验的对端 Close、本地 EOF 或 `poll_shutdown` 记录最早关闭意图，
排队、写入、flush、等待对端 Close 和底层 shutdown 共用原始两秒总预算。
重复 shutdown 或新的控制帧不能延长预算；正常空闲连接不启动该计时器。
本地主动关闭后停止应用数据，同时继续响应 Ping，直到对端 Close 或预算耗尽。
七项新增确定性虚拟时钟回归实际观察底层流释放和驱动取消。

## 本地执行结果

执行环境：Linux，Rust `1.99.1 (58cf8f9c3 2026-10-13)`；
依赖按 Cargo.lock 离线构建，网络测试仅使用临时本地独立 TCP/UDP 对端。
最终 release harness SHA-256：
`5c939a58837bd014ae82537885410e37837ffedb6ff698427101f4328a43c81d`。
这些结果来自提交前的候选工作区，不伪装为已提交源码的远端 CI。

| 检查 | 实际结果 | 范围与限制 |
|---|---|---|
| `cargo fmt --all -- --check` | 通过 | 全 workspace |
| `cargo check --workspace --locked --offline` | 通过 | 全 workspace |
| `cargo clippy --workspace --all-targets --locked --offline -- -D warnings` | 通过 | 警告作为错误 |
| `cargo test --workspace --locked --offline` | 83 项通过，0 跳过、0 失败 | API 1、core 策略 5、core 网络 11、DNS 8、protocol 22、routing 4、subscription 31、transport 1 |
| `cargo build --release --locked --offline -p swirl-api` | 通过 | 同次生成动态库、harness 与 inspector |
| `test_policy_groups.py` | 13 项通过，5.214 秒 | 原生出口上的独立 HTTP/HTTPS/双层 TLS 与可区分 SS UDP 对端 |
| `test_rust_core.py` | 24 项中 23 通过、1 跳过，26.906 秒 | 跳过 Qt VLESS，需要 Windows Qt 可执行文件 |
| SS、DoT、DoH、SOCKS4、WS、订阅采集、Codex 管理与工作流回归合计 | 97 项中 61 通过、36 跳过，49.146 秒 | Qt SS/SOCKS4/WS 各 1；Windows DPAPI 采集 22、管理 10；真实 Codex CLI 可选项 1 |
| Python 本地总计 | 134 项中 97 通过、37 跳过、0 失败 | 跳过项均未计作通过；Qt 留待 Windows CI |
| 工作流更新器 `--check` | 13 项回归通过 | 精确 +9 行工作流预览、幂等、半应用/重复拒绝、写入路径及上下文限制 |

工作流更新器回归已包含在上述 Python 总数中，不能重复相加。
最初受限容器的 loopback socket 返回权限错误；最终本地网络套件在本会话授权并经自动审核
允许的临时 socket 权限下执行。没有变更用户机器网络设置。

### 独立对端确实验证的内容

- fallback 按优先级选择；故障对端已经消费 POST 后，Rust 不把请求重放到另一出口或 DIRECT。
- url_test 健康改变只影响新连接；旧 TCP 保持原出口；无效配置原子回滚；完整配置替换不搬迁旧流。
- 轮询仅被实际路由的新会话消费，读取状态和手动选择不重置健康任务。
- 全不健康拒绝；过期健康、迟滞与图验证由 Rust 测试覆盖；重定向、错误证书或不匹配证书不变健康。
- 四个同时挂起的探测在配置替换和 stop 后释放，等待超过一次周期没有旧探测复活。
- 两个独立 SS 出口分别使用 AES-128-GCM 和 ChaCha20-Poly1305；A 变为不健康后，新 UDP
  关联走 B，旧关联针对旧/新目标继续走 A。完整配置删除两节点和组后，既有 A/B 关联仍走
  各自旧出口，新关联被丢弃。实际完成 A 四次、B 两次，共六次可区分 UDP 往返。
- 选择到不支持 UDP 的健康 HTTP 出口时，不能改用同组健康 DIRECT 成员。
- SOCKS4 inspector 候选至原生握手至独立服务端完成十个会话，覆盖五种输入 × 两个版本；
  USERID、IPv4/域名、echo、半关闭均检查，每个会话 `accepted=1 / active=0 / failed=0`，
  `last_error` 为空且双向字节数非零。INI 和全订阅策略组迁移不在该证据内。
- 既有独立 VLESS/Trojan WS/WSS、控制帧、背压和关闭回归随整套执行；新增 Qt WS 槽
  请求独立 HTTP 源站的 131073 字节响应，并检查掩码、目标地址和最终会话计数。
  Qt 槽的源码与 Python 对端存在，不等于本地 Linux 已实际执行 Qt。

## 本地公网尝试与远端门禁

本地 2026-10-17 12:31:38 UTC 的固定公网尝试失败，保留
[原始失败 JSON](evidence/RUST_PUBLIC_NETWORK_20261017_POLICY_LOCAL.json)。
该文件记录基线 `0bf2666`、`tracked_worktree_clean=false` 和本轮 release 二进制哈希，
准确表示提交前候选工作区，不代表基线二进制或最终 CI 提交。

| 公共目标 | DNS 路径 | 本地结果 |
|---|---|---|
| `example.com:443` | system | `DnsLookupFailed`；无应用流量 |
| `www.rust-lang.org:443` | system | `DnsTimeout`；无应用流量 |
| `example.com:443` | 原生 DoH，经 `1.1.1.1:443` bootstrap | `DnsHttpsConnect`；无应用流量 |

三项均为 `accepted=1 / active=0 / failed=1`，不能称公网验证通过。
远端公网验收使用同一提交的 release harness，严格要求认证 TLS、
预期 HTTP 状态、双向流量、正常关闭、`failed=0`、空 `last_error` 和一条连接记录。
公共 DIRECT/DoH 证据不外推到私有节点、WS 服务提供商、UDP、TUN 或长期性能。

### 当前提交的严格公网通过证据

`5dbe762` 的 #25 Linux job 于 **2026-10-17 12:48:17 UTC** 完成三项公网检查，
原始附件已下载并保留为 [VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_POLICY_VERIFIED.json)。
报告标记 `tracked_worktree_clean=true`，二进制 SHA-256 为
`914ee31cac2e00f75bb78bde55a22f68e60c6e98b4af8e6e71d906b59b5e1da0`。
它是当前提交在 CI 生成的二进制，不能与前述本地构建或上一阶段哈希混用。

| 公共目标 | DNS 路径 | HTTP | Core 上传/下载字节 | 会话收尾 |
|---|---|---|---|---|
| `example.com:443` | system | 200 | 700 / 4790 | 通过 |
| `www.rust-lang.org:443` | system | 301 | 690 / 5386 | 通过 |
| `example.com:443` | 原生 DoH，显式 Cloudflare IP bootstrap | 200 | 700 / 4790 | 通过 |

三项均为认证 TLS 1.3，`certificate_verified=true`、`orderly_close=true`，
每项 `accepted=1 / active=0 / failed=0`、`last_error=""`、`recorded_connections=1`。
这里的 301 是固定公网 HEAD 验收预期状态；健康探测自身仍按配置精确匹配 2xx，不跟随重定向。

[GitHub 原始附件](https://github.com/SOLHK/Swirl/actions/runs/39033762503/artifacts/12101273040)
ZIP SHA-256 为 `09ab062d72b63a9caf4f1e3695ed8ab6a73e0a0e0f7e07378276ab953400f83f`，
下载字节已与上传日志核对一致；解压 JSON 的 SHA-256 为
`67d7ec841062582c5a56c93812bb7b8d48267f4018aab507800eabc74b932974`。

本轮远端运行入口：

| 运行 | 实际作用 | 当前状态 |
|---|---|---|
| [Core implementation validation #21](https://github.com/SOLHK/Swirl/actions/runs/39033743434) | 由 `58969bc` 触发；日志明确实际测试 `5dbe762` | 成功，12:47:53 UTC 完成；App 提交、83 Rust、13 更新器回归及基础独立对端均成功 |
| [Swirl Rust Core #25 / Linux](https://github.com/SOLHK/Swirl/actions/runs/39033762503/job/117399364540) | `5dbe762`；83 Rust、100 Python、三项严格公网 | 成功；Python 96 通过、4 Qt 跳过；策略 13/13；公网 3/3 |
| [Swirl Rust Core #25 / macOS](https://github.com/SOLHK/Swirl/actions/runs/39033762503/job/117399364475) | `5dbe762`；83 Rust、100 Python | 成功；Python 96 通过、4 Qt 跳过；策略 13/13 |
| [Swirl Rust Core #25 / Windows](https://github.com/SOLHK/Swirl/actions/runs/39033762503/job/117399364415) | `5dbe762`；MSVC Rust、独立协议、Qt CTest 与四个独立 Qt 对端 | 全部成功；83 Rust；初次 134 Python 中 128 通过、6 跳过；随后四项 Qt 独立补跑均通过 |

`58969bc` 同时触发的 #24 使用更新前测试菜单，不能代替 #25 的新增门禁。
App 自己触发的 Core implementation validation #22 按既有防递归条件跳过；
该跳过不作为实现验收，实际 App 执行和源码验证以 #21 为准。
Core #21 的基础独立对端菜单共 74 项，69 通过、5 跳过：四项需要 Qt，另一项需要 inspector。
同一源码的 #25 Linux/macOS 已实际执行新增 inspector 和 13 项 Python 策略门禁，不能用 Core #21
的基础菜单代替它们；各平台 Qt 跳过项也不能被错误计入通过数。

#25 三平台整体于 **2026-10-17 12:55:06 UTC** 成功完成。
各平台均通过 fmt/check/clippy、83 项 Rust 和 release 构建；Python 策略套件分别为
Linux 13/13（5.232 秒）、macOS 13/13（7.176 秒）、Windows 13/13（6.353 秒）。

### Windows Qt 的真实执行

Qt 6.10.3 / MSVC 构建 `SwirlRustCoreTests`，以 `SWIRL_USE_RUST_CORE=ON` 链接本轮 Rust 动态库。
CTest `swirl-rust-qt-integration` **1/1 通过，3.12 秒**，包含 SOCKS4 参数接受、拒绝和 ABI 转换回归。
需要外部端口的槽随后由 Python 独立对端设置环境并明确指定槽名执行：

| 独立测试 | 实际结果 | 转发证据 |
|---|---|---|
| `ShadowsocksTests.test_qt_facade_http_obfs_with_udp_declared` | 通过，0.668 秒 | 既有 SS AEAD / HTTP obfs Qt 路径保持通过 |
| `RustCoreIntegration.test_vless_qt_data_path` | 通过，0.662 秒 | 既有 VLESS Qt 原生转发保持通过 |
| `Socks4Integration.test_qt_imported_socks4_and_4a_data_path` | 通过，2.453 秒 | URI、sing-box JSON、YAML × SOCKS4/4a，共六个 Qt 导入至独立对端 HTTP 会话；检查 USERID、本地 IP/远程域名、完整响应与零会话错误 |
| `WebSocketTransportTests.test_qt_vless_websocket_data_path` | 通过，1.166 秒 | Qt VLESS WS 请求实际源站 131073 字节响应，验证掩码、目标、数据及正常关闭计数 |

Windows 初次 134 项中的六个跳过为上述四项 Qt、一项可选 C++ 私有缓存 importer 和
一项 opt-in 真实 Codex CLI。四项 Qt 已按表补足，余下两项没有执行；Linux/macOS 的 Qt 跳过
也不被改写为该平台桌面验收通过。测试通过不代表所有 Python daemon 请求线程都被逐个 join。

CI 仅构建/执行 Qt 控制适配测试目标，没有本轮完整 Swirl 桌面安装包或个人机器视觉验收。
`windeployqt` 的日志仍保留 dxcompiler/dxil 与 VCINSTALLDIR 提示；不能用测试目标成功宣称
发行包运行库齐备。没有为消除提示而更改用户系统环境。

## CI 的具体增量

复用已有 App 的 Contents/Workflows 权限及限定分支的自动更新入口。
本次提交修改已受保护的 `tools/ApplyCoreDevelopment.py` 及其测试，
不修改 App Secrets 或调用工作流；App 已在 `5dbe762` 精确更新 `rust-core.yml`：

1. Linux/macOS 导出同次构建的 `SWIRL_RUST_INSPECTOR`，使新增 SOCKS4 inspector 数据路径实际执行。
2. Linux/macOS 与 Windows 添加 `test_policy_groups.py`，保留失败退出门禁。
3. Windows Qt 构建后运行 SOCKS4/4a 与 VLESS WS 的独立对端槽，并保留 SS/VLESS 原有回归。

审核前工作流 SHA-256 为
`c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`；
精确 +9 行后的预期和实际 SHA-256 均为
`50308ecf9ca19e1da4e26893ecb9c6aa8291dc5161976795cf89b4310dc89293`。
App 提交内容已与本地审核结果核对一致；测试执行结论按上方具体 Actions 登记。

## 复现与后续边界

从仓库 `core` 目录执行上述 Rust 门禁，然后在仓库根目录设置：

```sh
export SWIRL_RUST_HARNESS="$PWD/core/target/release/swirl-api"
export SWIRL_RUST_INSPECTOR="$PWD/core/target/release/swirl-inspect"
python3 tools/tests/test_policy_groups.py
python3 tools/tests/test_socks4.py
python3 tools/tests/test_websocket_transport.py
python3 tools/ApplyCoreDevelopment.py --check
```

Windows Qt 路径设置和完整回归见 [接续入口](CONTINUE_DEVELOPMENT.md)。
Qt 自动组/嵌套组转换、全订阅 Rust 接管、DNS 负缓存/多地址/分流/bootstrap、
智能 MRS/进程规则、更多协议/传输、TUN/LAN/系统接管、私有提供商及长期/性能验收仍未完成。
默认兼容构建保留 Mihomo；`SWIRL_USE_RUST_CORE=ON` 才是明确选择原生 Rust 的产品构建。
本阶段不宣称全项目迁移完成，也不替代个人 Windows 机器的安装包与视觉验收。
