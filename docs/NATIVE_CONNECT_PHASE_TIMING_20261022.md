# X1.4-A7 — 原生 URLTest 连接阶段观测

URLTest 现在通过实际 Rust 连接器收集建立连接各阶段的耗时，并通过现有 C ABI v1 的 JSON 返回。原来的 `outbound_connect_ms`、`origin_tls_ms`、`response_headers_ms` 含义不变；成功结果在 `metrics.outbound_timing` 增加固定结构，失败结果在 `failure.outbound_timing` 保留已经发生的连接阶段。无效输入在调用连接器之前拒绝时，不生成连接阶段报告。

这项工作提供测速组件可使用的观测数据，不把建立 TCP/TLS/QUIC 或写出请求称为完整协议互通。官方验收同时检查独立目标收到 HEAD、客户端解析真实 HTTP 响应，以及错误凭据无法到达目标。Qt/QML 暂未新增这些字段的显示；真实动态库测试也不等于 Qt 产品验收。

## 字段语义

以下时长均使用单调时钟、单位微秒；`null` 表示本次没有执行该阶段，实际执行但不足一个微秒可以是 `0`。解析/写入阶段发生多次时累加。并行 TCP 尝试与部分嵌套阶段可能重叠，**不能将所有字段求和当作总延迟**。

| 字段 | 记录的操作及边界 |
|---|---|
| `resolution_us` | 连接器调用解析器的耗时，包含 IP literal、hosts/cache、系统解析或 DNS 的必要工作；不是纯 DNS 网络 RTT。SOCKS4 本地目标解析与节点解析均计入。 |
| `tcp_dial_us` | 解析完成后的 TCP 地址尝试调度总耗时，包含地址回退等待，不含 DNS/TLS。 |
| `tcp_connected_attempt_us` | 最终成功的 `TcpStream::connect` future 的实际耗时；不包含前面的 DNS 或其他失败地址等待，也不应标为 ICMP 延迟。 |
| `tcp_attempts` / `tcp_failed_attempts` / `tcp_cancelled_attempts` | 实际启动、返回错误、或在完成前被丢弃的 socket 尝试数。丢弃包括地址失败后的取消和尝试超时；地址值不写入报告。 |
| `proxy_tls_handshake_us` | 已建立代理 TCP 连接后的普通 TLS 握手，不包含目标网站 TLS。 |
| `reality_handshake_us` | REALITY 认证及完整 TLS 握手的调用耗时，不包括之后的 VLESS 请求。 |
| `quic_handshake_including_tls_us` | QUIC 建立过程，明确包含 TLS 1.3，以及 endpoint 初始化和地址回退。Quinn 没有提供可独立拆分的 TCP/TLS 阶段；QUIC 节点的 TCP 字段为 `null`。 |
| `transport_setup_us` | WS、HTTPUpgrade、H2、gRPC、XHTTP 或 HY2 H3 的建立调用。H2 相关传输可能延迟读取响应，因此这个字段不证明延迟响应已验证。 |
| `protocol_request_encode_write_us` | VMess、VLESS/Vision、Trojan、Shadowsocks、TUIC CONNECT 的本地请求编码与写入，以及必要的 stream/adapter 建立；不代表认证确认。 |
| `authentication_request_encode_write_us` | TUIC AUTH 的 exporter/request 编码与单向 stream 写入。TUIC 没有认证 ACK。 |
| `authentication_exchange_us` | SOCKS5 用户名密码或 HY2 的认证请求/响应交换，失败和超时也保留已经耗费的时间。 |
| `authentication_response_accepted` | 仅在 SOCKS5 认证成功响应或 HY2 HTTP 233 及相关响应字段验证后为 `true`。`false` 还可能意味着协议没有明确 ACK、本次没有观察到 ACK；不能将其一概解释为认证被拒绝。 |
| `proxy_negotiation_us` | SOCKS5 无认证方法选择。 |
| `proxy_connect_exchange_us` | HTTP CONNECT、SOCKS4/5 CONNECT 或 HY2 TCP 的明确请求/响应交换。 |
| `quic_connection_reused` | 返回的 TUIC 连接是否来自活跃连接池。普通命中不产生本次 QUIC/AUTH 时长；并发插入竞态可能先建立新连接、随后选择已有连接，此时保留真实已发生的握手/写入时长，不能把所有 `reused=true` 都概括为没有开销。 |
| `failed_operations` / `interrupted` | 被观察的内部操作返回错误的次数，以及是否存在被丢弃的未完成操作。地址回退成功时也可能存在失败或被取消的尝试，不等于整次 URLTest 失败。 |

原来的 `outbound_connect_ms` 是连接器返回时的累计耗时，包含预检、解析、传输和协议建立。`response_headers_ms` 是从开始到验证最终 HTTP 响应首部的累计耗时。只有 `origin_tls_ms` 专门记录目标网站的 TLS 阶段；该阶段在连接器 timing scope 之外，不会再次写成代理 TLS。

## 采集方式与资源边界

