# X1.4-A：VMess 与 Shadowsocks 2022 原生运行记录

本记录覆盖 2026-10-22 在 Linux x86_64 上实际执行的 Rust Core 验证。代理客户端均为本仓库 Rust 连接器；官方 Xray 和 shadowsocks-rust 仅作为独立服务端，Python 仅提供独立 HTTP(S)、TCP、UDP、DNS 目标及密文攻击转发器。未在本记录中执行 Windows Qt 产品验收或公网节点测试。

## 已验证范围

| 协议组合 | 导入到原生配置 | 官方认证和双向数据 | 应用正常完成后的关闭 | UDP | Qt 产品 |
| --- | --- | --- | --- | --- | --- |
| VMess AEAD + TCP | 已验证 | 已验证 | 认证终止帧验证通过 | 未实现 | 未运行 |
| VMess AEAD + TLS | 已验证配置入口，TLS 单独互通 | 已验证，含严格证书与 SNI | 认证终止帧验证通过 | 未实现 | 未运行 |
| VMess AEAD + WebSocket | 已验证 | 已验证 | 认证终止帧及外层关闭通过 | 未实现 | 未运行 |
| VMess AEAD + WebSocket + TLS | 已验证配置入口，WSS 单独互通 | 已验证 | 认证终止帧及外层关闭通过 | 未实现 | 未运行 |
| Shadowsocks 2022 AES-128-GCM / AES-256-GCM | Clash、SIP002 URI、Xray 原生映射 | 两种均已验证 | 记录边界 FIN、目标半关闭通过 | 两种均已验证，含 Core SOCKS5 UDP | 未运行 |
| Shadowsocks AEAD AES-128-GCM / AES-256-GCM / ChaCha20-IETF-Poly1305 | 保留既有映射 | 三种均通过官方 TCP 回归 | 正常关闭通过 | 三种均通过 Core 到官方服务端回归 | 未运行 |

VMess 数据加密实际验证了 `aes-128-gcm` 和 `chacha20-poly1305`，`auto` 选择前者。现代 AEAD 请求只接受 `alterId=0`。非零 alterId、`none`、`zero`、CFB 和未知加密方式明确拒绝。TLS 指纹、非 Host 的 WS 请求头、early data 等不能执行的导入参数保持阻断。

Shadowsocks 2022 使用 SIP022 的精确 Base64 PSK 和 BLAKE3 会话密钥派生；任意文本密码不会被改造成 PSK。SIP023 多级 identity key、2022 ChaCha 变体和 SS2022 外部混淆插件尚未实现，明确阻断。SIP002 正式 URI 的 PSK 按百分号编码，整个 userinfo 不进行 Base64 编码。

## 实际测试

| 测试 | 结果 | 主要证据 |
| --- | --- | --- |
| VMess 协议单元测试 | 11 通过 | AEAD、HMAC 独立向量、认证终止、截断、畸形头、nonce 穷尽、恶意滴流固定期限 |
| VMess 导入单元测试 | 5 通过 | Clash / URI 严格归一化和拒绝路径 |
| `test_vmess_xray.py` | 13 通过，0 跳过，10.188 秒 | 四种传输、两种加密、错误 UUID/CA/SNI/参数、导入、节点切换、8 并发、4 MiB 与 64 MiB 流式传输 |
| VMess `--strict-half-close` | **未通过**：2 个方法，5 个失败条目 | 四种传输的目标等待客户端 EOF 情形，以及并发 WSS；完整数据 hash 正确，但认证终止或外层关闭失败 |
| SS2022 协议单元测试 | 10 通过 | 30 秒时钟窗、绑定、nonce、重放窗口、畸形帧、资源边界、记录进度期限 |
| SS2022 PSK 导入单元测试 | 2 通过 | 精确密钥长度、可选算法与 identity chain 拒绝 |
| `test_ss2022_official.py` | 12 通过，0 跳过，5.324 秒 | TCP/HTTPS、4 MiB 双向、半关闭、UDP/DNS/IPv6、两向密文篡改/重放、官方服务器重启、导入、Core UDP、既有三种 AEAD |

SS2022 的重放测试实际转发和重放官方服务端的密文。官方日志记录了重复 TCP salt 拒绝；UDP 测试验证目标仅收到一次请求，Swirl 仅交付一次响应，错误 tag 不污染有效包的窗口。响应换绑测试使用捕获的官方密文，验证另一条请求不能接受该响应。

上述回环测试通过不等于 Qt 产品验收完成。跨平台构建与 CI 结果由该分支的整体验收记录另行报告。

### 已归档的可复核记录

