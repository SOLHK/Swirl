# U1 订阅、节点与 Rust 产品链路源码审计

审计日期：2026-10-23。审计对象为统一集成分支在 **208e50dbd5f0b05b607afab0386fd4bb0dae8b79** 的已提交源码，以及随后待纳入的系统代理/诊断补丁 **b3a6f624372ecb4f67debc18bcf250a723f05c1f**。本文依据 Git 提交关系、实际 C++/QML/Rust 实现和测试输出编写；来源分支名称是审计时快照，不表示其后续 HEAD。

**本文是功能与缺口审计，不是最终同一 SHA 的验收证明。** 独立组件、候选工作树和来源分支上的测试不能相加为统一产品通过。最终干净提交 SHA、完整命令、环境、Actions 链接和重跑结果由 [U1 总报告](U1-REPORT.md) 记录。本文所述正在修复的项目，必须在最终提交重新检查实现与测试后才能改成通过。

> 后续集成状态说明：本文以 208e50db 的源码审计为历史基线，文中 U4/U5、后台取消等“待提交”表述不是最新分支的状态。这些实现已进入后续 U1 提交。F5 `2340f835a7f35321567554cbaf4613b425b54638` 的三平台九套导入回归、Windows 实际 DPAPI/取消/重试、七协议业务、九槽及完整 31 项捕获测试已有对应实际记录，详见 [U1 总报告](U1-REPORT.md) 的 F6 历史表。F6 的新 SHA 仍需重新回归，不能继承这些绿灯。非 Windows 加密存储、CA 生成/导入/签发及部署安装包仍是代码或交付缺口，不是仅待真机的事项。

## 1. 当前结论

订阅和手动节点已共用 NodeImportService、NodeStore、ProxyNode，并接入同一个主业务 RustCoreEngine。Xray/V2Ray JSON 与通用 URI/Clash 节点都经过同一 Rust DLL 的权威转换和运行时配置校验，不存在因为 Qt 解析成功就直接标记真实联网成功的许可。主业务节点切换、停止与重启沿同一所有权链管理。

跨平台完整产品闭环仍不能宣称完成。**Linux/macOS 的 NodeStore 加密实现缺失是代码问题**：protect 返回空，持久化明确失败；因此添加订阅、保存节点、重启恢复在这些平台被阻断。Windows 的加密持久化代码和相关自动化测试存在，但本文没有最终 SHA 的 Windows 真机、合法真实订阅与完整外网业务验收证据。受控本地 SOCKS 握手与双向业务数据测试也不能代替该验收。

后台订阅刷新在审计基线没有用户取消入口。后续 U1 候选已新增专门的 cancelRefresh(id)、排队/活动状态和挂起下载取消/重试回归，并补同步信号重入守卫；代码复核情况见第 9 节，Windows 加密持久化测试仍须实际执行，不能预先算通过。HTTP 条件缓存、304 复用以及新增/变更/删除的更新差异摘要尚未实现。

## 2. 来源与集成记录

下表的 S 编号仅为便于在功能表中引用；每项对应的完整 SHA 均列在本表。U 编号为 U1 的本地独立补丁提交，最终远端可追溯入口是其集成提交及提交说明，不保证这些本地 SHA 单独具有公开 GitHub 页面。

