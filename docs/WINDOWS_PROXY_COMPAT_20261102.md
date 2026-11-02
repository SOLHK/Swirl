# Windows 系统代理兼容性修复与验收记录 — 2026-11-02

## 当前结论与范围

本文保存提交前的研发证据。最终 Commit、PR、Actions 结果与实机门禁按关联 PR 的最终验收记录核对，不能把本地结果当作后续 CI 结果。

本轮在现有 Rust Core 中复现并修复了三个协议/路由缺陷，并修复了取证工具直接导出敏感代理字符串的问题。**这些证据尚不能证明用户当前 Codex「Couldn't load workspace settings」的唯一根因，也不能证明该桌面故障已经消失。**

| 项目 | 状态 |
| --- | --- |
| 起始远端 `test` | `63dde8812f85839aa6024cbba6c498c96cae022d`，开始时重新读取 |
| 独立开发分支 | `work/windows-proxy-compat-20261102` |
| 本文对应的本地证据 | 本轮候选工作树；最终提交身份须与提交后的 CI 重新绑定 |
| 最终 Commit / PR / Actions | **PENDING**：由提交后的实际记录填写，不能沿用基线或其他分支的结果 |
| 用户当前安装的 Swirl EXE/DLL 版本及 source SHA | **UNKNOWN**，没有取得当前 Windows 设备上的读数 |
| 相同 Windows 11 设备、订阅、节点的 Clash/Swirl A/B | **NOT_RUN**，当前执行环境没有该设备、节点和已登录桌面会话 |
| Codex Desktop 工作空间、认证多轮回复、已有项目、真实持续流 | **NOT_RUN** |
| 合并 `test` | **未合并；真实验收及适用 CI 门禁尚未完成** |

产品继续使用自研 Rust Core。没有引入 Mihomo、sing-box、Xray 等外部内核作为产品运行时，也没有修改独立开发中的 Native TUN、LAN Proxy、Gateway。没有更改 Codex 配置、账号资料、证书验证、系统环境变量，或为特定服务新增强制直连规则。

## 一、已证实的实现缺陷

### 1. V2 路由提前丢弃 DNS 候选地址

`core/crates/swirl-core/src/v2.rs` 的原路径在解析域名后只保留第一个 IP。后续连接器收到的已经是 IP 字面量，因此无法再利用其现有多地址连接调度：首个 A/AAAA 地址连接失败时，后续可用地址没有机会参与。两个真实 loopback/DNS fixture 在旧基线上失败，分别覆盖第二个 IPv4 地址及跨 IPv4/IPv6 地址族的可用候选。

修复保留 DNS 候选，交给现有 `connect_direct_resolved`。其适用范围严格限定为**路由已经选择 DIRECT 的 TCP 连接**：后续地址须保留同一规则身份、策略目标和分类语义，不重新选择策略组，不允许从代理节点回退到 DIRECT。多候选场景不再把首个 DNS 答案伪记为实际连接成功的 IP，并记录 `direct_candidate_count`。

