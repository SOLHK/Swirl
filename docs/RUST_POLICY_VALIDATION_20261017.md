# Rust 原生策略、SOCKS4 导入与 WebSocket 关闭阶段验收

日期：2026-10-17。唯一开发分支：`work/core-completion-20261017`。
接续基线：`0bf2666e118134d25071cd93e743702cba672f83`。
本阶段实际修改并运行原生 Rust 源码，未改 main、QML 界面、系统代理或系统 DNS，也未访问私有订阅。
本文区分实现、执行证据和待执行门禁；旧提交的 CI 成功不作为本阶段通过证据。

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

## 公网尝试与待执行的远端门禁

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
最终公网验收将在 GitHub Actions 使用同一提交的 release harness，严格要求认证 TLS、
预期 HTTP 状态、双向流量、正常关闭、`failed=0`、空 `last_error` 和一条连接记录。
公共 DIRECT/DoH 证据不外推到私有节点、WS 服务提供商、UDP、TUN 或长期性能。

本阶段尚未推送时，远端状态明确为待执行。完成后在本节登记实际源码提交、App 工作流提交、
运行 URL、job 结论和公开证据；不得提前登记成功。

## CI 的具体增量

复用已有 App 的 Contents/Workflows 权限及限定分支的自动更新入口。
本次提交修改已受保护的 `tools/ApplyCoreDevelopment.py` 及其测试，
不修改 App Secrets 或调用工作流；App 将精确更新 `rust-core.yml`：

1. Linux/macOS 导出同次构建的 `SWIRL_RUST_INSPECTOR`，使新增 SOCKS4 inspector 数据路径实际执行。
2. Linux/macOS 与 Windows 添加 `test_policy_groups.py`，保留失败退出门禁。
3. Windows Qt 构建后运行 SOCKS4/4a 与 VLESS WS 的独立对端槽，并保留 SS/VLESS 原有回归。

审核前工作流 SHA-256 为
`c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`；
精确 +9 行后预期为
`50308ecf9ca19e1da4e26893ecb9c6aa8291dc5161976795cf89b4310dc89293`。
只有实际 App 提交及对应 Actions 完成后，才能确认远端执行增量生效。

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
