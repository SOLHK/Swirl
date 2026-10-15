# PR #12 原生代理、订阅与界面升级验收

本轮基于 `2e270dec3ef3ef961871d76b7941fdc12dcc8f3b`，继续在 `feat/phase3-system-proxy-ui` 开发，PR 目标仍为 `test`。本报告取代上一轮报告中有关当前布局、透明度、文字渲染路径及订阅仅支持 Clash 的描述；历史测试保持原样，不作为新代码的替代证据。

## 已实现的运行路径

生产应用通过 `EngineController → SwirlEngineManager → ProxyEngine` 调度。`SwirlProxyEngine` 在应用进程内使用 Qt Network 监听、拨号、握手、转发与计数，没有启动别的核心冒充原生。节点和会话能力都满足时优先原生；复杂路由、DNS 配置、TUN/LAN、UDP Relay 及未完成的原生协议交给固定版本 Mihomo。

原生混合入站支持 HTTP 绝对 URI、HTTP CONNECT、SOCKS5 CONNECT、Basic/RFC1929 认证、IPv4/IPv6/域名地址、Qt 系统 DNS、严格验证的 TLS、有限队列、启动/握手/空闲超时与连接统计。TCP 读缓存为 64 KiB、写侧背压阈值 256 KiB、并发连接上限 256；HTTP 头上限 64 KiB，拒绝歧义 Content-Length、传输编码及升级请求。原生支持一次 HTTP 请求/连接，普通请求使用 Connection: close；完整持久连接、分块上传与 Upgrade 仍交给兼容实现。

原生出站有 DIRECT、HTTP CONNECT、SOCKS5 和 Trojan TLS。Trojan 使用协议定义的 SHA-224 认证及 Qt TLS，不发明密码算法。HTTP/SOCKS5 支持用户名/密码。高级传输及未验证选项不静默忽略，能力表给出兼容原因。设置显示实际引擎及回退原因，节点详情显示格式、能力与归一化说明。监听启动与远端请求成功分别显示。

原生网络失败只允许每次连接生命周期一次同节点 Mihomo 回退；切换等待旧引擎停止，取消/再次选择使旧异步任务失效。认证失败、证书错误、拒绝连接、DNS 与超时有明确诊断，绝不自动转为 DIRECT。客户端的原请求不能跨引擎无损续传，失败会返回客户端；后续请求及检测使用兼容引擎。

兼容路径保留显式入站认证，并拒绝与 LAN 认证相冲突的设置。专项测试实际证明无凭据请求不能到达源站，正确凭据的 HTTP/SOCKS 请求及引擎检测可完成；不能在回退中开启无认证监听。

`SwirlUdpExchange` 提供真实 IPv4/IPv6 UDP 请求/应答组件，检查应答来源、长度、超时和取消，每次使用独立 socket。它不等于完整 UDP Relay，也没有将其用于公开代理监听。原生 UDP Relay、复杂 DNS 和自研规则引擎仍研发中。

## 订阅格式兼容矩阵

统一流程是内容识别、归一化、安全验证、DPAPI 原子存储、真实选中节点及 HTTP/HTTPS 请求。以下 17 项均使用隔离 HTTPS 订阅源下载、重载、刷新及实际代理链验证，源服务器最终收到指定出口 `exit-A`。SS 用 aes-128-gcm，Trojan 用验证证书的 TLS，服务端为独立固定版本 Mihomo。测试不代表各生态的全部版本、规则或扩展已完全兼容。

| 请求格式 | 识别与表示 | 本轮实际链路 |
|---|---|---|
| Clash | YAML/JSON | SS，HTTP + HTTPS |
| Trojan Clash | YAML/JSON | Trojan，HTTP + HTTPS |
| Clash 兼容订阅 | 同一节点模型 | SS，HTTP + HTTPS |
| Trojan Clash 兼容订阅 | 同一节点模型 | Trojan，HTTP + HTTPS |
| Surge | INI/代理片段 | SS，HTTP + HTTPS |
| Trojan Surge | INI/代理片段 | Trojan，HTTP + HTTPS |
| Quantumult X | server_local/endpoint/tag | SS，HTTP + HTTPS |
| Trojan Quantumult X | server_local/over-tls | Trojan，HTTP + HTTPS |
| Shadowrocket | Base64/URI | SS，HTTP + HTTPS |
| Trojan Shadowrocket | Base64/URI | Trojan，HTTP + HTTPS |
| Shadowsocks SIP002 | URI/旧式 Base64 | SS，HTTP + HTTPS |
| Trojan 通用订阅 | URI | Trojan，HTTP + HTTPS |
| Surfboard | INI | SS，HTTP + HTTPS |
| Trojan Surfboard | INI | Trojan，HTTP + HTTPS |
| Loon | INI/无节头片段/位置字段 | SS，HTTP + HTTPS；另有真实 VLESS 订阅 |
| Trojan Loon | INI/位置字段 | Trojan，HTTP + HTTPS |
| sing-box | JSON outbounds | SS，HTTP + HTTPS；另测 VLESS 字段归一化 |

