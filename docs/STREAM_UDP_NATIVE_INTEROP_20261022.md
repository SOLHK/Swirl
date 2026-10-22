# X1.4-A6 — VLESS / Trojan 原生 UDP 与官方对端

新增 `swirl-protocol/src/stream_udp.rs` 实现经典 VLESS command 2 和 Trojan command 3 的 UDP 封装，并由统一 Core SOCKS5 UDP ASSOCIATE 入口调用。认证、TLS 和传输协商复用既有连接器；没有外部客户端代理进程。此记录针对原生配置和 Core 入口，不能代替每种订阅格式的导入验收。

## 协议边界与资源管理

VLESS 使用一次握手确定单个目标，每个包带 16 位长度；Core 的 VLESS association 以节点和目标地址共同作为键，避免把第二个目标的数据送给第一个目标。Trojan 的每个数据包包含独立地址、16 位长度、CRLF 及 payload，同一 carrier 可以发送多个目标。

参考 [Trojan 官方协议](https://github.com/trojan-gfw/trojan/blob/master/docs/protocol.md) 和固定 Xray `v26.10.21` 的 [VLESS 编码](https://github.com/XTLS/Xray-core/blob/v26.10.21/proxy/vless/encoding/encoding.go)、[Trojan 编码](https://github.com/XTLS/Xray-core/blob/v26.10.21/proxy/trojan/protocol.go)。所有非空 VLESS `flow` 在联网前拒绝；此实现不把 Vision/XUDP 改写为经典 UDP。REALITY 复用公共连接能力，但本套件没有实际执行 REALITY UDP，因此不标记该组合通过。

接收器保留部分帧及原始截止时间，使 Core 在发送分支就绪时取消接收 future 后仍能恢复读取。部分写入被取消或超时会使 carrier 进入失败状态，禁止在残缺帧后追加新包。单 payload 上限 65507 字节，接收缓存有界，部分帧超时为 5 秒；不会为每个包创建后台任务。Core 总 association 数仍受既有 16 个上限约束，关闭 SOCKS 控制 TCP 会关闭对应 UDP 生命周期。

## 实际执行与结果

环境为 Linux x86_64。独立服务端为官方 Xray `26.10.21 1b1647c`，实际二进制 SHA-256 为 `a27e3f95ab6ce270956d0cecd32eda4686a811afc71c64a6a734a3dede14883e`。服务端仅作测试对端，所有客户端流量经过 Swirl Rust Core。

`tools/tests/test_stream_udp_xray.py` 实际执行 8 个测试方法，用时 15.714 秒，全部断言通过。完整记录见 [official-results.json](evidence/x14-a6-stream-udp/official-results.json) 与 [official-tests.txt](evidence/x14-a6-stream-udp/official-tests.txt)。其中明确标记的上游限制探针不计为对应大包互通通过。

| 原生 UDP 组合 | 独立目标真实双向 UDP | TLS 校验 | 官方对端 |
|---|---|---|---|
| VLESS + TCP | 通过 | 不适用 | Xray 26.10.21 |
| VLESS + TCP + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |
| VLESS + WebSocket | 通过 | 不适用 | Xray 26.10.21 |
| VLESS + WebSocket + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |
| VLESS + gRPC + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |
| Trojan + TCP + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |
| Trojan + WebSocket + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |
| Trojan + gRPC + TLS | 通过 | 测试 CA / SNI | Xray 26.10.21 |

以上八种组合均经真正 Core SOCKS5 UDP ASSOCIATE 入口到达独立 UDP 目标，逐字节验证 37、1500、4000 字节数据。测试还覆盖：

- 经典 UDP 的 IPv4、IPv6、域名目标与真实 DNS wire 请求/响应。
- VLESS 对两个目标分开 carrier；Trojan 每包携带不同地址。
- gRPC 的原生配置内嵌 transport 与既有运行时显式 transport 两种入口都真实收发。
- 选择第二个节点不改写既有 association；关闭控制 TCP 后不继续转发。
- 旧服务端断开后不重放旧包；服务端恢复后新 association 可以收发。
- 错误 UUID、错误密码、错误 TLS SNI 均没有到达目标。
- 每个 Core 测试实例关闭后 `active == 0`，原始证据包含上传、下载和 UDP drop 统计。

没有启动 Qt，Windows/macOS 的执行状态须以各自 CI 结果另行确认。

## 官方回复大小限制

本实现的协议 parser 上限不能等同于对端支持上限。固定 Xray 使用 8192 字节公共 buffer，参见 [`common/buf/buffer.go`](https://github.com/XTLS/Xray-core/blob/v26.10.21/common/buf/buffer.go)。实际测试发现：

| 组合 | 已实际往返的最大本次测试 payload | 多 1 字节探针 |
|---|---:|---|
| VLESS + TLS，IPv4 目标 | 8190 字节 | 8191 字节到达目标，回复无法回到客户端 |
| Trojan + TLS，IPv4 目标 | 8181 字节 | 8182 字节到达目标，回复无法回到客户端 |

VLESS 回复长度占 2 字节；Trojan IPv4 回复的地址、长度和分隔符占 11 字节。超出上述大小的往返记录明确设置 `native_interoperability_pass: false`。测试套件通过表示确认了这个限制，不能表述为这些大包互通已通过。IPv6 和域名地址的 Trojan 头长度不同，本记录不推导未经实际运行的对应上限。空包、65507 字节上限和恶意帧只在本模块结构测试中覆盖，未宣称固定官方对端完成这些边界的双向互通。

## 结构测试与复现

6 个 Rust 模块测试实际通过，涵盖地址编码、完整/部分数据帧、错误分隔符、固定目标防串包、读取取消恢复以及写入取消后的失败状态，输出见 [unit-tests.txt](evidence/x14-a6-stream-udp/unit-tests.txt)。这些结构测试不替代上面的真实服务端数据测试。

```sh
cargo test --manifest-path core/Cargo.toml --locked -p swirl-protocol stream_udp::tests
cargo build --manifest-path core/Cargo.toml --locked -p swirl-core --example transport-runtime

SWIRL_TRANSPORT_RUNTIME=/absolute/path/transport-runtime \
SWIRL_TRANSPORT_CLIENT=/absolute/path/transport-client \
SWIRL_XRAY_BINARY=/absolute/path/xray-26.10.21 \
SWIRL_STREAM_UDP_EVIDENCE=/absolute/path/official-results.json \
PYTHONPATH=tools/tests python3 -m unittest -v test_stream_udp_xray
```

测试 fixture 使用临时合成身份与证书、loopback 监听、独立目标，并用 `xray run -config <临时配置>` 启动服务端。版本不符、缺失二进制或真实收发失败均使测试失败；不把 skip 或超时当成正向互通。此套件没有输出纯 TCP 延迟或公网性能结论。
