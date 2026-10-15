# 6A 网络连接修复与验证边界

本轮网络修复不修改 QML。同一工作区此前按 6A 要求完成的交互、弹窗和退出修改予以保留。

## 已确认的源码问题

- `NodeTestService` 复制主会话选项，使测速内核可能继承 TUN、网关、计费模式、LAN、入口认证和用户 DNS/规则。改为从默认选项按白名单构建独立测速会话，只保留内核身份、节点及拨号依赖；释放测试进程期间仍计入并发和 busy 状态。
- `MihomoAdapter::setRoutingMode` 将控制响应失败当作整个内核失败，可能关闭全部现有 TCP 连接。改为保留内核、读取实际模式并核实。控制请求已生效但响应丢失，以及请求被拒绝两种回归，在旧代码失败、新代码通过。监听端口、LAN、TUN 等安全检查继续生效。
- 原生转发原先与 GUI 共用事件循环。生产入口现在使用 `ThreadedEngine`，在独立线程运行内核和网络对象；GUI 只接收排队的状态快照。兼容引擎降级判断同时计入已接入但仍在握手的连接，避免一个新连接失败引发其他连接被停止。

## 路由和连接策略

- 默认 OpenAI/ChatGPT 域名路由指向 SWIRL；默认智能 DNS 对 chatgpt.com、openai.com、oaistatic.com、oaiusercontent.com 及子域使用同一 SWIRL 出口。GLOBAL 包含 SWIRL，避免默认选择器分离。
- 用户自定义规则、hosts、DNS 仍保留。命中部分已知 Codex 域名/进程且覆盖默认选择器时记录诊断；复杂规则仍需根据实际连接链核对。这不是对所有用户覆盖规则的一致性保证。
- 测速、导入更新不重启主内核、不调用清空连接接口。主动切换同类节点影响新连接；旧节点上的健康流继续传输，已失败的连接按真实 socket 结果结束。跨内核且仍有活动连接时提示需要显式断开重连。
- 未添加 Clash Verge 的 `auto_close_connection` 配置键，未修改 Codex、Clash 或 Windows 全局设置，未通过无限重试或延长超时隐藏失败。
- 原生连接日志记录关闭方、错误码、上游 CONNECT/SOCKS 返回码、握手/传输时间和字节数，不记录载荷或密码。HTTPS CONNECT 内部的 WS/SSE 应用语义仍是加密内容，不能仅凭 TCP EOF 判定响应完整。

## 自动化测试

使用 Qt 6.10.3 / MinGW 13.1 / Release；开启 `SWIRL_BUILD_UI_TESTS` 构建测试目标。Mihomo 通过仓库锁定的 manifest 校验。以下命令在已配置的构建目录运行：

```powershell
ctest --test-dir <build> -R 'swirl-(native|stream-regression|node-real-chain|engine-contract)' --output-on-failure
<build>/SwirlEngineTests.exe routingResponseFailurePreservesProcess
<build>/SwirlNodeTests.exe probesNeverInheritNetworkOwnership isolatedBatchNeverChangesMainSelection
$env:QTEST_FUNCTION_TIMEOUT='1500000'
$env:SWIRL_LONG_STREAM_SECONDS='1200'
<build>/SwirlNativeTests.exe threadedTunnelSurvivesUiStallAndIdle
```

测试覆盖真实本地 TLS、RFC6455 Upgrade/帧/ping/close、分块 SSE、服务端拒绝、截断流、慢接收、测速、节点切换、失败的新拨号与仍健康的旧流、规则/全局模式、实际导入服务更新。20 分钟 CONNECT 回环测试包含 135 秒空闲及 1.8 秒 GUI 线程阻塞。它们不等于真实 Codex 会话验收。

## 只读现场诊断

```powershell
./tools/Collect-CodexNetworkEvidence.ps1 -OutputPath ./network-path.json
python ./tools/Probe-CodexProxyPath.py --ports 7897 7898 --output ./reachability.json
```