另支持 VMess JSON URI、VLESS URI、SSR URI、HTTP/HTTPS/SOCKS URI，以及 WS/gRPC/H2、Reality、SNI、ALPN、flow 等字段映射。此处只有明确列出的链路通过了本轮联网测试；URI 可导入不代表对应协议/传输组合已实测。

名称、协议、地址、凭据、TLS/SNI、传输、UDP、扩展及来源保留。源内容/未映射选项只保存在已有 DPAPI 私有库；QML 只接收固定的差异提示。存在影响行为的未映射选项时阻止执行，不能丢字段后宣称兼容。拒绝重复键、循环 dialer 引用、过深嵌套、脚本/本地文件/系统网络设置和关闭证书验证。各生态的全局规则、脚本及客户端 API 不作为节点导入执行。

服务端可按 User-Agent 返回不同内容。订阅界面增加自动/Clash、Loon、Shadowrocket/通用、Surge/Surfboard、Quantumult X、sing-box 偏好；仍以返回内容判断实际格式。修改自动更新开关保留格式偏好。Reality 来源缺省指纹时显式采用 chrome，并显示说明、保存原文，不将其误报为源文件提供的字段。

## 授权商业订阅

用户明确授权的地址仅在本机用作测试，报告不保存地址、节点名称、服务器、UUID、密钥或令牌。返回 59 个 VLESS 节点，分别验证 Loon 与通用内容。Loon 修复缺省 Reality 指纹后，9 个抽样中 1 个成功；该节点 HTTP 200、HTTPS 204，并通过真实订阅更新后自动重启、选择保留及再次 HTTP/HTTPS 请求。通用内容首次 6 个抽样中 2 个成功，两节点各自 HTTP/HTTPS 请求成功。其他节点逐项记录失败或超时，不能把 59 个导入节点全部称为可用。

真实结果只代表当时网络、授权账号及有限抽样，两个客户端输出的节点顺序与字段可能不同。原始响应和调试缓存均 DPAPI 加密；没有公共转换服务，也没有修改已有 Windows 系统代理。

另做原生公网链路：HTTP、SOCKS5、Trojan 每种均访问真实 HTTP 站点（200）及 HTTPS 站点（204）。HTTP/SOCKS 的上游为明确指定的既有本机代理；Trojan 对端为独立本机 TLS 服务端，再经同一既有出口访问公网。此测试验证原生转发实际联网，不等于商业远端 Trojan 服务器覆盖。通用订阅的最终复测仍是 6 个抽样中 2 个成功，更新重连后 HTTP/HTTPS 再次通过。

## 原生与兼容协议边界

| 协议/能力 | Swirl 原生 | Mihomo 与本轮证据 |
|---|---|---|
| DIRECT、HTTP CONNECT、SOCKS5 | TCP 已实现，认证/失败/恢复已测 | 既有链路回归通过 |
| Trojan | 基础 TLS/TCP 已实现，独立服务端互操作通过 | TLS 兼容及格式链路通过 |
| Shadowsocks | 研发中 | aes-128-gcm 实际转发通过 |
| VLESS/Reality | 研发中 | 授权商业订阅实际 HTTP/HTTPS、更新重连通过 |
| VMess、SSR | 研发中 | 解析/配置已测；本轮未验证远端握手 |
| WS、gRPC、H2、QUIC、多路复用 | 原生研发中 | 保留参数，依具体节点交 Mihomo；不是全组合联网覆盖 |
| UDP 基础 | IPv4/IPv6 socket 组件已测 | 完整代理 UDP Relay 继续由兼容核心执行 |
| DNS/规则/TUN/LAN/进程策略 | 系统 DNS 拨号已实现，其余原生研发中 | 保留既有 Mihomo 及 Swirl DHCP/系统代理服务 |
| 其他固定核心协议 | 原生研发中 | 现有协议注册不变；仅配置接受的明确标注未测握手 |

高级断点/重放、完整 DNS 查询历史、部分 API/自动化/同步/私有组网等保持入口和“研发中”。真实草稿、配置保存、模块、脚本、捕获及规则操作仍可使用，不以占位数据冒充结果。

## 四角、字体、主题与交互