新增规则边界与回环测试检查：即使两个地址都可能走 DIRECT，也不能跨越不同规则；不能跨中国/非中国分类、使用禁止目标或不同端口；回环检查覆盖全部候选及 IPv4-mapped IPv6。没有通过全局关闭 IPv6 修复问题。多地址连接的依据见 [RFC 8305](https://www.rfc-editor.org/rfc/rfc8305.html)，本轮不据此宣称完整实现了该 RFC 的全部 DNS 调度要求。

### 2. 建立隧道前失败，只关闭连接而没有协议失败响应

原 V2 session 在请求解析成功后，若路由拒绝、目标无效或上游连接失败，会直接返回错误。客户端可能只观察到 EOF，无法从 HTTP/SOCKS 握手判断失败边界。新增回归在旧实现上失败。

修复在成功响应尚未开始时调用现有协议回复器，HTTP 返回 `502`，SOCKS5 返回失败回复，同时保留内核实际错误分类。错误回复受既有超时和取消机制约束。`reply_started` 在发送成功回复前置位，确保成功回复已经部分写出或 TLS 隧道已建立后，绝不追加 HTTP 错误文字污染字节流。

专门的负对照用截断和非法 VLESS 前缀触发 `StreamUnexpectedEof` / `StreamInvalidData`，要求 CONNECT 成功后仅结束原隧道，不能插入第二个 HTTP 响应。**这证明错误边界处理正确，不证明历史六个 Codex background stream 的 EOF 原因相同。**

### 3. 上游 HTTP CONNECT 只接受 `200`，拒绝其他合法 `2xx` 和中间响应

`core/crates/swirl-protocol/src/lib.rs` 原来只接受上游 `200`，没有继续读取 `100` / `103` 等中间响应。独立上游 fixture 在旧基线上复现两项失败；拒绝非成功状态的负对照原本通过并继续保留。

修复按 [RFC 9110 §9.3.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.6) 接受 CONNECT 的 `2xx` 成功响应，并按 [§15.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.2) 处理有界中间响应：最多八个，在原有整体握手截止时间内完成。`101`、重定向、`403`、`407`、`429` 和服务器错误仍不能变成成功隧道。

读取精确停在最终响应头结尾，不吞掉同包到达的 TLS/隧道数据；成功 CONNECT 的 `Content-Length` / `Transfer-Encoding` 不用于解析隧道内容。测试覆盖 HTTP/1.0、HTTP/1.1、200/201/204/299、连续 1xx 上限、合并到达的数据及半关闭后的尾部数据。

## 二、已存在的修复与 Windows 集成审查

[V3_NETWORK_STAGE_A.md](V3_NETWORK_STAGE_A.md) 已记录 HTTP/1.0 CONNECT 入站修复，当前 `test` 包含该能力。本轮保留并测试它，没有重复实现。该文档记录的 0.2.12 安装版本是历史快照，不能拿来认定用户今天仍在运行旧版。

`SystemProxySession` 已有 WinINet 与 HKCU registry 双表示读回、DPAPI 恢复记录、独立 guard、session 身份校验、异步等待及外部修改后放弃所有权的机制，本轮不改写这些正确路径。代理通知已有 `INTERNET_OPTION_SETTINGS_CHANGED` 与 `INTERNET_OPTION_REFRESH`，对应 [Microsoft WinINet option flags](https://learn.microsoft.com/en-us/windows/win32/wininet/option-flags)。

Clash 与 Swirl 当前实机行为差异还没有实测。可以确认的边界是：

- 历史 Clash 正常快照中 WinHTTP 也是 Direct，因而不能把 `netsh winhttp show proxy` 显示 Direct 单独当成故障原因，也没有据此覆盖机器级 WinHTTP 设置。
- Swirl 写入单一 `127.0.0.1:port`，没有 `socks=` 映射。[Chromium 官方代理说明](https://chromium.googlesource.com/chromium/src/+/main/net/docs/proxy.md) 中该单一无 scheme 配置默认 HTTP；WebSocket 使用其 other-proxy 路径。`socks=host:port` 默认 SOCKSv4 的规则不能套到 Swirl 当前写入值上。
- [OpenAI 官方系统代理说明](https://learn.chatgpt.com/docs/enterprise/managed-configuration#use-the-system-proxy-for-native-client-requests) 解释 `respect_system_proxy` 的作用范围和版本限制；它不证明已运行桌面的所有网络栈、插件、子进程均使用同一路径。本轮仅核对已有管理工具，没有执行配置修改。

## 三、schema 2 取证与隐私修复

原 `Collect-CodexNetworkEvidence.ps1` 直接序列化 registry `ProxyServer` 和 `netsh` 原文，可能带出代理凭据。相同 fixture 重放原 collector 时，敏感 marker 确实进入 JSON，回归失败；修复后该断言通过。

新增 `CodexNetworkEvidence.psm1`，报告字段采用白名单：代理 scheme/host/port、凭据是否存在、PAC 是否配置、bypass 数量与摘要。userinfo、query、fragment、URI path、PAC 地址、bypass 原文及任意异常文本不输出；含歧义分隔符的敏感协议映射整组省略。

原生只读 API 分别记录 WinINet、WinHTTP 默认配置与 current-user 配置；最后一项的语义见 [WinHttpGetIEProxyConfigForCurrentUser](https://learn.microsoft.com/en-us/windows/win32/api/winhttp/nf-winhttp-winhttpgetieproxyconfigforcurrentuser)。这些是静态快照，不执行 PAC，也不能单独证明某个既有进程的有效路由。

报告增加 comparison label、OS version、进程创建时间、受限版本字符串、Codex AppX 版本及 Swirl 磁盘包证据。Swirl identity 固定读取真实生产布局的 `Swirl.exe`、`swirl_api.dll`、`swirl-rust-build.json`，核对 `package-manifest.json` 中的 SHA-256 和 source SHA。`sourceIdentityVerified` 始终为 false：磁盘文件与 manifest 一致，不等于已加载 DLL 一致、可信构建来源或完整安装验收。进程环境字段也明确仅代表 collector 进程，不能冒充对既有 Codex 环境块的检查。

## 四、实际测试记录

以下数值从本轮本地日志的 `test result` 行汇总，包含 workspace unit/integration/doc-test 结果，不是 UI/实机验收百分比。

| 检查 | 实际结果 | 证据/边界 |
| --- | --- | --- |
| 未修改基线 Rust workspace | 804 passed，0 failed，0 ignored | `baseline-rust.log`；原有测试未发现新增回归所针对的缺陷 |
| 新 DNS 回归运行于旧实现 | 2 failed | `baseline-direct_dns_.log` |
| 新 pre-tunnel 回归运行于旧实现 | 1 failed | `baseline-pre-tunnel-confirmed.log` |
| 新 upstream CONNECT 回归运行于旧实现 | 1 passed、2 failed | `baseline-outbound-confirmed.log`；负对照保留 |
| 候选 fresh Rust workspace | **816 passed，0 failed，0 ignored**，退出 0 | `candidate-fresh-rust.log`，40 个结果段，使用新的构建目录 |
| 候选 Clippy，warnings 为错误 | 退出 0 | `candidate-fresh-clippy.log` |
| 候选 Rust dev 构建 | 退出 0 | `candidate-fresh-build.log`；不等于 Windows 安装包验证 |
| 原 collector + 新隐私 fixture | 退出 1，预期失败 | `codex-network-evidence-baseline.log` |
| 修复后 PowerShell collector suite | **24 assertions passed**，退出 0 | 实读 PowerShell **7.6.9**，Ubuntu；`codex-network-evidence-fixed.log` |
| Windows PowerShell 5.1 / 7 原生 API、包 identity 测试 | **PENDING CI** | Linux 明确输出 Windows native/package `NOT_RUN` |
| Python 独立 V2 HTTP/TLS/H2/WS/SSE fixture | **6 tests passed**，退出 0；14 个子场景、16 条 V2 session | `candidate-v2-compat-final.log`，6.035 秒；本地受控网络，不计入上述 816 |
| 持续连接 soak | **8 连接连续 60.003701 秒通过** | 同一 core、无重连、每连接 61 事件；[逐秒证据](evidence/windows-proxy-compat-20261102/soak-60s.json)。300 秒本地扩展及 CI 120 秒另记 |
| Windows Qt 集成、完整 Actions | **PENDING CI** | 本文编写时尚无对应最终提交的完整通过记录 |
| Windows 11 + 实际订阅 + Codex Desktop | **NOT_RUN** | 没有用 loopback 或 Windows Server runner 替代 |

新增 `test_windows_proxy_compat.py` 使用实际 `swirl-api/start_v2`、独立认证 HTTP/SOCKS5 节点和独立 TLS origin。其验收断言包括严格证书验证、同包 ClientHello、真实 HTTP/2 三路复用、WSS 首帧/分片/ping/close、分块 SSE 跨握手时间窗、半关闭延迟大尾部、取消和 stop 后资源释放。所有正向代理请求使用保留的 synthetic 域名并核对节点记录，不利用 loopback 自动 DIRECT 规则冒充代理成功。`h2` 等 Python 依赖仅属于测试。

可复现的旧基线失败日志与本地结果清单保存在 [evidence/windows-proxy-compat-20261102](evidence/windows-proxy-compat-20261102)。清单逐项区分执行、失败与跳过；例如 Linux 上全部跳过的 Codex DPAPI 管理测试不算通过。其余原始日志保留在本轮本地审计目录，完整跨平台日志由对应 GitHub Actions 保存。PR 最终验收记录须列明 Commit、Actions 和失败/跳过，不能把本地成功登记为跨平台成功。所有网络 fixture 仅使用合成目标及测试凭据。

## 五、Windows 11 同节点 A/B 实机步骤

### 1. 固定条件和记录原状态

使用同一 Windows 11 设备、网络、Codex 桌面版本及正常用户登录会话。核对两款软件真正等价的节点地址/端口、协议、传输、TLS/REALITY、SNI、ALPN、路由模式、规则、DNS 和 IPv6 条件；仅节点名称相同不够。比较工作在本地完成，凭据和完整订阅不写入报告。

先记录原代理/PAC/bypass/环境状态及当前安装包身份。以下命令从仓库根运行，`$evidenceRoot` 是本地私有目录；collector 不改变网络设置：

```powershell
$evidenceRoot = 'C:\SwirlEvidence\20261102'
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Baseline -OutputPath "$evidenceRoot\00-original.json"
```

Swirl 正在运行时自动发现其 EXE；未运行时，可用实际安装路径显式指定，例如：

```powershell
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Baseline -OutputPath "$evidenceRoot\01-installed.json" -SwirlExecutablePath 'C:\Program Files\Swirl\Swirl.exe'
```

示例安装路径必须换成真实位置。记录缺失、不可读、hash 不匹配或未知版本都保留为失败/未知，不能补填推测值。

### 2. A：Clash 正常路径

仅通过正常应用操作开启 Clash 系统代理，选择已核对节点。保存工作后正常退出并重新打开 Codex，记录新 PID/创建时间，避免把另一轮既有进程当成对照。执行下面采集，在本地记录每个动作的时间、成功/失败及错误类别：

```powershell
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Clash -OutputPath "$evidenceRoot\10-clash-before.json"
```

依次验证工作空间设置加载、新建对话、至少三轮回复、打开已有项目，并保持实际 WS/SSE 会话运行至少 30 分钟；同时验证 VS Code、Git/GitHub、curl、PowerShell、Chromium 及适用的 Node/Rust 客户端。记录它们实际使用的系统代理/API/环境入口，不能预设所有 CLI 都读取 Windows 系统代理。

```powershell
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Clash -OutputPath "$evidenceRoot\11-clash-after.json"
```

### 3. B：Swirl 相同路径

正常关闭 Clash 接管，保持网络和对照条件不变，再开启候选 Swirl 的系统代理及同一节点。按同样方式正常重启 Codex、执行完全相同的动作和持续时间：

```powershell
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Swirl -OutputPath "$evidenceRoot\20-swirl-before.json"
# 完成与 A 相同的桌面操作、客户端检查和持续流观察。
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Swirl -OutputPath "$evidenceRoot\21-swirl-after.json"
```

关联客户端 PID 到 Swirl loopback listener、内核所选节点/规则、DNS 与连接阶段，并用相同测试目标核对两轮出口 IP；collector 本身不测出口 IP、不读取节点凭据、不解密 TLS。内层 TLS、认证状态、WS/SSE 结果须由实际客户端或专门测试给出，不能由一条 CONNECT 200 推断。

对失败分开记录：代理握手/未进入 listener、DNS/IPv6、节点 TLS/REALITY、目标 TLS、HTTP/2、WS/SSE、提前 EOF、取消/超时、回环、系统代理不同步、真实 HTTP 403/429、明确 challenge、本地 workspace gate。HTTP 403 或 432 wrapper 本身不足以断定节点、OpenAI 服务端或账号有问题。若 A/B 不一致，按相同条件再做 A 复核，保留原始失败，不改认证、证书或路由掩盖结果。

### 4. 恢复和合并门禁

正常关闭 Swirl 系统代理，采集恢复状态：

```powershell
.\tools\Collect-CodexNetworkEvidence.ps1 -ComparisonLabel Baseline -OutputPath "$evidenceRoot\30-restored.json"
```

比较原始与恢复后的 WinINet/registry、PAC 存在状态、bypass 摘要、WinHTTP 和环境读数；在本地核对原 PAC/原配置的精确恢复。若其他应用期间改了代理，Swirl 应保留外部修改并放弃所有权，不能强制覆盖成旧快照。原生自动恢复测试只在一次性 Windows runner 上执行。

全部适用 CI、同节点 A/B、桌面多轮/持续流及恢复验收都取得真实证据后，才允许普通合并至 `test`。本任务不操作 `main`；未取得 Windows 11 证据时保留明确的未验收状态，不用 CLI、TUN 或模拟结果代替。

## 六、公开参考实现研究

以下资料于本轮核验，仅用于理解协议边界、制定测试和审查 Swirl 自有实现。Mihomo 是 Clash 系的公开实现参考，不代表用户设备上 Clash 的确切版本与配置；**源码/文档对照不是同节点实机 A/B 结果**。Surge 与 Loon 的以下资料描述 Apple 平台产品，不能当作 Windows 系统代理实现证据。没有复制这些项目代码或引入其内核运行时。

| 参考项目与一手来源 | 已核对行为 | 对本轮 Swirl 检查的用途 |
| --- | --- | --- |
| Mihomo / Clash 系：[代理端口](https://wiki.metacubex.one/en/config/inbound/port/)、[HTTP listener 源码](https://github.com/MetaCubeX/mihomo/blob/Meta/listener/http/proxy.go) | 官方文档区分 HTTP、SOCKS4/4a/5 与 mixed 端口；HTTP listener 按请求 HTTP 版本形成 CONNECT 成功响应，并把已缓冲字节交给隧道 | 对照 HTTP/1.0、HTTP/1.1、混合入站及 CONNECT 后预读数据完整性；没有从端口名推断用户实际协议 |
| sing-box：[Mixed inbound](https://sing-box.sagernet.org/configuration/inbound/mixed/) | mixed 接受 HTTP、SOCKS4/4a/5，配置包含认证用户；`set_system_proxy` 负责启动设置与停止清理，文档列出 Windows 支持 | 分别验证协议入口、认证和系统代理生命周期；该文档不足以推断具体 registry 格式或保证每个应用都遵循代理 |
| Xray：[HTTP inbound](https://xtls.github.io/en/config/inbounds/http.html)、[HTTP server 源码](https://github.com/XTLS/Xray-core/blob/main/proxy/http/server.go) | HTTP 入站承载 TCP，非空用户表启用 Basic 认证；CONNECT 保留 parser 预读字节，请求解析后清除握手读取 deadline；透明转发配置不当可形成回环 | 覆盖同包 ClientHello、认证失败、握手时限与持续流分离、回环边界；不把 HTTP CONNECT 当成 UDP 验收 |
| v2rayN：[SysProxyHandler.cs](https://github.com/2dust/v2rayN/blob/master/v2rayN/ServiceLib/Handler/SysProxy/SysProxyHandler.cs) | Windows 普通代理、清理和 PAC 是独立分支；普通代理默认生成 loopback 的 `host:port`，PAC 使用独立服务与配置路径 | 核对 Swirl 单一 HTTP proxy 字符串与 PAC 分层；继续保留 Swirl 已有原配置恢复和外部修改所有权规则 |
| Surge：[Understanding Surge](https://manual.nssurge.com/book/understanding-surge/en/) | 官方说明适用于 iOS/macOS；系统代理需要应用支持，命令行客户端行为可不同，虚拟网卡接管是另一入口 | 用于解释系统代理与 TUN 的能力边界；不据此宣称 Windows、Codex 或 Swirl Native TUN 已验证 |
| Loon：[平台说明](https://nsloon.app/en/)、[General configuration](https://nsloon.app/en/docs/General/) | 产品说明为 iOS/tvOS；`skip-proxy` 控制 HTTP proxy 绕过，`bypass-tun` / `include-tun` 控制另一层 TUN 路由，DNS 单独配置 | A/B 必须分别核对代理绕过、TUN、DNS 条件；这些配置不是本轮给 Codex 增加直连例外的依据 |

## 七、仍待验证或补足的实际边界

| 边界 | 当前源码/证据 | 对结论的限制 |
| --- | --- | --- |
| Fake-IP | `core/crates/swirl-dns/src/lib.rs` 明确声明未实现 Fake-IP | 不能将其他分支的 TUN 工作或系统 DNS 测试登记为 Fake-IP 已支持；本轮没有追加该功能 |
| TCP 保活 | `swirl-protocol/src/dial.rs` 的连接路径设置 `TCP_NODELAY`，没有显式启用或配置 TCP keepalive | 没有证据证明这一点就是 Codex 根因；本轮未盲目增加 keepalive 或放宽超时。QUIC 的 keepalive 配置不能代替 TCP/NAT 验证 |
| 实际获胜地址 | 多个 DIRECT 候选时 V2 trace 的 `chosen_ip` 为 null，保留 `direct_candidate_count` | 避免将第一个 DNS 答案误报为出口，但尚未回填连接调度实际获胜的 IP；不能据该字段推断完整连接路径 |
| 上游 HTTP 拒绝状态 | HTTP CONNECT 的 `403` / `407` / `429` 等仍汇总为 `UpstreamRejected` | 本轮修复成功响应兼容性，没有完成细化状态的诊断字段；现有错误码不足以区分认证、策略拒绝或限流，更不能据此认定节点质量 |
| 长时与网络变更 | 本地受控 soak 已运行 8 连接、60.003701 秒，300 秒扩展及固定提交 CI 另记；小时级真实网络、NAT 空闲过期、睡眠/恢复、网络切换均 **NOT_RUN** | 短协议 fixture 证明有限协议行为。后续受控 soak 即使通过，也须分别报告时长和负载，不能替代 Windows 11 实际节点及电源/网络事件验收 |
| 桌面因果链 | 当前用户安装包身份、请求是否到达 Swirl、实际节点参数、出口和认证桌面结果尚未取得 | 已修复三个可复现的内核缺陷；用户报告的 Codex 故障是否由它们触发，仍须第五节的同条件 A/B 证实 |