- VMess 最终安全补丁后的 [13 项官方互通汇总](evidence/x14-a2-vmess/verified-progress-timeout/summary.json)、[完整测试输出](evidence/x14-a2-vmess/vmess-interop-final.log)、[11 项协议单元测试](evidence/x14-a2-vmess/vmess-body-timeout-unit.log)。同一目录包含逐连接字节数、SHA256、关闭状态、目标统计和官方服务端日志。
- VMess [严格半关闭失败汇总](evidence/x14-a2-vmess/strict-half-close/summary.json)与[失败输出](evidence/x14-a2-vmess/vmess-interop-strict-half-close.log)保留原始失败状态；这是前一轮相同关闭路径的记录，未被最终正文超时补丁改写成通过。
- SS2022 最终 [12 项官方互通汇总](evidence/x14-a6-ss2022/final/summary.json)、[完整测试输出](evidence/x14-a6-ss2022/ss2022-interop-final.log)、[协议单元测试](evidence/x14-a6-ss2022/ss2022-unit.log)与[导入回归](evidence/x14-a6-ss2022/ss2022-xray-regressions-final.log)。后者的密码映射测试为 11/11，原生映射为 23/23。
- [VMess 归档清单](evidence/x14-a2-vmess/archive-manifest.json)和[SS2022 归档清单](evidence/x14-a6-ss2022/archive-manifest.json)记录各文件 SHA256。这些记录逐字节复制自实际运行输出，未复制服务端配置、私钥或密码文件；扫描未发现密码、PSK 或私钥块。

记录中的客户端 SHA256 标识当次实际测试二进制，不能用于声称之后的构建也已通过。带工作树改动的本地验证与 GitHub 对具体提交的 CI 结果分别记录。

同一当前工作树还完成了既有 REALITY / Vision 的 [46 次官方回归执行](REALITY_VISION_NATIVE_REGRESSION_X14A_20261022.md)，包括真实 Core TLS 1.3 Direct 切换；没有重新实现已有协议。

## 必须保留的限制

### VMess 目标半关闭

固定 Xray v26.10.21 的 `freedom` 出站在上传复制结束后启动 `downlinkOnly` 计时，但没有向目标调用 TCP `CloseWrite`。目标若必须等待客户端 EOF 才完成响应，默认 1 秒计时结束可能导致连接取消，VMess 认证终止帧来不及发送。严格测试保留失败退出，不将 `UnexpectedEof` 或 `WebSocketTransportClosed` 改写为成功。

目标自行结束应用响应的 HTTP(S) 与有限长度 echo 场景已通过正常关闭。两种行为必须分别记录；目标等待 EOF 的场景尚未通过官方互通验收。

### VMess 会话容量

VMess body nonce 包含 16 位记录计数器。Swirl 在第 65536 个 nonce 使用完毕后返回 `VmessNonceExhausted`，不会回绕重复使用 nonce。认证终止帧也消耗一个 nonce，所以能正常结束的方向最多使用 65535 个数据记录。

出站单记录最多 16 KiB，理论有效载荷上限为 **1 GiB 减 16 KiB**；较小的应用写入可能更早耗尽记录数。入站上限取决于服务端每个记录的载荷大小，不能宣称所有下载均可达到 1 GiB。64 MiB 双向流式实测通过。重新连接需要新会话，原应用请求不会被透明重放。

VMess 响应头和正文均在收到记录首字节后启用固定进度期限，零星补发字节不能续期；完整认证记录之间允许应用空闲。超时返回 `VmessRecordTimeout`，不会交付尚未通过认证的数据。恶意滴流测试和随后 13 项官方互通均已执行。

### SS2022 边界

TCP 初始 salt 和固定响应头按 SIP022 的单次读要求验证；不完整初始头立即成为错误。后续长度/载荷帧只在首字节到达后启用固定进度期限，完整记录之间的应用空闲不计入该期限。TCP 只在完整记录边界接受 FIN；SIP022 本身没有 VMess 式的认证终止记录。

UDP 每个客户端 association 使用独立会话和单调包计数器。每个服务器会话使用 1024 包滑动窗口，仅在认证、类型、时间戳、客户端会话绑定和地址验证都完成后更新。最多保留两个服务器会话，各保留至少 60 秒；第三个过早出现的会话明确拒绝。所有解析、缓存和任务均有固定上限。

## 服务端与复现入口

- VMess：官方 **Xray v26.10.21**，提交 `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`，沿用 `tools/tests/transport-peer-lock.json`；启动命令为 `xray run -config <独立临时配置>`。
- Shadowsocks：官方 **shadowsocks-rust v1.25.0**，MIT；`tools/tests/ss2022-peer-lock.json` 固定 Linux、Windows、macOS 两种架构的官方压缩包 SHA256。`fetch_ss2022_peer.py` 仅提取 `ssserver`，启动命令为 `ssserver --config <独立临时配置> --single-threaded -v`。
- 本地 Linux ssserver 文件 SHA256：`ce2ed6278044693b801c592642f3a5366b5d8b70db1bc537432c017ac4a844f7`。
- 通用密码学依赖：已有 `ring`、RustCrypto `aes 0.8.4`；新增通用哈希库 `blake3 1.8.7`，可选 Apache-2.0 许可。没有引入完整第三方代理客户端内核。

