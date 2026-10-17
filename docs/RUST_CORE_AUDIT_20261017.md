# Swirl 架构审计（接手基线，2026-10-17）

审计对象：`work/core-completion-20261017@8bd89f2` 与 `origin/main@87409c0`。本文记录接手时的实际源码，阶段修复和最新执行证据另见 [WebSocket 阶段验收](RUST_WS_VALIDATION_20261017.md)。审计不涉及私有订阅、账户凭据或 Secrets。

## 主要结论

1. `main@87409c0` 没有 `core/` Rust workspace。main 的最新提交为 2026-10-16 18:30:40 +08:00 的 “Release continuous card navigation and restore production animations”。开发分支已经继承这些 UI 修复并新增 Rust workspace；从 main 重建会重复大量已完成工作。
2. 当前开发分支存在真正由 Rust 执行的代理网络路径：`ThreadedEngine` 在 `SWIRL_USE_RUST_CORE=ON` 时选择 `RustCoreEngine`，经 ABI 到 Rust；Rust 拥有监听、协议、传输、DNS、路由、会话和统计。这个模式不调用 Mihomo 执行转发。
3. 默认 CMake 仍为 `SWIRL_USE_RUST_CORE=OFF`。默认产品运行 `SwirlEngineManager`，在历史自研 C++ 基础 HTTP/SOCKS5/Trojan 和 Mihomo 兼容引擎之间选择。因此“Rust workspace 已存在”不等于普通安装包已经全 Rust。
4. 自动组提交标题夸大了实际接入程度：`swirl-subscription/src/policy.rs`、`swirl-protocol/src/probe.rs`、`swirl-core/src/policy.rs` 三个文件没有被各自 crate root 声明或调用，未纳入编译/测试。`Selector` 仍只有 `id/members/selected`，路由仍只解一层手动 selector。自动组和嵌套手动组在此基线不能执行；它们只是候选实现文件，不能称为已完成。
5. DoH、SOCKS4/4a、VLESS/Trojan WS 的新源码实际接入，范围和缺口不同。SOCKS4/4a 仅 Rust IR/API 层可执行，Qt 和 Rust 离线订阅 inspector 尚未接受 socks4 节点。WS 已有 Qt 配置映射，但本基线 Qt 测试中没有 WS 专项；Python WS 分片/Ping 回归仍失败，不能用编译通过替代转发验收。
6. 所有 QML、assets、shaders、app、network 目录相对 main 没有差异。源码上保留了页面、动效、圆角、字体、图标和 Windows 平台功能；这不等于本轮已在 Windows 做视觉验收。

## 分层与执行路径

### Rust 专用构建

`main.cpp` → `EngineController` → `ThreadedEngine` 工作线程 → `RustCoreEngine` → `swirl_core_command` ABI v1 → `swirl-core` → `swirl-routing`/`swirl-dns`/`swirl-protocol`/`swirl-transport`。

- `src/Swirl.Quick/CMakeLists.txt` 的 `SWIRL_USE_RUST_CORE` 显式开关默认关闭；打开时限制为 Windows Qt 打包，使用 Cargo 生成 `swirl_api.dll` 并复制到 Qt 输出目录。
- `engine/ThreadedEngine.h` 在 Rust 模式构造 `RustCoreEngine`；UI 通过队列接收状态快照，网络运行不在 QML 里实现。
- `engine/RustCoreEngine.cpp` 只做现有节点、DNS、规则与组的 JSON 转换、生命周期、快照和现有探测 UI 的 HTTP 客户端请求。
- `engine/MihomoAdapter.cpp:380` 的启动入口在 Rust 构建中直接返回失败；`NodeTestService.cpp` 的 Rust 分支直接选择 Rust 引擎，无兼容重试。
- CMake 仍包含历史 C++ 引擎、Mihomo 元信息和依赖许可证；阻止启动与删除源码/打包依赖是不同状态。

### main / 默认兼容构建

`main.cpp` → `EngineController` → `ThreadedEngine` → `SwirlEngineManager` → `SwirlProxyEngine` 或 `MihomoAdapter`。

- `engine/SwirlProtocolRegistry.cpp` 定义历史 C++ native 基础能力；TUN、LAN、智能 MRS、自定义 DNS/规则/组和高级协议转到 Mihomo。
- `engine/SwirlEngineManager.cpp` 有明确的兼容 fallback 逻辑，原生连接失败但无活动连接时可切换到同一节点的 Mihomo；有活动连接时延后，防止破坏其他流。
- `engine/MihomoAdapter.cpp` 写入隔离的运行配置、检查指定 SHA/版本、由 `OwnedProcess` 启动进程，并通过本地控制 API 管理节点/规则/统计。
- `scripts/stage-mihomo.ps1` 按 `packaging/mihomo-manifest.json` 下载和校验 Mihomo v1.19.32，复制为 `core/mihomo.exe`。这条默认打包路径仍保留。

