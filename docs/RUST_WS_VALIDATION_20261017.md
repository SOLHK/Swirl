# Rust WebSocket 修复与接手验收（2026-10-17）

本轮开发分支：`work/core-completion-20261017`。接手基线为 `8bd89f2d59e582040d88ae52ef1b253beff3d33e`；
main 为 `87409c0bf9c957ef113f84c176c5a1529c27b9df`，本轮不改 main。此文区分源码、编译、独立网络对端、
Qt 配置映射、公网目标及私有节点，不把一个层级的结果代替另一个层级。

修复源码已推送为 [`510c62ade64418c76241bbe76ae118c5040dad92`](https://github.com/SOLHK/Swirl/commit/510c62ade64418c76241bbe76ae118c5040dad92)，
其 Git tree `9a04e97bb170d717be031019bc1adceb8c92c1a7` 与本地已验证提交 `f0ed42f` 完全一致。
现有 App 随后提交 [`a60c446fdb54c10753c2d367752c4e0275a89922`](https://github.com/SOLHK/Swirl/commit/a60c446fdb54c10753c2d367752c4e0275a89922)，仅更新 Rust CI 工作流。

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
以及 12 类危险/不支持参数拒绝与输出原子性。本地没有 Qt SDK；本轮 Windows CI 已完成这些测试目标的构建及运行，
但配置测试通过仍不能称已验证 Qt WS 真实转发。

## 第一阶段远端 CI 结果

[Swirl Rust Core #21](https://github.com/SOLHK/Swirl/actions/runs/39029167841) 在
`a60c446fdb54c10753c2d367752c4e0275a89922` 上运行，2026-10-17 11:42:56 UTC 完成，结论为 success。

| Job | 实际结果 |
|---|---|
| [Linux](https://github.com/SOLHK/Swirl/actions/runs/39029167841/job/117385982804) | Rust 57 项、独立协议 64 项、工作流安全 11 项通过；2 项 Qt 在此平台跳过 |
| [macOS](https://github.com/SOLHK/Swirl/actions/runs/39029167841/job/117385982566) | 同上；公网按设计仅 Linux 执行，macOS 公网 step 跳过 |
| [Windows](https://github.com/SOLHK/Swirl/actions/runs/39029167841/job/117385982751) | Rust 57 项、独立协议 64 项、工作流安全 11 项通过；Qt 构建与 CTest 1/1 通过（3.09 秒） |
| Windows 后续独立 Qt 对端 | Shadowsocks HTTP obfs 与 VLESS 的两项真实 Qt 转发分别运行并通过，补足独立协议步骤先前因未构建 Qt 而跳过的两项 |

上述协议回归包括 WS 10 项，原失败的分片/Ping 测试在三平台均通过。首次公网 step 虽然 success，
存在下面单独记录的关闭错误，因此不把工作流绿色结果扩展成无错误会话的完整验收。

## 公网验证与环境边界

`tools/Verify-PublicRustCore.py` 使用固定公开目标，执行两次原生 DIRECT HTTPS HEAD（example.com、www.rust-lang.org），
以及明确 `1.1.1.1:443` bootstrap、认证名 cloudflare-dns.com 的原生 DoH 后再访问 example.com。
客户端 TLS 保持认证，DoH 由 Rust/rustls 执行，检查运行时身份和真实收发字节，不使用环境代理、私有节点或系统配置更改。

本地实际尝试失败：系统解析出现 `DnsLookupFailed`/`DnsTimeout`，明确 IP 的 DoH 出现 `DnsHttpsConnect`。
独立 Python 原生 socket 对相同域名也报 `gaierror`，因此本地环境不能作为公网成功证据。
GitHub Actions #21 的 [Linux job](https://github.com/SOLHK/Swirl/actions/runs/39029167841/job/117385982804)
已执行同一脚本。2026-10-17 11:36:23 UTC（北京时间 19:36:23），三个 HEAD 请求均完成 TLS 1.3 证书校验，
分别收到 200、301、200。原生运行时均为 `swirl-rust`，来源工作区干净。

不过，原始报告的每个会话都记录 `failed=1`、`last_error=StreamIo`。当时脚本仅要求 HTTP 状态及真实流量，
因此 CI 公网 step 返回成功；不能把这个绿色 step 当成正常关闭的完整验收。
保留 [未经改写的第一次 JSON](evidence/RUST_PUBLIC_NETWORK_20261017_INITIAL.json)，
其 binary SHA-256 为 `7e83e9b89232f4712335ca9e4d8e6f3dacbb52b5f2daefbe357055792ce132d9`。
该记录保留用于与后续严格门禁的输出比较，不覆盖或删除首次失败统计。

### 第二阶段：修复验证客户端收尾并收紧门禁

相同独立本地 TLS 源站和真实 Rust DIRECT harness 的隔离实验已确认：只读 HEAD 头后直接关闭 SSL socket，
源站报 `SSLEOFError`，原生会话以 `failed=1 / StreamIo` 结束；仅将验证客户端改为 TLS `unwrap()`、
TCP 写半关闭并读取 EOF，双方正常完成关闭且 `active=0 / failed=0 / last_error=""`。Rust relay 未修改。

最终验证器在原 45 秒总预算内完成关闭、等待 `active=0` 且连接记录全部 `ended`，
明确要求只有一条实际连接记录、接受数为 1、双向字节非零、错误计数为零、错误字符串为空，再允许整体成功。
控制通道、stop 或子进程清理出错仍会使结果失败，TLS 认证和三个固定公开目标保持不变。

在既有 `test_rust_core.py` 中新增 4 项独立 TLS/网络回归与 1 项缺失连接记录的负向检查。
完整 23 项套件先通过 22 项并跳过 1 项 Qt；补入最后的缺记录检查及源站完成事件后，最终 5 项专项再次全部通过。
最终文件共有 24 项测试。第二阶段提交为
[`c0eb2211ea646da023119e9458139d538a311000`](https://github.com/SOLHK/Swirl/commit/c0eb2211ea646da023119e9458139d538a311000)，
由 [Swirl Rust Core #22](https://github.com/SOLHK/Swirl/actions/runs/39030038029) 验证。

### 第二阶段完整 CI：三平台及 Windows Qt 通过

#22 在 `c0eb221` 上运行，于 2026-10-17 11:56:56 UTC 整体完成，结论为 success。

| Job / 验证 | 实际结果 |
|---|---|
| [Linux](https://github.com/SOLHK/Swirl/actions/runs/39030038029/job/117388485791) | Rust 57 项通过；Python 协议/验证器共 71 项，69 项通过、2 项 Qt 跳过；工作流回归 11 项通过；严格公网 3 项通过 |
| [macOS](https://github.com/SOLHK/Swirl/actions/runs/39030038029/job/117388485801) | 同样通过 Rust 57 项、Python 69 项及工作流 11 项，2 项 Qt 跳过；公网按设计不在此平台运行 |
| [Windows](https://github.com/SOLHK/Swirl/actions/runs/39030038029/job/117388485663) | 同样通过 Rust 57 项、Python 69 项及工作流 11 项；后续 Qt 构建及 CTest 1/1 通过（3.17 秒） |
| Windows 后续独立 Qt 对端 | SS HTTP obfs 与 VLESS 的两项实际 Qt 转发分别执行并通过，覆盖此前因 Qt 尚未构建而跳过的两项 |
| Windows 采集/Codex 附加套件 | 采集 23 项中 22 项通过、1 项因未提供 C++ importer 跳过；Codex 11 项中 10 项通过、1 项真实 CLI 显式 opt-in 测试跳过 |

每个平台的协议回归均包含全部 10 项 WS 测试和新增 5 项公网验证器回归。
fmt、check、Clippy `-D warnings`、locked workspace tests 与 release 构建均通过。
Qt WS 专项仍只验收映射、拒绝与 Rust ABI 配置；上述实际 Qt 转发是既有 SS/VLESS 路径。

### 严格公网验收：3 项全部通过

#22 的 [Linux job](https://github.com/SOLHK/Swirl/actions/runs/39030038029/job/117388485791) 已通过严格验证。
报告时间为 2026-10-17 11:50:27 UTC（北京时间 19:50:27）。
原始输出保存为 [VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_VERIFIED.json)，
准确提交为 `c0eb221`、工作区来源干净、运行时均为 `swirl-rust`。

| 固定公开目标与路径 | HTTP | TLS | 上传 / 下载字节 | 正常关闭 | 最终会话 |
|---|---|---|---|---|---|
| 系统 DNS → Rust DIRECT → example.com HEAD / | 200 | 认证 TLS 1.3 | 700 / 4,793 | 是 | accepted=1、active=0、failed=0 |
| 系统 DNS → Rust DIRECT → www.rust-lang.org HEAD / | 301，不跟随重定向 | 认证 TLS 1.3 | 690 / 5,386 | 是 | accepted=1、active=0、failed=0 |
| Rust 原生 DoH → DIRECT → example.com HEAD / | 200 | 认证 TLS 1.3 | 700 / 4,791 | 是 | accepted=1、active=0、failed=0 |

三个结果的 `last_error` 均为空、`recorded_connections=1`、`orderly_close=true`，控制通道和进程清理成功。
DoH 显式使用 `1.1.1.1:443`、认证名 `cloudflare-dns.com`、`/dns-query`，不回退系统 DNS。
两轮 Rust binary SHA-256 完全相同：
`7e83e9b89232f4712335ca9e4d8e6f3dacbb52b5f2daefbe357055792ce132d9`。
这是验证客户端收尾修正前后的对照，没有更换或弱化 Rust relay。

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
- 预期及远端实际更新：`c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`

### 已取得的 App 写入证据

| 证据 | 实际结果 |
|---|---|
| 修复源码提交 | `510c62a`，12 个源码、测试和文档文件，不含直接 workflow 修改 |
| [Core implementation validation #17](https://github.com/SOLHK/Swirl/actions/runs/39029146435) | job `117385925803` 已完成且 success；Rust 57 项与独立协议回归通过，App 应用/提交/推送成功 |
| App 自动提交 | `a60c446`，唯一父级为 `510c62a`，唯一文件为 `.github/workflows/rust-core.yml`，23 行新增、1 行删除 |
| 远端文件校验 | 5,789 字节，SHA-256 与预先审核结果完全相同 |
| [Swirl Rust Core #21](https://github.com/SOLHK/Swirl/actions/runs/39029167841) | `actor=swirl-core-automation[bot]`、`event=push`、`head_sha=a60c446...`，已触发三平台测试 |

以上证明现有 App 已实际写入并推送该工作流，且其 push 能触发目标 CI。无需重新配置 App 或 Secrets。
完整 #17 日志在 11:33:37 UTC 明确打印 `510c62a..a60c446 HEAD -> work/core-completion-20261017`，
被测提交为完整 `a60c446fdb54c10753c2d367752c4e0275a89922`；11:36:22 UTC 撤销短期 App Token。
App 自身推送产生的 [Core implementation validation #18](https://github.com/SOLHK/Swirl/actions/runs/39029167834)
按已有防循环条件跳过时，不应算作 Rust 测试通过；验收应读取 #17 的实际被测提交与 #21 的三平台结果。

[Core implementation validation #19](https://github.com/SOLHK/Swirl/actions/runs/39030037978)
也已在 `c0eb221` 上成功完成。更新脚本报告 `Rust CI gates already current`，
修改前后 SHA-256 同为上述 `c40f0a47...`，没有生成重复 App 提交；其 Rust 57 项、Python 协议/验证器
69 项通过、2 项 Qt 跳过，与 #22 的完整平台结果相互对应。

第一次连接器创建 tree 曾返回 `user rejected MCP tool call`。用户随后明确“始终允许”，重试已成功，
该阻塞已解除。本地旧提交 `f0ed42f` 与远端 `510c62a` 的作者/时间元数据不同，源码 tree 相同。

## 下一阶段与未完成项

优先把自动组候选真正接入 IR/模块树/原生探测/会话快照，做独立 HTTP/HTTPS 选择与失效回归；然后补 SOCKS4 订阅与 Qt 映射。
WS 高级扩展（early data、额外请求头、压缩、多路复用）、gRPC/XHTTP、REALITY/Vision、VMess/SS2022、QUIC、智能 MRS、
DNS 分流、TUN/LAN、完整订阅执行、私有节点及长期弱网验收仍未完成。本轮不把这些未完成项改成静默降级。

## 主规范

- [RFC 6455：分片、控制帧、Ping/Pong、Close](https://www.rfc-editor.org/rfc/rfc6455)
- [Tokio 有界发送与背压](https://docs.rs/tokio/latest/tokio/sync/mpsc/struct.Sender.html#method.send)
- [Python select 可读语义](https://docs.python.org/3/library/select.html#select.select)
- [Cloudflare 官方 DoH wire-format 接口](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/)