| 编号 | 来源分支或补丁 | 完整来源 SHA | 实际功能与集成位置 |
|---|---|---|---|
| S1 | work/subscription-import-20261021 | bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29 | 订阅解析、节点目录、导入服务、持久化和更新基础；通过订阅桥接基线继承 |
| S2 | work/xray-v2ray-json-import-20261021 | 44dda9d4fe27a6667aa977d879d8dfc2ca82688d | Rust Xray/V2Ray JSON 解析和严格配置转换；通过桥接基线继承 |
| S3 | work/xray-v2ray-json-b-20261022 | 4e9f6ea0411c03bba418bb46884748ba7e0ba03b | JSON 扩展解析和边界；通过桥接基线继承 |
| S4 | work/xray-v2ray-native-20261021 | b88bb978d31fad1865e1b648cecd4f230bc3487c | 原生 outbound/运行时映射；通过桥接基线继承 |
| S5 | work/xray-v2ray-transport-20261022 | fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870 | 已实现的原生传输能力与严格边界；通过桥接基线继承 |
| S6 | work/xray-v2ray-qt-import-20261022 | 506014d6386610411f48c939ab62cb93a3509431 | Qt JSON 导入/预览、目录、运行测试；通过桥接基线继承 |
| S7 | work/subscription-native-bridge-20261023 | 442138a3d40fc13a9a761b43f3a2ce829a2b47ec | U1 订阅基线；实际权威桥接改动为 7b35bb1474fa5827c3e184231e07d059609532a7，tip 为后续测试 |
| S8 | R1 成果，work/core-completion-20261017 历史 | 5d96214ac80d63985cdccf4942c3c1d79035e793 | 统一 Rust 生命周期、DLL 检查、移除旧引擎运行入口；在 dbac73776979bab68d6b942fd402170d1bca1410 集成。审计时该分支 HEAD 为 f87b6f98eb7018c4a5e86f281fe707764565ce58 |
| S9 | work/qt-http2-security-20261023 | 9dd8a675eed6374ac1c35265074f594a39262479 | 请求级 Qt HTTP/2 缓解与下载回归；实质缓解为 8cf8d9ed93a38816ba09112ab485911e29480fca；在 aa5f7d10e5b43b4e6168171d3b4d306308727210 集成 |
| S10 | work/rust-native-protocols-x14a-20261022 | 2a41b360d0fed90bf2818d5e4c8e93b4f41f021b | HY2 等原生协议与 Windows 栈隔离成果；748040cb84f4a71d79a99cc50ab3807f828b6351 纳入。关键修复为 21c562a7c7adc2654416636e4de2f038ffc220cd、5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611、b6fba1827b0136c50123dab41fa4cb1c79a9ebce |
| S11 | work/product-ui-fixes-20261021 / work/swirl-performance-20261021 中的必要网络语义 | bbb4ea33d3a3ae596027b840af630260ba6bdbcc | 选择性重做 nodes-only 行为，未合入独立 UI/字体/版本改动；格式证据源 871cc6e93a083c8624aadae8d9f4c1fe8db6e7e8；748040cb84f4a71d79a99cc50ab3807f828b6351 记录来源 |
| S12 | work/swirl-performance-20261021 中的必要性能语义 | 2b186783a704af3f4c1a91cd835997485282e2ec | 测速引擎/遥测合并调度；完整 HTTPS 耗时标记来源 9e892b3746012ef8b1d983467b45cf6f336ddbe7；选择性纳入 748040cb84f4a71d79a99cc50ab3807f828b6351 |
| S13 | feat/phase3-final-integration 中的系统代理及隐私诊断 | 564e213ce604d7b79bb2414cd3aefba5744d46eb | 选择性移植 WinINET/native registry 差异检查及诊断脱敏；U5 保留原有恢复和 ownership 强度 |
| U1 | agent/u1-subscription | f362f94b277c3e11778b2982ffba38ce16214f78 | NativeNodeBridge 和通用节点导入 ABI；兼容修补 f7bb468d3b032c23a3fc2e3ed6e93bedd8b65323；均纳入 748040cb84f4a71d79a99cc50ab3807f828b6351 |
| U2 | agent/u1-subscription-tests | 92a4900b1c8581ce7d0796f989ccb9755d9d80a3 | 修正旧不合理协议 fixture；VLESS/WS UDP 正向转换/启动及畸形 UDP 类型负例；纳入 748040cb84f4a71d79a99cc50ab3807f828b6351 |
| U3 | U1 nodes-only 集成补丁 | dbfdc0bd355383234aecb1a537accaa5b9e592ca | 在原有原子存储/写 lease 上实现导入作用域，不另建数据库；纳入 748040cb84f4a71d79a99cc50ab3807f828b6351 |
| U4 | U1 系统代理下载补丁 | 6482e048d803f7087a4a5f9269209819e8e7914c | 系统/PAC 代理解析、候选回退、取消/超时和原有代理所有权保护；纳入 748040cb84f4a71d79a99cc50ab3807f828b6351 |
| U5 | agent/u1-system-proxy | b3a6f624372ecb4f67debc18bcf250a723f05c1f | 有界只读系统代理诊断、allowlist 状态、URI/PSK/auth/用户名脱敏及独立测试；审计时 root 待提交候选已纳入 |

分支包含相同源码不等于需要再次 cherry-pick。S2–S6 的实现由 S7 继承；U1 的新增入口复用 swirl-subscription 中已有映射器。R1 合并时保留 Qt 产品服务层和解析器，统一 loader，而不是通过删除服务层消除冲突。U3 在原有写 lease、revision、取消守卫上增加作用域，未以较旧的 nodes-only 整段替换强度更高的存储代码。

