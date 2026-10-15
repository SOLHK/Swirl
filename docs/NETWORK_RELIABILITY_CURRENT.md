# 当前源码的连接可靠性修复

本次修复基于用户指定目录中的 `0ae36d6`，在本地 `test` 分支增量实施。保留该版本的 Swirl 原生引擎、Mihomo 兼容引擎、DPAPI 系统代理快照、独立 ProxyGuard、真实 TelemetryService、TUN、网关、LAN、DNS、国内外 MRS 分流、用户规则和策略组。没有使用旧版本的系统代理管理器覆盖这些实现。

## 已定位的 Swirl 自身断连因素

1. 原生 `NativeSession` 在任何流式连接空闲 120 秒后执行 `IdleTimeout`，主动关闭连接。长时间生成或等待消息的 CONNECT / WebSocket 连接可能合法地超过这个间隔。
2. `SwirlProxyEngine` 和 `SwirlEngineManager` 原来的节点选择均执行停止、重新启动，导致其他已建立的连接一起中断。
3. 一条原生连接失败可能触发全局切换兼容引擎，关闭与失败无关的其他连接。
4. `EngineController` 在控制 API 进入 `Degraded` 时释放系统代理，后台订阅更新也会立即停止引擎。数据通道仍可运行时，这些控制行为会改变应用的网络环境。
5. 原生明文 HTTP 入口拒绝 `Upgrade`。Windows 系统代理中的 `ws://` 请求因此无法完成 WebSocket 握手。
6. 原生转发依赖 `QTcpSocket::disconnected` 结束整条连接，没有独立处理 TCP 两个方向的 EOF。

这些是代码中的实际行为与风险因素。尚未使用用户的真实 Codex、订阅或节点复现或验收，不能据此宣布所有重连问题已经解决。

## 实现机制

- 原生协议握手仍保留有界启动超时；完成握手的流式连接取消固定空闲断开。
- 新增 `NativeDuplexRelay`，接管完成握手后的数据转发，保留原 HTTP、SOCKS5、Trojan 认证和协议解析。Windows 复制现有 socket 句柄，再用 Qt `QSocketNotifier` 驱动非阻塞 `recv` / `send`，每次事件最多处理 32 KiB。每个方向的中间队列上限为 256 KiB；TLS 还包含 Qt 自己的有界读写缓存。输出拥塞时停止对应输入读取，不无限缓存。
- 纯 TCP 上游分别跟踪两侧 EOF。一个方向读到 EOF 后，先发完该方向待转发字节，再向另一侧执行发送半关闭；反方向继续读取和转发，直到双方结束。一个 FIN 不再直接中止全部反向数据。
- 保留 `QSslSocket` 处理 TLS 上游的证书、主机名及加密，不复制其内部 TLS 状态。处理 Qt 已解密缓存时安排有界的后续事件，关闭前排空缓存，避免大响应尾部卡住或截断。
- Windows 原生 socket 启用 TCP KeepAlive，配置空闲 30 秒、探测间隔 15 秒；TLS 上游在握手完成时配置同样的底层选项。Mihomo 使用官方 `disable-keep-alive`、`keep-alive-idle`、`keep-alive-interval` 配置。KeepAlive 是失活检测机制，不能保证任何远端永不断开。
- 原生明文 HTTP 入口校验并转发 WebSocket Upgrade，保留必要的 `Connection: Upgrade` 与 `Upgrade: websocket`。源站实际返回的 101 或拒绝响应透明传回；传输层不会把请求发送成功当作升级成功。CONNECT 中的 HTTPS、WSS 和 HTTP/2 字节保持透明。
- 同一引擎中的节点、路由选择仅影响新连接。已建立的连接继续使用创建时节点与出口，不尝试迁移到另一个服务器。确需切换引擎且存在原生流式连接时，明确提示用户先断开重连。
- 原生新连接失败且另有已建立连接时，延后全局兼容回退。排队回退真正执行前再次检查，避免竞态中切断刚建立的连接。
- Mihomo 节点选择通过 PUT 后 GET 核实实际结果。丢失控制响应或健康轮询失败时保留运行进程、已有隧道与系统代理，不以短时 API 超时充当业务连接超时。
- 后台订阅刷新只更新节点库，当前运行配置保留到用户手动断开重连。新增节点和凭据更新不会静默应用到运行中的连接。
- 控制 API 暂时异常时，抓包入口和订阅下载继续使用仍在运行的代理端口，不因健康标志短暂失败而切为直连。

