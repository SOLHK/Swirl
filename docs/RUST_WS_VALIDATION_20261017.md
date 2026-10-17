# Rust WebSocket 修复与接手验收（2026-10-17）

本轮开发分支：`work/core-completion-20261017`。接手基线为 `8bd89f2d59e582040d88ae52ef1b253beff3d33e`；
main 为 `87409c0bf9c957ef113f84c176c5a1529c27b9df`，本轮不改 main。此文区分源码、编译、独立网络对端、
Qt 配置映射、公网目标及私有节点，不把一个层级的结果代替另一个层级。

## 接手时的真实状态

- 全量获取仓库及分支历史后核实：main 尚无 Rust workspace；开发分支已继承 main 的连续卡片导航与动画修复。
- Rust 已接入独立网络执行路径，包含 HTTP/CONNECT、SOCKS4/4a/5、Trojan TLS、SS AEAD TCP/UDP、基础 VLESS、
  WS/WSS、UDP/TCP DNS、DoT、HTTP/1.1 DoH、基础规则与手动 selector。组合边界见 [架构审计](RUST_CORE_AUDIT_20261017.md)。
- 默认 Qt 构建依旧保留历史 C++/Mihomo 兼容路径；`SWIRL_USE_RUST_CORE=ON` 才是本轮 Rust 验收对象，不能称产品已全量迁移。
- 自动 url-test/fallback/load-balance 的三个候选文件未声明到模块树、未编译、未执行。旧提交标题不是已完成功能证据。
- [Core implementation validation #16](https://github.com/SOLHK/Swirl/actions/runs/39022566065) 的 Rust 检查成功、WS 分片回归失败。
  App Token 的生成与 checkout 成功，但当时没有实际工作流文件变更，不能据此认定 Workflows 写入已验证。

## 两个独立根因及修复

### 独立 Python 对端阻塞了源站尾部回传

旧的 `Framed.recv()` 在 `select()` 报告 WebSocket 可读后，吞掉 Pong 并继续等待下一条应用二进制帧。
源站即使已经有剩余数据，双向转发循环也无法回来读取它。本机原始基线重现与 Actions 相同的计数：
上传及源站接收 65,537 字节，回传仅 49,152 字节，Pong 5 个、掩码帧 11 个，最后超时。

修复为单帧事件读取 `recv_frame()`：Pong/空数据帧返回控制事件 `None`，关闭保持 `b''`，恢复对源站的调度。
协议握手继续使用等待应用字节的 `recv()`；已有缓冲数据也不再阻止检查源站可读状态。

隔离实验：只修 Python 对端、仍用原始 Rust binary，原分片测试与新增 Pong 后尾部测试均通过。
这证明原先分片失败不能直接归因于 Rust 解码。

### 原生 Rust 对合法 Ping 突发误断连

Rust 原来用 `try_send()` 把 Pong/Close 放入容量为 8 的队列。同一批合并的 Ping 填满队列后，
writer 还未得到调度，reader 就把正常排队当成 `WebSocketControlLimit`。原始 binary 在新增 33 个合并 Ping
的 WS 和 WSS 实测中均发生 EOF，确认这是独立的原生实现缺陷。

改为同一容量 8 的 `send().await`，满时施加背压，允许 writer 发送；receiver 退出则立即返回
`WebSocketControlClosed`。没有扩大队列、消息或分片上限。TLS 校验、随机客户端掩码、畸形帧拒绝、
控制帧 125 字节上限、Close 校验与原有关闭期限继续保留。Stream Drop 仍取消自有 driver。

新增 3 项 Rust 回归验证合并 Ping/Close、有界队列接收端退出，以及 17 字节应用缓冲和 31 字节网络缓冲下的
双向部分读写、33 个分片、全部 Pong 与 Close。Python 保留原失败测试，增加控制事件、Pong 后尾部、WS/WSS Ping 突发回归。

## 本地已执行结果

环境：Linux x86_64，Rust 1.99.1，锁定的 Cargo 依赖，Python cryptography 50.0.2；
除明确的公网尝试外，网络测试均使用临时 loopback 端口、合成认证和临时证书，不使用私有订阅或完整代理内核。

| 验证 | 实际结果 |
|---|---|
| 原始 `8bd89f2` 分片测试 | 按预期复现失败：65,537/49,152 字节，7.025 秒 |
| 修 Python 对端、原始 binary 的隔离测试 | 3 项通过，含原分片与 WS/WSS Pong 后尾部 |
| 原始 binary 新增 Ping 突发回归 | WS/WSS 均按预期复现 EOF |
| `cargo fmt --all -- --check` | 通过 |
| `cargo check --workspace --locked` | 通过 |
| `cargo clippy --workspace --all-targets --locked -- -D warnings` | 通过 |
| `cargo test --workspace --locked` | 57 项通过，包含新增 3 项原生回归 |
| `cargo build --release --locked -p swirl-api` | 通过 |
| `test_websocket_transport.py` | 10 项通过，无跳过 |
| `test_rust_core.py` | 18 项通过，1 项 Qt 转发测试因无 Qt executable 跳过 |
| `test_shadowsocks.py` | 8 项通过，1 项 Qt facade 测试因无 Qt executable 跳过 |
| `test_dns_tls.py` | 11 项通过 |
| `test_dns_https.py` | 9 项通过 |
| `test_socks4.py` | 8 项通过 |
| `ApplyCoreDevelopment.py --check` | 11 项工作流更新安全验证通过，仅读取/展示 diff |
| Linux 采集/Codex 管理附加测试 | 1 项证据分类通过；Windows DPAPI/真实 CLI 相关项明确跳过，不算通过 |

新增 2 个 Qt 测试槽验证 VLESS WS、VLESS WSS、Trojan WSS 现有字段映射和实际 Rust ABI 配置接受，
以及 12 类危险/不支持参数拒绝与输出原子性。本地没有 Qt SDK，需以本轮 Windows CI 实际结果补录；
即使配置测试通过，也不能称已验证 Qt WS 真实转发。

## 公网验证与环境边界

`tools/Verify-PublicRustCore.py` 使用固定公开目标，执行两次原生 DIRECT HTTPS HEAD（example.com、www.rust-lang.org），
以及明确 `1.1.1.1:443` bootstrap、认证名 cloudflare-dns.com 的原生 DoH 后再访问 example.com。
客户端 TLS 保持认证，DoH 由 Rust/rustls 执行，检查运行时身份和真实收发字节，不使用环境代理、私有节点或系统配置更改。

本地实际尝试失败：系统解析出现 `DnsLookupFailed`/`DnsTimeout`，明确 IP 的 DoH 出现 `DnsHttpsConnect`。
独立 Python 原生 socket 对相同域名也报 `gaierror`，因此本地环境不能作为公网成功证据。
GitHub Actions 将执行同一脚本并保存准确提交、binary SHA-256、时间、HTTP 状态、TLS 与计数；结果需要等待实际运行补录。

公网验证脚本另已检查统一 45 秒预算、慢速响应头截止时间、控制回复上限、损坏/关闭控制管道及自有进程清理。
源码身份的 Git 调用明确以脚本定位的仓库根目录运行；从 CI 的 `core/` 工作目录执行的模拟验证通过，
不会因相对路径误判脚本未跟踪。工作区有未提交核心或脚本改动时不能宣称来源匹配。这些脚本边界检查不是公网成功证据。

公网 DIRECT/DoH 成功仅证明这些目标和路径，不证明远端 WS 提供商、私有订阅、UDP、TUN、长时弱网或性能。

## 工作流写权限的实际验收

沿用现有 App Token job，不改 App 配置、Secrets、Token 权限或写入白名单。
`ApplyCoreDevelopment.py` 先运行安全门禁，再只对现有 `.github/workflows/rust-core.yml` 做已审核的幂等修改：

1. 精确追加本开发分支触发，保留 main/test 与 PR 条件。
2. 把 DoH/SOCKS4/WS 和脚本安全验证加入既有 Linux/macOS/Windows 测试菜单。
3. 加入仅 Linux 的固定公网验证及 7 天证据 artifact。

本地 `--check` 展示的工作流 SHA-256 为：

- 原始：`670ace2b30c0456f6a3d0dcc35c6c11583e9c95dcf3138c5e8843b0a6916b1b9`
- 预期更新：`c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`

必须验证 App 自动提交确有该 workflow diff、成功推送开发分支、远端内容哈希匹配、三平台运行使用相同提交。
仅 Token 生成成功或自动提交后的跳过运行不算实证。此阶段提交后再补录真实提交与 Actions 结论。

### 本次实际写入阻塞

已尝试通过 GitHub 连接器创建基于原始开发分支 tree 的阶段提交树，内容为本轮 12 个源码、测试和文档文件，
未包含 `.github/workflows` 直接修改。调用被拒绝，唯一返回原文为 `user rejected MCP tool call`，未给出具体原因。
因此没有创建或推送远端提交，也没有触发本轮 Actions。此结果不能解释成 GitHub App 的 Workflows 权限不足，
因为执行尚未到 App job 或其 `git push`。

拒绝后通过只读 API 再次核实：开发分支仍为 `8bd89f2d59e582040d88ae52ef1b253beff3d33e`，
main 仍为 `87409c0bf9c957ef113f84c176c5a1529c27b9df`。本轮修复保存在本地阶段提交中，
待允许该具体 GitHub 写入后续传；不改 App/Secrets，也不换写入通道绕过拒绝。

恢复后的顺序是：推送已测试的开发分支提交；核对现有 App 对 `rust-core.yml` 的真实自动提交和内容哈希；
等待该提交的 Linux/macOS/Windows 与公网结果；把准确提交、Actions URL、失败或跳过原因补入本文件。

## 下一阶段与未完成项

优先把自动组候选真正接入 IR/模块树/原生探测/会话快照，做独立 HTTP/HTTPS 选择与失效回归；然后补 SOCKS4 订阅与 Qt 映射。
WS 高级扩展（early data、额外请求头、压缩、多路复用）、gRPC/XHTTP、REALITY/Vision、VMess/SS2022、QUIC、智能 MRS、
DNS 分流、TUN/LAN、完整订阅执行、私有节点及长期弱网验收仍未完成。本轮不把这些未完成项改成静默降级。

## 主规范

- [RFC 6455：分片、控制帧、Ping/Pong、Close](https://www.rfc-editor.org/rfc/rfc6455)
- [Tokio 有界发送与背压](https://docs.rs/tokio/latest/tokio/sync/mpsc/struct.Sender.html#method.send)
- [Python select 可读语义](https://docs.python.org/3/library/select.html#select.select)
- [Cloudflare 官方 DoH wire-format 接口](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/)