## 3. 功能、产品接入与测试层级

层级定义：L1 为识别、解析和参数转换；L2 为 Rust typed config 校验与实际 listener 启动/停止；L3 为独立对端握手与双向业务数据；L4 为真实产品 UI、下载、加密保存、选择、分流业务、切换与重启的完整同 SHA 验收。测试某一层不自动满足更高层。

| 功能 | 来源 | 当前源码及产品入口 | 实现、集成和冲突处理 | 实际证据与未验收部分 |
|---|---|---|---|---|
| 格式识别与导入 | S1–S7、U3 | [NodeImporter](../../src/Swirl.Quick/engine/NodeImporter.cpp)、[SubscriptionNormalizer](../../src/Swirl.Quick/engine/SubscriptionNormalizer.cpp) | 已集成；Clash/Mihomo 兼容格式、URI/Base64/Shadowrocket、受支持 INI 和 sing-box 子集归一到 ProxyNode；JSON 走 Rust；修复 INI 方括号误入 JSON | 格式 fixture 为 L1，不能推导每种协议组合可联网 |
| JSON 权威转换 | S2–S7、S8 | [XrayJsonBridge](../../src/Swirl.Quick/engine/XrayJsonBridge.cpp)、[RustCoreLibrary](../../src/Swirl.Quick/engine/RustCoreLibrary.cpp) | 已集成；原始 JSON 交 Rust，并共享 R1 loader/ABI 检查；选择/启动时重放原始配置 | 组件覆盖转换与拒绝语义；真实服务器需按协议逐项 L3/L4 |
| 通用节点权威转换 | U1、S4、S5、S10 | [NativeNodeBridge](../../src/Swirl.Quick/engine/NativeNodeBridge.cpp)、[node_import.rs](../../core/crates/swirl-api/src/node_import.rs)、RustCoreEngine::buildNativeConfig | 已集成；Qt 归一结果连同原始参数交既有 Rust inspector，未新增另一套协议解析器；冲突值明确拒绝 | 13 个 URI/Clash 数据行有 L1/L2 候选结果；本地 SOCKS 受控业务有 L3；不是 13 种真实服务端互通 |
| 添加、删除、手动节点 | S1、S6、U3 | [ProxiesPage](../../src/Swirl.Quick/qml/pages/ProxiesPage.qml)、[SubscriptionsPage](../../src/Swirl.Quick/qml/pages/SubscriptionsPage.qml)、NodeImportService、NodeStore | 已集成；统一服务层；默认 nodes-only，显式 full-profile；删除订阅保留已有节点为手动节点，并清空来源关联 | UI 调用关系已核；Windows 持久化和完整交互需最终回归；非 Windows 被 A1 阻断 |
| 单一节点/配置存储与恢复 | S1、S6、S7、U3 | [NodeStore](../../src/Swirl.Quick/engine/NodeStore.cpp) 的 load、文件级 persistSnapshot/protect，ProxyNode 序列化 | 部分实现；一份 nodes.dpapi 包含节点、订阅和网络配置；选择 sidecar 只含 ID/快照摘要；旧版本迁移保留 | Windows 实现和测试存在；Linux/macOS protect 返回空，是代码缺口，不能标成只待设备验收 |
| 语义去重、刷新及选择保留 | S1、S6、U3 | NodeStore::semanticIdentity/sourceAnchor/prepareImport/commitImportAsync | 已集成；来源隔离、完整身份比较、稳定 ID；歧义/悬空策略引用拒绝整次更新；不恢复旧的弱存储实现 | 选择/重排/快照绑定/原子失败测试存在；最终 Windows 同 SHA 持久化回归仍须记录 |
| 更新作用域和策略保留 | S11、U3 | NodeImportService::applyParsedResult，EngineController 的作用域/配置验证 | 已集成；nodes-only 保留本地 DNS/规则/组；旧无 scope 订阅仍按 full-profile；不从新节点静默覆盖策略 | 19 格式作用域 fixture 是导入语义覆盖；不代表全格式原生运行或非 Windows 加密保存成功 |
| HTTP(S)/系统代理下载 | S1、S9、U4 | [NodeImportService](../../src/Swirl.Quick/engine/NodeImportService.cpp)::download/代理解析路径 | 已集成；活动 Core 本地代理优先，其次系统/PAC；外部仅 HTTPS，字面 loopback 可 HTTP；TLS 正常验证 | 本地 TLS/CONNECT、系统代理、重定向/超时/体积限制组件测试；真实生产代理/PAC 环境待验收 |
| 取消、重试与调度 | S1、S6、U4、后续 U1 候选 | NodeImportService::cancelImport/cancelRefresh、refreshSubscription、刷新队列、generation/提交守卫 | 手动取消已集成；后台专用取消已进入待提交候选，保留提交边界并隔离手动导入所有权 | 新增挂起下载、队列、重试、加密快照及重入回归；Windows 实际结果和最终 SHA 仍待记录 |
| 缓存与更新差异 | S1 | NodeImportService 的 HTTP 完成和应用结果路径 | 未实现条件缓存/304 重用及结构化差异摘要；当前报告解析数量，不是净新增/变更/删除数量 | A 类代码缺口；无测试可以替代尚未实现的行为 |
| Qt 下载安全 | S9、U4 | [HttpRequestPolicy](../../src/Swirl.Quick/network/HttpRequestPolicy.h)、NodeImportService 请求构造 | 已集成请求级 HTTP/2 缓解；TLS 验证保持；统一下载路径调用该策略，不另留旧订阅下载器 | 适用版本与官方公告核对见统一安全报告；本文只证明产品请求调用关系和回归边界 |
| 主业务 Core 生命周期、节点切换 | S8、S7、U1 | [main.cpp](../../src/Swirl.Quick/main.cpp)、[EngineController](../../src/Swirl.Quick/engine/EngineController.cpp)、[ThreadedEngine](../../src/Swirl.Quick/engine/ThreadedEngine.h)、[RustCoreEngine](../../src/Swirl.Quick/engine/RustCoreEngine.cpp) | 已集成；一个主业务 Core 所有权链，启动/配置/选择/关闭沿同一 handle；无 Mihomo 回退 | L2 和受控 SOCKS L3 证据；真实 UI/存储/路由/切换/重启 L4 待最终平台验收 |
| 测速与时间口径 | S12、S8 | [NodeTestService](../../src/Swirl.Quick/engine/NodeTestService.cpp) | 已集成；至多三个独立 Rust 测速 worker，与主业务 handle 隔离；HEAD 最终响应首部累计耗时、出站建立累计耗时及目标 TLS 耗时分别记录。出站值包含节点 DNS/TCP 或 QUIC/协议握手，不是裸 RTT；不包含响应体下载或 Core 启动 | 不能据此宣称比 Loon/Clash 更快；需同节点/目标/协议/网络条件的测量 |
| 敏感信息保护 | S1、S6、U1、U5 | ProxyNode::publicInfo、publicSubscriptions、桥接诊断过滤、[DiagnosticService](../../src/Swirl.Quick/app/DiagnosticService.cpp) | 已集成基础脱敏；U5 为待提交候选补强；URL/凭据不作为下载错误文本；日志/导出统一处理 | U5 有持久化/重载/导出脱敏回归；不是对任意未来日志的形式化无泄漏证明 |

