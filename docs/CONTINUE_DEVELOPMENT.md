# Swirl 接续开发入口

最新阶段：[旧式 Loon SS 原生转发及跨平台诊断验收](RUST_LOON_SS_NATIVE_20261018.md)。功能源码4ea4139，最终测试源码d7e79df：三平台CI、Qt集成、私有复核均成功；18/18缓存入口可解析，新增入口的前三个SS节点严格HTTPS通过。旧macOS测试失败已定位为唤醒时延假设并修正测试契约，产品超时与校验器不变。订阅窗口仍关闭，继续仅使用D盘加密缓存。

最新采集及导入阶段见 [本机订阅窗口与旧式 Loon Trojan](RUST_SUBSCRIPTION_WINDOW_20261018_LOCAL.md)。新窗口18个入口均已加密保存到D盘，供应商请求已停止；原始缓存保留。双源与固定SS本机实测已通过；Linux/Windows CI成功，macOS同一DNS诊断测试两次失败，详情和准确源码SHA见该记录。

**最新补记：原密钥通过已有 GitHub Secret / Windows runner 在内存中复用，无需用户寻找或重发。**
[本机双源与固定 SS 实测](RUST_WINDOWS_FIXED_SS_20261018.md)已完成：16个远端URL与本地完全一致，
本地另有两个未对应条目；14份本地缓存正文均与当前远端不同，但三个SS来源对的可执行参数完全一致。
同一旧密文 #9 的节点1/2/3在用户Windows上Python/Rust TCP均3/3通过，随后严格TLS 1.3、HTTP200、
双向转发及正常关闭均3/3通过。实际私有运行39099020539为success；供应商刷新0，密钥未导出/更换。
此前“本机缺密钥、固定SS未测”是下方阶段的历史状态，已由本次证据取代。云端Linux TCP失败仍保留，
不能据Windows成功推断云端IP被封，也不能外推全部节点、UDP或完整GUI配置。Rust源码未再改动。

2026-10-18 Windows 本地接续：新增 [DNS 失败缓存阶段](RUST_DNS_FAILURE_CACHE_20261018.md)。
在原有 SOA 负缓存之外，完成的上游失败按原错误码缓存一秒；先走备用解析器、保留 TLS 校验和
原连接超时，配置换代清缓存。128 项 Rust、23 项独立 DNS 和本机 Qt CTest/四个协议对端已通过；
最终实测源码 `b903b8b1d9c5e0c40c3dee5033447900665d1835` 的 Core 39097773884 三平台及
App 39097773891 均已成功。Linux/macOS 各167项Python通过/4项Qt跳过；托管Windows补齐Qt后
203项通过/2项可选跳过，本机202项通过/3项明确跳过。首轮Windows端口夹具失败及修正均保留。
本机DIRECT严格HTTPS两项通过，Cloudflare DoH失败；托管Linux三项公网门禁通过，不能混为一谈。
本地旧 DPAPI 缓存与 GitHub 当前正文哈希均不相同，现有 Fernet 密钥尚不可用，固定 SS Windows
对照仍未执行；没有刷新供应商订阅。后续所有新产物放 D:\Codex，旧 C 盘环境只读复用。

更新日期：2026-10-18 UTC。第二轮从 `13ea97af5c94198ecba4ed79b16cfc7b1b676f27` 接续。
当前以 [第二轮采集与 DNS/TCP 阶段记录](RUST_CAPTURE_DIAGNOSTICS_VALIDATION_20261018.md) 为准；
以下 2026-10-17 的 #32、两份缓存及三项超时记录保留为历史对照，不代表第二轮获取数量。

## 第二轮当前结果