## 实现与证据边界矩阵

下表“源码存在/可执行”来自代码审阅；没有把测试文件存在视为本轮测试已运行。用户提供的既往 CI 结果应由主代理对照 GitHub 运行与提交 SHA 记录。

| 模块/能力 | 当前实际实现 | 依赖或保留边界 | 证据与尚未验证范围 |
|---|---|---|---|
| Rust workspace 与 ABI | 7 个 crate；ABI v1 提供 start/configure/select/select_group/snapshot/stop；输入有界、固定错误码 | `swirl-api` 的 unsafe 局限在 FFI 缓冲复制，其他 crate 禁止 unsafe；不链接完整代理内核 | `core/Cargo.toml`、`swirl-api/src/lib.rs`；自动组命令/报告未接入 |
| 会话运行时 | 两个 Tokio worker，1–256 并发连接、配置代次、旧连接保留原配置、取消和统计 | Tokio 提供调度/socket，Swirl 写生命周期与策略绑定 | `swirl-core/src/lib.rs`、`tests/network.rs`；长期弱网、平台接管未验收 |
| HTTP/HTTPS CONNECT 与 SOCKS5 TCP | 自研入/出站、认证、地址编码；HTTP/SOCKS5 出站可加验证 TLS | rustls、ring、WebPKI 提供 TLS/密码实现 | `swirl-protocol/src/lib.rs`、`tools/tests/test_rust_core.py`；真实私有节点不是合成对端结论 |
| SOCKS4/4a | Rust 原生入/出站 CONNECT、用户 ID、remote_dns 语义；IPv6 出站显式拒绝 | 无完整外部内核 | `swirl-protocol/src/socks4.rs` 已 mod 引入；`Outbound::Socks4` 已在 IR，`test_socks4.py`；Qt allowlist 与 inspector `protocol()` 均未接入 |
| Trojan | Rust TLS 上密码摘要与 CONNECT framing | 严格 TLS 校验；不支持 Trojan UDP | `swirl-protocol/src/lib.rs`、Python TLS 对端；普通/WSS 组合须分别验收 |
| Shadowsocks AEAD | 自研 TCP/UDP framing、地址、salt/nonce、replay 窗口；3 种 AEAD；HTTP obfs | ring/RustCrypto 提供密码算法；无 SS core/插件进程 | `swirl-protocol/src/shadowsocks.rs`、`test_shadowsocks.py`；SS2022、SSR、TLS obfs 未实现 |
| VLESS v0 | Rust TCP framing、UUID、延迟读取响应头；可叠加 TLS/WS | 无 Xray 执行依赖 | `swirl-protocol/src/vless.rs`；Vision/REALITY/扩展加密/mux/UDP 未实现 |
| WS/WSS 传输 | 原生 RFC 6455 binary framing，客户端掩码、升级验证、控制帧、边界/背压；连接代码实际调用 | HTTP/1.1；只允许 Host/path，不支持 early data、额外头、多路复用和扩展 | `swirl-protocol/src/websocket.rs`、`swirl-subscription/src/websocket.rs`、`inspect_websocket.rs`；基线 Python 分片/Ping 失败待修。Qt 仅已有映射未有 WS 专项实证 |
| 通用 TCP/TLS 传输 | 双向背压、独立半关闭、TLS 校验/SNI/ALPN、统计 | rustls、tokio-rustls、ring、WebPKI；协议实现与成熟原语依赖分开 | `swirl-transport/src/lib.rs`；gRPC/XHTTP/HTTP2/QUIC 代理传输未实现。抓包 HTTP2 不能算 Rust 代理 HTTP2 |
| UDP | SOCKS5 UDP ASSOCIATE，自研控制生命周期、来源钉住、最多 64 目标、30s 回包窗口、4 个并行准备任务；只对 DIRECT/SS AEAD 执行 | TCP 通过不能当成其他协议 UDP 完成 | `swirl-core/src/lib.rs` 的 `prepare_udp/udp_associate/udp_response`；其他出口显式失败 |
| 系统/普通 DNS | 系统 resolver + hosts；自研 UDP/TCP DNS wire、A/AAAA/CNAME/TTL、缓存；共享 8-query semaphore | OS 系统解析仍用 Tokio `lookup_host`，不是自写 libc DNS；本地 hosts 仍由平台文件提供 | `swirl-dns/src/lib.rs`、`wire.rs`；EDNS/DNSSEC/负缓存/Fake-IP 未实现 |
| DoT | 显式 IP bootstrap 与单独认证名；一条验证 TLS 流上 A/AAAA/CNAME；有界超时 | 直连所配 resolver，不经代理策略，无明文 fallback | `swirl-dns/src/dot.rs`、`dns_tls.rs`、`test_dns_tls.py`；域名自动 bootstrap、DNS split 未实现 |
| DoH | 原生 HTTP/1.1 POST，每次 DNS 交换新 TLS 连接；长度/chunked/EOF framing；HTTP Age/Cache-Control 限制 TTL | 明确的 https_path 与 HTTP/1.1 ALPN；不会重定向、混入明文或自动系统 bootstrap | `swirl-dns/src/doh.rs` 由 dot.rs path mod 引入；`test_dns_https.py`；Qt 现有 encrypted HTTPS 字段映射已接入 |
| 手动路由 | 顺序域名/后缀/关键词、source/target CIDR、端口、MATCH；延迟 DNS 并将匹配 IP 钉住到连接 | 仅 concrete-node 一层手动 selector；GEOIP/GEOSITE/MRS/进程规则缺失 | `swirl-routing/src/lib.rs`、`swirl-core::route`、`RUST_NATIVE_ROUTING.md`；多地址带策略重试未做 |
| 自动组和嵌套手动组 | 仅候选文件；没有编译接入。运行时仍拒绝 strategy/probe 字段、selected group、嵌套成员 | 不可把孤立文件、提交标题或 cargo 通过计为功能 | 三个 orphan 文件见下节；Qt 只允许 type=select；没有运行时自动组集成测试 |
| Rust 订阅/IR | 自研检测和转换，保留 original/unknown；Clash YAML/JSON、sing-box、URI/Base64、INI 部分可出隔离 TCP 候选 | serde/serde-saphyr/url/base64；完全配置执行固定标记 false；无下载集成 | `swirl-subscription/src/inspect.rs`；Xray/V2Ray JSON 与多种协议只识别/保留，不能称可联网 |
| 产品订阅与节点存储 | 仍是 Swirl 自写 Qt/C++ 的 `NodeImportService/NodeImporter/SubscriptionNormalizer/NodeStore`；下载更新、DPAPI、未知字段保留 | fkyaml 用于 YAML；Qt Network 提供请求；尚未切为 Rust 服务 | `NodeImportService.cpp:126` 直接调用 C++ `NodeImporter::parse`，不是 Rust inspector；Python capture/DPAPI 另行保留 |
| 界面/平台/抓包 | Qt Quick/QML、C++23 Windows 平台适配、系统代理归属/恢复、单实例/退出、抓包、脚本/网关服务保持现状 | Qt、Windows API；抓包 HTTP2 链接 vendored nghttp2；不是 Rust 网络能力迁移完成 | `main.cpp`、`app/`、`network/`；main→基线这些目录无差异，不代表已做视觉验收 |
| TUN/LAN/网关/智能 MRS | Rust 启动时拒绝，历史功能留在兼容构建 | 后续需平台网络/路由接管；当前 Rust workspace 没有 swirl-tun | `RustCoreEngine.cpp::configuration` 首部；不能切默认 Rust 使现有功能无说明失效 |

