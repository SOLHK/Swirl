# S3 MAX → Ultra 研发交接（阶段冻结）

用户已要求停止本阶段新增研发。冻结总入口见 [S3_MAX_HANDOFF_20261023.md](../S3_MAX_HANDOFF_20261023.md)。下一窗口完成剩余研发后再统一构建最终安装包，由用户做私人订阅及真实联网验收。

## 1. 代码基线和交付边界

- 开发分支：`work/swirl-s3-max-ultra-20261023`。
- 本轮可执行源码 HEAD / 测试 SHA：`3c1fdf29cdb847c59680778efd74eb73a727a7fc`。后续收尾提交仅更新本交接和验证记录，不把它冒充另一次编译验收；最终文档提交的完整 SHA 在交付消息及 `git rev-parse HEAD` 中核对。
- UI 来源：`work/ui-window-node-performance-20261023`，`7056dea1c920cee57208c1aae54b3550a850f758`。
- 订阅/Rust 来源：`work/subscription-unified-integration-20261023`，`384dfe7d15a6f37e206f6db0e4768fa07d4f717d`。
- 共同祖先：`b8aa4f6f40a091697e89ae4c8291789661edca60`。第一次查询时目标远端分支不存在；新建独立检出，未重置或强推，未修改 main/test/来源分支。
- 8 个相关远端 HEAD 已在开始和交付前重新读取。完整来源、祖先关系和 U1 独有提交清单见 [s3-source-inventory.json](s3-source-inventory.json)。`git merge-base --is-ancestor <ui/u1> HEAD` 均成功。

| 检查点 | 完整提交 | 内容 |
|---|---|---|
| A/B | `e4c5ebdb7f662106e14079456d57fc565a4f17b8` | UI 为第一父提交的双亲整合，逐文件解决 17 个冲突，后台采用 U1，保留 U2 界面 |
| C | `5eca691384a9816874cdc0a51cc2cbba42773b53` | 活动会话配置事务、线程停止/启动顺序、订阅身份回归 |
| C/E | `fb8be80bc7785da1302e06ca12aacb21a470dfa7` | DLL 弹窗及替换失败修复、Shadowsocks 官方 fixture 环境隔离 |
| E | `61f9458628b0bb0a64d07bb3db1bfbc8a6c896e2` | 节点刷新性能、实际新版 UI 测试接口、后续研发约束 |
| C/E | `3c1fdf29cdb847c59680778efd74eb73a727a7fc` | 新 CI 失败触发的 QUIC FIN/ACK 生命周期根因修复及真实对端回归 |

已由 U1 包含的 Rust 原生协议、Qt 桥接、Qt HTTP 修复、DNS/MRS 分支不得重复 cherry-pick。`work/u1-public-close-diagnostic-20261023` 的 tip `5ae6b88270193fc40c3a08d871031b050fc500f2` 不是 U1 祖先，基于较早状态；未整分支合并，以免撤销 F6 的规则/测试门禁。当前源码中已有严格关闭及直连对照，旧分支不再作为运行时基线。U1 历史 QML 和旧窗口曲线没有覆盖 U2；Git ancestry 包含来源提交不表示接受每个旧 UI 文件的最终内容。

## 2. 已完成的源码工作