构建本仓库 `transport-client`、`ss2022-client`、`transport-runtime`、`swirl-inspect` 后，设置对应 `SWIRL_*` 可执行路径并运行两个 Python 套件。测试要求缺失的二进制报错，不跳过。`SWIRL_TRANSPORT_EVIDENCE`、`SWIRL_VMESS_EVIDENCE`、`SWIRL_SS2022_EVIDENCE` 保存逐连接报告、官方日志、目标统计和汇总；所有凭据均为合成测试值。

VMess 与 SS2022 共用 `SWIRL_TRANSPORT_CLIENT`、`SWIRL_TRANSPORT_RUNTIME`、`SWIRL_INSPECT_BINARY`。VMess 使用 `SWIRL_XRAY_BINARY`；SS2022 使用 `SWIRL_SS2022_SERVER` 和 `SWIRL_SS2022_CLIENT`。命令分别为 `python tools/tests/test_vmess_xray.py` 和 `python tools/tests/test_ss2022_official.py`。严格半关闭诊断必须单独执行 `python tools/tests/test_vmess_xray.py --strict-half-close` 并保留其失败，不能并入成功计数。

## 通用密码学依赖许可复核

本轮对 `aes 0.8.4` 和 `blake3 1.8.7` 的 Linux、Windows、macOS x86_64 / arm64 锁定依赖图进行复核，包含编译工具依赖，合计 18 个不同 crate 版本。下载 crate 的 SHA256 与 `Cargo.lock` 一致，许可证文件与相应锁定压缩包中的原文一致。[完整机器可读记录](evidence/x14-a6-ss2022/dependency-licenses/review.json)包含每个版本、声明许可、所选许可、源码地址及许可证文件哈希；四个目标的 `cargo tree` 原始输出也已保存。这是依赖图审查，不代表在四个平台实际运行了构建或互通。

| 组件 | 声明许可 | 本记录采用的许可选项 | 用途 |
| --- | --- | --- | --- |
| `aes 0.8.4` | MIT 或 Apache-2.0 | Apache-2.0 | VMess AuthID、SS2022 UDP 独立头的 AES 块操作 |
| `blake3 1.8.7` | CC0-1.0、Apache-2.0 或 Apache-2.0 WITH LLVM-exception | Apache-2.0 | SS2022 会话子密钥派生 |
| `constant_time_eq 0.4.2` | CC0-1.0、MIT-0 或 Apache-2.0 | Apache-2.0 | BLAKE3 通用基础依赖 |
| `generic-array 0.14.7` | MIT | MIT | 密码学定长数组基础组件 |
| 其余 14 个锁定 crate 版本 | MIT / Apache-2.0 双许可 | Apache-2.0 | 通用数组、密码学 trait、CPU 特性及编译工具 |

这些依赖的源代码未作修改。发行链接后的二进制时，需要保留所选许可证、版权声明及适用的 NOTICE；本次没有引入完整第三方代理客户端或修改依赖许可。官方 Xray（MPL-2.0）与 shadowsocks-rust（MIT）作为测试服务端的许可和固定版本另在 peer lock 中记录，不随此实现成为产品客户端内核。

## 本机性能观测

本轮为无调优 debug 构建，与官方服务端和 Python 目标在同一 Linux 主机并发运行。它们是测试环境观测，不是公网带宽或优化后的发布性能基准。

| 场景 | 每方向应用数据 | 传输阶段时间 | 每方向数据速率 |
| --- | ---: | ---: | ---: |
| VMess TCP | 4,194,321 字节 | 241.330 ms | 16.57 MiB/s |
| VMess TCP + TLS | 4,194,321 字节 | 263.128 ms | 15.20 MiB/s |
| VMess WS | 4,194,321 字节 | 281.777 ms | 14.20 MiB/s |
| VMess WS + TLS | 4,194,321 字节 | 284.739 ms | 14.05 MiB/s |
| VMess TCP + TLS 大传输 | 67,108,864 字节 | 4097.096 ms | 15.62 MiB/s |
| SS2022 AES-128-GCM | 4,194,321 字节 | 288.541 ms | 13.86 MiB/s |
| SS2022 AES-256-GCM | 4,194,321 字节 | 270.989 ms | 14.76 MiB/s |

`connect_us` 包含 DNS、连接、适用的 TLS/WS 和请求头写入，不能称为纯 TCP 延迟；认证完成以实际响应解密和收发数据为依据。UDP 示例另用 `setup_including_dns_udp_socket_us` 标记解析和 socket 准备，认证由随后实际返回的数据证明。没有测量峰值 RSS。

## 一手参考

- [Xray 固定版本 VMess 实现](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/vmess)
- [Xray 固定版本 freedom 出站](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/freedom/freedom.go)
- [SIP022 AEAD-2022](https://shadowsocks.org/doc/sip022.html)
- [SIP002 URI](https://shadowsocks.org/doc/sip002.html)
- [shadowsocks-rust v1.25.0](https://github.com/shadowsocks/shadowsocks-rust/releases/tag/v1.25.0)
- [BLAKE3 crate 与许可证](https://github.com/BLAKE3-team/BLAKE3/blob/master/Cargo.toml)