## 4. 数据完整性与并发检查

- **原始字段保留。** 非 JSON 节点保存 originalConfiguration、options、conversionIssues 和凭据；保留语义配置，不承诺 YAML 注释/排版逐字还原。JSON 原文按 SHA-256 去重保存，节点记录 sourceNodeIndex，重载时重新经 Rust 解释。缓存中的可执行标志不能单独授予执行权限；新 DLL 拒绝旧配置时保留原配置并禁用执行。
- **关键参数不以默认值覆盖冲突。** NativeNodeBridge 对 server、port、用户、密码、cipher、SNI 等归一字段与保留参数作一致性检查。未知字段保留并产生转换问题或严格拒绝；非法 UDP 类型不能被布尔默认值吞掉。空/缺省可选项兼容修补不会放宽非空未知字段。
- **去重不是仅比较服务器和端口。** semanticIdentity 包括协议、大小写规范化主机、端口、用户名、密码、cipher、SNI、选项及必要的未映射原始参数。同端点不同凭据/传输不合并；不同订阅来源不相互吞并。先精确语义匹配，再按可信原始位置或唯一来源别名匹配；歧义拒绝整个计划。
- **更新原子性。** prepareImport 只构造计划；写 lease、owner/revision、cancel guard 和 QPointer 生命周期保护异步提交。工作线程使用值快照，成功提交后才采用新内存状态。策略引用失效时拒绝节点和配置整个事务。QSaveFile 不启用直接覆盖回退，选择 sidecar 绑定密文快照摘要，旧 sidecar 不得覆盖更新后的选择。
- **刷新不等于自动重连。** 当前活动会话保留其启动时不可变节点快照；后台更新不自动替换正在使用的凭据、不自动切到 DIRECT。已移除节点的活动会话到停止为止；新节点/新凭据需要显式断开重连。选择失败有回滚路径，空选择不能隐式变成直连。
- **大小和资源边界。** 下载/导入受 4 MiB 限制；节点 1–2000、订阅至多 32、存储快照 32 MiB；另有单节点原始配置/选项、深度及遍历预算。FFI 单节点输入另有 1 MiB 限制。达到限制明确失败，不截断配置后继续启动。
- **主 Core 与测速 Core 的准确关系。** main 创建一个主 ThreadedEngine；桥接转换复用 RustCoreLibrary，不启动另一个业务实例。NodeTestService 可创建至多三个隔离测试 Core，独立 loopback 端口，不继承 TUN/LAN/用户路由。这是同一 Rust 实现中的明确用途隔离，不能描述为“整个进程永远仅有一个 Core handle”。

