# Swirl 自研内核架构与开源研究报告

研究日期：2026-10-15。源码下载在本轮工作目录 `work/research`，未复制入产品或添加新的上游运行依赖。

## 研究对象与执行证据

| 项目 | 固定源码 | 阅读的实现 | 实际执行与边界 |
|---|---|---|---|
| [Mihomo](https://github.com/MetaCubeX/mihomo/tree/v1.19.32) | `88dcbf7f1614a67c3b36b848ee3592dfa92ada36` / v1.19.32 | adapter/parser.go，adapter/outbound/http.go、socks5.go，transport/socks5，DNS/tunnel/config | 固定产品二进制 SHA256 校验一致；Swirl 真实代理链回归；Go common/structure 单测通过，socks5 包可构建但上游无测试 |
| [sing-box](https://github.com/SagerNet/sing-box/tree/dfb80349bf5779ec0a3f834c9ec2794345bff8f0) | `dfb80349bf5779ec0a3f834c9ec2794345bff8f0` | adapter/outbound.go、lifecycle.go，protocol/socks/outbound.go，common/dialer、route | Go common/geosite 测试通过；common/interrupt 可构建但无测试。不是整个 sing-box 协议矩阵验收 |
| [Xray-core](https://github.com/XTLS/Xray-core/tree/0888beb38a9ba45440557175e71ce21cf8ba3b13) | `0888beb38a9ba45440557175e71ce21cf8ba3b13` | proxy/proxy.go，proxy/trojan、vless，transport/internet/tls，app/dispatcher | Go common/protocol 与 common/net 测试通过；尚未声称 VMess/VLESS/Reality 全部互操作通过 |
| [subconverter](https://github.com/tindy2013/subconverter/tree/a0d4eab28cb8b6c782d4ce5c3a918de4829b4a72) | `a0d4eab28cb8b6c782d4ce5c3a918de4829b4a72` | src/parser/subparser.cpp，generator/config/subexport.cpp，utils/base64 | 完整 CMake 配置实试受本机缺少 PkgConfig 阻塞；原样 Base64/string 源码编译成隔离研究程序，14 项往返/已知值检查通过。未将其描述成全转换器测试 |
| [v2rayN](https://github.com/2dust/v2rayN/tree/95f438abc93714150adf55acac7ceb03b3713032) | `95f438abc93714150adf55acac7ceb03b3713032` | ServiceLib/Manager/CoreManager.cs，Handler/SubscriptionHandler.cs、Fmt，Services/CoreConfig | .NET 10 ServiceLib.Tests Release 实际执行：133 成功，0 失败，0 跳过 |

Go 研究工具使用校验过 SHA256 的官方 go1.27.2 Windows amd64 包。Mihomo 初次依赖下载 EOF，经备用 Go 模块镜像重试成功。下载工具与研究构建产物仅在工作目录。

## 架构结论

Mihomo 的 ParseProxy 按协议解码结构化参数，再建立独立 outbound；HTTP 与 SOCKS 的拨号、TLS 握手、协议握手分层。DNS、规则、TUN 与生命周期并非节点导入器职责。Swirl 继续保留已校验的 MihomoAdapter 处理目前成熟功能。

sing-box Outbound 明确区分类型、tag、网络能力和依赖，并将 DialContext 与 ListenPacket 分开；生命周期分为 initialize/start/post-start/started，取消上下文和清理作用域可传递。Swirl 原生 TCP 会话采用异步状态机、超时、容量上限、背压和可取消销毁；TCP 成功不能证明 UDP Relay 支持。

Xray Inbound/Outbound 通过 dispatcher/dialer 与传输 Link 解耦；TLS/Reality、VMess/VLESS 认证和数据封装属于不同层。原生实现先采用现有 Qt 的证书验证和密码学设施，不复制上游密码学代码，不自创算法。尚未验证的传输选项不能被原生引擎静默忽略。

subconverter 将生态格式解析映射到统一节点，再独立导出目标格式；Quantumult X 的 endpoint 与 tag、over-tls、tls-host 等字段与 Surge/Loon 的位置字段不同。格式不能等同协议。Swirl 应先归一化成现有 ProxyNode，保留来源与原始差异，再复用现有安全验证和 DPAPI 原子写入。未知影响行为的选项需保留且明确拒绝/兼容调度，不能丢弃后宣称完全支持。

v2rayN 在生成配置后才停止旧核心并启动新核心，订阅与配置生成与 UI 分开，实际运行核心有独立状态。Swirl 采用统一 ProxyEngine 下的引擎管理器：能力满足时使用 Swirl 原生；TUN、复杂路由、未验证协议/传输继续使用 Mihomo。运行失败可回退兼容实现，但绝不绕过指定节点回退直连，不能无限重启，也不能把“监听已启动”描述成“远端联网成功”。

## 职责映射与推进

| 职责 | 实现方向 |
|---|---|
| SubscriptionParser / NodeNormalizer | 多格式识别与规范化适配，现有 NodeImporter 统一安全验证 |
| CapabilityRegistry / ProtocolRegistry | 协议 + 传输 + 选项 + 会话功能的能力判定；区分原生、兼容、未知 |
| SwirlProxyEngine / Inbound / Transport / Outbound | 独立 C++ 监听、分段握手、真实 TCP 转发；不启动现成程序冒充原生 |
| EngineManager | 保留 ProxyEngine 接口；引擎选择、停止/重启、有限回退、实际运行引擎显示 |
| ConnectionManager | 连接 ID、真实字节计数、活动快照、错误和超时、有限队列 |
| DNS / TLS | 基础解析与 Qt 验证 TLS；高级 DNS 与传输兼容暂交 Mihomo |
| Routing / RuleEngine | 阶段性支持边界明确；未原生实现的进程/地理/MRS/TUN 路由交兼容引擎 |

基础联网通过后再推进加密协议；Shadowsocks、Trojan、VMess、VLESS、SSR 的原生状态分别记录，不以 URI 解析或配置校验替代协议互操作。公开网络请求与本地隔离请求分开，商业订阅尚无本轮授权测试材料。

## 许可证与复用决定

固定 Mihomo、sing-box、subconverter、v2rayN 的源码许可证为 GPL-3.0（具体 only/or-later 以各自 LICENSE/文件头为准）；Xray-core 为 MPL-2.0。直接链接/复制 GPL 代码及修改 MPL 文件都需履行相应许可义务。本轮只研究架构，不复制这些项目实现进 Swirl；subconverter 研究程序不分发。保留既有 Mihomo 分发许可、对应源码链接和 Qt/字体等第三方声明。

新增原生协议实现依据公开协议定义独立编写，继续用已存在的 Qt Network/TLS 依赖。任何引入额外密码学库或直接代码复用导致的重大许可证选择，按用户任务书先提交具体方案供用户决定。