- 固定订阅截止 `2026-10-18T02:04:09Z`；16/16 正文已在截止前逐份加密校验并推送私有仓库，新增14、刷新2，最后远端检查点 `cea2a1e` 于02:03:59确认。截止后不再请求供应商订阅入口。
- 三份独立本轮密文、上轮窗口及旧主归档历史均保留。首次严格离线合并因 #12 等值 `peer/sni` 别名被过度拒绝而失败；源码 `44488e7a88c66125164e85720278be052f4aa74b` 修复后，16份原生解析及正式离线合并成功，私有提交 `0f84c4cb676d0ce868e5a873eda28de8cc0fe570`，解密/正文哈希/旧窗口不变均已核验。16入口含7种正文哈希，1440为节点记录数，不是唯一节点数。
- 新增同一产品拨号器的 `swirl-diagnose` 和独立 Python DNS/TCP 对照；固定上轮 #9 节点1/2/3，共享每样本10秒，两个后端DNS合计最多3秒、最多两个待完成TCP。TCP成功不等于SS认证或HTTPS通过。
- 这三个固定旧样本已在托管Linux实测：两引擎各解析4个IPv4/0个IPv6，各尝试4/剩余0，全部TCP超时。样本总耗时9547/9547/9545ms；没有进入SS混淆/认证/HTTPS。私有运行39091919549如实failure，报告推送并核对远端 `cca8b53e0829ffb49c0a2d14a5aaecdd7a87d30d`。订阅入口请求数为0。用户Windows本轮仅证实执行了采集，不能把托管Linux诊断当作本机网络证据。
- 修复IPv6 URI主机、INI位置/命名参数冲突、legacy SS保留字符密码、SIP002百分号编码及等值URI别名/严格UDP布尔值。125项Rust workspace测试及fmt/check/Clippy已通过；新增Python导入7/7，11个独立SS加密会话和4个严格TLS Trojan会话通过，未知CA与错误名称按预期拒绝。
- 完整本地Python15套共200项：163通过、37明确跳过、0失败；最终Release库及三个原生程序通过。Windows/macOS首次#33各有两个TCP拒绝测试夹具失败；`63df5807499fddad6936d918f8807e550ca3e528`仅修正关闭监听端口的测试方式，保留全部20项，未改产品调度或超时。UI和用户网络设置未改。
- 当前16份完整客户端配置的组/DNS/路由执行标志均为false；8份SS各90条为待联网TCP候选，8份Trojan各90条因源配置要求关闭证书验证而阻止执行。解析成功与完整产品执行、供应商联网分别记录。
- 最终实测源码为 **`056fd56387e15d65259eff5f612b3ad7a1ce7009`**：[Rust Core #35](https://github.com/SOLHK/Swirl/actions/runs/39093009560)三平台全通过，[App #32](https://github.com/SOLHK/Swirl/actions/runs/39093009558)也通过。各平台125项Rust及Release通过；Linux/macOS各Python162通过/4Qt跳过；Windows补齐Qt后198通过/2可选跳过，CTest1/1及四个Qt独立对端全通过。
- Windows实际回环拒绝通知耗时为系统2006ms/诊断器2027ms，证明原500/200ms夹具截止过短；最终夹具分离确定性调度和OS实测，产品超时不变。严格公网DIRECT/DoH三项通过，仍不代表供应商SS通过。App157个源码文件及模式逐一匹配056fd563，无意外源码提交。
- 最后的交接提交仅更新文档/JSON证据，源码、测试、工作流须与056fd563完全相同；不要把文档HEAD当作另一轮已经执行的CI。私有证据提交、归档哈希及保留的#33/#34失败见最新验收文档。
- 私有最终交接HEAD为 `ee99c85064ca2688a35e30dc714ae56da68fad07`，只更新README并已按提交读回核验；正式合并与实际诊断报告分别仍是0f84c4c和cca8b53。公开最终三平台、Qt及App的结构化证据见 [RUST_CI_20261018_VERIFIED.json](evidence/RUST_CI_20261018_VERIFIED.json)。

## 持续约束与上一轮背景

- **当前唯一开发分支：`work/core-completion-20261017`。** 用户最新指令覆盖历史 `test` 要求；不改 main、不强推。已配置的 GitHub App/Secrets 沿用，不重新配置。
- 用户已明确持续授权本开发分支的修复、测试与 GitHub 写入（“始终允许”）；在既有权限内继续实施，无需重复询问同一开发分支的常规提交。
- 原生 IR/API 已接入嵌套手动组、`url_test`、`fallback`、`load_balance`、经实际出口的 HTTP/HTTPS 健康探测和会话策略视图。上一轮 Qt 完整配置转换和 Controller 保存已接入前向手动嵌套、url-test/fallback、显式 round-robin；默认哈希负载均衡和自动组嵌套仍拒绝。QML 控件不变，Windows #32 Qt 编译、CTest 1/1 和四项独立 Qt 协议对端已通过，详细边界见 [原生策略组](RUST_NATIVE_POLICIES.md)及第一轮记录。
- 健康视图在 listener accept 时固定；旧 TCP/UDP 保留原出口，完整配置替换/stop 取消旧探测。失败应用请求不重放，无健康成员不静默直连；四个跨配置代共享探测名额和有界期限限制后台工作。
- SOCKS4/4a 的 Rust subscription inspector 与 Qt 节点转换已接入，十个本地 inspector 至独立对端的真实会话通过。Windows #25 新增 SOCKS4/4a 六个 Qt 转发会话、VLESS WS 的 131073 字节真实响应均通过；Qt CTest 与既有 SS/VLESS 对端也通过。本地 Linux 没有 Qt SDK，不能把 Windows 证据外推为各平台桌面验收。
- WebSocket 关闭预算现在从最早关闭意图开始，覆盖拥塞队列、旧数据、Close 写入/flush、对端回复和底层 shutdown。既有 DoH、WS/WSS 及协议握手继续复用，没有重写已有传输。
- 当前阶段默认产品仍保留 C++/Mihomo 兼容构建。必须用 `SWIRL_USE_RUST_CORE=ON` 验证原生 Rust；该模式不会回退完整外部内核。智能 MRS、TUN、LAN 和未迁移协议仍会明确拒绝。
- DNS 缓存已按大小写规范化的主机共享 IP 集合，并接入严格 SOA 的 NXDOMAIN/NODATA 负缓存；UDP/TCP、DoT、DoH 共用校验与合并逻辑。RFC 9520 的解析失败缓存、DNS 分流及自动 bootstrap 仍未实现。
- 上一轮已实现同一解析结果的有界多地址 TCP：最多两个待完成连接、250ms 间隔、原有总期限，TCP 获胜后先取消其他候选再发送协议数据。保留 CIDR 固定 IP，不在 TLS/认证失败后重试。Snapshot 已增加白名单失败阶段和每连接静态错误；延迟 SS/混淆响应错误仍属 StreamIo，不假定初始写入就是认证成功。
- 用户已授权使用 `Swirl-Private-Tests` 中现有加密归档，在私有 Actions 内仅于内存解密、通过 stdin 交给原生 inspector/harness，只保存白名单报告。此项是旧版“私有缓存不进 CI”表述的明确例外；原始 URL、令牌、节点凭据和解密配置仍不得进入公开 Git/CI、日志或外部转换服务。未获新窗口授权，不刷新订阅 URL。
- 第一轮（2026-10-17）窗口内云端 16 项均为 HTTP 403；随后现有 Windows 采集器取得 #9/#10 的有效更新（212456/210026 字节），其余 14 项仍为 403。该轮实际 2 份更新、0 个新增、14 个缺失，逐份加密推送到独立窗口归档。该轮固定截止 18:39:54 UTC，最后请求于 18:38:29 完成。私有 `ff9b187065e633db94fbd67773ae4062a1b81d59` 已安全合并当时的 `secure/subscriptions.enc`，解密/正文哈希校验通过，窗口密文未改变，旧正文仍在 Git 历史。该历史记录不能替代第二轮16份的结果。
- 第一轮私有 `aa690e40c9d8d12b0639fd6ac76c56e6b21ada8d` 报告固定源码 `99ad9b3`，三个 SS 抽样均 `UpstreamTcpTimeout / tcp_connect`，应用上传/下载 0，未进入混淆或协议认证；当时报告缺少DNS/逐地址耗时。该轮交接提交为 `5820fda2242c9a5d53ed1e35fa8589fe5abc14fa`，第二轮最新私有证据见本页开头。
- 用户本轮明确追加“可以在C盘，速度”，因此允许复用现有 C 盘 Windows runner。默认 D:\Codex 偏好与该次明确授权分别保留。当前云端 Linux 工作区不等于用户 Windows 磁盘，GitHub 推送不等于已保存到 D 盘。
- 第一轮结果以 [连接与 Qt 策略阶段验收](RUST_CONNECTION_POLICY_VALIDATION_20261017.md) 为准；[DNS 与订阅阶段](RUST_DNS_SUBSCRIPTION_VALIDATION_20261017.md)及下方旧运行保留为历史证据。#32 是第一轮的已核验结果，第二轮见20261018阶段记录。

## 上一轮验收状态（历史，#32）

- [Rust Core #32](https://github.com/SOLHK/Swirl/actions/runs/39061540612) 于 19:25:24 UTC 三平台全部成功，[App #29](https://github.com/SOLHK/Swirl/actions/runs/39061540617) 也成功，均固定 `99ad9b3`。各平台 fmt、check、Clippy `-D warnings`、101 项 workspace 测试和 release 构建全部通过。
- 本地 13 套 Python 共 169 项，132 通过、37 明确跳过、0 失败；新增连接阶段 8/8、原生 probe 7/7、工作流更新器 15/15。
- 37 个跳过为四项 Windows Qt 对端、22 项 Windows DPAPI 采集、10 项 Windows DPAPI 管理和可选真实 Codex CLI。不能算作本机通过。
- Linux/macOS 各 11 套 Python 135 项，131 通过、4 Qt 跳过、0 失败。Windows 初次 169 项为 163 通过、6 跳过；Qt 编译后 CTest 1/1 通过（6.92 秒），四项 Qt 独立对端补跑通过，按独立项计最终 167 通过、2 可选跳过（C++ importer、真实 CLI）。
- [本轮公网原始 JSON](evidence/RUST_PUBLIC_NETWORK_20261017_CONNECTION_VERIFIED.json) 3/3 通过：严格证书 TLS 1.3、HTTP 200/301/200、正常关闭及双向流量，每项 `accepted=1 / active=0 / failed=0`，错误码/阶段为空。范围仅明确原生 DIRECT 和原生 DoH。
- 私有合成工具 33/33 通过；实际离线合并成功且先推送归档，再测试节点。三个 SS 的 TCP 超时被如实报告为工作流 failure；Trojan 因配置不安全未执行。详细密文/正文哈希、提交和失败运行见 [阶段记录](RUST_CONNECTION_POLICY_VALIDATION_20261017.md)。
- 该历史阶段当时的后续任务是同三个缓存SS的独立DNS→逐地址TCP对照；第二轮已完成，详见本页开头和20261018记录。完整订阅组/路由/DNS到产品的严格转换仍待继续。

## DNS 与订阅阶段验收（历史，#30）

| 内容 | 该历史阶段执行证据 |
|---|---|
| Rust 格式、check、clippy、workspace 测试及 release 构建 | 全部通过；90 项 Rust 测试通过，0 失败/跳过 |
| 首轮完整本地 Release Python 回归 | 12 套件共 156 项，119 通过、37 明确跳过、0 失败；各套件退出码均为 0 |
| 新增 DNS 负缓存独立对端 | 原 15 项语义测试及后补 3 项端口分配测试共 18/18 通过；另有 5/5 旧 DNS 定向回归通过 |
| 新增原生出口 probe 边界 | 6/6 通过；包含实际 Rust harness 访问独立拒绝连接的 SS 对端 |
| 私有测试工具合成回归 | 补充静态错误码白名单后 9/9 通过，独立于公开 Python 总数；覆盖脱敏、密钥环境清除、失败报告和有界抽样 |
| 本轮源码与测试修正 | [`95b4fbc`](https://github.com/SOLHK/Swirl/commit/95b4fbc8f58b166a93fcc10b648bef39d396c4d6) 实现，App [`95b46f4`](https://github.com/SOLHK/Swirl/commit/95b46f4e3494feede242650324ac6ea542912c4a) 仅增加 6 行测试；[`fa37637`](https://github.com/SOLHK/Swirl/commit/fa376375bd67e77b8253eee4bcf40d4633b08c3d) 修正 Windows 早拒绝测试假设；[`f13c695`](https://github.com/SOLHK/Swirl/commit/f13c695ab1747e84de8594bfe208bd278b6149a6) 修正 DNS 对端配对端口分配 |
| 最终 Linux/macOS CI | [Swirl Rust Core #30](https://github.com/SOLHK/Swirl/actions/runs/39055991802)，实际源码 `f13c695`；两平台各 90 Rust 通过，125 Python 中 121 通过、4 Qt 跳过、0 失败 |
| 最终 Windows/Qt CI | 同一 #30；90 Rust 通过，初次 159 Python 中 153 通过、6 跳过；Qt CTest 1/1（3.14 秒），四项独立 Qt 对端全部补跑通过，最终 159 个独立 Python 用例为 157 通过、2 个可选项跳过 |
| 最终严格公网门禁 | 同一 #30 Linux；[原始 VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_DNS_VERIFIED.json)，3/3 通过：HTTP 200/301/200、验证证书的 TLS 1.3、正常关闭、双向流量、每项 `accepted=1 / active=0 / failed=0`，无会话错误 |
| 现有加密归档的原生 SS/Trojan 抽样 | 两份解析通过；三个 SS 样本 `UpstreamTimeout`、零目标流量，Trojan 因关闭证书校验未执行；[私有报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/ae7ebe3e409c254012aa82cb47117b7620c87e9f/reports/native-core-95b4fbc-20261017.json) 如实保留联网失败 |

37 个跳过包括四项 Windows Qt 对端、22 项 Windows DPAPI 采集、10 项 Windows DPAPI 管理和一项
可选真实 Codex CLI。一次 release 链接错误后原命令重试成功，根因未确定；完整命令、结果及证据边界见
[本轮阶段记录](RUST_DNS_SUBSCRIPTION_VALIDATION_20261017.md)。
`f13c695` 的 Rust `core` 树与共享 verifier 均与私有固定版本 `95b4fbc` 完全相同。
公共 #30 已于 2026-10-17 18:08:08 UTC 三平台整体成功；同一源码的
[App #27](https://github.com/SOLHK/Swirl/actions/runs/39055991875) 也成功。Windows 余下两个可选跳过项
为 C++ importer 和真实 Codex CLI；Linux/macOS 的 Qt 跳过项不计为已验收桌面支持。
本轮此前 Windows reset 和 Linux 端口碰撞的失败运行、具体修正及最终源码身份均记录在阶段文档中。
私有原生测试已经执行；尚未取得私有节点的联网通过证据，不能把解析或转换成功计作通过。

## 策略、SOCKS4 与 WebSocket 阶段验收（历史，#25）

以下是上一阶段 `58969bc` / `5dbe762` 的已完成证据，详见 [策略阶段记录](RUST_POLICY_VALIDATION_20261017.md)。

| 内容 | 该历史阶段执行证据 |
|---|---|
| Rust 格式、check、clippy、workspace 测试及 release 构建 | 全部通过；83 项 Rust 测试通过，0 失败/跳过 |
| 本地 Python 回归合计 | 134 项中 97 通过、37 明确跳过、0 失败；其中策略独立对端 13/13 通过 |
| 可区分 UDP 出口 | 两个独立 SS 出口共六次往返；健康切换和完整配置替换后旧关联仍固定原出口 |
| 本地固定公网尝试 | 三项在 DNS/连接阶段失败；[原始 JSON](evidence/RUST_PUBLIC_NETWORK_20261017_POLICY_LOCAL.json) 保留，未计作通过 |
| 该阶段源码提交 | [`58969bc`](https://github.com/SOLHK/Swirl/commit/58969bce15f9995573f15661bbd1ca75530938af)，已推送；远端源码树与本地验收暂存树一致 |
| App 工作流提交 | [`5dbe762`](https://github.com/SOLHK/Swirl/commit/5dbe762d4b85543939d8ca476451f137e210a559)，仅 `rust-core.yml` +9；[Core implementation validation #21](https://github.com/SOLHK/Swirl/actions/runs/39033743434) 成功 |
| 该阶段 Linux/macOS CI | [Swirl Rust Core #25](https://github.com/SOLHK/Swirl/actions/runs/39033762503)，实际提交 `5dbe762`；两平台均成功，各 83 Rust、96/100 Python 通过，4 Qt 跳过；策略 13/13 |
| 该阶段 Windows/Qt CI | 同一 #25 全部成功；83 Rust，初次 134 Python 中 128 通过、6 跳过；Qt CTest 1/1（3.12 秒），随后 SS/VLESS/SOCKS4/WS 四项独立 Qt 对端全部补跑通过，余下两项可选私有 importer/真实 CLI 未执行 |
| 该阶段严格公网门禁 | 同一 #25 Linux；[原始 VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_POLICY_VERIFIED.json)；三项 HTTP 200/301/200、认证 TLS 1.3、正常关闭、双向流量、每项 `accepted=1 / active=0 / failed=0`，无会话错误 |

工作流更新器已通过 13 项安全回归；App 实际提交与精确 +9 行预览的 SHA-256 均为
`50308ecf9ca19e1da4e26893ecb9c6aa8291dc5161976795cf89b4310dc89293`。
新增策略对端、portable inspector 和 Windows SOCKS4/WS Qt 实测，不调整 App 或 Secrets。
#25 三平台整体于 2026-10-17 12:55:06 UTC 成功完成。公网报告准确标记 `5dbe762`、干净工作区，
CI release harness SHA-256 为 `914ee31cac2e00f75bb78bde55a22f68e60c6e98b4af8e6e71d906b59b5e1da0`。
完整命令、边界、哈希和各项跳过原因见 [该阶段验收](RUST_POLICY_VALIDATION_20261017.md)。

## 上一阶段远端提交与验收（历史）

| 内容 | 证据 | 该历史阶段状态 |
|---|---|---|
| Rust WS 背压与独立对端调度修复、专项回归和文档 | [`510c62a`](https://github.com/SOLHK/Swirl/commit/510c62ade64418c76241bbe76ae118c5040dad92) | 已推送开发分支 |
| App 自动提交工作流更新 | [`a60c446`](https://github.com/SOLHK/Swirl/commit/a60c446fdb54c10753c2d367752c4e0275a89922)、[Core implementation validation #17](https://github.com/SOLHK/Swirl/actions/runs/39029146435) | App 生成 Token、checkout、提交并推送 workflow 均成功；唯一改动为 `rust-core.yml` +23/-1 |
| Linux、macOS、Windows Rust 与独立协议验证 | [Swirl Rust Core #21](https://github.com/SOLHK/Swirl/actions/runs/39029167841)，`a60c446` | 三平台均成功；各 57 项 Rust 测试、64 项独立 Python 协议测试通过，初次协议运行各有 2 项 Qt 测试跳过 |
| Windows Qt 与独立对端 | 同一 #21 的 Windows job | Qt CTest 1/1 通过，用时 3.09 秒；随后 SS Qt 与 VLESS Qt 对独立对端的真实转发分别通过，补足前述 2 项 Qt 跳过；Qt WS 仍只有配置映射/拒绝证据 |
| 初次公网 HTTP/TLS 与原生 DoH 路径 | 同一 #21 的 Linux job；[阶段验收及原始报告](RUST_WS_VALIDATION_20261017.md) | 收到 HTTP 200/301/200、认证 TLS 1.3 和真实流量；当时三个会话为 `failed=1`、`last_error=StreamIo`，未满足正常关闭验收，已由下述验证客户端补丁处理 |
| 公网验证客户端收尾与严格门禁修复 | [`c0eb221`](https://github.com/SOLHK/Swirl/commit/c0eb2211ea646da023119e9458139d538a311000)、[Core implementation validation #19](https://github.com/SOLHK/Swirl/actions/runs/39030037978) | 已推送，#19 成功；修复 TLS/TCP 收尾并要求零会话错误，没有修改 Rust relay |
| 严格公网 HTTP/TLS 与原生 DoH 路径 | [Swirl Rust Core #22](https://github.com/SOLHK/Swirl/actions/runs/39030038029)，`c0eb221`；[VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_VERIFIED.json) | Linux 三项全部通过：HTTP 200/301/200、认证 TLS 1.3、双向流量非零、`orderly_close=true`，每项 `accepted=1 / active=0 / failed=0`、`last_error` 为空、连接记录为 1 |
| 第二阶段跨平台回归 | 同一 #22，已整体成功 | Linux/macOS/Windows 各 57 项 Rust 通过；Python 协议/验证器共 71 项，69 项通过、2 项 Qt 跳过；另有 11 项工作流回归通过。Windows 随后 Qt CTest 1/1 通过（3.17 秒），两项独立 Qt 转发分别通过，补足前述 Qt 跳过 |

已核对 App 提交的 `.github/workflows/rust-core.yml` SHA-256：
`c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`，与本地审核的预期内容一致。
这次真实提交/推送证明 Workflows 写权限已生效；没有重新配置 App、修改 Secrets 或改动 main。
本地已通过的测试、明确跳过项和失败的公网尝试见 [阶段验收](RUST_WS_VALIDATION_20261017.md)；
#21 于 2026-10-17 11:42:56 UTC 完成且整体成功，但初次公网门禁未检查会话正常关闭。
独立对照确认其 `StreamIo` 来自验证客户端直接关闭 TLS socket；`c0eb221` 修复客户端收尾并收紧门禁，
#22 的严格公网报告时间为 11:50:27 UTC，三项均通过；11:56:56 UTC 三平台整体成功。两轮 Rust binary SHA-256 完全一致：
`7e83e9b89232f4712335ca9e4d8e6f3dacbb52b5f2daefbe357055792ce132d9`。
这证明所测 DIRECT/DoH 路径的真实请求与正常关闭，不代表私有提供商、WS 节点、UDP 或 TUN 已验证。
该阶段 Windows Qt 的成功不替代后续 Qt WS 真实转发、个人电脑视觉验收或其他平台的桌面产品验证。

## 仓库是否完整

**当前源码位于 SOLHK/Swirl 的 `work/core-completion-20261017`，包含原 test 分支完成的 Rust 工作。**
这与“所有规划功能已完成”不同：Rust 全量迁移仍在进行。
开始前执行 `git fetch origin`、核对 `origin/work/core-completion-20261017`、工作区状态及当前分支，避免从旧的 main/test 覆盖接手后的工作。

仓库包括 Qt/C++/QML 界面和平台代码、Rust 七个 crate、Cargo.lock、依赖清单、
本地合成测试、GitHub Actions、字体/图标、规则资源、vendored nghttp2 源码及构建脚本。
没有需要另行取得的私有源码子模块，也不依赖本机工作目录里的未提交代理内核代码。

编译器、Qt SDK、Rust 工具链、Cargo 第三方包、Python 测试依赖和生成的 EXE/DLL
不是项目源码，需按文档安装/恢复。默认兼容构建的 Mihomo 二进制由
`scripts/stage-mihomo.ps1` 按提交的 manifest 下载并校验；Rust 构建不得使用它回退。
历史 `build-current-portable.ps1` / `build-quick-windows.ps1` 面向兼容构建，不能直接当 Rust 打包脚本。
本机交付 ZIP 不一定等于 GitHub Releases 上最近的旧版安装程序，必须核对提交和内核身份。

历史完整性检查：`72d5bd5` 纯 Git 导出包含 630 个文件，无源码子模块、LFS 占位文件或
构建缓存之外的被忽略文件；从独立导出目录读取 Cargo workspace 得到全部 7 个 crate，
Qt/Rust CMake configure/generate 成功。此检查不声称重新完成了一次全量编译，已有构建测试见下文。

私有订阅 URL、令牌、节点凭据、DPAPI 缓存、用户配置、SDK、构建缓存、临时交付脚本
和本机验证日志刻意不进 Git。它们不是缺失的源码。接手者可用仓库内合成服务端继续开发，
不得为补齐仓库而上传用户私有材料；云端也无法解密本机 Windows 用户的 DPAPI 缓存。

## 必须延续的约束

1. 每完成一个可验证阶段，提交并推送 **work/core-completion-20261017**，然后核对远端提交及实际被测试的 SHA。不得推送、合并或重置 main。
2. 保留现有 UI 布局、视觉和交互；继续 Rust 自研数据路径，不包装完整外部代理内核冒充自研。
3. 独立实现和审查，不要求常规 Gemini 审核。用户现已允许换开发者/模型继续，旧“唯一集成人”描述不是阻止接手的理由。
4. 未知参数保留并报告；不关闭 TLS 校验、不伪造兼容性、不静默直连或自动重放请求。
5. 继续使用已缓存材料；第二轮16份正文已经独立加密持久化，合并状态见最新阶段记录。旧“只有两份正文”的描述属于第一轮历史。私有Actions离线验证无需再打开窗口；第二轮截止后刷新供应商URL须另获新的开启指令。
6. 分开记录解析、参数转换、合成对端、私有节点、UDP、TUN、性能和跨平台证据。未测不能称通过。
7. 用户额度有限，优先完成具体实现与必要验证，不反复重审历史方案。每阶段更新本文件或对应能力文档。

完整要求见 [合并开发约束](SWIRL_CORE_DEVELOPMENT_CONTRACT.md)。历史文档如与本文件或后续用户指令冲突，以较新指令为准。

## 当前实现与代码位置

| 位置 | 已实现 |
|---|---|
| `core/crates/swirl-protocol` | HTTP/CONNECT/SOCKS4/4a/5 入站；HTTP CONNECT、SOCKS4/4a/5、Trojan TLS、SS AEAD TCP/UDP、simple-obfs HTTP、基础 VLESS v0 TCP/TLS；VLESS WS/WSS、Trojan WSS |
| `core/crates/swirl-routing` | 顺序域名/后缀/关键词、目标端口、来源/目标 CIDR、MATCH；有界嵌套手动组与自动组会话选择 |
| `core/crates/swirl-dns` | 自研 Rust DNS 报文/UDP/TCP/严格 DoT/HTTP-1.1 DoH/A/AAAA/CNAME/TTL；按主机缓存 IP 集合、严格 SOA 负缓存、有界系统解析、精确 hosts、各代缓存隔离及共享并发上限 |
| `core/crates/swirl-core` | 有界运行时、不可变会话配置/健康视图、原子节点/组/配置更新、旧 TCP/UDP 保留原出口、流量统计；四名额健康探测、过期与取消、测速/fallback/轮询 |
| `core/crates/swirl-subscription` | typed IR、Clash YAML/JSON、sing-box JSON、URI/Base64、部分 INI 识别与保留、脱敏能力报告；严格 DoT/DoH/WS/策略字段和图验证；有限 SOCKS4/4a 导入已接入，并非所有格式都可执行 |
| `core/crates/swirl-transport` / `swirl-api` | 验证 TLS、背压/半关闭；ABI v1 JSON 控制、stdin harness、离线 inspector |
| `src/Swirl.Quick/engine/RustCoreEngine.*` / `RustDnsConfiguration.h` | 现有 Qt 控制层到 Rust DLL；规则、前向嵌套手动组、自动组叶子及显式轮询、本地 DNS 与 DoT/DoH/WS/SOCKS4 映射；明确拒绝未迁移语义 |
| `tools/` | 私有采集/离线分析、独立协议/DoT/DoH/策略对端、Codex 本地代理配置管理、受限工作流更新与测试 |

关键边界：[规则与 Qt 手动组](RUST_NATIVE_ROUTING.md)、[原生策略](RUST_NATIVE_POLICIES.md)、[本地 DNS](RUST_LOCAL_DNS.md)、[DoT](RUST_DOT.md)、
[SS-02 审核处理](SS02_REVIEW_DISPOSITION.md)、[Codex 管理](CODEX_PROXY_MANAGEMENT.md)。
手动组没有新增 UI 选择按钮；默认首成员或明确 default-selected，API 支持 select_group。
智能 MRS 路由尚未迁移，因此启用该默认设置的会话仍会被 Rust 拒绝；不可静默降级为全局。

## 从 GitHub 独立构建

用户 Windows 机器上先进入 `D:\Codex` 再克隆；Qt SDK、工具链和构建目录也应位于该目录下。

```sh
git clone --branch work/core-completion-20261017 https://github.com/SOLHK/Swirl.git
cd Swirl/core
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked -p swirl-api
```

Rust workspace 可在 Windows/Linux/macOS 验证；Qt Rust 桌面打包当前只支持 Windows。
Windows 示例在仓库根目录执行，Qt 路径需替换为实际 SDK。Qt MinGW 库必须搭配 MinGW，
Qt MSVC 库必须搭配 MSVC。CMake 3.25+，Qt 6.10.3（含 ShaderTools），Rust stable、匹配 C 编译器及 Python 3.11+。

```powershell
cmake -S src/Swirl.Quick -B build/rust-qt -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=D:/Codex/Qt/6.10.3/mingw_64 -DSWIRL_USE_RUST_CORE=ON -DSWIRL_BUILD_UI_TESTS=ON
cmake --build build/rust-qt --target Swirl SwirlRustCoreTests --parallel 6
ctest --test-dir build/rust-qt -R '^swirl-rust-qt-integration$' --output-on-failure
py -3 -m pip install cryptography==50.0.2
$env:SWIRL_RUST_HARNESS=(Resolve-Path build/rust-qt/rust-target/release/swirl-api.exe).Path
$env:SWIRL_RUST_INSPECTOR=(Resolve-Path build/rust-qt/rust-target/release/swirl-inspect.exe).Path
$env:SWIRL_RUST_QT_TESTS=(Resolve-Path build/rust-qt/SwirlRustCoreTests.exe).Path
py -3 tools/tests/test_rust_core.py
py -3 tools/tests/test_shadowsocks.py
py -3 tools/tests/test_dns_tls.py
py -3 tools/tests/test_dns_https.py
py -3 tools/tests/test_dns_negative.py
py -3 tools/tests/test_connection_stages.py
py -3 tools/tests/test_socks4.py
py -3 tools/tests/test_websocket_transport.py
py -3 tools/tests/test_policy_groups.py
py -3 tools/tests/test_native_probe.py
py -3 tools/tests/test_core_development.py
py -3 tools/tests/test_subscription_capture.py
py -3 tools/tests/test_codex_management.py
```

Qt DLL 需在 PATH 或由 windeployqt 部署。MSVC 多配置输出的 EXE 位于 `Release/`，调整上述路径。
核心 DLL、harness 与 inspector 必须来自同一次构建。Python 脚本中需 C++ 私有导入器或真实 Codex CLI
的可选测试需要额外环境变量；跳过项必须报告。不要把普通 CTest 中 SS/VLESS/SOCKS4/WS 外部对端的跳过项当通过，
上面的 Python 测试设置 Qt 路径后会运行对应槽。

Rust 预览部署至少需 Swirl.exe、swirl_api.dll、各辅助 EXE、Qt/QML 运行库以及适用许可证。
使用 windeployqt --release --qmldir src/Swirl.Quick/qml 部署，**不暂存 Mihomo**。
制作普通用户安装包前重新构建 `SWIRL_BUILD_UI_TESTS=OFF`；开发预览不得称正式完成版。
完整 MSVC CI 命令见 [Rust workflow](../.github/workflows/rust-core.yml)。

## 已有验证与仍需做的工作

DoT 阶段的实际提交、CI 与待个人电脑验收范围见 [DoT 文档](RUST_DOT.md) 和 [PR #22](https://github.com/SOLHK/Swirl/pull/22)。不沿用旧数字证明新实现；本轮私有节点测试状态以新阶段记录为准，未修改个人 Windows 网络。

上一自定义 UDP/TCP DNS 阶段：本机 Rust 43 项、独立协议 28 项（含 IPv6 DNS 服务端和 TCP 重试）、
采集/离线 23 项及 Qt Rust CTest 通过；fmt/check/clippy 通过。DNS 核心报文与网络执行代码
在 `core/crates/swirl-dns/src/wire.rs`，Qt 只转换已有设置。该历史阶段没有验证真实公网 DNS、
私有节点 DNS、DoH/DoT、EDNS 或 DNSSEC；对应提交跨平台结果查看 Actions。

`72d5bd5` 本机 Windows GNU/Qt 6.10.3：39 项 Rust、23 项独立协议（含 Qt SS/VLESS 对端）、
23 项采集/离线测试，以及 Qt Rust CTest 通过。fmt/check/clippy 通过。独立 SDK PATH 的预览启动、
ZIP CRC、包内 DLL 哈希及私有内容扫描通过。GNU 链接器仍有 `.drectve` 警告，未隐藏。
这些本机结果不替代对应提交的 GitHub CI；查看 [该提交 Actions](https://github.com/SOLHK/Swirl/actions?query=branch%3Atest)。
规则阶段 `7c7b884` 的旧版节点 UI 164 项通过；该修复已包含在当前源码。
更早的本机记录为缓存 14 份导出、12 个不同文档离线解析通过；该历史统计不能证明现有 GitHub 归档已取得全部 16 项正文，也不包含本轮私有节点联网验收。

此前 #25/#30 的三平台、Windows Qt 和严格公网门禁是历史证据。既有 Qt 组转换、
有界 TCP 多地址和失败阶段均继承；第二轮先完成限时采集，再补诊断及真实导入兼容缺口。
最新验收以阶段记录中的源码和运行身份为准。
后续按以下边界继续：

1. 三个固定旧SS样本在托管Linux已完成独立DNS/TCP对照，均停在TCP超时。下一步先核实并复用Windows现有Git/Python/cryptography；可用后以同一密文/节点索引做有界来源网络对照，复用原生二进制，不重装、不刷新订阅；只有TCP恢复才继续SS混淆/AEAD/严格HTTPS。仍不可由三个样本推断整份订阅失效。
2. 完整订阅到 Swirl IR/Qt 的组、DNS、路由字段继续逐项转换；当前 Qt 组映射已实现的子集不重写。缺省哈希负载均衡、自动组嵌套和旧 QML 无法编辑的字段仍需明确处理，不能静默丢失。
3. DNS 主机缓存、NXDOMAIN/NODATA/SOA 与已解析地址的 TCP 回退已实现；RFC 9520 失败缓存、渐进 DNS、bootstrap/分流及智能 MRS/进程规则仍待推进。保持规则固定 IP，不重写既有加密 DNS/报文/TTL。
4. gRPC/XHTTP、REALITY/Vision、VMess/SS2022、QUIC 等缺少协议与传输，分别提供互操作证据。WS 基础已实现，本轮只覆盖明确的有限组合。
5. TUN、LAN、网关、平台权限/系统代理接管与异常恢复；不擅自改变用户当前网络。
6. 私有节点联网验收、长期/弱网/性能验证，最后才移除旧内核依赖；现有缓存测试授权继续有效。本轮已取得16/16正文，今后再次刷新仍须新的下载窗口授权。

不要重写已完成模块或删掉兼容构建来制造“全自研完成”。所有阶段仍需保留 UI 与用户数据。