具体实现见 [PR12_NATIVE_UI_FIXES.md](PR12_NATIVE_UI_FIXES.md)。文字和控件取消整个窗口内容的离屏 MultiEffect 遮罩，直接使用原生场景图文本；缓存壁纸模糊与材质轮廓单独处理。四阶连续轮廓统一半径，并保护零导数计算；设置 DNS 底栏取消穿过底角的矩形背景。没有采用硬切 Win32 区域损害抗锯齿。

材质 alpha 0.975/0.98、壁纸染色权重 0.86，减轻背后文字透出；生产仍读取真实壁纸，不动态捕获后方应用。默认 HarmonyOS 字体与 Qt DPI 保持。100/125/150/200% 进程 DPR 的 D3D11 四角/合成/窗口操作各 62 项通过，这不等于更改系统 DPI 或全部 GPU/HDR 验收。

主题通过实际鼠标、键盘与独立进程重启验证，Light/Dark/System 与透明/减少动画设置持久化。活动页重排但数据来源保留；面板六标签、过滤/搜索和真实服务保留，清空仅作用于请求或日志，DNS Hosts 与研发中的查询历史分开。节点身份及请求卡片共享可逆动画进度，时长统一增加 20%。

## 构建与验收证据

独立 Windows 11 / Qt 6.10.3 / MinGW 13.1 / C++23 Release 构建；生产关闭 SWIRL_BUILD_UI_TESTS。完整集成 CTest 19/19 通过，432.38 秒。参数类型、HTTP 歧义头、VMess 重复键及面板相关复测 8/8（248.09 秒），认证保持修复后的引擎/节点回归 3/3（131.23 秒）。最终原生专项为 13 成功、0 失败，公网 opt-in 另跑 3 成功、0 失败；常规集成中的这一 opt-in 跳过不冒充覆盖。结果与性能原始数据一同交付，不覆盖首次失败记录。

原生专项验证包括 HTTP 与 SOCKS 入站、认证 HTTP/SOCKS 出站、Trojan TLS 独立服务端、错误 SNI、分段握手、拒绝 UDP ASSOCIATE、超时、取消、端口复用、同节点回退、IPv4/IPv6 UDP、1 MiB 上传、2 MiB 下载及最终字节统计。公网测试与本地受控测试分开记录。性能报告不以显示器 Hz 或 Qt 回调频率代替真实呈现 FPS；不可用刷新率明确缺测。截图/GIF 为真实 Qt 渲染采样，GIF 不作为 FPS 计时证据。

生产部署后在 PATH 无 Qt SDK 的环境跑完 61 页并退出 0。首次原生冒烟遍历完成但测试退出路径被阻止，原始失败保留；完成信号改为 C++ 的隔离测试 exit 路径后，输入/页面 2/2、最终页面 1/1 及生产独立部署复测通过，不修改普通关闭/未保存确认流程。

本次 Windows 与 Qt 均实际切换并报告 60/120/144/165/240Hz，每档 180 次、共 900 次交互通过。基于自身 D3D11 swapchain 有效呈现跨度，FPS 为 59.97/120.00/143.84/162.15/236.03；显示间隔 P95 为 16.667/8.333/6.944/6.061/4.167ms，P99 为 16.667/8.333/6.944/12.121/8.333ms。165/240Hz 仍有漏刷；一个不可用统计及 148 个模糊/不一致跨度记录保留，不补造。此实测替代旧报告中 144/165Hz 缺测的结论，未做光学面板或点击到光子延迟测量。

WDDM 进程 GPU 内存 63 次有效采样，专用分配峰值约 222.31 MiB，最后 212.86 MiB；后半段稳定。GDI 在各档结束保持 41，转场引用全部归零。私有提交随 57,582 条观测和 JSON 构造增长，最后两档增量收敛；此运行不能证明不存在长期内存泄漏。最小化 60 秒进程 CPU 718.75ms，约一个核心的 1.20%，不是整机占用百分比。详细原始数据见本地 PERFORMANCE.json / GPU-MEMORY.json。

## 许可证与后续

源码研究、固定版本、实测范围和许可见 [SWIRL_NATIVE_RESEARCH.md](SWIRL_NATIVE_RESEARCH.md)。没有复制五个研究项目的协议实现到产品，也未引入新密码学库；继续分发既有 Qt、MinGW、Mihomo、HarmonyOS 字体及完整第三方许可。subconverter 完整构建受缺少 PkgConfig 阻塞，仅其原样 codec 研究测试通过，不能称其完整转换器通过验收。

下一批是原生 Shadowsocks AEAD、随后 VLESS/Reality、VMess/SSR 及 UDP Relay/高级传输，每项先做独立互操作和实际出口验证再接管；在此之前保留 Mihomo。实体 4K/HDR、多屏、其他 GPU 以及专用 LAN 网关端到端需要对应环境，不虚报本轮覆盖。