### Codex 在系统代理下的路由一致性

Mihomo 的智能分流配置现在把 `chatgpt.com`、`openai.com`、`oaistatic.com`、`oaiusercontent.com`、`auth0.com` 和 `statsigapi.net` 明确交给当前 `SWIRL` 节点选择器。这些域名规则位于国内域名及 IP 规则集之前，避免同一 Codex 会话中的 HTTPS / WebSocket 请求因规则集或 CDN 地址匹配而被分到直连。用户主动设置的自定义规则仍排在这些默认规则之前；切换 `SWIRL` 选中节点只影响新连接，已有连接保留原出口。Swirl 不调用 Mihomo 的连接清空接口，也不会为延迟测试自动关闭活跃业务连接。

此调整参考 [openai/codex#18647](https://github.com/openai/codex/issues/18647) 的代理侧案例：报告者发现 OpenAI 专属组若固定在失效节点，而主选择器使用另一可用节点，规则模式下的流式会话会反复重连。它是用户环境中的诊断线索，并不证明本机截图的 `request timed out` 就由规则分流引起。现有日志只有脱敏的 Mihomo 握手失败事件，仍需在实际选定节点、系统代理归属和 Codex 会话中复测。

另有 [openai/codex#18471](https://github.com/openai/codex/issues/18471) 的 Windows A/B 报告指出，仅设 Windows 系统代理时 Codex 的 WebSocket 路径可能没有继承该代理，显式代理环境变量才成功握手。Swirl 设置页只提供当前混合端口的进程级环境变量示例，不擅自改 Codex 的配置、用户环境变量或其传输 provider。自定义 HTTP/SSE provider 也不是 Swirl 能保证生效的 Mihomo 选项。

普通明文 HTTP 请求继续沿用单请求、长度校验与关闭策略，避免将后续不同目标的代理请求误当作同一个源站字节流。此次未宣称原生普通 HTTP 支持所有连接池、分块请求或代理流水线用法；需要这些能力可选择兼容引擎。

## TLS 半关闭与主动兼容入口

Qt 的 `QSslSocket` 没有独立发送 TLS `close_notify` 后仍继续保留读取的公共接口。原生 TLS 上游收到客户端 EOF 后保留反向读取，但不能保证以 TCP/TLS EOF 定界的请求完整兼容。普通 HTTPS 和 WebSocket 有自己的消息边界，通常不依靠 EOF 结束请求；具体软件仍须真实验收。

用户可在“设置 → 代理”中，先断开连接，再启用“优先使用 Mihomo 兼容引擎”，然后重新连接。该设置只保存在 Swirl 本地偏好中，节点、DNS、规则和 TUN 配置保持原值。它不修改 `.codex` 配置或密钥。

## 系统代理与异常恢复边界

沿用当前版本 `SystemProxySession` 和独立 `SwirlProxyGuard.exe`，没有叠加第二套接管器。继续同时保存 WinINet 连接配置与旧式代理注册表视图的原始值，快照由当前用户 DPAPI 加密。读取连接标志优先使用 `INTERNET_PER_CONN_FLAGS_UI`，保留自动检测设置；写入和恢复使用微软要求的 `INTERNET_PER_CONN_FLAGS`。

本次补充：

- 进程查询权限不足、时间戳读取失败或等待失败不等同于进程死亡；守护进程不会据此贸然恢复活跃代理。
- 写入前保存 `applyUnconfirmed` 标记，完整写入并读回后才确认。通知、读回或回滚失败时保留恢复快照与所有权，界面显示接管状态未确认。
- 若一次中途失败后，当前配置既不等于原设置，也不等于完整 Swirl 接管值，无法证明差异来自部分写入还是其他软件。保留快照并提示检查 Windows 代理，不擅自覆盖、不删除原 PAC 备份、不宣称恢复成功。
- 已确认其他程序修改代理时让出控制权。守护进程在会话快照被释放或替换后退出，反复开关不会积累旧守护进程。

Windows 策略、权限、磁盘或系统调用本身失败仍可能阻止自动恢复。此时错误与快照会保留，不能保证无条件恢复所有系统状态。

## 用户主动连接诊断

“设置 → 代理 → 本地连接诊断”接受用户填写的 HTTP、HTTPS、WS 或 WSS 地址。只有点击开始后才建立诊断连接，不使用用户订阅自动发起外网测试。

检查本机端口、CONNECT 状态码、TLS 证书及主机名、实际 HTTP 响应，或 WebSocket 101 与 `Sec-WebSocket-Accept`。WebSocket 发送随机掩码 Ping，验证相同载荷 Pong，短时观察 10 秒；控制帧、分片和 7/16/64 位帧长度按边界处理，单帧超过 8 MiB 时只关闭诊断连接。

诊断记录与现有引擎诊断信号关联，包含 Swirl 主动停止、引擎切换、订阅更新延后和控制接口异常等事实。报告不保存目标路径、查询参数、请求正文、WebSocket 载荷或关闭原因文本；关闭帧只记录数字代码。TCP FIN/RST、超时或 502 本身不足以区分上游节点和 Codex 服务端，报告明确保留“来源未确定”。

地址可能要求登录、特定路径或 WebSocket 子协议，通用诊断未完成不等于代理故障。短时 Ping/Pong 通过也不等于 Codex 长期稳定性验收通过。

## 不遵循系统代理的程序

设置页提供只读 PowerShell 代理环境变量示例。完全退出目标应用后，从该终端启动才可能继承；具体程序是否读取由其实现决定。忽略系统代理和环境变量时，应使用应用自身代理设置，或由用户主动开启当前版本已有的 TUN 增强模式。Swirl 不静默写环境变量、不接管 Codex 密钥，不假设任何服务端故障可由本地代理修复。

## 验证状态

新增源码覆盖了原生 Upgrade 转发、切换节点保留现有连接、失败新连接不触发全局回退、大流量转发和主动选择兼容引擎等情形。用户要求节点、代理连通性与图形化软件测试由本人执行，因此回环和真实协议测试仅保留源码并编译，未代替用户运行。

编译和获准的纯内存检查结果由最终交付报告单独记录。所有真实 Codex 重连、长任务、节点切换、DNS/规则/TUN 与视觉结果均等待用户填写验收，当前没有人工验收通过结论。

官方依据：[微软代理选项说明](https://learn.microsoft.com/zh-cn/windows/win32/api/wininet/ns-wininet-internet_per_conn_optiona)、[Mihomo KeepAlive 配置](https://github.com/MetaCubeX/Meta-Docs/blob/main/docs/config/general.en.md)、[Qt 6.8 原生 socket 关闭实现](https://github.com/qt/qtbase/blob/6.8/src/network/socket/qnativesocketengine_win.cpp)。

## 多实例与端口冲突

控制 API 默认尝试 9097；自动模式发现被占用时，会预留操作系统分配的空闲回环端口，配置和界面同步显示实际端口。手动指定控制端口仍严格使用指定值并报告冲突。公开代理端口不会静默更改：若 7898 被另一个 Swirl 或其他程序占用，需要关闭重复实例或在界面更换代理端口。独立节点测速使用自己的测试会话，测试成功并不等于主代理会话已连接；节点页现已明确区分。
