# Swirl S3-MAX 阶段冻结交接 · 2026-10-23

本阶段按用户要求停止新增研发，只收尾、保存证据、提交和推送。下一窗口继续剩余研发，全部开发完成后再统一构建最终 Windows 安装包，由用户完成真实订阅导入和联网验收。本文件不是最终产品验收证书。

## 1. 分支、提交与整合关系

- 当前分支：[work/swirl-s3-max-ultra-20261023](https://github.com/SOLHK/Swirl/tree/work/swirl-s3-max-ultra-20261023)。
- **最终研发 Commit / 本文所有当前构建与测试的精确源码 SHA：`3c1fdf29cdb847c59680778efd74eb73a727a7fc`。**
- 本交接和证据文件在该提交之后单独提交，收尾不修改运行代码、测试实现或工作流。包含本文件的最终交付提交 SHA 由 `git log -1 --format=%H -- docs/S3_MAX_HANDOFF_20261023.md` 查询，并在交付回复给出；不将文档提交冒充另一次构建验收。提交无法在自身内容中预填自己的 Git SHA。
- UI 基线：`work/ui-window-node-performance-20261023` / `7056dea1c920cee57208c1aae54b3550a850f758`。
- U1 来源：`work/subscription-unified-integration-20261023` / `384dfe7d15a6f37e206f6db0e4768fa07d4f717d`。
- 共同祖先：`b8aa4f6f40a091697e89ae4c8291789661edca60`；整合提交 `e4c5ebdb7f662106e14079456d57fc565a4f17b8` 以 UI 为第一父提交，逐文件解决冲突。两个来源均为当前 HEAD 的祖先，保留其成果及历史；旧 QML 最终内容未覆盖新版 UI。
- 已提交修复依次为 `5eca691384a9816874cdc0a51cc2cbba42773b53`、`fb8be80bc7785da1302e06ca12aacb21a470dfa7`、`61f9458628b0bb0a64d07bb3db1bfbc8a6c896e2`、`3c1fdf29cdb847c59680778efd74eb73a727a7fc`，详细内容见下文及 [Ultra 技术交接](handoffs/S3_MAX_TO_ULTRA.md)。
- 所有 8 个相关来源 HEAD 在开始和收尾重新读取，来源完整 SHA、祖先关系及 U1 独有提交清单见 [来源记录](handoffs/s3-source-inventory.json)。旧 `work/u1-public-close-diagnostic-20261023` tip `5ae6b88270193fc40c3a08d871031b050fc500f2` 不属于 U1 祖先，未整分支合入，避免撤销更新的规则/门禁实现；当前严格关闭测试仍保留。
- 独立检出位于 `D:/Codex/work/Swirl-s3-max-ultra-20261023`；未重置、强推或修改 main、test、来源及其他并行窗口分支。

## 2. 已完成的订阅和产品链

1. 普通导入与 JSON 导入共用权威 Rust 转换及执行能力，串通 NodeImportService、NodeImporter、NodeStore、NativeNodeBridge、XrayJsonBridge、RustCoreLibrary、RustCoreEngine、ThreadedEngine、EngineController 与 NodeTestService。执行前重新验证，不以旧缓存的“支持”标签授权运行。
2. 节点选择和切换使用运行中原子 configure；失败配置、无节点、非法监听变化保留有效会话，成功切换保持监听及旧隧道，新请求走新节点。显式 stop 不再被后续 start 的 epoch 丢弃，迟到状态/诊断被过滤。
3. 订阅取消、重试、写入 lease/revision/generation、DPAPI 原子保存、旧数据迁移、节点身份保持和 nodes-only 策略保留已集成。真正端点变化使用户策略悬空时，整次刷新拒绝且原密文、策略、选择和成功时间不变。迁移只使用合成加密 fixture，未读取私人订阅。
4. 下载保留证书验证、重定向/大小/超时/取消限制及 HTTP/2 安全处理，规避已失效的自身代理端口。Qt 产品服务层没有第二个隐藏代理内核。
5. Mihomo/旧 C++ 内核运行及交付路径已删除，继续清理旧暂停/路径监控脚本和无用许可证资产。Clash/Mihomo **输入格式**仍支持；历史文档/负向测试里的名称不是运行依赖。
6. DLL/EXE 校验 ABI、完整源码 SHA、内容 build ID；实际 loader 28 项通过。损坏测试 DLL 的 Bad Image 弹窗通过线程局部错误模式解决，加载错误仍保留；替换失败不清空已验证函数入口。MSVC/MSVC 和经目标验证的 x64 MinGW/GNU 严格配对。
7. 指定 UI 的窗口/侧栏曲线、尺寸、裁剪、玻璃、阴影、搜索/筛选/收藏/详情和分层 Esc 保留。108 文件源码保护通过；只接必要后台状态/确认/取消。节点无关遥测不再触发整行刷新，UI 测试适配真实新版控件和可见点击路径，未退回旧布局。

## 3. 实际格式和原生协议范围

L1 = 识别，L2 = 参数转换，L3 = 原生配置启动，L4 = 独立服务端真实传输，L5 = 用户 Windows 安装后真实订阅验收。下表的 L2/L3/L4 只覆盖明确测试的子集，**所有 L5 均 NOT TESTED**。“支持某软件”不代表其全部规则、脚本或协议扩展已兼容。

| 输入格式 | 当前范围及缺口 |
|---|---|
| Clash/Mihomo YAML/JSON | 常见代理及受支持参数转换；未知执行语义拒绝，不能当完整 Mihomo 配置执行器 |
| Surge / Surfboard / Loon / Quantumult X | 各自代理区受支持语法、SS/Trojan 等子集；Loon 的受支持 HTTP-obfs 有独立传输；不是全部规则、重写和脚本解释器 |
| Shadowrocket / URI / Base64 / 混合节点 | 标准链接、VMess JSON 和 Base64 包装走通用路径；不推定私有扩展全支持 |
| v2rayN | 标准分享链接支持对应协议；`v2rayn://` 私有 ProfileItemDto 备份格式未实现 |
| Xray/V2Ray JSON | 严格结构/重复键/类型/体积检查，展开出站及用户；Qt 导入→保存→恢复→实际传输有独立 fixture |
| sing-box JSON | 已有字段映射子集；Qt TUIC 桥接仍有缺口，不能把 TUIC 核心通过当作此格式全链通过 |

| 原生协议/传输 | 当前 L3/L4 证据与限制 |
|---|---|
| VLESS / REALITY / Vision | 独立 Xray 对端及明确指纹/flow 组合通过；保留拒绝不支持组合和禁止普通 TLS 静默降级 |
| VMess AEAD | TCP/TLS/WS/WSS、64 MiB、并发、重连及普通响应通过；**严格目标半关闭仍 FAIL：2 方法、5 处失败** |
| Trojan TLS | 证书/名称、认证、已支持封装及 UDP 受控对端通过；未知组合不推定支持 |
| Shadowsocks AEAD / 2022 | 官方 ssserver TCP/UDP、3 类 AEAD、2022 AES128/AES256、重放/篡改及受控 HTTPS 严格关闭通过；**公网 gstatic 严格 TLS 关闭 FAIL** |
| Hysteria2 | 官方对端 17 项及生命周期/取消/重连/Core/FFI 测试；本轮修复 QUIC FIN 尚未 ACK 时连接先销毁，最终三平台 native CI 通过；不代表供应商 WAN 稳定性已验收 |
| TUIC v5 | 独立 Rust 对端 TCP/UDP、分片、心跳、复用、取消/切换通过；v4/0-RTT/禁用 SNI 等未支持要求拒绝；格式映射缺口另计 |
| WS / H2 / gRPC / HTTPUpgrade / XHTTP / QUIC / UDP | 仅 `test_imported_transports_xray.py`、`test_stream_udp_xray.py` 和 native 菜单的明确组合；H2 锁定独立旧对端，不宣称协议与传输的所有组合通过 |

AnyTLS、Snell、Hysteria1、SSR、WireGuard、SSH 等剩余协议不可因被识别就标记原生联网完成。逐字段范围、代码入口及下一窗口要求见 [详细能力矩阵](handoffs/S3_MAX_TO_ULTRA.md#3-订阅与协议能力矩阵)。

## 4. 当前源码自动化结果

以下均对应源码 `3c1fdf29cdb847c59680778efd74eb73a727a7fc`。

| 验证 | 结果 |
|---|---|
| Rust workspace，`cargo test --manifest-path core/Cargo.toml --workspace --locked --offline` | **680 passed / 0 failed / 0 ignored**，40 suites（含 doctest） |
| Rust fmt / clippy（all targets，`-D warnings`） | 退出 0；GNU linker 有 `.drectve` warning，未宣称零警告 |
| Windows 完整 CTest | **28 suites passed / 0 failed**，含 UI、网络安全、DNS/MRS、模型和生命周期 |
| 独立 Qt 导入/DPAPI/存储 CTest | **9 suites passed / 0 failed**，223 个 Qt pass incidents |
| Rust–Qt 主套件 | **85 passed / 9 conditional skips**；skip 不计通过，另由下列 Windows CI 实际 fixture 执行 |
| Windows Qt 独立 fixture CI | **9/9 槽实际执行，0 缺失** |
| 本机受控原生协议网络菜单 | **103 methods passed / 0 failure / 0 error** |
| 原严格 VMess 半关闭 | **FAIL：2 methods / 5 failure assertions**，断言未放宽 |
| UI 源码 / Rust-only / 包与身份保护 | 108 文件；8 tests；29 包断言和 14 staging cases；42 身份 cases；合成身份检查不冒充实际 DLL 验证 |
| Release UI_TESTS=OFF 产品 | 本机 GNU v0.1.6.0 构建、自测 HTTP/SOCKS5/CONNECT/监听释放、缺 DLL 拒绝和两次隔离 UI 启动通过；与 CI MSVC 包分别记账 |

完整命令、环境、原日志哈希、产物身份和步骤结果见 [验证 JSON](handoffs/s3-validation.json) 及 [详细测试说明](handoffs/S3_MAX_TO_ULTRA.md#5-当前源码测试及证据)。本机原日志保留在 `D:/Codex/outputs/s3-max`。没有在用户电脑执行会写 WinINET 的 `SwirlSystemProxyTests`，也未改变 Clash、系统代理、TUN、路由或 DNS。

## 5. GitHub Actions 与真实失败

| 当前源码运行 | 终态 | 结论 |
|---|---|---|
| [Native protocols · 39975447341](https://github.com/SOLHK/Swirl/actions/runs/39975447341) | **SUCCESS** | 三平台 6 作业通过 |
| [Source/package guards · 39975447333](https://github.com/SOLHK/Swirl/actions/runs/39975447333) | **SUCCESS** | 源与打包保护通过 |
| [Windows Qt fixtures · 39975447359](https://github.com/SOLHK/Swirl/actions/runs/39975447359) | **SUCCESS** | 实际 9 槽完整执行 |
| [Retained network · 39975447372](https://github.com/SOLHK/Swirl/actions/runs/39975447372) | **FAILURE** | 三平台原严格 VMess 两方法及汇总门禁失败 |
| [Unified product · 39975447386](https://github.com/SOLHK/Swirl/actions/runs/39975447386) | **FAILURE** | Linux 和 Windows 公网 Shadowsocks 严格 TLS 关闭失败；构建/产品门禁及候选包生成通过不能覆盖整个工作流失败 |

- **VMess**：4 MiB+17 双向字节及哈希完整，仍缺认证结束/正确 WS 关闭；目标等待上传 EOF 的半关闭契约未通过。Xray freedom 的目标 CloseWrite 行为是待对照验证的原因，不能简单宣布对端问题或 Swirl 无缺陷。下一步增加同版本官方客户端与目标 EOF 收据，保持原失败测试。
- **公网 Shadowsocks**：证书验证通过、HTTP 204 后，origin-close 发生 `SSLEOFError`；相同解析地址的直连对照也失败。受控严格 TLS 正/负对照 3/3 及官方 SS HTTPS 通过。当前证据提示公网源站关闭行为需要区分，但不能将 204 改写为严格关闭成功，也未证明所有代理路径无缺陷。
- **历史 macOS HY2**：[39972868023](https://github.com/SOLHK/Swirl/actions/runs/39972868023) 在 `61f9458628b0bb0a64d07bb3db1bfbc8a6c896e2` 真实 HTTPS 关闭失败；新增 QUIC 回归先 0/2、修复后 2/2，当前源码三平台 native 通过。保留历史失败，不用后来绿灯删除证据。
- 本分支 **全部 25 次运行**（含中间失败及 4 次 cancelled 产品运行）的 SHA、终态、失败/取消步骤和链接保存在 [CI 历史](handoffs/s3-ci-history.json)。取消不算通过，已失败的子作业不会被取消终态隐藏。原关闭失败、直连对照及修复前证据在 [保留失败 JSON](handoffs/s3-retained-failures.json)。

## 6. Windows 安装包状态

**候选包已生成并保留；最终安装、正式发布与私人订阅验收均未完成。**

- [Actions 候选包下载入口](https://github.com/SOLHK/Swirl/actions/runs/39975447386/artifacts/12511774885)，工件名 `Swirl-Rust-Windows-x64-candidate-3c1fdf29cdb847c59680778efd74eb73a727a7fc-1`。
- 工件 ZIP 为 168678481 字节，SHA256 `e6eb8a4f90b666d749a3e4d1c6eaacd1d185c40b983c93986f800f7225b3dad6`；本地下载完成且该整体摘要匹配，归档包含 `Swirl-Setup.exe` 和 `Swirl-Rust-x64.zip`，并非源码 ZIP 冒充安装器。
- **完整 portable 清单检查 FAIL**：1509 个清单文件无缺项，但多出测试产生的 `Swirl-diagnostics.txt`。UI smoke 在清单生成后写入诊断文件，随后被打包；逐文件哈希与 PE 检查在此失败后没有执行。因此不能宣称完整安装器已核验。
- [安装包检查记录](handoffs/s3-installer-verification.json) 保留这一问题。下一窗口修复 staging/最终清单顺序并重新构建；当前阶段不继续修改打包代码，不删除远端工件，不覆盖已安装产品。Actions 工件有保留期限，下载入口可能要求 GitHub 登录。
- 最终安装包下载及验收已按用户要求暂缓；当前候选包不是最终推荐安装版本。

## 7. 下一窗口研发优先级

| 顺序 | 工作及完成条件 |
|---|---|
| P0 | 严格 VMess：官方客户端/目标 EOF/认证结束帧对照，修复根因，三平台保留原严格断言通过 |
| P0 | 公网严格关闭：同地址同证书 direct/proxy 分段关闭对照与可控公网 origin，区分源站行为和代理缺陷；真实失败继续报告 |
| P1 | 安装包清单：去掉测试诊断产物或在 smoke 后生成最终清单，逐文件校验、版本/身份、NSIS/portable 内容一致 |
| P1 | 格式缺口：sing-box TUIC/HY2 字段桥接、v2rayN 内部分享格式；逐字段保真/拒绝负例，再做 Qt→DPAPI→Rust→独立对端 |
| P1 | 剩余协议/传输：按明确需求和锁定独立对端逐项实现；禁止只加协议 allowlist 或静默降级 |
| P1 | Windows QUIC WAN 稳定性：隔离设备上的丢包、休眠/切网、NAT/MTU、长时间取消/重连；不干扰用户 Clash |
| P1 | TUN/网关/LAN/计费接管与高级规则/DNS：当前未实现的接管路径明确拒绝；补平台权限、路由/DNS 所有权、恢复与完整规则语义 |
| P1 | 跨平台存储：非 Windows `NodeStore::protect` 当前返回空；实现 Keychain/Secret Service 密钥管理及加密/迁移，不加明文 fallback |
| P2 | 应用签名自动更新/回滚（订阅定时刷新已存在）、ETag/304 和订阅变更摘要；复用现有事务，不另造状态系统 |

已完成 loader、导入转换、DPAPI 事务、节点模型、QUIC 修复和 UI 曲线不应重复开发。格式适配、跨平台存储、平台 TUN、签名更新可在下一窗口划分独立任务；共享 NodeStore/EngineController/ABI 由明确集成人协调。本阶段不启动这些后续研发。

## 8. 最终真实联网验收步骤（待所有研发完成后）

1. 下一窗口在同一最终源码 SHA 重新完成 Rust、原生互通、严格关闭、Qt/DPAPI/身份/选择切换/刷新取消、HTTP 安全、DNS/MRS、生产 tests-OFF 与 UI 回归，保留失败/跳过的真实状态。
2. 统一构建最终 Windows 安装包，核对 EXE/DLL 源码、版本、摘要和完整清单，验证安装/升级/卸载及失败恢复。当前阶段不安装。
3. 用户在准备好的验收环境自行导入私人订阅；不向仓库、CI、日志、转换服务或聊天提交令牌、密码及节点。逐格式/协议/传输记录样本范围。
4. 用户验证导入/刷新/取消/失败回滚、规则和 DNS 保留、收藏/选择/搜索/详情、节点切换、TCP/UDP、HTTPS 关闭、长连接、重连及休眠恢复。
5. 若需证明不依赖 Clash，必须由用户准备允许改变网络状态的独立验收环境并明确授权；采集监听所有权与实际出口/路由证据，结束后恢复。当前环境的受控测试不能证明无 Clash/TUN/透明转发依赖。
6. 分别记录“构建成功”“自动化通过”“受控联网通过”“用户真实供应商与安装后验收通过”。只有实际执行并有证据的组合可提升到 L5，禁止概括成所有真实订阅均已联网。

## 9. 冻结交付核查

收尾提交仅包含本文件、更新后的 Ultra 交接和白名单验证/失败/CI/安装包记录。推送目标固定为当前分支，不强推；交付回复给出最终完整提交 SHA，并核对 `git rev-parse HEAD` 与 `git ls-remote origin refs/heads/work/swirl-s3-max-ultra-20261023` 一致。文档提交使用 `[skip ci]`，不重复构建或将已有源码结果伪装为新 SHA 的结果。远端 Actions 和安装包工件保持原状。
