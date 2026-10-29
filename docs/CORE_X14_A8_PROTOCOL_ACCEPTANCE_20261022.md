# X1.4-A8 原生协议能力矩阵与最终验收边界

日期：2026-10-22。分支：`work/rust-native-protocols-x14a-20261022`。

**结论：X1.4-A 按本文声明的 Rust Core 原生协议子集完成验收，X1.4-B 的 Core
前置门禁已满足，可以正式启动 Qt 产品整合。Qt 产品本身尚未完成本轮验收。**

验收绑定源码提交 `21c562a7c7adc2654416636e4de2f038ffc220cd`，包括 A8 栈分派修复
和随后发现的 HTTP/3 认证收尾竞态修复。六个作业均已正式完成并成功；已读取全部
原始作业日志，并下载、解析三平台上传工件，没有以运行中状态或旧提交绿灯替代。
本文件的追加文档提交不改变这份已验收的生产代码或测试源码。

## 一、最终提交与三平台门禁

| 项目 | 最终核验结果 |
| --- | --- |
| 验收源码 SHA | [`21c562a7c7adc2654416636e4de2f038ffc220cd`](https://github.com/SOLHK/Swirl/commit/21c562a7c7adc2654416636e4de2f038ffc220cd) |
| GitHub Actions run | [39814238782](https://github.com/SOLHK/Swirl/actions/runs/39814238782)，`completed / success`，六作业全部成功 |
| Windows Hysteria2 原有 17 个方法 | **17 实跑、17 通过、0 失败、0 错误、0 跳过**；上传工件含 41 条客户端执行记录 |
| Linux 1 MiB 实测主线程栈下原有 17 个方法 | **17/17，零跳过**；41 条客户端记录的实际 soft/hard `RLIMIT_STACK` 均为 **1,048,576 字节** |
| 三平台生命周期取消、释放、同运行时重连 | 均成功；pending 连接任务 2→0，认证后取消任务 3→0，同运行时重连 64 KiB、正常关闭后 0 任务；独立目标 2 条连接均关闭、0 活跃 |
| X1.4-A Core 范围关闭 | **可以关闭本文声明的 Core 范围**；不包含第六节扩展缺口、上游限制及 Qt 产品验收 |
| X1.4-B 正式启动 | **可以启动**；先整合第七节已核实其他分支成果，再完成当前新增协议产品链 |

| 平台 | Rust 门禁作业 | 官方互通作业 | 动态库 C ABI 步骤 | 原始作业链接 |
| --- | --- | --- | --- | --- |
| Windows | 全部成功；645 项测试通过、0 失败、0 忽略 | 成功；HY2 原 17/17、生命周期通过 | 6/6，实际加载本次 DLL；源码身份一致 | [Rust](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948382878) / [官方互通](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948383479) |
| macOS | 全部成功；644 项测试通过、0 失败、0 忽略 | 成功；HY2 原 17/17、生命周期通过 | 6/6，实际加载本次动态库；源码身份一致 | [Rust](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948383323) / [官方互通](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948383364) |
| Linux | 全部成功；644 项测试通过、0 失败、0 忽略 | 成功；默认与 1 MiB HY2 各 17/17、两种生命周期通过 | 6/6，实际加载本次动态库；源码身份一致 | [Rust](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948383253) / [官方互通](https://github.com/SOLHK/Swirl/actions/runs/39814238782/job/119948383611) |

完整完成状态、方法名、日志摘要、下载工件 SHA256、实际栈限额、生命周期计数与
动态库身份保存在 [最终代码 CI 收据](evidence/x14-a8/ci-auth-fix-39814238782.json)。
Linux 专用的额外受限栈步骤在 Windows/macOS 上按平台条件不运行；这些平台原有
17 个方法全部实际执行，没有跳过失败项。Windows 栈参数未增大。

新加的四个真实 QUIC/HTTP3 认证收尾回归也在三平台全部通过。原版、b6 补丁和
最终栈分派修复的同工具链比较见 [栈回归记录](CORE_X14_A8_STACK_REGRESSION_20261022.md)。
实测修复解决了 1 MiB / 768 KiB 场景；更小栈仍有失败边界，不能宣称任意小栈安全。

对应工作流：[rust-native-protocols.yml](../.github/workflows/rust-native-protocols.yml)。
六个作业为 `native-protocols` 和 `official-interop` 各乘三个操作系统；C ABI 是
官方互通作业内的实际步骤，不是另外三个独立作业。以上六作业均属于同一验收 SHA，
没有拼接不同提交的绿灯。Rust 门禁为以下四项：

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

## 二、状态定义

- **实现完成（限定子集）**：源码中存在可执行配置、校验和连接器，不代表所有扩展。
- **历史官方互通记录**：仓库已有固定官方服务端的真实数据、认证及失败证据；记录
  绑定其自己的源码/二进制身份，不能证明后续提交通过。
- **本轮 CI 通过**：第一节已核实的源码 SHA、完成作业及原始日志所覆盖的组合。
- **Qt 产品验收通过**：需要实际 Qt 导入、加密保存/重载、节点选择、启动、真实数据、
  切换、停止及正确错误显示。本轮 Core/C ABI 套件不等价于此状态。
- **尚未测试**：有实现或测试源码，但本文没有该组合本轮执行证据。
- **明确不支持**：校验器拒绝，或不存在原生执行器；不得降级后算作支持。

所有官方互通测试均由 Swirl Rust 执行代理客户端和 Core 转发。Xray、Hysteria、
TUIC、shadowsocks-rust 仅为隔离的独立服务端。Python 提供独立应用目标和测试控制。
这些回环证据不代表真实供应商节点、公网/弱网长稳、用户物理 Windows 或 TUN 验收。

## 三、八协议能力矩阵

“实现”与“历史”均限于该行及后文列明的组合；官方互通列的 A8 通过结论绑定第一节。

| 协议 | 导入 | 原生配置 | 握手/认证 | 双向收发 | 官方互通 | Qt 产品验收 |
| --- | --- | --- | --- | --- | --- | --- |
| HTTP CONNECT | 通用订阅子集、Xray JSON 映射已实现；Xray 导入链有官方测试 | `HttpConnect`，认证及可选代理 TLS | CONNECT / Basic 认证已实现 | TCP；隧道内 HTTP/HTTPS、2 MiB 双向有测试 | Xray plain HTTP CONNECT 有历史记录；A8 **通过**。代理端 HTTPS CONNECT 不能由目标 HTTPS 推出 | 本轮未验收；旧投影可接受基础协议，仍需最终产品链复测 |
| SOCKS5 | 通用订阅子集、Xray JSON；plain Xray SOCKS 导出开启 UDP | `Socks5`，认证、可选 TLS、UDP | 无认证/用户名密码和 UDP ASSOCIATE 已实现 | TCP/UDP、DNS、IPv6、切换/重连有测试 | Xray plain SOCKS5 TCP/UDP 有历史记录；A8 **通过** | 本轮未验收；基础协议已在旧投影白名单，不能推出当前全链路通过 |
| Shadowsocks | 经典 AEAD 和 SIP022 AES 子集；Clash/SS URI/Xray 映射 | `Shadowsocks`；三种经典 AEAD、两种 2022 AES | 密钥、认证帧、2022 会话绑定已实现 | TCP/UDP；4 MiB、DNS、IPv6、篡改/重放、重连有测试 | 固定 shadowsocks-rust 有历史记录；A8 **通过** | 本轮未验收；Qt 仍只接受三种经典 AEAD，2022 AES 投影阻断 |
| Trojan | 通用 TCP/WS 子集、Xray JSON；增强传输由 Xray 映射保留 | `Trojan`，TLS 必需；持久化增强传输、经典 UDP | TLS/密码/请求已实现 | TCP 与 command 3 UDP；传输组合见下表 | 固定 Xray 有历史记录；A8 **通过**，仅工作流内组合计本轮覆盖 | 本轮未验收；Qt 增强传输和 Trojan UDP 尚未接入 |
| VLESS | 通用 TCP/WS/REALITY 子集、Xray JSON | `Vless`，TLS/REALITY、限定 Vision、增强传输、经典 UDP | UUID、适用 TLS/REALITY/Vision 已实现 | TCP 与 command 2 UDP；无 Vision UDP/XUDP 支持 | 固定 Xray 有历史记录；A8 **通过**，仅工作流内组合计本轮覆盖 | 本轮未验收；Qt 增强传输和 VLESS UDP 尚未接入 |
| VMess AEAD | Clash、VMess URI、Xray JSON 的现代 AEAD 子集 | `Vmess`；`alterId=0`，AES128/ChaCha，`auto` | 现代 AEAD 认证、TLS/WS 分层已实现 | TCP/TLS/WS/WSS；4 MiB 四传输及 TCP/TLS 64 MiB 有测试；UDP 不支持 | 默认 13 方法有历史通过记录；A8 **通过**；另外 2 个严格目标半关闭方法仍为未通过限制 | 本轮未验收；Qt 执行投影拒绝 VMess |
| Hysteria2 | Clash、`hy2://` / `hysteria2://` | `Hysteria2`；TLS、pin、Salamander、带宽、UDP | QUIC/TLS、HTTP/3 密码认证已实现；A8 认证响应竞态已修复并随最终源码验收 | TCP/UDP、DNS、4 MiB、IPv6、重连/并发有测试；部分上游限制保留 | 原 17 方法及新增生命周期门禁；A8 **通过**。17 方法包含限制探针 | 本轮未验收；Qt 执行投影拒绝 Hysteria2 |
| TUIC v5 | Clash、TUIC URI 及已映射的原始对象字段 | `Tuic`；UUID/密码、TLS、pin、relay、拥塞/心跳 | v5 TLS exporter 认证已实现 | TCP、UDP native/quic 两模式、分片/DNS、IPv6、重连；历史对端空包限制保留 | 固定历史官方 v1.0.0 参考端 9 方法有记录；A8 **通过** | 本轮未验收；Qt 执行投影拒绝 TUIC |

实现主源：[`Outbound` / 配置校验](../core/crates/swirl-subscription/src/lib.rs)、
[通用导入](../core/crates/swirl-subscription/src/inspect.rs)、
[Xray 原生投影](../core/crates/swirl-subscription/src/xray/convert/native.rs)、
[统一连接器](../core/crates/swirl-protocol/src/lib.rs)、
[Core UDP 分派](../core/crates/swirl-core/src/lib.rs)。

必须保留两个导入边界：

1. Xray 原生投影的 VLESS、Trojan、Shadowsocks 当前设 `udp: false`；plain SOCKS5
   设 `udp: true`。协议连接器具备 UDP 能力，不等价于所有格式导入都自动启用它。
2. gRPC/H2/HTTPUpgrade/XHTTP 的持久化导入来自 Xray/V2Ray JSON 映射。通用
   Clash/URI `inspect` 路径对未实现的非 TCP/WS 参数仍会拒绝。不能把已有增强
   传输连接器解释为所有订阅格式都已无损适配。

## 四、VLESS / Trojan / VMess 组合矩阵

本节“有实现”不自动表示本次官方 CI 已执行。`N` 指 native 六作业所安排的真实
官方测试；`T` 指另一个 transport 工作流有测试源码，本轮 native 工作流不运行它。
具体执行结果仍以第一节为准。

| 协议层组合 | VLESS | Trojan | VMess AEAD | 本轮 native / 另行 transport 验收范围 |
| --- | --- | --- | --- | --- |
| TCP 无外层 TLS | 有实现 | 明确要求 TLS | 有实现 | N：VMess TCP、VLESS 经典 UDP；T：VLESS TCP 的应用 HTTP/HTTPS 全项 |
| TCP + TLS | 有实现 | 有实现 | 有实现 | N：VMess TCP、VLESS/Trojan 经典 UDP；T：VLESS/Trojan 应用 HTTP/HTTPS 全项 |
| WS 无 TLS | 有实现 | 明确要求 TLS | 有实现 | N：VMess TCP、VLESS UDP；T：VLESS 应用 HTTP/HTTPS |
| WSS | 有实现 | 有实现 | 有实现 | N：VMess TCP、VLESS/Trojan UDP；T：VLESS/Trojan 应用 HTTP/HTTPS |
| gRPC + TLS | 有实现 | 有实现 | 明确不支持 | N：两协议导入→普通 Core→HTTP/HTTPS、4 MiB、UDP；T：更完整 gRPC 模式/故障集 |
| gRPC 明文 h2c | 有实现 | 不接受无 TLS Trojan | 明确不支持 | T：VLESS Tun/TunMulti；本轮 N 不覆盖该明文组合 |
| legacy HTTP/2 + TLS | 有实现 | 有实现 | 明确不支持 | N：VLESS 导入、数据、关闭；T：两协议，固定 Xray v1.8.24 |
| legacy HTTP/2 明文 | 明确不支持 | 明确不支持 | 明确不支持 | `Http2TlsRequired`，不以 h2c gRPC 代替 |
| HTTPUpgrade | 明文/TLS 有实现 | TLS 有实现 | 明确不支持 | N：VLESS TLS 导入、数据、关闭；T：VLESS 明文/TLS、Trojan TLS |
| XHTTP `stream-one` | h2c/TLS 有实现 | TLS 有实现 | 明确不支持 | N：VLESS TLS 导入、数据、关闭；T：VLESS h2c/TLS、Trojan TLS |
| REALITY + TCP | 有实现 | 不支持 | 不支持 | N：Rustls / Chrome133 官方 Core profile |
| REALITY + gRPC | 有实现 | 不支持 | 不支持 | T：Tun/TunMulti、HTTP/HTTPS、取消和负向；本轮 N 未执行 |
| REALITY + XHTTP `stream-one` | 有实现 | 不支持 | 不支持 | T：HTTP/HTTPS、大数据、取消和负向；本轮 N 未执行 |
| REALITY + WS/H2/HTTPUpgrade | 明确不支持 | 不支持 | 不支持 | `RealityTransportUnsupported` |
| REALITY TCP + `xtls-rprx-vision` | 有实现 | 不适用 | 不适用 | N：Rustls / Chrome133，TLS1.3 Direct 与内层认证关闭等 |
| 普通 TLS + Vision | 明确不支持 | 不适用 | 不适用 | `VisionCombinationUnsupported` / `VlessFlowUnsupported` |
| Vision + WS/gRPC/XHTTP | 明确不支持 | 不适用 | 不适用 | `VisionTransportUnsupported` |
| Vision UDP / XUDP | 明确不支持 | 无对应验收 | UDP 不支持 | 经典 VLESS/Trojan UDP 不能作为 XUDP 证据 |

边界由 [协议传输校验](../core/crates/swirl-protocol/src/transport.rs)、
[持久化传输校验](../core/crates/swirl-subscription/src/stream_transport.rs)、
[Xray 安全/传输映射](../core/crates/swirl-subscription/src/xray/security.rs) 共同约束。
持久化 `StreamTransport` 适用于 VLESS/Trojan；VMess 仅接受 TCP 或 WebSocket。

## 五、本轮工作流与测试源码的对应关系

| 固定服务端套件 | native 工作流入口 | 已定义的主要断言 |
| --- | --- | --- |
| HTTP / SOCKS | [test_basic_proxies_xray.py](../tools/tests/test_basic_proxies_xray.py)，8 方法 | Xray 导入、HTTP Basic/SOCKS 认证、TCP/UDP/DNS、2 MiB、IPv6、切换、重连；另覆盖 SOCKS4/4a |
| VMess | [test_vmess_xray.py](../tools/tests/test_vmess_xray.py)，默认 13 方法 | 四种传输、AES/ChaCha、4 MiB、64 MiB、错误 UUID/CA/SNI、导入、并发、切换 |
| Hysteria2 | [run_hysteria2_official.py](../tools/tests/run_hysteria2_official.py) → [原 17 方法](../tools/tests/test_hysteria2_official.py) | 完整方法数、零跳过；TCP/UDP/DNS/TLS/pin/Salamander/带宽/重连/IPv6/并发及限制探针；Linux 另以实测 1 MiB 主栈执行 |
| Hysteria2 生命周期 | [test_hysteria2_lifecycle.py](../tools/tests/test_hysteria2_lifecycle.py)，1 方法 | pending future drop、认证后取消、任务回到基线、同 runtime 重连和目标真实关闭；Linux 另以 1 MiB 执行 |
| TUIC v5 | [test_tuic_reference.py](../tools/tests/test_tuic_reference.py)，9 方法 | 4 MiB、错误 UUID/密码/TLS/pin、两种 UDP、65,507 字节、DNS、导入、IPv6、重连/并发及空包限制 |
| QUIC Core | [test_quic_core.py](../tools/tests/test_quic_core.py)，6 方法 | 原生入口 TCP/UDP/DNS/HTTPS、认证负向、旧连接保持、新节点选择、重启、TUIC 心跳/DNS 代次 |
| 动态 C ABI | [test_quic_ffi.py](../tools/tests/test_quic_ffi.py) | 实际加载本次构建动态库并运行 Core 套件，记录库身份；不是 Qt QLibrary/Swirl.exe 验收 |
| 分阶段计时 | [test_native_timing.py](../tools/tests/test_native_timing.py)，3 方法 | VMess WSS、HY2 认证响应/拒绝、TUIC 认证写入/连接复用语义 |
| Xray 传输导入 | [test_imported_transports_xray.py](../tools/tests/test_imported_transports_xray.py)，5 方法 | VLESS gRPC/H2/HTTPUpgrade/XHTTP、Trojan gRPC 的 TLS 组合；未修改原生导出配置即启动 Core，4 MiB、HTTP/HTTPS、负向及正常关闭 |
| VLESS/Trojan UDP | [test_stream_udp_xray.py](../tools/tests/test_stream_udp_xray.py)，8 方法 | VLESS raw/TLS/WS/WSS/gRPC TLS；Trojan TLS/WSS/gRPC TLS；DNS/IPv6、节点切换、关闭/重连、官方回包边界 |
| SS2022 / 经典 AEAD | [test_ss2022_official.py](../tools/tests/test_ss2022_official.py)，12 方法 | 2022 AES128/AES256、TCP/UDP、4 MiB、重放/篡改、导入、重启、经典三种 AEAD 回归 |
| REALITY / Vision | [test_reality_native_release.py](../tools/tests/test_reality_native_release.py)，四个 profile 入口 | Rustls、Chrome133，各带/不带 Vision；正式 Core、官方 Xray、认证负向、应用数据与关闭 |

另一个 [rust-transport.yml](../.github/workflows/rust-transport.yml) 的 push 分支为
`work/xray-v2ray-transport-20261022`，安排 TCP/WS、gRPC、legacy H2、HTTPUpgrade、
XHTTP、Core 传输选择、TLS policy、REALITY 增强传输等完整套件。测试源码包括：

- [test_transport_c1_xray.py](../tools/tests/test_transport_c1_xray.py)
- [test_transport_grpc_xray.py](../tools/tests/test_transport_grpc_xray.py)
- [test_transport_http2_xray.py](../tools/tests/test_transport_http2_xray.py)
- [test_transport_http_xray.py](../tools/tests/test_transport_http_xray.py)
- [test_transport_xhttp_xray.py](../tools/tests/test_transport_xhttp_xray.py)
- [test_transport_reality_xray.py](../tools/tests/test_transport_reality_xray.py)

它们未由本轮 native 六作业自动执行。只读取这些文件，或引用其历史记录，不能把
Trojan H2/HTTPUpgrade/XHTTP、REALITY gRPC/XHTTP 等组合记为本轮三平台 CI 已通过。

## 六、原有测试通过后仍必须保留的限制

### 官方对端限制及未通过的关闭语义

1. **Hysteria2** 原 `test_12_record_official_server_limitations_without_claiming_support`
   特意检验两项失败：目标等待上传半关闭时返回 `TcpTruncated`；4096 字节 UDP
   请求到达目标，但官方回包超时。17 方法全部符合预期，仍不能宣称这两组合通过。
2. **VMess** `--strict-half-close` 选择另一个 2 方法类；历史严格目标半关闭仍失败，
   不属于默认 13 方法绿灯。应用自行完成响应后的关闭与目标等待客户端 EOF 是不同
   行为。保留 [原失败记录](VMESS_SS2022_NATIVE_X14A_20261022.md)。
3. **TUIC** 历史官方 v1.0.0 对端在零长度 UDP 回包 framing 中退出。
   `test_historical_reference_empty_reply_limitation_is_recorded` 记录该现象，
   `native_interoperability_pass` 为 false，不能把负向探针算作空包互通成功。
4. **VLESS/Trojan 经典 UDP** 固定 Xray 的 IPv4 回包载荷已测边界分别为 8190 / 8181
   字节；再大 1 字节目标能收到而回复丢失。这是该官方对端/组合的边界，不可宣称
   任意 UDP 最大载荷均已验收。
5. **HTTP/SOCKS 的 TLS 层** `test_basic_proxies_xray.py` 使用无代理 TLS 的官方
   Xray 入站。其 HTTP/HTTPS 用例中的 HTTPS 指隧道内目标 TLS；它没有证明
   HTTPS CONNECT 或 SOCKS5-over-TLS 的官方互通。源码存在这类 TLS 包装，
   本轮这些代理端 TLS 组合应记为尚未测试。

### 明确未实现或被拒绝的扩展

| 范围 | 明确边界 | 权威源码 |
| --- | --- | --- |
| VMess | 非零 alterId、旧 CFB、none/zero、UDP、global-padding、authenticated length、未支持指纹/early data、增强 HTTP 传输和 REALITY | [vmess 配置](../core/crates/swirl-subscription/src/vmess.rs)、[协议校验](../core/crates/swirl-protocol/src/transport.rs) |
| SS2022 | ChaCha 变体、SIP023 identity chain、2022 外部混淆组合 | [ss2022 配置](../core/crates/swirl-subscription/src/ss2022.rs) |
| Hysteria2 | 端口跳跃/多端口切换、ECH、Salamander 之外的 obfs | [hysteria2 配置](../core/crates/swirl-subscription/src/hysteria2.rs) |
| TUIC | v4/token、reduce-rtt、disable-sni、fast-open、udp-over-stream=true、未映射扩展 | [tuic 配置](../core/crates/swirl-subscription/src/tuic.rs) |
| SOCKS5 | TLS 控制通道上的 UDP | [Config 校验](../core/crates/swirl-subscription/src/lib.rs) |
| XHTTP | auto、packet-up、stream-up、HTTP/3、downloadSettings、xmux 等未映射选项 | [stream transport](../core/crates/swirl-subscription/src/xray/stream_transport.rs) |
| HTTP/2、HTTPUpgrade | legacy H2 无 TLS、多 host 等未映射选项；HTTPUpgrade early data | [stream transport](../core/crates/swirl-subscription/src/stream_transport.rs) |
| REALITY / Vision | 任意未支持指纹、spiderX、REALITY WS/H2/HTTPUpgrade、普通 TLS Vision、Vision 增强传输、Vision UDP/XUDP | [REALITY 配置](../core/crates/swirl-subscription/src/reality.rs)、[传输校验](../core/crates/swirl-protocol/src/transport.rs) |
| 其他协议 | SSR、Hysteria v1、AnyTLS、NaiveProxy、Snell、Mieru、WireGuard、SSH 没有本分支原生 Outbound 执行器 | [`Outbound`](../core/crates/swirl-subscription/src/lib.rs) |

此外，长时间/弱网/休眠恢复、真实供应商全量、非当前目标平台、所有协议组合的
统一性能上限均未由本工作流全面验收。VMess 保留 nonce 计数上限和显式耗尽错误，
64 MiB 实测不能解释为任意长流量均可无界运行。

## 七、X1.4-B 的明确边界

Qt 逐项审计和接续工作见
[CORE_X14_A8_QT_HANDOFF_20261022.md](CORE_X14_A8_QT_HANDOFF_20261022.md)。
该文核查实际 `NodeImportService`、`NodeImporter`、`NodeStore`、`RustCoreEngine`、
`EngineController`、QML、CMake、C ABI，不以 Core 绿灯替代产品验收。

当前已经存在 C ABI `start/configure/select/select_group/stop`、Rust 动态库加载及
旧协议的 Qt 转换路径，但仍须在 X1.4-B 完成：

1. Qt 导入/编辑衔接 Rust 权威转换，并将完整私密原生配置保存在节点模型中，
   经过 DPAPI 保存/销毁/重载后字段、能力和诊断不丢失。
2. VMess/Hysteria2/TUIC、SS2022、VLESS/Trojan UDP 和增强传输的 Qt 执行映射；
   节点列表能显示协议不等价于可执行。
3. 实际 Qt A/B 节点切换、配置更新失败回滚、旧活动连接保持，认证/TLS/超时/取消
   正确显示；修复 Settings 启动入口清空选择的源码问题并实测两种启动入口。
4. 显式 Rust 构建/打包，运行真正 Swirl.exe 的 QLibrary 路径，核对 DLL 身份、ABI、
   缺失/不兼容错误和进程/流量路径。
5. 核对独立 R1 替换分支后整合旧引擎清理：本分支仍有兼容构建源码和默认选项，
   Rust 模式没有自动 Mihomo 回退不等于整个产品包已清除旧路径。
6. 实际产品系统代理恢复、已支持 DNS/规则分流与生命周期。TUN、LAN、网关等
   当前明确未接入/拒绝的产品能力单列，不能由 QUIC TCP/UDP 通过推出。

正式启动 X1.4-B 的 Core 前置门禁已由第一节六作业完成。即使 X1.4-A 按已声明 Core 范围
关闭，也不应使用“所有订阅导入后直接联网”或“Qt 产品已经完整可用”的表述。

### 已核实、应复用的其他分支成果

以下为固定 SHA 下的只读源码核查，没有合并或改动其他窗口；也没有重新核验这些
分支的全部 CI。上文 Qt 缺口描述限定于本 X14 分支，不能推广为全仓库从零缺失。

| 分支与核实 HEAD | 已有实现 | X1.4-B 整合边界 |
| --- | --- | --- |
| `work/rust-core-full-replacement-20261022` / [`5d96214ac80d63985cdccf4942c3c1d79035e793`](https://github.com/SOLHK/Swirl/commit/5d96214ac80d63985cdccf4942c3c1d79035e793) | 已删除实际旧引擎实现；CMake 强制 Rust；`RustCoreLibrary` 校验 PE 架构、ABI、`swirl_core_build_info` 的 build ID/source SHA 与 EXE 配对 | 复用清理和加载器；需把 Rust 导出、构建 ID 生成、CMake 配对一起整合。该分支 Qt 白名单仍是旧七协议，未完成 VMess/HY2/TUIC 接入 |
| `work/xray-v2ray-qt-import-20261022` / [`506014d6386610411f48c939ab62cb93a3509431`](https://github.com/SOLHK/Swirl/commit/506014d6386610411f48c939ab62cb93a3509431) | 已有 `XrayJsonBridge`、`swirl_import_xray_v1`、私有 nativeOutbound/sourceDocument、DPAPI 源文档保存、每次执行前 Rust 重验证 | 复用 Xray JSON 桥接架构；该分支 Rust Outbound 尚无 VMess/HY2/TUIC，也没有 X14 增强字段；HY2/TUIC URI、Clash 等还需衔接 |
| `work/x13-a-protocol-runtime-20261022` / [`fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870`](https://github.com/SOLHK/Swirl/commit/fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870) | 所核查 Qt 关键文件仍为旧投影、Rust 默认 OFF，没有新增 nativeOutbound/导入桥 | 其传输历史记录不能替代当前新协议 Qt 产品验收 |

X1.4-B 应先整合前两条已完成路径，再补齐本轮协议、其余订阅格式、错误呈现与
实际产品验收。不得重新实现已有旧内核删除、DLL 身份校验或 Xray JSON 桥接。

## 八、固定对端与历史证据索引

| 对端 | 固定版本 / commit | 锁定来源 |
| --- | --- | --- |
| Xray 当前 | v26.10.21 / `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` | [transport-peer-lock.json](../tools/tests/transport-peer-lock.json) |
| Xray legacy H2 | v1.8.24 / `6baad79f9881ee2cf75bdc825b3e2e92b289477a` | 同上 |
| Hysteria2 | app/v2.13.0 / `ca8fbd874fd6ca82413948de6dc5924405e103e1` | [native-protocol-peer-lock.json](../tools/tests/native-protocol-peer-lock.json) |
| TUIC 历史官方参考 | tuic-server-1.0.0 / `a299ef02d9f4ab5a0edbf58b9998f41bf768b332` | 同上 |
| shadowsocks-rust | v1.25.0 | [ss2022-peer-lock.json](../tools/tests/ss2022-peer-lock.json) |

上述 lock 包含平台下载物 SHA256；版本和对端不能在失败后静默更换。

- [A8 栈问题、A7/b6 原失败、本地受限栈和生命周期证据](CORE_X14_A8_STACK_REGRESSION_20261022.md)
- [VMess / SS2022 历史互通及严格半关闭失败](VMESS_SS2022_NATIVE_X14A_20261022.md)
- [Hysteria2 历史互通](HYSTERIA2_NATIVE_INTEROP_20261022.md)
- [TUIC 历史互通](TUIC_NATIVE_INTEROP_20261022.md)
- [导入传输的历史互通](IMPORTED_TRANSPORT_NATIVE_INTEROP_20261022.md)
- [HTTP / SOCKS 官方互通](HTTP_SOCKS_OFFICIAL_INTEROP_20261022.md)
- [REALITY / Vision 回归](REALITY_VISION_NATIVE_REGRESSION_X14A_20261022.md)
- [Qt 产品交接](CORE_X14_A8_QT_HANDOFF_20261022.md)

历史报告中的通过数字只描述其原有构建。本轮 Windows 栈修复和三平台六作业
成功结论仅绑定第一节的最终源码与实际证据；历史 Qt 或其他传输分支记录没有
被提升为本轮产品或组合验收。

## 九、分阶段提交与修改文件

每个阶段在编辑前核对指定分支远端 HEAD；均使用非强制、带预期父提交的更新。
没有修改 main、重写远端历史、覆盖其他工作区，或重新实现已完成的协议。

### 阶段一：公共连接器栈帧分离与长期受限栈门禁

提交：[5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611](https://github.com/SOLHK/Swirl/commit/5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611)。
CI：[39804698115](https://github.com/SOLHK/Swirl/actions/runs/39804698115)，六作业全部成功。
Linux/macOS Rust 各640项、Windows 641项；Windows HY2原17方法全部通过。

解决：QUIC进入大型混合协议poll栈帧造成的Windows栈溢出；同时修正HTTPUpgrade
负向用例对Windows 10053的异常分类。未扩大栈、超时或减少数据；错误认证仍不得到达目标。
新增1 MiB真实官方联网、严格17方法/零跳过、取消释放及同运行时重连门禁。
遗留：本地全套复测随后发现独立HTTP/3认证收尾竞态，进入阶段二；Qt产品未验收。

实际修改文件：

```text
.github/workflows/rust-native-protocols.yml
core/crates/swirl-protocol/examples/hysteria2-lifecycle.rs
core/crates/swirl-protocol/src/lib.rs
docs/CORE_X14_A8_QT_HANDOFF_20261022.md
docs/CORE_X14_A8_STACK_REGRESSION_20261022.md
docs/evidence/x14-a8/hy2-a8-small-stack.json
docs/evidence/x14-a8/hy2-lifecycle-default.json
docs/evidence/x14-a8/hy2-lifecycle-small-stack.json
docs/evidence/x14-a8/local-regression.json
tools/tests/native_client_stack.py
tools/tests/run_hysteria2_official.py
tools/tests/test_hysteria2_lifecycle.py
tools/tests/test_hysteria2_official.py
tools/tests/test_imported_transports_xray.py
```

测试命令及原版/修复版实测差异见
[栈回归记录](CORE_X14_A8_STACK_REGRESSION_20261022.md)；CI原始作业结论见
[阶段一收据](evidence/x14-a8/ci-stack-fix-39804698115.json)。

### 阶段二：HTTP/3正常停止请求方向时保留认证响应

提交：[21c562a7c7adc2654416636e4de2f038ffc220cd](https://github.com/SOLHK/Swirl/commit/21c562a7c7adc2654416636e4de2f038ffc220cd)。
CI：[39814238782](https://github.com/SOLHK/Swirl/actions/runs/39814238782)，最终结果绑定第一节。

解决：仅精确处理请求流的RemoteTerminate(H3_NO_ERROR)，继续严格读取认证响应。
错误密码、非233状态、认证头、其它终止码、连接错误和截止时间均保持原校验。
官方对端确定性对照从0/12正确结果变为12/12；无诊断延迟的生产构建120/120通过。
四个新增真实QUIC/H3回归通过；本地四门禁644项全过；原17方法默认与1 MiB均全过；
取消重连、TUIC、Core、动态C ABI和计时亦重新实际执行通过。

实际修改文件：

```text
core/crates/swirl-protocol/src/hysteria2.rs
core/crates/swirl-protocol/src/hysteria2/authentication_tests.rs
docs/CORE_X14_A8_AUTH_FINISH_20261022.md
docs/evidence/x14-a8/auth-delayed-after.json
docs/evidence/x14-a8/auth-delayed-before.json
docs/evidence/x14-a8/auth-finish-regression.json
docs/evidence/x14-a8/ci-stack-fix-39804698115.json
docs/evidence/x14-a8/hy2-auth-fixed-default.json
docs/evidence/x14-a8/hy2-auth-fixed-small-stack.json
```

命令、源码/可执行文件哈希、原始失败和修复后回执见
[认证收尾修复记录](CORE_X14_A8_AUTH_FINISH_20261022.md)。
剩余范围：第六节的明确协议扩展/上游限制，以及第七节的Qt产品接入。

### 阶段三：最终验收与X1.4-B交接

在阶段二六作业完成后整理本文件、最终CI收据与继续开发入口，仅追加文档证据。
生产代码和测试源码保持阶段二身份；文档提交触发的独立CI以GitHub检查结果及最终
交付答复为准。该阶段不把Qt源码审计或历史其他分支结果升级为当前产品验收。