1. **统一产品链**：NodeImportService → NodeImporter/SubscriptionNormalizer → NativeNodeBridge 或 XrayJsonBridge → 同一 RustCoreLibrary → RustCoreEngine/ThreadedEngine → EngineController。普通节点归一参数和 JSON 原文分别进入 Rust 导入 ABI；执行时重新转换，持久化的能力标签不是执行授权。NodeTestService 使用同一 Rust 能力，HEAD 成功后区分出站建立耗时和完整 HTTP 耗时。
2. **保留 UI**：NodeViewModel、搜索/筛选/收藏/详情、分层 Esc、页面几何、窗口与侧栏轮廓、遮罩/抗锯齿、阴影/玻璃/动画均保留。108 个文件由 [s3-ui-baseline.json](s3-ui-baseline.json) 和 `tools/Verify-S3UiBaseline.py` 固定。5 页只接后台状态、JSON 确认和取消；DNS 页只删除不可达的旧内核文案分支，保护器仍检查整页其余字节。WindowEdge、WindowsBackdrop、所有轮廓 shader 未修改。
3. **删除旧内核交付路径**：保留 U1 对 MihomoAdapter、SwirlProxyEngine、NativeDuplexRelay 等旧实现的删除；继续删除旧 Mihomo 专用路径/监控/暂停脚本、旧导入说明、未使用 GPL 许可证资产和打包豁免。Rust-only 保护测试防止重新引入。Clash/Mihomo YAML 作为输入格式保留；历史证据和禁止旧内核的负向测试不是产品依赖。
4. **运行时事务**：活动 `start` 原来先 stop 后验证，坏配置或重复启动会断开有效连接。现在使用 Rust `configure` 原子更新；不合法配置、无节点、监听端口变化均拒绝且保留旧会话。有效切换复用监听，已有隧道继续 A，新连接使用 B。修改前新增回归 3 pass / 7 fail；修复后通过。
5. **线程生命周期**：显式排队 stop 必须执行，即使之后又排队 start；旧状态和旧诊断按 epoch 丢弃，不能跳过释放操作。覆盖换端口停止/重启、旧监听释放、后续双向流量。
6. **Windows DLL**：损坏 DLL 的真实加载曾弹 Bad Image 并使测试超时。现在用线程局部 `SetThreadErrorMode` 抑制加载器对话框，所有返回路径恢复原模式；Qt 与独立 LoadLibraryExW 诊断保留真实错误。拒绝 DLL 替换不再清空已验证的函数入口。加载器 28 项检查含实际 ABI/源码/内容身份及错误 DLL。
7. **构建身份**：MSVC ↔ MSVC Rust 继续严格配对；补充经编译器目标验证的 x64 MinGW ↔ GNU Rust 配对。实际 DLL 必须与 EXE 的源码 SHA、内容 build ID 和 ABI 一致，固定不卸载以保护线程/TLS 析构。MinGW 测试 DLL 去掉错误的 `lib` 前缀。
8. **存储/订阅**：保留 U1 的 DPAPI 写 lease、revision、generation、源身份、原子保存、取消/重试、nodes-only 策略保留及旧数据迁移。名字变化保留 ID；真正端点变化导致悬空策略时拒绝整次刷新，已验证密文、选择、策略、端点和成功时间不变。未读取用户现有 DPAPI 数据，旧数据升级用合成加密 fixture 验证。
9. **下载安全**：只使用活动核心的有效端口或系统/PAC 候选，避免回到已失效自身端口；保留 TLS 验证、重定向/体积/取消/超时边界及请求级 HTTP/2 缓解。未增加隐藏代理核心。
10. **性能/UI 回归**：节点状态指纹初始化，排除无关会话 latency/流量引起的行刷新。测试更新到 U2 的实际 Item 侧栏、Theme 尺寸、内嵌字体页、筛选弹窗、NodeViewModel 与 100 ms 防抖；像素/性能断言保留。180 节点 fixture 用不同端口，避免把同端点别名误当 180 个节点。详情覆盖列表后测试必须返回再点击可见行；旧坐标曾误点编辑按钮，实际截图已确认。
11. **CI/版本**：候选版本 `0.1.6`，NSIS 显式读取 PRODUCT_VERSION.txt。新分支接通 5 组工作流，第三方 Qt/MSVC setup action 固定 SHA；安装包在生产 DLL/EXE/独立目录/UI 门禁后构建，公开网络测试失败仍使作业失败，不改为 continue-on-error。
12. **官方 SS fixture**：父环境 `RUST_LOG=warn/off` 会抑制 TCP/UDP 就绪收据，曾使所有 SS 场景在传输前失败。只给官方服务端子进程设置 info，保留双绑定收据、端口冲突、真实传输和严格关闭断言；新增父环境不被修改的回归。
13. **QUIC 原生关闭根因修复**：61f9458 的 [macOS Hysteria2 HTTPS CI](https://github.com/SOLHK/Swirl/actions/runs/39972868023) 出现真实 SSLEOFError。Quinn 的 AsyncWrite shutdown 只排队 FIN，最后会话随后关闭连接可丢失 TLS close_notify；finish 对收到 STOP_SENDING 也可能返回成功。新增真实 QUIC 无固定 sleep 回归，修改前 0/2、修改后 2/2。现在等待 FIN/数据被 ACK，5 秒有界完成，STOP/断开/超时保留错误；发送收尾 Future 归 stream 所有，取消无后台遗留，读半边可继续、重复 shutdown 幂等。官方 HTTPS 原方法重复 8 个新会话，严格检查对端每次关闭通知。该修复共享于 HY2/TUIC，不能仅验证 HY2。

## 3. 订阅与协议能力矩阵

本表采用用户定义：L1 格式识别；L2 完整解析及参数转换；L3 Rust 配置启动；L4 独立服务端实际传输；L5 用户私人订阅及 Windows 安装后验收。**子集通过不代表该软件的所有协议/扩展都通过；所有 L5 均 NOT TESTED。**

| 格式族 | L1/L2 实际边界 | L3/L4 已验证范围与限制 |
|---|---|---|
| Clash/Mihomo YAML/JSON | 常见代理字段、URI 扩展、保留未知字段；未知执行语义明确拒绝 | SS AEAD/2022、VMess、VLESS/Trojan、HY2/TUIC 的相应 fixture 已有启动/传输；不是完整 Mihomo 配置执行器 |
| Surge、Surfboard | `[Proxy]` 支持的 SS/Trojan/HTTP/SOCKS 等语法；19 格式 Qt 作用域/持久化有覆盖 | SS/Trojan 导入到独立对端；全量规则/DNS/脚本不等价，nodes-only 保留本地策略 |
| Loon | 位置/命名参数、引号和凭据分隔符、SS HTTP-obfs 受控映射 | SS/Trojan/受支持 HTTP-obfs 的认证、数据、半关闭；TLS-obfs 等未实现组合拒绝 |
| Quantumult X | `[server_local]` 的受支持代理行；别名冲突/类型错误拒绝 | 测试覆盖 SS/Trojan 子集；不是完整 filter/rewrite/script 解释器 |
| Shadowrocket、URI、Base64、混合链接 | 标准 URI/VMess JSON/Base64 包装及混合受支持节点；未知选项保留诊断 | 对应协议 fixture 通过的组合可以 L3/L4；不能推导每个厂商私有扩展 |
| v2rayN | 标准 VMess/VLESS/SS/Trojan/HY2/TUIC 分享链接走通用路径 | 标准链接的相应传输已覆盖；**`v2rayn://` 私有 ProfileItemDto 备份链接尚未实现** |
| Xray/V2Ray JSON | 严格结构、重复键/类型/大小边界，展开出站和用户，保留不可执行配置 | HTTP/SOCKS、VMess、VLESS/Trojan 及受支持传输；Windows Qt 实际文件/保存/恢复/传输由独立 fixture 检查 |
| sing-box JSON | 映射子集，不是全字段支持；TLS、传输未知参数拒绝且保留原文 | 已覆盖 SS 和部分 VLESS/Trojan/VMess 传输；**Qt TUIC 适配仍标记研发中**，不能借 TUIC 核心已通过宣称导入闭环完成 |

| 原生协议/传输 | L3/L4 状态 | 必须保留的边界 |
|---|---|---|
| VLESS/REALITY/Vision | 独立 Xray 对端、Chrome/Rust 指纹及 Vision 在 retained CI 检查 | 仅实际列出的指纹/flow/传输组合；不能静默普通 TLS 降级 |
| VMess AEAD | TCP/TLS/WS/WSS、64 MiB、并发、断线重连、已完成响应的关闭通过 | **目标依赖上传 EOF 的严格半关闭 FAIL**，两方法五处失败；4 MiB+17 哈希完整不能抵销关闭失败 |
| Trojan TLS | 证书/名称验证、TCP 与已支持封装、UDP 对端验证 | 错证书/凭据必须阻止到达目标；不允许为了兼容关闭证书验证 |
| SS AEAD / 2022 | 官方 ssserver TCP/UDP、三 AEAD、2022 AES128/AES256、重放/篡改/重连、受控 HTTPS 严格关闭 | **公开 gstatic TLS 关闭 FAIL**；同端点直连对照也 SSLEOFError，仍不能改判 PASS |
| Hysteria2 | 官方对端 17 项；取消、重连、栈隔离、C ABI/Core/UDP/TLS 有当前测试 | Windows loopback 证据不等于用户供应商/真实 WAN 重连和 MTU 验收 |
| TUIC v5 | 独立 Rust server 的 TCP/UDP native/quic、分片、心跳、复用、取消、切换 | v4/0-RTT/禁用 SNI 等未支持要求拒绝；sing-box 全格式映射是独立缺口 |
| WS/H2/gRPC/HTTPUpgrade/XHTTP/QUIC | `test_imported_transports_xray.py`、`test_stream_udp_xray.py` 及 native workflow 的明确组合 | H2 使用单独锁定旧对端；XHTTP 等模式/扩展不是笛卡尔积全支持；VMess 不自动继承 VLESS/Trojan 的传输矩阵 |

代码入口：`core/crates/swirl-subscription/{src/inspect.rs,src/xray,src/hysteria2.rs,src/tuic.rs}`、`src/Swirl.Quick/engine/{SubscriptionNormalizer,NativeNodeBridge,XrayJsonBridge}.cpp`。Qt `NodeImportScopeTests` 的 19 个格式数据行证明作用域/保存/策略，不单独证明 L4。独立网络测试文件和最终结果见第 5 节。

## 4. Ultra 接续任务和验收标准

| 优先级 | 可直接开工的任务 | 文件/验收要求 |
|---|---|---|
| P0 | VMess 严格半关闭 | `swirl-protocol/src/vmess.rs`、`test_vmess_xray.py`。当前发送认证空帧并保留下行；当前源码分析提示 Xray freedom 上传结束未向目标 TCP CloseWrite，目标等待 EOF 可能导致响应无法正常结束；这是待独立客户端/目标事件对照确认的归因，不能视为已排除 Swirl 缺陷。增加同版本官方客户端对照及目标 EOF 事件收据，分别判定协议实现/服务端契约；保持两原始失败测试，不放宽 EOF/WS/TLS 断言 |
| P0 | 公开 SS TLS 关闭 | `test_r1_public_proxy.py`。同一解析地址、TLS 验证成功和 HTTP204 后，代理与 direct control 都缺 orderly close。受控带 close_notify 的 HTTPS 已通过，当前证据倾向公网源站关闭行为，但没有证明所有代理情况无缺陷。增加逐段字节/关闭次序对照和可控公网 origin，原公开失败仍必须展示 |
| 完成研发后 | Windows 最终安装/用户验收 | 按用户最新要求暂缓；下一窗口完成研发和最终构建门禁后，再由用户正常退出旧应用并自行安装验收。不得因本机 Release/loopback 成功就宣称安装、私人订阅或绕过 Clash 成功 |
| P1 | 候选包清单不一致 | UI smoke 在清单生成后写入 `Swirl-diagnostics.txt`，实际 portable 多出此文件。下一窗口修正 staging/最终清单顺序，保留当前失败；本阶段不改打包代码、不删除工件 |
| P1 | sing-box TUIC/HY2 扩展桥接 | 从 `SubscriptionNormalizer::singBox` 和 Rust `Tuic::from_raw` 的差异开始；补字段保真、单位/默认值、TLS、UDP、congestion/heartbeat/zero-RTT 负例；用实际 Qt 导入→DPAPI→Rust→官方对端，不能只增加协议名 allowlist |
| P1 | v2rayN 内部分享格式 | 按官方 `v2rayn://<ConfigType>/<base64url ProfileItemDtoJson>` 版本约束实现，保留未知字段并拒绝未知执行语义。不要重做已有标准 URI 路径 |
| P1 | 剩余协议/组合 | AnyTLS、Snell、Hysteria1、SSR、WireGuard、SSH、TUIC v4、VMess 非 WS 传输、XHTTP 未支持模式/多路复用等按真实需求逐项安排独立 peer；现有识别不得当作原生联网 |
| P1 | 跨平台安全存储 | `NodeStore.cpp::protect` 的非 Windows 分支返回空，Linux/macOS 保存确实未实现。实现 Keychain/Secret Service 的密钥管理和加密文件、迁移/锁定/失败原子性；不能添加明文 fallback。当前平台 build/self-test 通过不表示完整产品可保存 |
| P1 | TUN/网关/局域网/计费接管 | RustCoreEngine 当前明确拒绝；需要平台设备/权限/路由/DNS 所有权和崩溃恢复。只在隔离设备/runner开发，不能在用户当前 Clash 链路上试验 |
| P1 | 规则/DNS完整性 | 已有 DNS/MRS、规则/组的受支持实现不要重写；补剩余订阅全档案语义、RULE-SET/provider、fake-IP/高级 DNS、脚本/重写的明确映射。未支持时保持整个配置事务失败，nodes-only 仍保留用户策略 |
| P1 | WAN QUIC 稳定性 | 在独立 Windows 机器上加入丢包、切网、休眠、NAT/MTU、长时间并发/取消；复用当前栈隔离和生命周期测试，不恢复旧不安全路径 |
| P2 | 应用自动更新 | 订阅定时更新已存在，**应用程序签名更新/回滚机制尚未实现**。设计签名元数据、版本单调、下载哈希、退出确认与失败回滚；不得混称订阅刷新和软件更新 |
| P2 | 订阅更新体验 | 条件请求/ETag/304、结构化新增/变更/删除摘要；复用 NodeStore 写 lease/revision 和 cancelRefresh，不另造存储系统 |
| P2 | CI与安装包 | 处理本轮明确失败；Windows MSVC 与本机 GNU 分别记证据。保留生产 tests-OFF、无 DLL 负向门禁、双次 isolated UI 启动、精确 DLL 哈希、NSIS 版本一致；候选包不是正式发布 |

可以并行推进“格式映射及其独立 fixtures”“跨平台存储”“TUN 平台所有权”“签名更新/打包”，但同一 NodeStore/EngineController/ABI 文件必须由一名集成人负责。协议修改与 Qt UI 通过稳定 ABI 协调。不要重复实现已完成的 loader、普通/JSON 转换、DPAPI 事务、节点模型、轮廓 shader；新增字段先补拒绝/保真和真实流量测试。

## 5. 当前源码测试及证据

所有当前证据对应 `3c1fdf29cdb847c59680778efd74eb73a727a7fc`；旧 SHA 的中间通过/失败单独保留。

| 验证 | 命令/入口 | 实际结果 |
|---|---|---|
| Rust workspace | `cargo test --manifest-path core/Cargo.toml --workspace --locked --offline` | 680 passed / 0 failed / 0 ignored，40 suites，含 doctest |
| Rust 格式/静态检查 | `cargo fmt --manifest-path core/Cargo.toml --all -- --check`; `cargo clippy --manifest-path core/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings` | 退出 0；GNU linker 曾报告 `.drectve` warning，不能称零 warning |
| Windows 完整 CTest | `ctest --test-dir D:/Codex/build-swirl-s3-max-20261023 -E swirl-system-proxy-recovery --output-on-failure` | 28 suites / 0 failed，含原生字体、外观、节点、导航、Hero、HTTP 安全、DNS/导入/生命周期；未注册系统代理写入测试 |
| 独立 Qt 导入/存储 | `ctest --test-dir D:/Codex/build-swirl-s3-import-20261023 --output-on-failure` | 9 suites / 0 failed；真实 DPAPI/取消/作用域/JSON/ABI |
| Rust–Qt 主套件 | `SwirlRustCoreTests` | 85 passed / 9 conditional skips；条件 fixture 项的 skip 不算通过，另由 Windows Qt fixture Actions 实际执行 |
| Windows 独立 Qt fixture | `python tools/Run-U1QtFixtures.py` (Actions) | 9/9 槽实际执行，缺失 0；authentication-failure/cancel/http-control/reject/tls12 生命周期 |
| 实际 DLL loader | `SwirlRustCoreLibraryTests` | 28 passed；含成功/错误 DLL/ABI/source/build/恢复模式 |
| 受控原生网络 | `python -m unittest test_vmess_xray.VmessXrayTests test_imported_transports_xray test_stream_udp_xray test_basic_proxies_xray test_ss2022_official test_subscription_import test_hysteria2_official test_hysteria2_lifecycle test_tuic_reference test_quic_core test_quic_ffi test_native_timing -v` | 103 methods，success=True，失败断言 0，错误 0；本机环境变量指向锁定服务端、当前 inspector/client/DLL |
| 严格 VMess | `python tools/tests/test_vmess_xray.py --strict-half-close` | **FAIL**：2 methods / 5 处失败断言；原报告不覆盖、不豁免 |
| UI 源保护 | `python tools/Verify-S3UiBaseline.py` | 108 文件通过；不是人工视觉/L5 验收 |
| 源/包/身份保护 | `python tools/test_rust_only_runtime.py`; `scripts/tests/Test-RustProductPackagePolicy.ps1`; `tools/tests/Test-SwirlCoreIdentity.ps1` | 8 tests；29 package assertions + 14 staging cases；42 identity cases（该脚本含合成元数据，不替代实际 DLL） |
| 本机正式产品 | CMake `Release`, `SWIRL_BUILD_UI_TESTS=OFF`; `Swirl.exe --rust-core-self-test`; `--smoke-test` 两次 | EXE v0.1.6.0，HTTP/SOCKS5/CONNECT/监听释放通过；缺 DLL 拒绝、两次隔离 UI 启动通过。GNU 测试/正式 DLL SHA256 相同 `53cc55e6239b6fbdbc8e487b8276aacbde62428c513f2e214029c20abc8365c1` |

| 当前 SHA 的 Actions | 终态 | 失败范围 |
|---|---|---|
| [U1 complete Windows Qt independent fixtures](https://github.com/SOLHK/Swirl/actions/runs/39975447359) | SUCCESS | 全部作业通过 |
| [U1 retained native network regressions](https://github.com/SOLHK/Swirl/actions/runs/39975447372) | FAILURE | retained-network-tests (macos-14): Execute both original strict VMess peer-closure methods, Require complete actual results and matching source identity; retained-network-tests (ubuntu-24.04): Execute both original strict VMess peer-closure methods, Require complete actual results and matching source identity; retained-network-tests (windows-2022): Execute both original strict VMess peer-closure methods, Require complete actual results and matching source identity |
| [R1 source and package guards](https://github.com/SOLHK/Swirl/actions/runs/39975447333) | SUCCESS | 全部作业通过 |
| [Swirl Native Protocols X14](https://github.com/SOLHK/Swirl/actions/runs/39975447341) | SUCCESS | 全部作业通过 |
| [Rust sole runtime and unified product](https://github.com/SOLHK/Swirl/actions/runs/39975447386) | FAILURE | windows-product: Windows native public Internet requests; rust: Public Internet through authenticated Rust Shadowsocks |

候选安装包已由生产门禁后生成：[Actions 下载入口](https://github.com/SOLHK/Swirl/actions/runs/39975447386/artifacts/12511774885)。Artifact `Swirl-Rust-Windows-x64-candidate-3c1fdf29cdb847c59680778efd74eb73a727a7fc-1`，大小 168678481 字节，sha256:e6eb8a4f90b666d749a3e4d1c6eaacd1d185c40b983c93986f800f7225b3dad6。下载归档包含 `Swirl-Setup.exe` 和 portable ZIP，整体 artifact SHA256 已核对。**完整包清单检查 FAIL**：1509 个清单文件无缺项，但多出 `Swirl-diagnostics.txt`；后续逐文件哈希及 PE 检查没有执行，不能称完整安装包验证成功。详见 [s3-installer-verification.json](s3-installer-verification.json)。整体工作流的公网严格关闭失败仍未豁免。保留全部远端工件；未安装到用户机器，不是正式发布，最终安装验收已按用户要求暂缓。

公开 SS 的控制证据：验证证书并收到 HTTP204 后，代理与相同解析地址直连对照均在 origin-close 报 SSLEOFError；受控 close_notify 正/负对照全部保留。HTTP 成功与严格关闭失败分别记录。已修复的旧 macOS HY2 失败在 61f9458 的 run 39972868023，不用后来绿灯删除历史失败。

本分支全部 25 次 CI（含历史失败及 4 次 cancelled 产品运行）的终态、失败/取消步骤和链接保存在 [s3-ci-history.json](s3-ci-history.json)；取消不算通过，后来成功不覆盖历史失败。

详细计数、当前作业/步骤、原始日志 SHA256、EXE/DLL 身份及 artifact 清单见 [s3-validation.json](s3-validation.json)；保留的失败、直连对照及修复前证据见 [s3-retained-failures.json](s3-retained-failures.json)。本机原始记录在 `D:/Codex/outputs/s3-max`；GitHub artifacts 有保留期限，请在到期前按需保存。


## 6. 开发环境与重跑

- 独立检出：`D:/Codex/work/Swirl-s3-max-ultra-20261023`；本机输出：`D:/Codex/outputs/s3-max`。
- 本机 Windows / Qt 6.10.3 MinGW / Rust 1.99.1 GNU；CI Windows 使用 Qt 6.11.3 MSVC。两者不能相互冒充。
- CMake 显式指定可用 Python（含 cryptography），不要让 FindPython 自动选到另一个无依赖解释器。Qt offscreen 测试要设已安装 SDK 的插件目录；`SWIRL_TEST_ROOT` 必须预先创建为 D 盘绝对目录。
- `SwirlSystemProxyTests` 是实际 WinINET 写入测试。本机未执行；普通 CTest 不注册该项，禁止设置 `SWIRL_SYSTEM_PROXY_TEST`。状态诊断测试只读真实配置并使用独立测试注册表键。
- 首轮/中间失败没有删除：缺离线依赖、GUI 测试插件、旧字段/几何/坐标 fixture、错误 Python、父 RUST_LOG、原始严格关闭失败分别记录在本机日志。测试命令曾误写模块名/重用 C ABI 证据路径，后续完整菜单已使用正确模块和新目录重跑；这些启动错误不能归为协议失败或虚计通过数。
- 不安装覆盖现有产品，不启动私人订阅，不停止 Clash，不改变代理/TUN/路由/DNS。没有声称“无 Clash 独立联网”或 L5 完成。

## 7. 主要参考

- [v2rayN 官方订阅/内部分享格式](https://github.com/2dust/v2rayN/wiki/Description-of-subscription)：参考标准输入和私有备份格式边界，不复用其运行时。
- [sing-box VLESS 配置](https://sing-box.sagernet.org/configuration/outbound/vless/)：按具体 flow/UDP/transport 字段对照，不以客户端品牌推断兼容性。
- [Tokio 双向转发半关闭](https://docs.rs/tokio/latest/tokio/io/fn.copy_bidirectional.html)。
- [锁定 Xray VMess 加密/结束帧](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/common/crypto/auth.go)、同提交 `proxy/vmess/inbound/inbound.go` 与 `proxy/freedom/freedom.go`。
- [Microsoft SetThreadErrorMode](https://learn.microsoft.com/en-us/windows/win32/api/errhandlingapi/nf-errhandlingapi-setthreaderrormode)：避免隐藏加载器对话框，不修改整个进程的错误模式。
- [Quinn SendStream::stopped](https://docs.rs/quinn/0.11.12/quinn/struct.SendStream.html#method.stopped)：finish 排队、ACK 完成、STOP_SENDING 的区别；已对照本次锁定依赖源码。
- 独立服务端版本/哈希仍以 `tools/tests/*peer-lock.json` 为准；只作为测试对端，禁止装进产品充当 Rust Core。
