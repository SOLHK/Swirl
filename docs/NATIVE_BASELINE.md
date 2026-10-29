# Swirl 原生迁移：首轮源码审计与采集准备

审计基线：`e6a8ddf6f8e73097bc168456bece17ca9142f1be`。
本轮开发分支：`codex/native-subscription-window`。实际构建使用本分支独立 worktree；原检出与 main 未修改。
本文件记录首轮成果，不是全部自研内核已完成的声明。

## 实际调用边界

| 模块 | 当前源码事实 | 验收边界 |
|---|---|---|
| SwirlEngineManager | start 按 nativeSessionReason 选原生/Mihomo；部分原生失败可回退 | 产品仍依赖完整外部内核；禁止宣称已全部自研 |
| SwirlProxyEngine | Mixed HTTP/CONNECT/SOCKS5 入站；HTTP CONNECT/SOCKS5/Trojan 出站 | TCP 基础实现；仅受支持的 TLS 参数；不支持 UDP Relay |
| SwirlProtocolRegistry | 原生协议白名单 http/socks5/trojan；UDP、未知扩展拒绝原生 | 确实有限制，但会指向兼容引擎，不等于原生实现 |
| NativeDuplexRelay | 有界队列、背压、半关闭；现有连接保留旧出口 | 本轮回环 WS/WSS/SSE、切换、失败隔离、流量计数通过；不替代真实公网长期验收 |
| NodeTestService | 基线始终实例化 MihomoAdapter；本轮改为支持的节点使用 SwirlProxyEngine | 原生测速失败不重试兼容；明确兼容偏好仍使用历史实现；结果带 engineKind |
| SwirlUdpExchange | 单次直连 UDP 交换、来源匹配、超时、取消 | 不是 SOCKS UDP、Trojan UDP、TUN 或完整 UDP 会话管理 |
| DNS/规则/策略组/TUN | nativeSessionReason 将这些会话交给 Mihomo | 原生化尚未完成；不能删功能或隐藏回退冒充完成 |
| NodeImportService | 串行下载、30 秒总计时、即时解析、自动更新间隔 | 无网站授权窗口模型；本轮采集 CLI 独立运行，未替换现有后台更新器 |
| NodeStore | Windows DPAPI、QSaveFile、保存失败保留旧库 | 1 MiB 存储上限；不能与 8 MiB 采集缓存上限混淆 |
| SystemProxySession | 已有代理所有权、快照及恢复逻辑 | 本轮不改系统代理；恢复实机验收未重做 |
| CodexLauncher | 既有新子进程代理环境启动器 | 不等于 respect_system_proxy 检测/授权修复/条件回退已集成 |
| 新 SubscriptionCapture.py | 批量根订阅/已知依赖、精确 URL 授权、DPAPI 原文、限额/截止、离线重放 | Python 准备工具；未接入安装包/产品 C++ 更新器；未知格式保留但不宣布导入成功 |

核心证据文件位于 `src/Swirl.Quick/engine/`：上述同名类、`ProxyNode.*`、
`NodeImporter.*`、`SubscriptionNormalizer.*`。不以 README 支持列表替代握手实现。

## 格式层矩阵

| 客户端/生态 | 本仓库识别路径 | 参数与完整配置语义 | 本轮证据 |
|---|---|---|---|
| Clash/Mihomo、Verge Rev、FlClash、Clash Meta | Clash YAML/JSON | 节点扩展部分保留；DNS/规则/组完整语义需另行审计 | 选定合成导入用例通过；无本轮私有样本 |
| sing-box | outbounds JSON 转换 | 部分 TLS/传输映射；未知出站字段报 conversionIssues；全配置语义未完成 | 源码检查 |
| Hiddify | 可能复用 URI/sing-box；需按实际导出识别 | 不因软件名推断格式和版本 | 待样本/官方版本研究 |
| v2rayN / v2rayNG | URI/Base64 公共路径 | Xray/V2Ray 完整 JSON 不应视为 sing-box JSON | 公共路径源码存在；完整配置未验证 |
| V2Ray/Xray | URI 部分；无完整专用配置适配证据 | REALITY/flow/XHTTP 等字段解析不等于握手可用 | 待规范研究与实现 |
| NekoBox/NekoRay | 需区分 sing-box/URI/客户端数据库 | 版本差异未确认 | 待样本 |
| Surge / Surfboard / Loon | INI [Proxy] | 节点行映射；其他 section 多数跳过；原始完整配置不能靠节点库保全 | 源码检查；缓存保留完整输入 |
| Quantumult X | [server_local] | 节点映射；策略、重写等完整语义未完成 | 源码检查 |
| Shadowrocket | 多行 URI/Base64 路径 | 特有扩展及配置版本仍需调查 | 源码检查 |
| Stash | 可能复用 Clash，特有扩展未知 | 未验证完整配置 | 待样本 |
| Egern | 无独立已验证适配路径 | 未完成 | 待样本/规范 |
| Karing / Streisand / V2Box | 不按软件名假定输入格式 | 共享格式和私有扩展待验证 | 待样本/规范 |
| 其他格式/未来版本 | 采集器格式无关保存 | Unknown 保留；不自动执行脚本或删除字段后联网 | 未识别合成格式缓存测试通过 |

INI 适配器当前会跳过非节点 section；sing-box 适配器以 outbounds 为中心。
这不满足最终“完整配置未知字段和资源语义保留”的全部目标。新原始缓存先保住完整输入，
下一阶段应建立文档级模型，不能只依赖 `ProxyNode.originalConfiguration`。