新增 `swirl-protocol/src/timing.rs` 使用 Tokio task-local `RefCell<ConnectTimings>`，只在显式 URLTest 的 outbound 建连 future 周围建立 scope。采集结构是固定字段、可复制的值，没有事件列表、全局日志、订阅内容、节点地址或认证凭据。没有创建新的后台任务；既有 H2/H3 driver、QUIC 心跳和系统 DNS worker 不继承该 task-local，不能污染本次观测。

所有计时包装仍等待原来的 future，原 timeout/deadline、重试、socket 调度及协议 wire 未改。未安装 scope 的普通连接不分配采集对象，也不读取计时时钟。SOCKS、TCP、TLS、REALITY、QUIC 的观测点都在 `swirl-protocol` 边界；通用 `swirl-transport::secure` 没有添加代理 TLS 观测，因此解析器内部的 DoT TLS 不会被误归为代理 TLS。

计时 guard 在 URLTest deadline 导致内部 future 被丢弃时，记录已耗费时间并标识 `interrupted`；失败快照在原 scope 内取出。公开错误类型只为该固定快照分配一个 `Box`，避免扩大所有 `Result` 的错误值；输出内容仍为固定大小，并验证序列化小于 2 KiB。

**用户主动 `probe_cancel` 保留原 API 行为**：取消运行任务、清空 metrics/failure、返回 `cancelled` 状态，不对外承诺取消瞬间的 partial 报告。失效 generation 不会把过期结果覆盖到新请求。正常的超时/协议失败则返回 partial timing。

## 实际验证

最终定点测试记录保存在 [x14-a7-timing](evidence/x14-a7-timing/metadata.json)：

- [collector tests](evidence/x14-a7-timing/collector-tests.txt)：3 个通过、0 个失败、0 个跳过。验证超时 partial、嵌套 scope 隔离、不继承到后台任务、无 scope 不采集，以及模拟时钟下 20ms 解析不混入 4ms 成功 TCP 尝试。它们是观测机制单元测试，不是协议互通证据。
- [probe focused tests](evidence/x14-a7-timing/probe-focused-tests.txt)：实际执行 API 1、Core 3、protocol 12，共 16 个通过。包含真实 loopback HTTP、真实 TLS ClientHello 后的握手超时、目标 TLS 不混入代理 TLS、失败状态保留计时，以及实际导出 C ABI 返回的有界脱敏 JSON。筛选掉的其他测试不计为已执行。
- [Clippy](evidence/x14-a7-timing/clippy.txt) 和 [构建](evidence/x14-a7-timing/build.txt) 通过。最初的 Clippy 指出扩大的错误值，已通过上述固定快照 `Box` 修正，没有关闭 lint。

独立服务端仍是既有固定官方版本：Xray 26.10.21、Hysteria 2.13.0、历史官方 TUIC server 1.0.0。新 `tools/tests/test_native_timing.py` 只复用其生命周期/证书/版本校验 helper，不继承或重复计数原有方法，也没有 Python 代理实现。

| 实际入口 | 测试结果 | 原始证据 |
|---|---|---|
| Rust Core `transport-runtime` | 3 个方法、8 次 probe，0.748 秒，全部预期断言通过 | [结果](evidence/x14-a7-timing/native-runtime-results.json)、[输出](evidence/x14-a7-timing/native-runtime-tests.txt) |
| Python ctypes → 实际 `libswirl_api.so` → 导出 C ABI v1 → Rust Core | 相同 3 个方法、8 次 probe，2.287 秒，全部预期断言通过 | [结果](evidence/x14-a7-timing/dynamic-ffi-results.json)、[输出](evidence/x14-a7-timing/dynamic-ffi-tests.txt) |

两次分别真实验证了：

1. VMess + WebSocket + TLS：目标收到 HEAD 并返回 204；独立 DNS/TCP/TLS/transport/request 阶段存在。HTTP 503 保留同一连接阶段，但 URLTest 按状态失败；错误 UUID 的目标请求数不增加。没有给 VMess 请求写入附加认证成功标签。
2. Hysteria2：QUIC 与 TLS 合并字段存在，TCP/普通代理 TLS 字段为空；HTTP 233 后 `authentication_response_accepted=true`；错误密码在认证阶段失败且不触达目标。
3. TUIC：新连接记录 QUIC 与 AUTH 写入，认证 exchange/accepted 不冒充 ACK。另用真实 echo stream 保持同一 QUIC 连接，在 probe 前后均收发 marker；随后 HEAD 记录复用，没有虚构新的 QUIC/AUTH 耗时。错误密码仍无目标 HEAD。

动态库证据记录加载文件 SHA-256 `1e0241aef55dc8f1e9bc9f0522e03516f5bb6c3bc1b7a171bf7c68c8f98e493d`、ABI 版本、输入/输出边界以及每种控制命令的调用计数。它通过的是实际共享库，不是把 Rust example 的 JSON 接口称为 C ABI。

这些微秒数来自 Linux debug loopback，只用于证明不同阶段实际存在、含义没有混淆。它们不是公网 RTT、Release 性能基准或与 Clash/Loon/Surge 的性能排名。Windows/macOS 该新 suite 的结果以对应 A7 GitHub Actions 为准；不得用本地 Linux 结果提前填写三平台通过。
