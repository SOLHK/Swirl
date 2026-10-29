# 第二轮订阅采集、DNS/TCP 对照与 URI 兼容阶段

本阶段从开发分支 `work/core-completion-20261017` 的
`13ea97af5c94198ecba4ed79b16cfc7b1b676f27` 接续。此前完整通过三平台测试的源码为
`99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63`，两者之间仅有文档补记。
本阶段实现提交为 `44488e7a88c66125164e85720278be052f4aa74b`；
两次 TCP 拒绝测试夹具修正依次为 `63df5807499fddad6936d918f8807e550ca3e528` 和
`056fd56387e15d65259eff5f612b3ad7a1ce7009`，均仅修改测试文件。
不得把工作流启动、订阅下载或 TCP 连接成功代替协议及 HTTPS 验证。

## 第二轮限时采集

消息时间为 2026-10-18 09:54:09 +08:00，绝对 UTC 截止为
**2026-10-18T02:04:09Z**。该截止传入现有 Windows 自托管采集器；复用已有 runner、
Secrets 和密钥，没有注册新 runner 或修改用户网络配置。截止后不再刷新供应商 URL。

| 原始索引 | 基准请求 | 正常请求头对照 | 正文类型核验 | 本轮最终获取 |
|---|---|---|---|---|
| #1–#8、#13–#16 | 403，重定向 0 | 200，重定向 0；12 份有效正文 | 已逐份加密校验 | 新增 12 |
| #11、#12 | 403，重定向 0 | 200，重定向 0；因 HTML MIME 被拒绝 | 后续 200；整份内容符合严格 URI 列表或其 Base64 编码，实际 HTML 仍拒绝 | 新增 2 |
| #9、#10 | 200，重定向 0；2 份有效正文 | 不重复请求 | 已逐份加密校验 | 刷新 2 |

最终下载 **16/16，新增入口 14、原有入口刷新 2、仅旧缓存保留 0、最终请求失败 0**。
完整尝试记录为 32 次：16 次最终有效获取，14 次 HTTP 403，2 次 HTTP 200 的正文类型拒绝。
这些早先失败不能从证据中删除，也不能被当成最后仍有 16 条失败。

基准 User-Agent 维持 `ClashMeta/1.0`。成功对照增加正常的 `Accept: */*` 与
`Accept-Encoding: identity`，没有改变或猜测凭据、伪造付费权限或绕过鉴权。
由于时间和服务端状态没有独立控制，只能证明该正常请求配置随后获得成功，不能确定是哪一个
请求头单独导致 403 恢复。所有记录到的 403 均发生在重定向前。

匿名入口检查发现四个路径组：#1–#8/#13–#16 共用一类、#9/#10 为同主机的另两条路径、
#11/#12 位于第二主机同一路径。未发现重复链接、HTML 转义分隔符、无效百分号、片段或空白。
不记录真实域名、路径、查询参数值或订阅标识。

### 已验证的独立密文

每次获取有效正文后，先 Fernet 加密、解密并核验正文 SHA-256，再推送私有 GitHub，
并通过返回的提交 SHA 读取远端密文验证。后续请求不能覆盖前面成功的正文。

| 私有路径 | 最后持久化提交 | 范围 |
|---|---|---|
| `secure/subscriptions-window-20261018.enc` | `e14a69454bf68e8dda4afa998c8eebbc28b59994` | #9、#10 |
| `secure/subscriptions-window-20261018-diagnostics.enc` | `0ed638e47582618bbc6ecac59134b32018b6fce2` | 12 个先前缺失入口 |
| `secure/subscriptions-window-20261018-content.enc` | `cea2a1eba57266ed7e2d4639da1817e119279af8` | #11、#12 |

#11 最后请求于 02:03:50.4917529Z 完成、#12 于 02:03:54.9483463Z 完成；
最后远端检查点于 **02:03:59.026Z** 确认，早于截止。
三次真实采集运行：[基准](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39088274841)、
[请求头对照](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39088411373)、
[正文类型核验](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39088694724)。

离线合并前旧主归档 SHA-256 为
`95be7a1a2e8c15a88afc9d3e348c6dba4f8101c861268794707b239fa97dd96b`；
不可变上轮窗口 SHA-256 为
`62ea6ec5b30fadb234b507573ace503ed0f6745a55b1d3a4f53e8099fc6250ce`。
本轮独立密文、旧窗口和 Git 历史均保留。离线合并必须绑定这些来源，不能用成功下载计数代替
解密、完整正文哈希或原生解析检查。