## 协议、传输和测试分层

| 协议/版本组合 | 识别/参数 | Swirl 原生 TCP | 原生 UDP | 本轮互操作/真实公网 |
|---|---|---|---|---|
| HTTP CONNECT / SOCKS5，基础 TCP、认证 | 已有 | 已有 | 无 Relay | 原生+合成回环对端通过；无真实节点 |
| HTTPS 代理/SOCKS5+TLS | 部分字段 | TLS 路径存在，组合覆盖不完整 | 无 | 不能由 HTTPS 目标测试推导 HTTPS 上游全部通过 |
| Trojan 基础 TLS | 已有 | 已有 | 无 | 历史参考服务端用例存在，本轮未运行；无真实节点 |
| Shadowsocks AEAD / 2022 | 节点字段可识别，cipher 版本语义需审计 | 未实现 | 未实现 | 现有部分格式用例由 Mihomo 转发，不能算原生 |
| ShadowsocksR 协议/obfs 组合 | URI/字段部分 | 未实现 | 未实现 | 未验证 |
| VMess | URI/字段部分 | 未实现 | 未实现 | 未验证 |
| VLESS TLS / REALITY / flow | 参数部分映射 | 未实现 | 未实现 | 未验证 |
| Hysteria / Hysteria2 | Clash 字段/部分 sing-box | 未实现 | 未实现 | 未验证 |
| TUIC / AnyTLS | 注册表可识别部分 | 未实现 | 未实现 | 未验证 |
| NaiveProxy | 无完整适配证据 | 未实现 | 未实现 | 未验证 |
| Snell / Mieru | 节点字段部分 | 未实现 | 未实现 | 版本/组合待研究 |
| WireGuard / SSH 隧道 | 节点字段部分 | 未实现 | 未实现 | 未验证 |
| 其他 VPN/私有扩展 | 以样本和官方规范确定 | 未完成 | 未完成 | 不虚构协议 |

TCP/TLS 有实际基础路径。代理协议封装层的 WebSocket、HTTP/2、gRPC、HTTPUpgrade、
XHTTP、QUIC、ShadowTLS、obfs、多路复用及各自 UDP 扩展均不可由普通 CONNECT 的
WS/WSS 应用透传测试推导支持。项目存在 nghttp2，但位于其他网络功能，不等于原生出站
已经实现 HTTP/2/gRPC。协议实现必须逐组合补矩阵，不能任意组合排列出虚假的支持范围。

## 本轮修复与执行证据

1. 新采集器 20 项 Windows DPAPI/回环/离线导入测试通过，涵盖真实 HTTP 服务、gzip、
   非法响应、大小限制、重试、实际开启时间、截止中断、不同窗口、认证头隔离、重复源、
   引用循环/深度、原子写失败、旧缓存保留、C++ 导入及禁止覆盖已有节点库。
2. 公开 `https://sing-box.sagernet.org/schema.json` HTTPS 下载成功，原始响应 27972 字节。
   通过现有 loopback HTTP 代理采集；不是 Swirl 原生出口验收。
3. C++23 / Qt 6.10.3 / MinGW 13.1：独立目录编译真实 SwirlEngine 和测试工具。
   NativeEngineTests 选定 10 个测试函数，Qt 报 12 passed（包括 init/cleanup）。
   NetworkRegressionTests 选定 5 个用例，Qt 报 7 passed（包括 init/cleanup）。
   ImportTests 选定 7 个函数，Qt 报 9 passed（包括 init/cleanup）。
4. 原始失败证据保留：原生长连接测试的附带测速找不到 Mihomo；已改原生测速路径。
   大流量测试统计最初为 122 对 2097337：最后一个连接的统计尚未发布，
   现在等待两个连接完成及相同的严格总量断言，不删除断言、不伪造计数。
5. 本轮没有改变 QML/字体/图标/布局资源；这是源码差异结论，未宣称实机视觉验收完成。
6. 完整 Swirl Windows 桌面程序构建通过；这是开发测试构建，尚未制作全原生正式安装包。

## Codex 只读核对

本轮本机发现桌面包 `26.1013.3656.0`、PATH 上 CLI `0.163.0-alpha.10.2`。
该 CLI 的 `features list` 返回 `respect_system_proxy under development true`。
这比用户提供的旧版本现场证据更新，但只证明此 CLI 的有效开关状态，不证明所有桌面进程、
手机操作或重连路径已验收。未改配置、未读账户令牌、未重启 Codex。
官方配置参考：[Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)。
版本特定支持以实际 CLI 输出为准；不能把旧版本结论推广到所有版本。
授权修改/备份/按字段条件回退的产品管理命令仍需实现。

## 下一阶段不可省略的完成条件

- 统一配置文档模型、版本/未知字段/资源/转换诊断，与现有入口集成。
- 逐协议、逐传输实现并用固定参考服务端互操作；外部内核仅作隔离参考。
- 原生专用构建必须在所有入口（主连接、测速、诊断、TUN）禁止完整外部内核；
  本轮只修复了可原生测速的路径，还没有完成这一构建模式。
- Windows 产品安装包、实际私有节点、真实 Codex 新连接/远控/手机操作/重连、
  休眠唤醒、性能及 UI 实机验收尚未完成。
- Gemini 尚未回复；首份审查包只表示已准备交接，不能记作共同审查通过。