## 5. 下载、取消和错误行为的具体边界

外部订阅 URL 必须 HTTPS，URL 中的 userinfo/fragment 被拒绝；HTTP 只允许明确的 127.0.0.1 或 ::1 测试端点。总期限 30 秒，包含系统/PAC 代理解析；Qt 传输期限 15 秒；响应体同时受 Content-Length 和流式读入上限约束。重定向最多五次，仅允许同 scheme、host 和有效端口，不允许降级或跨源携带订阅令牌。

活动 Swirl HTTP 代理优先；非活动时通过平台系统代理/PAC 查询保留有序 HTTP/SOCKS5/DIRECT 候选，DIRECT 仅来自系统明确返回。过期的自身代理端口被过滤，但不会误删其他程序的 loopback 代理。字面 loopback 下载绕过系统和 Core 代理。

cancelImport 中的 generation、reply 断开/abort/deleteLater 和工作回调校验保护手动取消后重试；平台代理解析的阻塞调用本身不一定可中断，但过期回调无权再应用结果。审计基线对 m_committing 或非空 m_source 提前返回，因此该基线的后台刷新不可取消。后续候选单独新增 cancelRefresh：取消排队项或在提交前撤销对应 source 的活动回调，不通过放宽 cancelImport 来混用所有权。关闭对象清队列仍是另一种生命周期行为；提交阶段及成功提交后的 nodesApplied 通知阶段禁止取消。

自动更新按启用状态与 15–10080 分钟间隔调度；失败有 900 秒冷却，手动刷新可重新发起完整请求。网络恢复并不包含 Range 断点续传，也没有 ETag/Last-Modified 条件请求、磁盘响应缓存或 304 复用。错误保持旧节点；结果数量不是差异摘要。

下载错误使用固定描述/状态码，避免把 URL query、响应正文或原始 TLS 异常写入日志。ProxyNode::publicInfo 不包含凭据、原始参数；公开订阅列表不包含 URL。Rust JSON 路径对任意未知键作脱敏，Qt 标签和原生桥接诊断使用相应过滤。U5 继续覆盖 SOCKS/TUIC URI、用户名、auth/PSK 和 Unicode 域名等导出路径。这里的结论是已检查调用链未发现直接记录原始认证材料，不是任意输入下的完整隐私证明。

## 6. 实际支持边界：不能把格式成功当作协议联网

依据 [inspect.rs](../../core/crates/swirl-subscription/src/inspect.rs)、[inspect_stream.rs](../../core/crates/swirl-subscription/src/inspect_stream.rs)、[inspect_reality.rs](../../core/crates/swirl-subscription/src/inspect_reality.rs)、[vmess.rs](../../core/crates/swirl-subscription/src/vmess.rs)、[hysteria2.rs](../../core/crates/swirl-subscription/src/hysteria2.rs)、[tuic.rs](../../core/crates/swirl-subscription/src/tuic.rs) 及 [Xray security::map_stream](../../core/crates/swirl-subscription/src/xray/security.rs) 核查。下表为源码能力与拒绝边界，不是标准服务端全矩阵实测。

