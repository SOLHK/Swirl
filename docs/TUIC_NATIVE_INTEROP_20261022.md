# X1.4-A4 — TUIC v5 原生实现与实际互通

本记录对应 Swirl 自研 Rust 客户端。QUIC/TLS 使用通用 Quinn/rustls 库，TUIC 的 exporter 认证、命令、UDP 分片、会话及生命周期由 Swirl 实现。测试中唯一的外部代理可执行程序是独立服务端；客户端路径始终是 `swirl-protocol` 或 `swirl-core`。

## 协议版本与对端身份

实现严格选择 TUIC v5（版本字节 `0x05`）。UUID 是 TLS exporter label，password 是 exporter context，得到 32 字节认证 token。Authenticate 使用单向 QUIC stream；TCP Connect 使用双向 stream；UDP 支持 QUIC Datagram 的 `native` 模式和单向 stream 的 `quic` 模式。

依据为 [TUIC v5 规范](https://github.com/tuic-protocol/tuic/blob/master/SPEC.md)。当前规范仓库明确不提供现行官方实现，因此本阶段准确称为“历史官方参考服务端互通”，不把其他维护者的实现称为官方。

固定对端为 [tuic-server-1.0.0 release](https://github.com/tuic-protocol/tuic/releases/tag/tuic-server-1.0.0)，tag commit `a299ef02d9f4ab5a0edbf58b9998f41bf768b332`；`--version` 实际输出 `1.0.0`。已读取官方 release API 和各平台的 `.sha256sum`：

| Asset 后缀 | SHA-256 |
|---|---|
| `x86_64-unknown-linux-musl` | `adb808944ca829857bf408d2ee438a156e8171543dbbed3e94964b66b4135393` |
| `x86_64-apple-darwin` | `2031a3ae3c76d64ed63b803f4f3ff34536d4ecfdf3b0e190acb518657819f5fe` |
| `aarch64-apple-darwin` | `989c9fe8288bd07217198b844af83bfac7d949f1445b7447f324701e0e0b8825` |
| `x86_64-pc-windows-msvc.exe` | `09c3bf3790117bf4c0d0505ada439800f19b68a52a018ca2cda7e7f8125adeb6` |

下载 URL 前缀为 `https://github.com/tuic-protocol/tuic/releases/download/tuic-server-1.0.0/tuic-server-1.0.0-`。本记录的实际执行环境为 Linux x86_64；存在其他平台的资产不表示已执行这些平台的测试，跨平台状态以对应 GitHub Actions 运行结果为准。

## 新增实现

- `swirl-transport/src/quic.rs`：TLS 1.3、默认链及 SNI 校验、ALPN、显式 insecure、始终生效的叶证书 SHA-256 pin、IPv4/IPv6 多地址尝试、有界 QUIC 配额、endpoint 所有权及 stream 适配。insecure 不跳过握手签名验证。
- `swirl-subscription/src/tuic.rs`：统一 v5 原生配置，严格映射 Clash/Mihomo 和 TUIC URI，恢复并核对 URI UUID/password，拒绝不支持的关键字段及冲突值。
- `swirl-protocol/src/tuic.rs`：Swirl 自有 v5 wire codec、认证、TCP、多目标 UDP、native/quic 两种 UDP 模式、有界分片重组、心跳及正常关闭。TCP 活跃连接复用按配置摘要、Tokio runtime 和当前 DNS 结果隔离，不持有空闲强引用。
- `swirl-protocol/examples/tuic-client.rs`：通过统一 Rust connector 的实际流量验收驱动；私有配置从有界 stdin 输入，仅输出固定错误码、字节数、hash 和有明确含义的阶段计时。
- `tools/tests/test_tuic_reference.py`：固定参考服务端、独立目标及负面路径。
- `tools/tests/test_quic_core.py`：从真正 Core SOCKS5 CONNECT/UDP ASSOCIATE、HTTP CONNECT 入口，经 TUIC/Hysteria2 到独立 TCP/UDP/DNS/HTTPS 目标。

Quinn `0.11.12` 和 quinn-proto `0.11.19` 的本地 crate manifest 许可均为 `MIT OR Apache-2.0`。这些依赖提供通用 QUIC，不提供 TUIC 代理内核；未复制或链接历史参考代理程序的协议实现。

## Linux 实际验收

A4 提交时的直接 connector suite 为 9 个测试方法、11.862 秒、20 次正向数据交换、6 次预期认证/TLS 拒绝，以及 1 次明确保留的上游缺陷探针。完整脱敏结果见 [reference-results.json](evidence/x14-a4-tuic/reference-results.json)，运行输出见 [reference-tests.txt](evidence/x14-a4-tuic/reference-tests.txt)。

| 组合/行为 | 实际证据 | 状态 |
|---|---|---|
| v5 TCP / TLS 1.3 | 4 MiB 上传、4 MiB 下载，逐字节及 SHA-256 校验，目标观察到客户端半关闭 | 原生互通通过 |
| v5 UDP `native` | 123、4096、65507 字节，真实目标收包并回包；大包经过协议分片 | 原生互通通过 |
| v5 UDP `quic` | 相同三个大小，真实单向 stream relay | 原生互通通过 |
| DNS over 两种 UDP mode | RFC DNS wire query/response，事务 ID、QR 和目标端口校验 | 原生互通通过 |
| 错误 UUID / password | 客户端拒绝/关闭；目标连接数为零 | 拒绝路径通过 |
| CA、SNI、ALPN 错误 | 不能到达目标 | 拒绝路径通过 |
| pin 正确/错误 | 正确 pin 实际收发；insecure=true 下错误 pin 仍拒绝 | 通过 |
| IPv6 proxy endpoint + domain target | 官方服务端监听 `::1`，实际传输完成 | 通过 |
| Clash / TUIC URI 导入 | 导入器输出原生节点后真实连接；URI 明确使用 insecure+正确 pin | 通过 |
| 多节点与并发 | 两个独立参考服务端、四个并发客户端，目标字节及连接计数核验 | 通过 |
| 空 UDP 回复 | 目标收到空包，历史参考服务端封装回复时 abort | **互通未通过，上游缺陷已保留** |

Core suite 为 6 个测试方法、20.018 秒，包含 TUIC `native`、TUIC `quic` 和 Hysteria2，见 [core-results.json](evidence/x14-a4-tuic/core-results.json) 和 [core-tests.txt](evidence/x14-a4-tuic/core-tests.txt)。TUIC 对应实际验收包括：

- SOCKS5 CONNECT 与四条并发流；切换节点后已有流继续收发；同一进程停止并重新启动 Core。
- SOCKS5 UDP ASSOCIATE 的 123/3072/4000 字节收发及域名 DNS；关闭控制 TCP 后停止转发；新 association 正常工作。
- HTTP CONNECT 后应用层 HTTPS，独立目标证书验证、正文校验和 TLS close_notify。
- 选择错误凭据节点后新 TCP/UDP 请求没有到达目标，已存在的有效 association 继续工作。
- 参考服务端 idle timeout 为 2 秒，客户端 TUIC heartbeat 为 1 秒；闲置 3.1 秒后同一流继续双向收发，不能由通用 10 秒 QUIC keepalive 解释。
- 同一 Core 改变代理域名的 DNS 映射后，新请求不复用旧地址的活跃连接；旧流仍存活；恢复映射后新请求成功。
- 每组结束时 Core `active == 0`，证据包含上传、下载和 UDP drop 计数。

这些测试没有启动 Qt，因此**不是 Windows Qt 产品端到端验收**。

后续生命周期复核修正了两点：Dissociate 等待超时或失败后也始终关闭 QUIC connection；接收队列持续就绪时，每处理 32 个心跳或不完整片段主动让出异步调度。使用修改后重新构建的客户端和 Core 再次执行固定官方对端测试，直接 suite 9 个方法 / 12.631 秒、Core suite 6 个方法 / 20.124 秒全部满足原有断言。保留独立后续记录 [lifecycle-reference-results.json](evidence/x14-a4-tuic/lifecycle-reference-results.json)、[lifecycle-reference-tests.txt](evidence/x14-a4-tuic/lifecycle-reference-tests.txt)、[lifecycle-core-results.json](evidence/x14-a4-tuic/lifecycle-core-results.json) 和 [lifecycle-core-tests.txt](evidence/x14-a4-tuic/lifecycle-core-tests.txt)。这次回归验证不把空 UDP 回复的历史对端缺陷改为通过。

## macOS CI 原始失败、平台探针与修正范围

A4 提交 `930be89374a64d600730b3056e8a756bba5fcde4` 的 [macOS 官方互通 job](https://github.com/SOLHK/Swirl/actions/runs/39783473847/job/119840407828) 实际失败：`native` 和 `quic` 模式的 65507 字节 UDP 均为 `TotalTimeout`，目标只收到两组 123/4096 字节数据，没有收到两个最大包。该 suite 为 9 个方法、36.395 秒、3 条失败（两个子测试及最终目标列表断言）。此结果不能记录为 macOS TUIC 全部通过。

保留 [原始失败日志段](evidence/x14-a4-tuic/macos-ci-39783473847-failure.txt)、[原始 artifact 中的 tuic.json](evidence/x14-a4-tuic/macos-ci-39783473847-tuic.json) 和 [来源/摘要/限制元数据](evidence/x14-a4-tuic/macos-ci-39783473847-metadata.json)。下载的原 artifact ZIP SHA-256 为 `2bcf8e012f800a64b787ea6a649abcae5ed98a479cb547c3e7331c93cd01b569`，与 Actions 上传记录一致。旧 harness 在断言后才追加 JSON 记录，导致这两个失败正向 case 不在其 JSON 内；原 job 日志完整记录了失败。现已改为先记录结果、再断言，并用 `native_interoperability_pass: false` 保留未通过结果。

Apple 官方 XNU 固定快照 `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea` 的 [`udp_usrreq.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/netinet/udp_usrreq.c) 将默认 `udp_sendspace` 设为 9216，由 `net.inet.udp.maxdgram` 控制新 UDP socket 的发送缓冲；[`uipc_socket.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_socket.c) 对超出该上限的原子 datagram 返回 `EMSGSIZE`。[IPv6 attach](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/netinet6/udp6_usrreq.c) 使用相同全局发送/接收默认值。当前源码接收默认值约为 192 KiB，并可在初始化时增大；不能套用其他版本的旧默认值。

固定历史官方 TUIC 的 [`udp_session.rs`](https://github.com/tuic-protocol/tuic/blob/a299ef02d9f4ab5a0edbf58b9998f41bf768b332/tuic-server/src/connection/udp_session.rs) 为目标创建普通 UDP socket，未设置发送缓冲大小，最终直接 `send_to`。这些源码支持“服务端目标 UDP socket 的平台默认上限”这一原因；原 CI 没有记录 sysctl 或服务端日志，因此 **9216 是源码默认值，不能称为原失败 runner 的实测值**。修正后的 CI 必须用下面的探针和原协议测试进一步确认。

新增独立测试准备脚本 `tools/Prepare-NativeInteropPlatform.py`：

- 默认只测量，不修改系统。每次使用新建且未修改 buffer 的 socket，在 IPv4 和 IPv6 上实际往返 123、4096、65507 字节，记录阶段、errno、SO_SNDBUF/SO_RCVBUF 与 SHA-256。
- Darwin 记录 `net.inet.udp.maxdgram`、`net.inet.udp.recvspace`、`kern.ipc.maxsockbuf`；只有显式 `--prepare-macos`、实测最大包失败与默认 buffer 上限相符时才允许 `sudo -n sysctl`。
- 按需将 `maxdgram` 改为 65535。如果实测旧/自定义 `recvspace` 小于 65535，则按需设为 131072；当前默认足够时不改接收配置。不会扩大 `maxsockbuf`。
- 调整在所有独立服务端创建 socket 前完成；随后用新的 socket 完整重测，任何失败返回非零。原 65507 字节 TUIC case 保持不变。普通 Linux/Windows 调用即使传此 flag，也不会修改任何系统设置。

该脚本仅用于临时 CI runner，**不是产品运行依赖，也不证明任何代理协议互通**。没有把默认 macOS 的大包失败静默改为跳过。若机器不允许调整，探针明确失败，保留报告。

Linux 对普通调用和带 flag 调用的 6 个底层往返均实际通过，且 `system_setting_changed: false`，见 [默认探针](evidence/x14-a4-tuic/platform-linux-default-probe.json) 和 [flag 探针](evidence/x14-a4-tuic/platform-linux-flag-probe.json)。修改后的官方 TUIC suite 再跑 9 个方法 / 11.773 秒，两个模式的原 65507 字节仍全部通过；4096 字节 native case 从独立官方服务端日志确认收到完整 **3 片**，见 [平台回归结果](evidence/x14-a4-tuic/platform-regression-linux-results.json) 与 [执行输出](evidence/x14-a4-tuic/platform-regression-linux-tests.txt)。每个独立服务端最多保留 64 KiB 脱敏日志，UUID/密码不进入公开证据。

A5 提交 `40be930b6328e3d292eb913bc14e45c27ea95f42` 的 [macOS job 119853790695](https://github.com/SOLHK/Swirl/actions/runs/39787300601/job/119853790695) 已实际通过。已独立下载 artifact `12429183080` 并核对 SHA-256 `675fd32ed0bb9d9a9f777d5d4e1b20e2f8a8e8f219b0d059d62b3fdb007f84ab`，原始 [平台探针](evidence/x14-a4-tuic/macos-ci-39787300601-platform.json)、[TUIC 结果及脱敏服务端日志](evidence/x14-a4-tuic/macos-ci-39787300601-tuic.json) 和 [来源摘要](evidence/x14-a4-tuic/macos-ci-39787300601-metadata.json) 均已归档：

| 该 runner 的实测值 | 调整前 | 调整后 |
|---|---|---|
| `net.inet.udp.maxdgram` / 新 socket `SO_SNDBUF` | 9216 | 65535 |
| `net.inet.udp.recvspace` / 新 socket `SO_RCVBUF` | 786896 | 786896，未修改 |
| `kern.ipc.maxsockbuf` | 8388608 | 8388608，未修改 |
| IPv4 / IPv6 原始 65507 字节往返 | 发送即 `EMSGSIZE`，errno 40 | 完整往返、字节与 SHA-256 一致 |

探针之后才启动的固定 TUIC 服务端通过全部 9 个测试方法（13.122 秒）；`native` 与 `quic` 的 65507 字节均真实上传、下载并正常关闭。4096 字节 native case 在服务端日志中观察到完整 **4 片**。片数受路径 MTU 影响；测试只要求多于一片且全部片号存在，不固定为 Linux 记录的 3 片。Core QUIC 入口同时通过 6 个方法（21.361 秒）。

该结果证明**临时 macOS runner 显式调整 UDP 新 socket 发送上限后**的 Rust 原生 TUIC 互通，不证明未调整的默认 macOS 能让该历史参考服务端转发最大 UDP 包，也不属于 Qt 产品验收。原始 A4 失败记录继续保留；后续成功没有覆盖失败证据。

## A6 配置预检与 QUIC 上下文复核

定点检查发现一项实际缺陷：合法 base64 包装的无效 CA DER 能通过订阅结构验证，Core 启动后，Hysteria2 和 TUIC 在构建 QUIC TLS 配置前已先查询节点 DNS。使用真实本地 UDP DNS 观察 socket，旧二进制的两个协议均产生 44 字节查询，见 [修复前观察](evidence/x14-a6-quic-preflight/before-core-dns-observation.json)。这是一项无效配置先联网的缺陷，不能只依靠稍后的证书握手失败处理。

修复增加无网络的 `quic::validate` 及 Hysteria2/TUIC 公共预检，TCP、UDP 在解析节点地址前完成 CA DER、SNI、ALPN、pin、拥塞控制及协议配置校验；Core 启动也使用同一入口。证书验证上下文缓存最多 32 项，按 CA、ALPN、显式 insecure 和 pin 隔离，不缓存 socket、endpoint 或 Tokio runtime；上下文复用不启用 session resumption 或 0-RTT。缓存锁内只查询或更新有界队列，证书解析在锁外完成。

新增 `swirl-protocol/tests/quic_preflight.rs` 用真实本地 DNS socket 观察拒绝路径：两个协议的 TCP 和 UDP 均立即返回 `TlsTrustAnchor`，观察期间没有 DNS 数据。此定点回归已实际通过 1 个测试、0 个失败、0 个跳过，见 [执行日志](evidence/x14-a6-quic-preflight/dns-observer-regression.txt)。这项证据仅证明配置预检行为，不当作协议互通通过记录。后续完整门禁与固定官方对端回归结果以对应 A6 记录为准。

## 保留的失败与边界

第一次未删减的参考服务端测试包含空 UDP round trip，导致该对端 abort，后续同进程测试随之失败。原始结果和输出保存在 [initial-failure.json](evidence/x14-a4-tuic/initial-failure.json) 与 [initial-failure.txt](evidence/x14-a4-tuic/initial-failure.txt)。定位到固定 tag 的 [`Fragments::next`](https://github.com/tuic-protocol/tuic/blob/a299ef02d9f4ab5a0edbf58b9998f41bf768b332/tuic/src/model/packet.rs)：为零长度 payload 取第一个字节的地址导致越界。后续把该缺陷探针隔离到独立服务端，并明确记录 `native_interoperability_pass: false`；未修改服务端，也未把空包 round trip 写成通过。

客户端 packet parser 支持零长度 payload；这种单元级处理不能替代独立对端成功证据。重组最多 32 个待完成 packet、总数据 256 KiB、单 UDP payload 65507 字节，5 秒清理过期片段；stream-mode 收包保留部分读取状态，允许 Core 在发送分支就绪时取消接收 future。

本阶段不支持 TUIC v4/token、0-RTT/reduce-rtt、disable-SNI、fast-open、udp-over-stream 或未映射扩展；有要求时明确拒绝。未提供用户可控 QUIC endpoint 迁移接口。Android/iOS/OpenHarmony 未实际验证。TLS ClientHello 指纹模拟不属于此实现；配置中的 `client-fingerprint` 不会被静默忽略。

## 性能记录的含义

A4 提交记录中 debug loopback 单次 4 MiB 双向传输总耗时为 367218 微秒，连接阶段为 6752 微秒；20 次正向交换的连接阶段中位数为 5050 微秒。该字段名是 `connect_including_dns_quic_auth_us`，涵盖 DNS、QUIC/TLS 和认证请求发送，**不是纯 TCP 延迟，也不独立证明服务端已接受认证**。认证成功由随后独立目标的数据验证。未把本地 debug 数据用于声称公网吞吐或与其他产品的性能优劣。

## 复现

```sh
cargo build --manifest-path core/Cargo.toml --locked -p swirl-protocol --example tuic-client
cargo build --manifest-path core/Cargo.toml --locked -p swirl-core --example transport-runtime

# 以下变量分别指向实际构建产物与经 hash 校验的独立服务端。
SWIRL_TUIC_CLIENT=/absolute/path/tuic-client \
SWIRL_TUIC_SERVER=/absolute/path/tuic-server \
SWIRL_TUIC_EVIDENCE=/absolute/path/reference-results.json \
PYTHONPATH=tools/tests python3 -m unittest -v test_tuic_reference

SWIRL_TRANSPORT_RUNTIME=/absolute/path/transport-runtime \
SWIRL_TUIC_SERVER=/absolute/path/tuic-server \
HY2_SERVER=/absolute/path/hysteria \
SWIRL_QUIC_CORE_EVIDENCE=/absolute/path/core-results.json \
PYTHONPATH=tools/tests python3 -m unittest -v test_quic_core
```

服务端命令为 `tuic-server -c <临时配置>`。fixture 生成临时 CA、证书与合成凭据，绑定 loopback，默认保留服务端原始日志于临时目录；公开证据不包含密码、UUID、私钥或订阅内容。缺失可执行文件或版本/hash 不匹配均直接失败，没有 skip-as-pass。