## 自动组未接入的直接代码证据

- `swirl-subscription/src/lib.rs` 开头只有 `mod dns_tls; mod websocket; pub mod inspect;`，没有 `mod policy` / `pub use PolicyStrategy,HealthProbe`。
- `Selector` 定义只有 `id: String, members: Vec<String>, selected: String`。`Config::validate` 要求 selected 是 concrete node，成员也必须是 concrete node，单组所选必须位于成员集。
- `swirl-core/src/lib.rs` 没有 `mod policy`；`Plan` 仅 `config/resolver`；`session` 与 UDP 路由没有 PolicyView；Snapshot 没有健康报告。
- `swirl-protocol/src/lib.rs` 没有 `mod probe` 或 `pub use health_probe`。
- `swirl-subscription/src/policy.rs` 引用了当前 Selector 不存在的 `strategy/probe` 字段；`swirl-core/src/policy.rs` 引用了当前不可导出的 PolicyStrategy、HealthProbe 和 `swirl_protocol::health_probe`。
- 因此文件存在但不可达；cargo fmt/check/clippy/test 默认都不会追踪这些未声明模块，其内置测试也不运行。
- 当前 `tools/ApplyCoreDevelopment.py` 只有两处将旧不支持传输测试的 ws 改为 grpc 的字符串替换，没有把策略候选接入任何 crate。

## 本轮相关风险与建议

### P0：WS 数据完整性和 GitHub 验证身份

先修复分片/Ping 失败；保留长消息、大流量、控制帧优先级、半关闭与取消负面测试。不能只加等待时间或删断言来掩盖丢字节/阻塞问题。精确记录修改前 SHA、修复 SHA、各 CI 实际测试 SHA 与退出码。