| 格式/协议组合 | 已接入的参数/能力 | 明确限制或拒绝行为 |
|---|---|---|
| VMess URI/Clash/JSON | AEAD、alterId=0、auto/aes-128-gcm/chacha20-poly1305；TCP 或 WebSocket，按配置 TLS | 旧 alterId、UDP、REALITY、启用 global padding/authenticated length 不支持；H2/gRPC/HTTPUpgrade/XHTTP 在 map_stream 提前拒绝，不会被降为 TCP；TLS 指纹只支持明确的原生选项 |
| VLESS TCP/WebSocket | UUID、TLS/SNI/ALPN、合法 WS 参数；普通配置的 UDP | WS 非 Host 自定义头、非零 early-data 等未实现配置不能静默遗漏；畸形 UDP 类型拒绝 |
| VLESS REALITY/Vision | 通用节点显式支持的 rustls/chrome/chrome_133 指纹、public key/short id；Vision 为 REALITY+TCP 的 xtls-rprx-vision | Xray 输入另有来源名称边界：chrome/HelloChrome_133 可映射，内部 rustls/chrome_133 不能当 Xray 来源别名。推断默认指纹不授予执行；REALITY UDP、普通 TLS Vision、vision-udp443、其他 flow、非 TCP Vision 不支持 |
| VLESS/Trojan gRPC/H2 | 既有 Rust stream mapper，显式服务名/主机等参数 | 要求相应 options；gRPC 未映射 host 参数不能猜成 authority，非零 ping 等不支持；Clash H2 要求明确单个 host，多主机/省略 host 不推断 |
| HTTPUpgrade/XHTTP | HTTPUpgrade 显式开启；VLESS 已映射的 XHTTP stream-one | fast-open、early-data 的未实现值拒绝；XHTTP auto/packet-up/stream-up/未知 extra 不支持；REALITY 高级传输仅所实现的 gRPC/XHTTP 组合，不能推导全部 transport 支持 |
| Trojan | 密码、TLS/SNI/ALPN、受支持 TCP/WS/stream；按对应 typed outbound 处理 UDP | 必须 TLS；非空 username、SS 专用 cipher 等不适用字段拒绝；TLS 验证不能关闭 |
| Hysteria2 | 原生 v2 QUIC、TCP/UDP、h3、密码、Salamander、受限带宽/证书参数 | ports/mport hopping、ECH 等未实现；hysteria:// v1 不猜成 v2；产品入口拒绝 insecure/skip-cert-verify；Windows 专项必须独立验收 |
| TUIC | v5 UUID/password、native/quic UDP relay、cubic/bbr/new_reno | v4 token、reduce-rtt/disable-sni/fast-open/udp-over-stream 等启用选项不支持；URI 额外路径及冲突别名拒绝；不得关闭证书校验 |
| SOCKS5 | TCP、可选 TLS、普通 UDP、认证 | TLS+UDP 不支持；受控本地 SOCKS 业务测试不能代表全部服务器兼容性 |
| SOCKS4/4a | USERID、TCP、远端域名能力按对应版本 | password、TLS、UDP、启用 TFO 不支持 |
| HTTP 代理 | CONNECT TCP、可选 TLS 和认证 | 不支持 UDP、REALITY 或混合未定义 transport |
| Shadowsocks | Rust 已实现的 AEAD/2022 范围及明确映射的 HTTP obfs | 不能按目录里的协议名称宣称所有 cipher/plugin 支持；未知 plugin、TLS obfs、启用 TFO 等拒绝 |
| SSR/Snell/Hysteria1/WireGuard/SSH/AnyTLS/Mieru 等目录类型 | 可识别/保留的部分格式和原始选项 | 目录协议枚举不构成原生执行能力；未通过 Rust inspector 的节点保留诊断，禁止执行 |
| Clash/INI full-profile | 有限 proxy-groups/rules 映射，要求末尾 MATCH；只允许受支持的自包含节点/组/DIRECT/REJECT 引用 | DNS 及其他全局 dialect 未映射时明确拒绝；不允许猜测外部已存节点、SWIRL/GLOBAL 别名。nodes-only 不应用这些全局参数 |
| Xray/V2Ray/sing-box 完整配置 | 支持范围内的 outbound 提取，原始 JSON 保留 | 不等于应用其 inbounds/DNS/routing/所有全局配置；未支持的执行字段形成拒绝诊断，不用另一内核兜底 |