第一项记录进程路径、PID、TCP 端点、Windows/WinHTTP 代理、代理环境变量是否配置及相关 DNS 缓存。Process 环境仅属于采集进程，不代表已运行 Codex 的环境。第二项仅检查未认证 HTTP CONNECT/TLS/HTTP；403、404 不能视为 Codex 流成功，也不能据此断言代理认证错误。

## 2026-10-16 现场结论与未验收项

00:17:49（UTC+8），当前会话记录 `error decoding response body` 并重试 1/5。附近的路径快照显示 Codex app-server 经 Clash 的 7897；旧 Swirl 运行在 7898，修复版仍在构建目录。另有远程控制 WebSocket 10060 超时，它与模型 Responses 输出通道不同，不能合并归因。现有记录不足以确定断开由服务端、节点、Clash 或本地网络哪一层触发。

两代理生成配置均关闭 TUN；Clash 使用 fake-ip，Swirl 使用 redir-host。没有实证证明本次发生 Fake-IP 缓存污染或双重接管，也没有通过清缓存伪装修复。当前执行器没有代理环境变量，不代表运行中的所有 Codex 子进程均如此。

真实 Codex 经新版 Swirl 的长流、Windows 系统代理接管/恢复、真实 TUN、UAC 取消、真实订阅定时 HTTPS 更新、用户商业节点切换、不同出口 IP 下的会话行为仍未完成验收。需要在明确授权的切换窗口进行；不能从回环测试推导这些场景已修复。

### 后续受控验收（01:37–01:46，UTC+8）

用户随后明确授权临时切换系统代理，并另行授权附件中的设置转场、圆角、README 修复与 main 推送。下列结果替代上段中“系统代理接管/恢复尚未验收”和“没有真实 Codex 测试”的部分；TUN 等剩余项目仍未验收。

- 使用与 `611f086` 网络实现一致的测试 GUI（记录了实际可执行文件 SHA-256，测试入口开启，嵌入版本号来自提交前配置），从当前用户真实 DPAPI 节点库副本启动。保留生产实例，独立端口 17988/19097，未复制网络接管设置，TUN/LAN/网关关闭。
- 新版自身的 SystemProxySession 接管当前用户 Windows 代理，原值为 Clash 7897。测试后正常释放、停止所有测试内核；ProxyEnable、ProxyServer、ProxyOverride、AutoConfigURL 的存在性和值均与原始快照匹配。未改动 Clash、Codex 配置或用户/机器代理环境变量。
- 同一个 Codex 可执行文件、同一个登录状态：仅系统代理时，独立临时 `codex exec --ephemeral` 在 55 秒受控截止前未成功，出现请求超时；给另一个新进程显式传入 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY=本次 Swirl 端口后，9 秒成功返回指定内容。环境只在新测试进程内存在，结束即消失。
- 真实 Codex 的 135 秒只读工具等待后继续流式输出并完成，总计约 189 秒。期间收到一次 HTTP 503，Codex 正常重试后完成；因此不能把这个样本写成“全程零重连”。工具等待期间对真实主内核切换全局/规则、单节点独立测速均完成，主内核 PID 保持一致。
- 当前桌面 app-server 观察到连向新版 17988 的连接，同时仍有旧 7897 连接及外部 443 直连尝试。远程控制 WebSocket 10060 仍存在。单次切换 Windows 代理不能保证已启动桌面的所有通道重新获得代理设置。
- 系统 `getaddrinfo(chatgpt.com)` 返回 157.240.1.9，`ws.chatgpt.com` 返回 157.240.3.8；经原代理访问 Cloudflare HTTPS DNS 分别得到 104.18.32.47/172.64.155.209 和 104.18.39.21/172.64.148.235。Codex 直连 SYN-SENT 地址与系统缓存吻合。结合进程代理 A/B，支持“部分后台请求未正确采用代理且遇到异常系统解析”的判断；不能据此把所有失败归因于 Swirl、Fake-IP 或单一 DNS 服务。

