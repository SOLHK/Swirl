# 第二轮订阅采集、DNS/TCP 对照与 URI 兼容阶段

本阶段从开发分支 `work/core-completion-20261017` 的
`13ea97af5c94198ecba4ed79b16cfc7b1b676f27` 接续。此前完整通过三平台测试的源码为
`99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63`，两者之间仅有文档补记。
本文记录本阶段已经发生的结果；后续 CI 和私有节点结果应以对应的固定提交证据补记，
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

## 已执行的本地验证

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
三平台 CI、Windows Qt 及固定供应商样本结果需完成后补记。

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