首次离线合并运行
[39089887154](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39089887154)
的 26 项工具回归与 Release inspector 构建通过，但真实合并返回 `MergeParseRejected`。
原子替换没有发生，旧主归档不变。已追加逐窗口的脱敏原生解析报告来确定实际失败入口；
此时不能将正式主归档合并记作通过。后续处理继续使用已取得的密文。

追加解析运行 [39090162334](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39090162334)
证实 14 份 Clash YAML 及 #11 Base64 共 15 份解析通过；#12 返回 `ConflictingUriParameter`。
独立的 [缓存 URI 形状诊断](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39090764240)
不请求任何网络入口，其私有报告提交 `3113aee8a1999422b9f1695a82e81d536b2a85c7` 证实：
#12 的 90 个 Trojan URI 都依次含 `peer` 和 `sni`，URL 解码后的值全部相同；
没有原始同名重复、未知键、非法百分号、URI authority/凭据冲突或 plugin 冲突。
这是等值别名被过度拒绝的解析器缺口，不能通过挑选某个值或取消 TLS 安全检查修复。

### 最终离线合并与逐入口解析

修复后，[正式离线合并运行 39091680104](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39091680104)
实际成功，固定原生源码 `44488e7a88c66125164e85720278be052f4aa74b`；
新主归档与报告推送到私有提交
[`0f84c4cb676d0ce868e5a873eda28de8cc0fe570`](https://github.com/SOLHK/Swirl-Private-Tests/commit/0f84c4cb676d0ce868e5a873eda28de8cc0fe570)。
`decrypt_verified`、`body_hashes_verified`、`window_archives_unchanged` 均为 true。
最终解密失败 0、原生解析失败 0、归档缺失 0；早先 #12 的解析失败及两次正文类型拒绝仍在历史报告中。

主归档 `secure/subscriptions.enc` 的最终 SHA-256 为
`25516c4a63cd2b22bbbbe2cd2343fd9c67c03dea2c503c3290fb0b6812bb5a8c`。
三份本轮窗口密文的 SHA-256 依次为：

- 基准窗口：`44ad4abe8d98f8b2cd8c2cc91a300d277789e49f843b6f9bb34ca5adad211d7b`
- 请求头对照：`a322675c8619f969d7acbc2fecf2910e313a269366e1564333084bd80431bfab`
- 正文类型核验：`b2ac62bf7f34ccaa77fde4e447c83af69589eb38b2493b387323038aee040d9e`

| 索引 | 最终 HTTP | 实际正文格式 | 节点记录 | 本轮归档分类 |
|---|---|---|---|---|
| #1 | 200 | Clash YAML | 90 SS | 新增 |
| #2 | 200 | Clash YAML | 90 Trojan | 新增 |
| #3 | 200 | Clash YAML | 90 SS | 新增 |
| #4 | 200 | Clash YAML | 90 Trojan | 新增 |
| #5 | 200 | Clash YAML | 90 SS | 新增 |
| #6 | 200 | Clash YAML | 90 Trojan | 新增 |
| #7 | 200 | Clash YAML | 90 SS | 新增 |
| #8 | 200 | Clash YAML | 90 Trojan | 新增 |
| #9 | 200 | Clash YAML | 90 SS | 刷新 |
| #10 | 200 | Clash YAML | 90 Trojan | 刷新 |
| #11 | 200 | Base64 URI 列表 | 90 SS | 新增 |
| #12 | 200 | Base64 URI 列表 | 90 Trojan | 新增 |
| #13 | 200 | Clash YAML | 90 SS | 新增 |
| #14 | 200 | Clash YAML | 90 Trojan | 新增 |
| #15 | 200 | Clash YAML | 90 SS | 新增 |
| #16 | 200 | Clash YAML | 90 Trojan | 新增 |

16 个入口不等于 16 份互不重复的节点集；正文 SHA-256 去重后为 7 份字节内容，1440 是
重复格式/入口中的节点记录数，不是独立节点数。8 份 SS 正文均声明 aes-128-gcm 与 HTTP obfs，
各有 90 个待联网核验的 TCP 候选。8 份 Trojan 正文各 90 个记录均要求关闭证书验证，
以 `CertificateVerificationDisabledUnsupported` 阻止执行；没有为增加成功数修改原始安全语义。
全部 16 份的 `complete_configuration_execution_supported` 仍为 false：完整客户端配置的
组、DNS、路由到产品的执行链尚未普遍接通。该事实与正文解析全部通过分别报告。

[最终私有合并报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/0f84c4cb676d0ce868e5a873eda28de8cc0fe570/reports/subscription-window-20261018.json)
保存每个入口全部 HTTP 尝试、正文哈希、格式和能力分类。
后续独立的 [16 份缓存复验](https://github.com/SOLHK/Swirl-Private-Tests/blob/cca8b53e0829ffb49c0a2d14a5aaecdd7a87d30d/reports/native-corpus-20261018.json)
也全部解析通过，没有启动供应商订阅请求或节点请求。

私有最终交接提交为
[`ee99c85064ca2688a35e30dc714ae56da68fad07`](https://github.com/SOLHK/Swirl-Private-Tests/commit/ee99c85064ca2688a35e30dc714ae56da68fad07)，
仅更新 README，已按该提交读回并核对完整内容及远端 main。归档和诊断报告仍分别由
`0f84c4c`、`cca8b53` 的实际运行产生；这次交接没有改变归档、Secrets 或工作流，也未触发新的供应商请求。

## 同一 Rust 拨号器的可执行诊断

新增 `swirl-diagnose` stdin JSON 程序，直接观察产品正在使用的 `dial_addresses` 调度器，
没有另写一个不同的 Rust 拨号算法。产品原有连接超时、地址去重/交错、250ms 调度间隔、
最多两个待完成 TCP 与 2s 槽位轮换保持原值。观察器不保存地址或系统错误字符串。

报告只包含：DNS/TCP/总耗时、IPv4/IPv6 匿名数量、已尝试/未尝试数量、峰值并发、
每次尝试的局部编号和固定 `success/refused/timeout/unreachable/other/cancelled` 结果。
目标仅由 stdin 输入，不出现在进程参数或 stdout/stderr。成功 TCP 立即关闭，不发送协议数据。

`tools/Diagnose-NativeConnectivity.py` 独立使用系统 `getaddrinfo` 与非阻塞 TCP，
由父进程串行启动 Python 和 Rust 子进程。每个固定样本共享 **10 秒总预算**，
两方 DNS 各最多 **1500ms**，总计不超过 **3 秒**；两个后端不会重叠拨号。
每方最多两个待完成 TCP，父进程限制子进程整个寿命，超时后关闭并回收。
子进程报告须通过固定错误词表、计数、时间、退出状态的一致性验证。

诊断数据源固定为上轮窗口的 #9 节点 1、2、3，不能从新合并的 16 份正文重新抽取前三个节点。
此前三项原生错误均为 `UpstreamTcpTimeout / tcp_connect`，没有证明 SS 认证或混淆失败。
仅当本轮同一旧样本 Rust TCP 成功后，才有资格另行进行 SS HTTP obfs、AEAD 和严格 HTTPS
验证；其协议阶段预算及结果与上述十秒 DNS/TCP 诊断分开报告。

### 三个固定旧 SS 样本的实际结果

[私有原生验证 39091919549](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39091919549)
在 GitHub 托管 Linux 执行，源码为 `44488e7a88c66125164e85720278be052f4aa74b`。
41 项私有脱敏/归档/诊断工具测试及 Release 构建通过；真实 TCP 阶段失败，工作流如实为 failure。
诊断失败后的报告持久化步骤成功，已核对私有远端提交
[`cca8b53e0829ffb49c0a2d14a5aaecdd7a87d30d`](https://github.com/SOLHK/Swirl-Private-Tests/commit/cca8b53e0829ffb49c0a2d14a5aaecdd7a87d30d)。

| 固定样本 | 引擎 | DNS 毫秒 | TCP 毫秒 | IPv4 / IPv6 | 尝试 / 剩余 | 最大待完成 | 结果 |
|---|---|---:|---:|---|---|---:|---|
| #9 节点 1 | Python | 384 | 4366 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |
| #9 节点 1 | Rust | 537 | 4213 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |
| #9 节点 2 | Python | 537 | 4214 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |
| #9 节点 2 | Rust | 4 | 4747 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |
| #9 节点 3 | Python | 347 | 4403 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |
| #9 节点 3 | Rust | 544 | 4207 | 4 / 0 | 4 / 0 | 2 | 4 次超时 |

三个样本父进程实测总耗时分别 **9547、9547、9545ms**；两引擎 DNS 实测合计分别
921、541、891ms，均满足每样本 10 秒与 DNS 3 秒上限。各引擎原始总耗时为 4751–4752ms，
保留实际调度耗时，没有截断成预算值；父进程将退出/回收纳入总预算，本次实测均低于 10 秒。
每个结果均为 `UpstreamTcpTimeout / tcp_connect`，没有观察到拒绝或网络不可达错误。
无 IPv6 地址被返回，不能据此宣称验证过供应商 IPv6 连通性。

独立 Python 和产品 Rust 对同一缓存端点得到一致的失败阶段，说明当前证据指向 TCP 建连前置条件；
它没有确定服务端、路由、来源网络或防火墙中的具体根因，更没有证明 SS 密码、AEAD 或混淆错误。
TCP 成功 0/3，进入 SS HTTP obfs/AEAD/严格 HTTPS 0/3；协议检查按资格门禁未启动。
没有重试供应商订阅 URL，也没有修改产品超时。上轮 3 个样本身份由不可变窗口密文和 #9
正文哈希绑定；新主归档中的节点没有替换这三个测试对象。

[完整脱敏结果](https://github.com/SOLHK/Swirl-Private-Tests/blob/cca8b53e0829ffb49c0a2d14a5aaecdd7a87d30d/reports/cached-tcp-20261018.json)
包含逐次编号/地址族/耗时/结果、预算合规、源码/二进制/Python 工具哈希。
`63df580` 和 `056fd563` 只修正测试夹具；其 Rust、独立诊断工具与该私有实测源码逐字相同。
托管 Linux 的失败不能外推为用户 Windows 当前网络失败；该机器本轮已证实执行的是订阅采集。

## 实际订阅语义修复

`swirl-subscription/src/inspect.rs` 修复以下真实缺口：

1. 使用 `url::Host` 取 IPv6 地址本体，避免把 authority 的方括号误传给 typed IR 的主机校验。
   SS/Trojan/VLESS 及共享 URI 入口保留原始输入，外层 Base64 同样适用。
2. Surge/Loon INI 的命名及位置参数不能互相覆盖；密码或加密方式发生别名冲突时，
   两种声明顺序都返回 `DuplicateIniParameter`。保留原文，不产生候选或 DIRECT。
3. legacy `ss://BASE64(method:password@authority)` 用最后一个 `@` 分出 authority，
   用第一个冒号分出 method/password；密码中的 `/ @ # %40 %GG` 按字面保留。
   legacy 密码不能再被 URL 分隔符或百分号解码改写。
4. SIP002 百分号编码严格检查，支持转义的 Base64 padding；明文 method/password 分开解码，
   不重新拼接拆分，防止 method 中的编码冒号改变密码语义。
5. 针对已取得的 #12 正文，只允许 `peer/sni`、`type/network`、
   `allowInsecure/skip-cert-verify` 三组不同拼写在解码后的 typed 值相同时合并。
   原始 URI 保留两种拼写和顺序；不同值、同名重复、凭据覆盖和插件冲突仍然拒绝。
6. 已识别的 URI `udp` 严格接受 `0/1/false/true`，保留声明与实际能力的区别，
   没有为 Trojan 增加 UDP 转发；`allowInsecure=true` 仍不能生成 TCP 执行候选。

未知字段仍保留并明确阻止尚未实现的执行语义。本阶段没有宣称所有订阅的完整策略组/DNS/路由
都已转换为可运行产品配置，也没有新增 VMess、SS2022、REALITY、Vision、gRPC、XHTTP、
Hysteria2、TUIC 或 TUN 的假实现。Qt/C++/QML 文件和既有用户设置没有修改。

### 具体修改的源码与工具

| 路径（仓库根目录相对路径） | 改动及可执行结果 |
|---|---|
| `core/crates/swirl-protocol/src/dial.rs`、`diagnostics.rs`、`lib.rs` | 产品拨号调度器可选观察器、固定错误分类、匿名计数/时间报告及回归；原有连接策略不变 |
| `core/crates/swirl-api/src/bin/swirl-diagnose.rs` | 可构建运行的 stdin 诊断程序，输入长度/字段/重复键/时间预算校验，成功连接无负载关闭 |
| `core/crates/swirl-subscription/src/inspect.rs` | IPv6、INI冲突、legacy/SIP002密码语义、等值URI别名及严格UDP声明修复；43项crate测试 |
| `core/crates/swirl-api/Cargo.toml`、`core/crates/swirl-protocol/Cargo.toml`、`core/Cargo.lock` | 增加既有workspace依赖关联；没有更换外部依赖版本 |
| `tools/Diagnose-NativeConnectivity.py`、`tools/tests/test_connectivity_diagnostics.py` | 独立系统DNS/TCP后端、共享预算的子进程对照、脱敏验证和真实/确定性测试 |
| `tools/tests/test_subscription_import.py` | 原始配置经Rust IR到独立SS/Trojan对端的凭据、握手、转发和关闭验证 |
| `tools/ApplyCoreDevelopment.py`、`tools/tests/test_core_development.py`、`.github/workflows/rust-core.yml` | 三平台门禁、三个可执行文件存在检查、Windows失败退出传播、App更新器幂等和漂移拒绝 |

除上述源码/工具外，仅修改交接、README和本阶段验收/证据文件。
本阶段 **Qt/C++/QML 改动文件数为 0**，没有变更液态玻璃、窗口/导航、动画、节点展示或用户数据。
原生模式没有增加 Mihomo 调用，兼容构建继续保留。

## 实现提交 44488e7 的本地验证

| 检查 | 已观察结果 |
|---|---|
| Rust fmt、workspace check | 通过，`--locked --offline` |
| workspace Clippy | 通过，所有 target，`-D warnings` |
| workspace tests | 最终 **125 通过，0 失败，0 忽略**；本轮新增 24 项 |
| Release workspace | 原生库及 `swirl-api`、`swirl-inspect`、`swirl-diagnose` 构建通过 |
| 新订阅导入 Python 对端 | 最终 **7/7 通过，0 跳过**；11 个 SS AEAD 会话及4个严格TLS Trojan会话完成认证、双向转发和关闭；未知CA与错误服务器名称两项按预期拒绝 |

11 个 SS 会话中，IPv6 URI/Base64 为 3 个，Surge/Loon 为 2 个，保留字符密码经
legacy/Base64/SIP002 为 6 个。Python 对端使用独立的预期密码派生密钥，可检出错误解析后
“还能拿到节点名称”却无法认证的情况。它们属于真实回环协议数据交换，不是供应商公网成功。
本地默认沙箱禁止创建套接字；上述套接字测试在已批准的测试权限下运行。
最终workspace复验曾在编译链接阶段因复用的 `swirl_core` 产物无法加载而停止，尚未运行测试。
保留失败日志，仅清理项目crate的dev/debug缓存，不改源码、不删除测试、不动Release后，
同一完整命令通过125项。CI仍需在其独立环境检查同一提交。
最终同一源码的完整本地 Python 共 **15 套、200 项：163 通过、37 明确跳过、0 失败**。
其中新 DNS/TCP 诊断 20/20、新订阅转换 7/7、工作流更新器 19/19。
37 个跳过为 4 个 Qt 对端、22 个 Windows DPAPI 采集、10 个 Windows DPAPI 管理和
1 个可选真实 CLI。早于等值别名修复的首次全量结果为198项，不能当作最终计数。
最终 Release `--workspace --lib --bins --locked --offline` 再次通过，原生库及三个程序齐全。
三平台 CI、Windows Qt 与私有节点证据的源码及范围分别记录，不能把可选跳过当作通过。

### 保留的首轮三平台失败及修正

[Rust Core #33](https://github.com/SOLHK/Swirl/actions/runs/39091610693) 固定 `44488e7`：
三平台 fmt/check/Clippy、125 项 workspace 与 Release 均通过；Linux 的全部 Python 门禁和
3 项严格公网检查通过。macOS 和 Windows 的 Python 各执行到 159 项：153 通过、4 Qt 跳过、
2 个新诊断测试失败。两项均将“绑定但未监听”的套接字当作立即拒绝连接的端点，
实际在该系统返回 timeout；这没有建立产品协议失败证据。

`63df580` 将两个夹具改为真正关闭的监听端口，先分配备用成功监听端口防止二者重用；
保留真实套接字校验，并增加确定性的 `ECONNREFUSED` 后立即选择下一地址、无等待且套接字
全部关闭的断言。原有 20 项测试全部保留，本地 20/20 通过、0 跳过；没有更改任何产品超时或调度器。
Windows #33 的其余 41 项 Python、Qt 安装/构建/CTest/四个对端补测及二进制 artifact 均未运行；
macOS 后续 7 项 importer 未运行。其失败不被后续成功覆盖。
[App #30](https://github.com/SOLHK/Swirl/actions/runs/39091610659) 在同一 `44488e7` 实际成功，
更新器幂等且未产生额外源码提交。

第一次夹具修正后的 [Rust Core #34](https://github.com/SOLHK/Swirl/actions/runs/39092269132)
固定 `63df580`：Linux 和 macOS 的全部 Rust 门禁与 166 项 Python（162 通过、4 Qt 跳过）均通过；
Linux 严格公网仍为 3/3；[App #31](https://github.com/SOLHK/Swirl/actions/runs/39092269198) 也成功。
但 Windows 仍在相同两项失败，实测分别约 505ms 和 204ms，达到各自 500ms/200ms 测试截止。
其其余 41 项 Python、artifact 和 Qt 全部未执行，工作流整体仍为 failure。
关闭监听端口的改动不能被称为已修复 Windows；该失败与 #33 一起保存在
[初始 CI 证据](evidence/RUST_CI_20261018_INITIAL.json)。
两个阶段的严格公网原始报告分别保存为
[44488e7](evidence/RUST_PUBLIC_NETWORK_20261018_INITIAL.json) 和
[63df580](evidence/RUST_PUBLIC_NETWORK_20261018_FIXTURE1.json)，不会用它们替代整个平台的验收。

核对 CI 的 CPython 3.14.8 `SelectSelector` 后确认：Windows 分支将写关注套接字同时放入
`writefds` 和 `exceptfds`，把异常就绪并入 `EVENT_WRITE`，诊断器随后读取 `SO_ERROR`。
这符合 Microsoft 对非阻塞连接失败事件的描述，没有发现遗漏的异常就绪路径。
真实回退测试的 200ms 截止短于既有 250ms stagger，依赖系统更早交付拒绝错误，不能作为
所有系统的时间保证。后续校验须独立测量 OS 拒绝通知时间，并分别保留确定性调度和真实 TCP 证明。

第二次测试修正 `056fd563` 将这两层明确分开，产品及独立诊断工具均未改动：

- 在确定性 500ms/200ms 测试中同时覆盖 POSIX `ECONNREFUSED` 和 Winsock `10061`，
  要求拒绝分类正确、无等待、立即启动下一地址、峰值一条连接且所有套接字关闭。
- 对真正关闭的回环端口，独立系统 `socket.connect` 与诊断器各用固定 3 秒测试观测预算，
  两者必须实际返回 refused；系统只返回 timeout 时仍报测试失败，不能改记通过。
  输出仅含结果和毫秒，不含端点。此项用于测量 OS 通知时间，不改变产品或供应商样本预算。
- 两地址真实回环测试用固定 1 秒观测预算，允许既有 250ms 间隔产生第二次尝试。
  第二条必须真正连接成功；第一条只允许 refused 或已取消，不能接受 timeout/other/成功。
  如果发生取消，须证明第二条在间隔之后启动且峰值并发为 2；EOF、无负载、匿名计数检查保留。

全部原有 20 项诊断测试仍保留，本地实测 20/20、0 跳过。Linux 的独立系统与诊断器均在
0ms 量级收到拒绝，真实回退为 refused→success。

## 最终三平台、Qt 与公网验收

[Rust Core #35](https://github.com/SOLHK/Swirl/actions/runs/39093009560) 于
**2026-10-18T03:28:03Z** 整体完成并成功，固定源码
**`056fd56387e15d65259eff5f612b3ad7a1ce7009`**。
[App validation #32](https://github.com/SOLHK/Swirl/actions/runs/39093009558) 同一源码也实际成功。
最终编译/测试源码树为 `251146540cf5b742da6fb69de7d780fe2a10c18c`。
[最终三平台与 App 结构化证据](evidence/RUST_CI_20261018_VERIFIED.json)
包含逐套测试计数、明确跳过、Windows Qt 构建与真实时序、原始日志哈希、已下载制品及源码一致性检查。

| 门禁 | Linux | macOS | Windows MSVC |
|---|---|---|---|
| fmt / workspace check / all-targets Clippy `-D warnings` | 全通过 | 全通过 | 全通过 |
| Cargo workspace tests | 125通过、0失败、0忽略 | 125通过、0失败、0忽略 | 125通过、0失败、0忽略 |
| Release `--workspace --lib --bins` | 通过 | 通过 | 通过 |
| 初次完整 Python | 166项：162通过、4Qt跳过 | 166项：162通过、4Qt跳过 | 200项：194通过、6明确跳过 |
| 新 DNS/TCP / importer 两套 | 20/20、7/7 | 20/20、7/7 | 20/20、7/7 |
| Qt 编译及 CTest | 本轮未运行桌面Qt | 本轮未运行桌面Qt | Qt6.10.3编译通过；CTest1/1，6.85秒 |
| 四项独立 Qt 对端补测 | 未运行 | 未运行 | VLESS、SS HTTP obfs、SOCKS4/4a、VLESS WS各1/1 |
| Python最终独立用例统计 | 162通过、4跳过、0失败 | 162通过、4跳过、0失败 | **198通过、2可选跳过、0失败** |
| 严格公网 HTTPS/DoH | 3/3通过 | 工作流限定Linux，未执行 | 工作流限定Linux，未执行 |

Windows 最后两个可选跳过为未提供的 C++ 私有 importer 与真实 Codex CLI；四项最初的 Qt
跳过随后全部实跑通过。四次补测与最初200项中的同名测试对应，不重复计为204个独立用例。
Qt构建通过CMake在 `build/rust-qt/rust-target` 独立构建Rust库并部署给 `SwirlRustCoreTests`，
验证实际Qt→Rust数据路径及该构建路径。它与前面 `core/target` 的独立Release构建分别记录，
没有未经哈希核验就宣称两处DLL字节相同，也不代表用户个人Windows的视觉验收或完整桌面发行包。

Windows观测行明确记录：独立系统连接 **2006ms** 返回 refused，诊断器 **2027ms** 返回 refused；
各自固定3秒测试预算内实际收到拒绝。双地址真实测试于 **264ms** 成功，启动时间 `[0,263]ms`、
结果 `[cancelled,success]`、并发峰值2。这解释了#33/#34的短测试截止，并验证产品原有250ms
间隔在OS尚未通知拒绝时仍可尝试第二地址。确定性即时拒绝断言、真实拒绝/连接/EOF与资源关闭
检查均保留；产品及固定供应商样本预算未增加。

### 公网报告及二进制归档

[最终公网原始JSON](evidence/RUST_PUBLIC_NETWORK_20261018_VERIFIED.json) 标记上述完整提交、
`tracked_worktree_clean=true`，原生harness SHA-256为
`d659bdb675b8e09d7b80e1c25222d60ecd3ee18ffd7753645296286d6c185f77`。

| 公共目标路径 | HTTP | 毫秒 |
|---|---:|---:|
| 系统DNS → example.com，显式原生DIRECT | 200 | 107 |
| 系统DNS → www.rust-lang.org，显式原生DIRECT | 301 | 118 |
| 原生DoH → example.com，显式原生DIRECT | 200 | 222 |

三项全部TLS1.3且证书验证、正常关闭、原生会话收敛为true；每项 `accepted=1 / active=0 / failed=0`，
双向流量为正、错误码/阶段为空。该证据验证公共DIRECT/DoH路径，供应商SS仍以私有失败报告为准。

公网artifact `12123219094` 的下载ZIP SHA-256与GitHub发布值一致：
`fc741bb6bb582587006854ea5da10cbb2a342d6b62fcdbc50a6da85425b8fba9`。
Windows [原生内核归档](https://github.com/SOLHK/Swirl/actions/runs/39093009560/artifacts/12123637108)
为5,259,771字节，ZIP CRC和SHA-256均已核验：
`2147a349e02100c0a901c34032f49db8e92d14c66f5f13544a40ef88928a7182`。
其中实际包含 `swirl_api.dll`、`swirl-api.exe`、`swirl-inspect.exe`、`swirl-diagnose.exe`，
均有有效PE文件头；没有把上传步骤成功代替归档内容检查。

App的19项更新器回归及125项Rust通过；六套额外Python对端共74项，69通过、5明确跳过
（4项Qt、1项未提供inspector环境）。更新器前后工作流SHA-256均为
`9d72dd3d6aa7b58590eeae4ca5621094110a5f5d77f2486fde0ea19376ffba7d`，没有新增自动源码提交。
App artifact `12123149508` 的ZIP SHA-256为
`8181d5ce2e40d544f98d16d25ae250c8530b20543f44998826b0ca6a5310ee1b`，
`CORE_TESTED_COMMIT` 为 `056fd563`，归档内157个源码文件的字节和可执行权限位逐一匹配该提交。
工作区记录只有工作流产生的三个证据文件，没有源码改动。

### 尚未完成的范围及接续顺序

1. 固定旧SS样本在托管Linux的TCP前置条件仍未恢复。先核实并复用用户Windows已有Git/Python/
   cryptography及原生二进制，再以同一密文/索引/有界预算做来源对照；不刷新订阅或改变系统网络。
2. 继续完整订阅→typed IR→组/DNS/路由→Qt产品配置的严格转换，继承已完成的组子集，保留未知语义。
3. 分阶段完成VMess、SS2022、REALITY、Vision、gRPC、XHTTP、Hysteria2、TUIC及QUIC互操作。
   本轮没有为这些功能新增占位实现，不能据已完成的WS/WSS推断它们已支持。
4. TUN、其余协议UDP、DNS分流/Fake-IP、进程/GEOIP/GEOSITE/MRS、LAN/系统接管、网络切换恢复及
   长期资源/性能验证仍待推进。当前兼容构建继续保留，原生模式保持明确能力拒绝。

本阶段提交及证据未修改公开 `main`，其HEAD保持
`87409c0bf9c957ef113f84c176c5a1529c27b9df`，所有远端更新均使用非强制的预期HEAD检查。
阶段结束的交接提交只补README、Markdown及JSON证据，需核对其源码、测试与工作流和上述已测试提交
完全一致后才更新远端分支。该文档提交本身不冒充新的编译测试运行。

## 原始设计依据

以下只用于理解边界及互操作，Swirl 改动独立实现，未复制第三方代理内核源码：

- [RFC 8305 地址排序与连接调度](https://www.rfc-editor.org/rfc/rfc8305)
- [hyper-util 成熟连接器](https://github.com/hyperium/hyper-util/blob/master/src/client/legacy/connect/http.rs)
- [Tokio 绝对截止](https://docs.rs/tokio/latest/tokio/time/fn.timeout_at.html)和
  [运行时关闭边界](https://docs.rs/tokio/latest/tokio/runtime/struct.Runtime.html#method.shutdown_timeout)
- [Shadowsocks 官方 SIP002](https://github.com/shadowsocks/shadowsocks-org/wiki/SIP002-URI-Scheme)和
  [legacy Config Format](https://github.com/shadowsocks/shadowsocks-org/blob/main/docs/doc/configs.md)
- [Outline 官方 SS 配置解析](https://github.com/OutlineFoundation/shadowsocksconfig/blob/master/src/shadowsocks_config.ts)
- [url::Host 文档](https://docs.rs/url/latest/url/enum.Host.html)、
  [Surge SS 配置](https://manual.nssurge.com/policies/shadowsocks.html)、
  [Loon 节点示例](https://github.com/Loon0x00/LoonExampleConfig/blob/master/Nodes/ExampleNodes.list)
- [CPython 3.14.8 Windows selector](https://github.com/python/cpython/blob/v3.14.8/Lib/selectors.py)、
  [Microsoft select 的非阻塞连接事件](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-select)及
  [CPython 历史 localhost 延迟报告](https://github.com/python/cpython/issues/85480)；
  历史延迟报告提供调查线索，不替代本轮 Windows 的实测耗时。