主业务运行时另外明确拒绝尚未实现的 TUN、gateway、LAN 等配置。保留设置并给出错误有助于兼容旧数据，但不构成这些运行模式已实现；相关缺口属于代码问题。

## 7. 已观察测试证据与可用范围

本节故意保留失败与作用域限制。日志不自带完整源码快照时，不能借后来重写的 toolchain 文件追认旧日志属于新 SHA。所有缓存 DLL、dirty worktree 或独立分支结果只能作为诊断/组件证据。

| 证据 | 实际观察 | 可以证明什么 / 不能证明什么 |
|---|---|---|
| u1-qt-tests-B.log，候选工作树 | 七个组件目标通过，loader 曾因旧 build fixture 失败；之后的修复/重跑应按新日志单列 | 证明候选组件能运行，且构建身份失配被拒绝；不能将此日志写成全部通过或绑定最终 SHA |
| build/xray/swirl-native-node-bridge.xml | 13 个 URI/Clash 数据行解析、Rust 转换、listener 启停通过；importedSocksNodesCarryRealTrafficSwitchAndRejectWrongCredentials 通过 | 前者 L1/L2；后者受控独立 SOCKS 的握手/业务/切换/错误凭据 L3，绕过真实 UI 和加密存储，不是 L4 |
| u1-product-tests-candidate.log | RustCoreTests：43 pass、28 fail、9 个既有条件 skip；失败主要在非 Windows 存储前置；该 Linux stream 失败也在安全保存前置，遥测另有无效 UUID fixture；后续 Windows stream 暴露的是语义去重后计数旧断言 | 必须保留失败，不能把存储失败称为“Linux 不适用”后算绿；后续代码变更要求重跑 |
| u1-208-windows-product.log，208e50dbd5f0b05b607afab0386fd4bb0dae8b79 | Windows Server 2022、Qt 6.11.3/MSVC 2022；RustCoreTests 为 68 pass、3 fail、9 个既有条件 skip | 三项失败涉及 Xray 权威模型/来源名称、提前原生拒绝、INI 稳定 ID 的旧断言；对应修补 9e6120544e4f9dd87bff4fd34c08edb6559cc1b0 保留存储/业务/回滚意图并添加正反例，须统一新 SHA 重跑 |
| b3a6f624372ecb4f67debc18bcf250a723f05c1f 的 build/system-proxy-local-tested-sha.txt、build/system-proxy-local-regression.log | Linux、Qt 6.10.3、GCC 13、C++23；23 个 SystemProxyState 与 12 个 Diagnostic 测试通过，0 fail/skip | 精确独立提交的组件证据；Windows 独立 volatile registry fixture 在 Linux 未执行；不能替代 U1 最终 SHA |
| Xray Store / NodeImportScope 持久化测试源码 | encryptedDocumentRoundtrip、legacyStoreMigration、refreshAndSelectionIdentity、reorderedAccountsKeepSelectedIdentity、selectionSidecarSnapshotBinding、atomicFailureKeepsOldStore；及 nodes-only policy/selection/scope 测试存在 | Windows DPAPI 前提下必须运行最终二进制；注入式格式验证通过不等于真实加密存储通过 |
| 下载组件测试源码与候选输出 | 真实本地 TLS/CONNECT、证书拒绝、同源重定向、系统代理回退、自身旧代理过滤、loopback 绕过、取消/重试、代理解析超时等 | 受控下载链证据；没有真实提供商临时订阅、平台生产 PAC 或 Windows 真机完整流程的替代作用 |

建议最终回归直接使用既有 [NativeNodeBridgeTests](../../src/Swirl.Quick/tests/NativeNodeBridgeTests.cpp)、[NodeImportScopeTests](../../src/Swirl.Quick/tests/NodeImportScopeTests.cpp)、RustCoreTests、SubscriptionFormatTests、Xray Download/Store/Runtime 测试及对应 CMake 注册目标。不得为生成绿色结果跳过非 Windows 的产品持久化失败；应先实现该平台保护器，或如实记录产品不支持。本文不新增重复测试，也不以来源分支的历史通过替代最终测试。

## 8. 剩余工作分类

### A. 必须继续研发的代码问题