这解释了浏览器可用而 Codex 请求失败的差异：两者实际连接路径与解析路径并不一致。代理路径和完整响应已经实测，但完整桌面重新启动、全部远程控制通道、连续 20 分钟真实模型流及真实 TUN 仍需验收。没有修改系统 DNS、hosts 或清空缓存来隐藏问题，也没有改重试次数或延长网络超时。

参考案例是排查线索，不是通用配置处方：
- https://github.com/openai/codex/issues/18647
- https://github.com/openai/codex/issues/24045
- https://github.com/clash-verge-rev/clash-verge-rev/issues/7613
- https://github.com/yq6666-66/codex-reconnecting-troubleshooting

## 仅为新 Codex 桌面进程设置代理

仓库提供 [Start-CodexWithSystemProxy.ps1](../tools/Start-CodexWithSystemProxy.ps1)，用于在用户自行退出桌面应用后，以当前显式 Windows 回环代理启动新的 Codex 桌面进程。它不是 Codex 配置修补器，也不保证解决服务端 HTTP 503 或所有桌面通道问题。

使用 Windows x64 PowerShell 7，先在新版 Swirl 中连接节点并明确启用系统代理，再运行：

```powershell
pwsh -NoProfile -File ./tools/Start-CodexWithSystemProxy.ps1 -CheckOnly
```

核对输出的 `proxy` 是否是准备验收的 Swirl 端口。脚本读取当前设置，不把本次临时使用的 17988 写死；如果 Windows 已恢复到 Clash 7897，它会如实显示 7897。`launchAllowed: false` 表示仍发现桌面进程。`-CheckOnly` 只检查，不启动程序。

保存工作并自行完全退出 Codex 桌面后，从同一终端执行：

```powershell
pwsh -NoProfile -File ./tools/Start-CodexWithSystemProxy.ps1
```

默认从当前用户安装的 `OpenAI.Codex` 包发现桌面 EXE；需要时可通过 `-CodexPath` 指定本机桌面 `ChatGPT.exe` 或 `Codex.exe` 的绝对路径，不应指向后台 CLI 的 `bin/codex.exe`。脚本不会停止现有进程或中断正在进行的对话，也不会替用户关闭此应用。已有进程可能被 Electron 复用，无法通过再次打开窗口获得新环境，因此必须先完全退出。

脚本同时只读检查 WinINET 连接配置与当前用户注册表视图，要求显式代理已启用、端点一致、地址为回环 IP、端口为 1–65535。PAC、自动检测、协议映射、远程地址、代理凭据和两份配置不一致均拒绝启动。`localhost` 归一化为 127.0.0.1，避免对代理自身再做域名解析。

`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 仅写入新进程的 `ProcessStartInfo.Environment`，`NO_PROXY` 限为回环地址；后代进程是否采用这些值仍取决于其实现。脚本不写用户/机器环境变量、Codex 配置、注册表、DNS、hosts 或证书，不读取令牌，也不打印完整环境或请求内容。退出该进程后，本次注入不会保存在系统设置中。

当前已验证脚本的安全校验、子进程环境构造及本机 `-CheckOnly`：系统代理已恢复到 7897，已运行的桌面进程被识别为禁止新启动。**没有在本次对话中完全退出并重新启动 Codex GUI**，因此新启动桌面的全部模型、WebSocket 和远程控制通道仍待实测。已有真实成功样本是独立 CLI 子进程，不能把它写成整个桌面应用已经修复。135 秒工具等待样本出现的 HTTP 503 也保留为实际失败事件。

纯校验回归不启动应用、不访问网络、不修改系统设置：

```powershell
pwsh -NoProfile -File ./tools/tests/Test-CodexProxyLauncher.ps1
```