当前 `core-development.yml` 的 App token 配置存在，但“token 生成成功”不能单独证明 `.github/workflows/` push 权限。应通过同一 App 身份提交一个必要、可审核且不涉及 Secrets 的 workflow 改动，核对远端 commit，观察该改动实际触发验证。

### P1：新的协议验证需进入正常多平台 CI

`rust-core.yml` 的 push/pull_request 当前只监听 test/main，portable/windows Python 协议列表仍为 core/SS/DoT。开发分支的新 DoH/SOCKS4/WS 仅由 `core-development.yml` 的 Ubuntu 单任务执行。建议给开发分支启用已有 Rust CI，并将这三套测试加入 Linux/macOS/Windows，维持已有 Qt/订阅/Codex 回归。若编译缓存等优化必要，应保持精确源码身份与失败检查。

### P2：Qt WS 映射回归

已知 Qt 映射支持 VLESS WS/WSS、Trojan WSS，默认 Host/path、显式 Host/path、SNI/ALPN 分离。应增加最小正反回归，校验映射结果能由 Rust ABI 接受，并保留未知参数、early-data、自定义头和关闭 TLS 校验的拒绝逻辑。单纯配置接受不能记为 Qt end-to-end 代理转发；真正 Qt WS 转发需连接独立 WebSocket 对端再测原始 origin。

### P3：后续完成已有自动组候选

不能直接把孤立文件接入后就宣布完成。必须逐段接入 IR 验证、选择图/循环检测、具体节点 probe、会话级健康快照、TCP/UDP 路由、热更新/取消、状态报告。验收必须包含全部不健康时失败关闭、无应用重放/静默直连、fallback 优先级、url-test 容差、轮询仅在真实新会话消费时递增、旧会话出口稳定、probe 任务总量/队列边界。

候选 `policy.rs` 还有需明确的调度问题：run 会把一批最多 512 个 probe 全部以 4 并发排空后才处理下次调度；若多成员超时，长批次会使后续组延迟、已测成员健康过期。这个行为有界，但短 interval 在满预算下不保证按时刷新，需测试和公开语义，不能承诺所有节点 interval 精确执行。

### P4：产品接管与剩余协议

现有 Qt 组编辑/节点存储/订阅整体不是 Rust 执行；SOCKS4 产品入口未接通。随后再推进智能规则/DNS split/bootstrap、VMess/SS2022/REALITY/Vision/gRPC/XHTTP/QUIC 等有规范的组合、UDP/TUN、跨平台和长时性能。必须先补真实能力再切换默认构建和移除旧内核。

## 本次审阅范围和未做的事

已读 AGENTS、继续开发入口、完整开发约束、core README/Cargo，审阅所分配的 Rust subscription/DNS/routing/API 全部模块及其内置测试、runtime/probe/policy 关键调用链、Qt Rust adapter/DNS adapter/线程 facade/测试/CMake、历史 C++ engine manager/registry、Mihomo 启动/下载打包路径、C++ importer/update 入口、main 启动与 UI 服务连线，核对 main 日志及差异。

已静态列出 Python test 方法名称/数量，未运行测试：core 19、SS 9、DoT 11、DoH 9、SOCKS4 8、WS 7、subscription capture 23、Codex management 11。部分包含可选 Qt/Windows/外部 CLI skip；数量是定义数量，不能写成通过数量。

本审计代理未编译 Qt、未运行私有节点、公网流量、Windows 外观/TUN、没有查看 App 私钥/Secrets、没有 git commit/push。后续代码修改与运行结果由主代理另记录。

## 随后获授权补充的 Qt WS 回归（待 Windows CI）

主代理授权后，仅修改 `src/Swirl.Quick/tests/RustCoreTests.cpp`，新增两个槽：

- `webSocketMapsExistingFieldsAndRustAcceptsConfiguration`：VLESS WS 默认 Host/path、VLESS WSS 显式 Host/path 与 SNI/ALPN 分离、Trojan 默认强制 TLS；每种配置交给真实 Rust ABI 启动/停止，断言运行状态和 Rust 身份。这是配置映射与 ABI 接受测试，不是 Qt WS 真实转发测试。
- `webSocketRejectsUnsupportedParametersWithoutPartialConfiguration`：覆盖未实现传输、TCP 附带 WS 参数、错误类型、early data、自定义/重复/注入请求头、歧义路径、HTTP/2 ALPN、未实现 UDP、关闭证书验证、VLESS flow；验证返回失败且输出对象保持哨兵值，并验证启动拒绝、无活动内核。

已完成 `git diff --check -- src/Swirl.Quick/tests/RustCoreTests.cpp`，退出码 0。未执行本地 Qt 编译/CTest；当前环境没有可调用的 pkg-config，主代理将使用 Windows Rust CI 编译与执行。没有改 QML、Rust 协议源文件、自动组或 Secrets，没有提交/push。