1. **Linux/macOS 安全存储保护器及迁移。** NodeStore.cpp 的文件级 protect(input, decrypt) 和 LAN 密码保护是 Windows 专用；需要平台安全存储实现、兼容/可回滚迁移及失败语义，不能明文回退。修复前跨平台完整保存/重启产品链不成立。已比对 47 个远端 refs（43 个唯一 HEAD）的 7 个 NodeStore blob，以及全部可达历史中 14 个相关提交/13 个 blob：protect 只有一种实现，均为非 Windows 返回空，未发现可直接合入的平台保护器。
2. **条件缓存与更新差异。** ETag/Last-Modified、304、更新差异摘要和必要的缓存失效策略未实现；失败后重试是新下载，不是断点恢复。
3. **未实现的产品模式/配置组合。** TUN/gateway/LAN、完整第三方 DNS/routing 方言及上表未支持协议组合按实际需求继续研发；不能标成“只待真机”。严格拒绝这些组合是当前安全行为，并非协议全覆盖完成。

### B. 已开发但尚未完成集成的问题

本次已核的订阅主链来源没有另外确认的遗漏实现需要整段合入；S2–S6 不应重复合并。本文件所在的 U1 集成提交同时包含 U5、后台取消和 Windows 三项断言校正，它们的执行状态归 C，不能因已写代码即标记通过。此结论限于表中已核来源，不代表其他无关实验分支已合入。

### C. 已集成但没有通过统一回归的问题

历史候选产品 RustCoreTests 有 28 个实际失败；非 Windows 存储根因归 A1，不能当作已通过。后台取消的加密快照/重启/重试与提交边界、loader、遥测、节点身份和 stream 回归，以及 CI 编译/工作流修复，必须在同一最终干净 SHA 重跑并记录。本文没有最终 Windows/macOS/Linux 全绿的证据，不引用其他分支绿灯填空。

### D. 已实现、仍需 Windows 或其他真实环境验证的问题

Windows DPAPI 保存/更新/重启、系统代理恢复与所有权、真实平台 PAC、Windows Hysteria2 栈/QUIC/退出、合法真实订阅的端到端 UI 操作、国内直连/国外代理与最终出口、业务切换后网络恢复，均需相应环境的最终 SHA 验收。Linux/macOS 先完成 A1，之后才可把其持久化测试归入此类。凭据只能在私有环境使用，证据不得泄露 URL、令牌或节点认证材料。

**产品状态回答：** 主业务架构和关键组件已统一，存在实际受控代理业务证据；当前证据不足以宣布所有平台从订阅导入到真实业务联网及重启恢复完整闭环。Linux/macOS 首个明确阻断是安全保存；Windows 的代码链需由最终提交的完整平台回归与真实产品验收确认。本文不将这两种情况混为一类。

## 9. 后续候选只读复核：后台刷新取消

本节检查 root 待提交的 NodeImportService.h/.cpp、SubscriptionsPage.qml 和 XrayDownloadTests.cpp，未改写其工作树，不把候选源码视为已发布提交。

- cancelRefresh 只移除指定队列项或取消匹配 source 的活动刷新；unknown ID 不得取消手动导入，cancelImport 也不得取消后台刷新。generation 递增撤销旧解析/系统代理回调，reply 先断开再 abort/deleteLater。取消仅更新服务内状态和冷却时间，不调用节点库写入，因此已存密文/选择保持原值。
- m_committing 在写入前设置，并保持到成功通知后的 finish；NodeStore 原有 write lease、revision、值快照和原子替换不变。取消不得在加密提交已开始或 nodesApplied 表示持久化完成后返回成功。
- next 在通知前复制 URL/id 并捕获 generation；changed 直接槽同步取消、编辑或删除来源之后，必须重新验证 busy/source/generation/shutdown，才可开始下载。手动文本、文件、URL、确认和 apply 入口也需在 changed 后做等价守卫，避免取消已成功却仍解析或保存。
- 新 Windows 测试包含半响应悬挂下载、排队取消、活动取消、原密文逐字不变、选择/节点重载、再下载成功以及提交/已提交通知阶段拒绝取消；另有非 Windows 可运行的手动所有权及重入边界测试。这些是新增测试覆盖，**此审计尚无新最终 SHA 的 Windows 执行结果**。
- 独立核查远端和历史未找到 Keychain/libsecret/QKeychain/keyring 产品存储实现。源码中的 macOS temporary keychain 仅用于 TLS 下载 fixture，不能充当节点库加密保护器；A1 保持代码缺口。
