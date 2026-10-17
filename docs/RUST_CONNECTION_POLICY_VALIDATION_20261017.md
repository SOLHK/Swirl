# Rust 多地址连接、失败阶段与 Qt 策略组验收

本阶段从 `work/core-completion-20261017@d27fcc74ed549f2219f97da1f5c56a83bace3ac1`
继续。日期使用 UTC；用户本地采集发生于 2026-10-18 凌晨。保留 C++23/Qt/QML 界面和兼容构建，
没有调用完整第三方代理内核，也没有修改 GitHub App 或 Secrets。当前实现不等于全量迁移完成。

## 限时订阅结果

本轮先处理私有 `SOLHK/Swirl-Private-Tests`，然后才进行公开内核开发。采集代码使用固定绝对截止时间
`2026-10-17T18:39:54Z`，包括重定向检查；实际最后一项请求于 18:38:29 完成。
窗口结束后不再请求服务商订阅入口。后续归档解密、格式检查、合并和缓存节点验证不刷新订阅。

| 入口 | 云端实际响应 | 原有 Windows 采集器实际响应 | 本轮计数 |
|---|---|---|---|
| #1–#8 | HTTP 403 | HTTP 403 | 缺失，未取得有效正文 |
| #9 | HTTP 403 | 有效正文 212456 字节，已分批加密推送 | 原有缓存刷新，不计新增 |
| #10 | HTTP 403 | 有效正文 210026 字节，已分批加密推送 | 原有缓存刷新，不计新增 |
| #11–#16 | HTTP 403 | HTTP 403 | 缺失，未取得有效正文 |

**16 个入口中，本轮实际取得 2 份有效正文；新增入口为 0，原有缓存刷新为 2，仍缺 14。**
云端 16 项全为 403，不能将其工作流成功、测试夹具中的成功数量或保留旧归档误记为下载成功。
旧归档未因下载失败而删除。Windows 成功正文首先进入独立的
`secure/subscriptions-window-20261017.enc`，旧 `secure/subscriptions.enc` 保留，随后离线验证合并。

| 私有提交/运行 | 已核对的用途 |
|---|---|
| [`eaf3f7c`](https://github.com/SOLHK/Swirl-Private-Tests/commit/eaf3f7c9c4c6d35d0236d1730c4224b372d4959d) | 有界云采集、绝对截止、保留旧正文、逐次加密校验和持久化 |
| [云采集 39058746714](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39058746714) | 18:35:20–21 的真实 16 项 HTTP 403 |
| [`ad5c367`](https://github.com/SOLHK/Swirl-Private-Tests/commit/ad5c367b02c44daa0a40174e32085e427d451162) | 云端失败后安全保留两份旧有效正文 |
| [`f8e6add`](https://github.com/SOLHK/Swirl-Private-Tests/commit/f8e6add95de04ddb9caab0765c7b283a37f6eb00) | 复用现有 Windows 采集流程，新增截止、逐份校验和独立归档 |
| [Windows 采集 39058955884](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39058955884) | 18:38:13–29 执行实际请求；两份更新成功，其余十四份为 403 |
| [`45412c9`](https://github.com/SOLHK/Swirl-Private-Tests/commit/45412c9648e041dab3ff1fd2ac3a75d92b5a9511) | #9 于 18:38:20 单独持久化 |
| [`a476540`](https://github.com/SOLHK/Swirl-Private-Tests/commit/a476540348c1d280fd30002b10ffa70a2b244c18) | #10 于 18:38:26 单独持久化 |
| [`d92b119`](https://github.com/SOLHK/Swirl-Private-Tests/commit/d92b1196965717a8b323f01705b5779647322d31) | 18:38:34 完成窗口归档最终持久化 |

Windows 复用了原有自托管 runner 的 C 盘目录。用户在本轮明确追加“可以在C盘，速度”，
因此允许继续使用该已配置位置。云端 GitHub 保存不能表述为已写入用户 `D:\Codex`。
未把明文订阅、解密密钥或节点配置写入公开仓库、日志或 Actions Artifact。

离线合并报告、严格格式/节点计数和当前源码私有网络结果将在完成后补记；在取得证据前不宣称成功。
上一阶段确实解析了两份 Clash/Mihomo YAML，各含 90 个 SS/Trojan 条目；不能仅按服务商客户端标签推断格式。

## 选择本阶段的依据

源码审阅确认 Rust 策略运行时和 DNS 主机/SOA 负缓存已经实现，不能再次开发同一模块。
实际缺口是：TCP 对 DNS 返回地址逐个无限等待，外层统一 `UpstreamTimeout` 掩盖故障阶段；
Qt 组转换和 Controller 保存路径仍只保留有限手动组字段，不能传递已有的自动策略和前向引用。
本阶段直接修复这两个边界，新增独立服务端验证；没有添加未实现的协议空壳。

实施前参考的一手设计资料：

- [RFC 8305，第 4–5 节](https://www.rfc-editor.org/rfc/rfc8305)：已解析地址交错、尝试间隔和获胜后取消。
- [Tokio TcpStream](https://docs.rs/tokio/latest/tokio/net/struct.TcpStream.html)：异步连接接口及生命周期。
- [sing-box direct outbound](https://github.com/SagerNet/sing-box/blob/testing/protocol/direct/outbound.go)：将解析地址和回退策略交给 dialer 的边界。
- [Mihomo 配置](https://github.com/MetaCubeX/mihomo/blob/Meta/docs/config.yaml)和
  [load-balance 语义](https://wiki.metacubex.one/en/config/proxy-groups/load-balance/)：默认哈希语义不能静默替换为轮询。
- [sing-box URL test](https://github.com/SagerNet/sing-box/blob/testing/docs/configuration/outbound/urltest.md)与
  [selector](https://sing-box.sagernet.org/configuration/outbound/selector/)：配置和选择职责。

独立实现 Swirl 代码，没有复制上述项目的实现，没有新增 Cargo 依赖或修改锁文件。

## Rust 连接行为

DNS、全部 TCP 尝试、TLS、WebSocket Upgrade 和协议握手消耗同一个绝对期限，
使用原有 `handshake_timeout_ms`。不会为每个步骤重新获得完整超时预算。
对同一批 DNS 结果去重，保留解析器的首选地址族和族内顺序，交替尝试 IPv4/IPv6；
最多 16 个地址、两个待完成 TCP 连接，仍在等待时以 250 ms 间隔发起下一项。
已明确失败或退休的连接立即释放名额并接续下一地址，不让已失败尝试耗尽较短的总预算。
启动连接时若还有未尝试地址，该连接最多等待 2 秒，以便后续地址获得名额；最后候选使用剩余总预算。

所有 TCP future 由当前调用持有。TCP 一旦成功，先释放其他候选，再发送 TLS、认证、协议及应用数据。
TLS/认证失败不会换地址重试，应用请求不重放。路由层固定的 IP 字面值仍是唯一目标，
不能重新解析域名并利用其他 DNS 答案绕过 CIDR 决策。

这不是 RFC 8305 全部实现：解析器仍等待 A/AAAA 的组合结果，没有渐进 DNS、历史地址偏好或 NAT64 合成。
2 秒名额释放是 Swirl 的有界资源权衡，不是 RFC 强制值。UDP、DoT/DoH bootstrap 连接和已选定的路由策略
没有被扩大为任意多地址重试。

控制 API 增加 `last_error_stage`，连接记录增加 `error` / `failure_stage`。原有静态错误码保留，
新增 `UpstreamDnsTimeout`、`UpstreamTcpTimeout`、`UpstreamTlsTimeout`、`UpstreamProtocolTimeout`、
`WebSocketUpgradeTimeout`、`UpstreamAddressLimit` 和 SS 混淆写入分类。
阶段限固定集合：`dns`、`tcp_connect`、`tls_handshake`、`websocket_upgrade`、`protocol_handshake`、
`http_obfs`、`initial_write`、`stream_io`、`routing`、`inbound`、`unknown`；无错误为空字符串。
公开/私有 probe 只输出白名单阶段，未知对端文本不能借此进入报告。

`http_obfs` 目前准确表示 SS 初始混淆帧写入。转发开始后发生的延迟混淆响应或 SS 解密错误仍为 `StreamIo`；
没有新增首个应用响应的固定空闲超时，也不能把初始写入成功当成服务端已完成认证。

## Qt 到 Rust 策略转换

两遍解析组名和成员，支持前向引用、手动组嵌套，以及手动组指向自动组。
`url-test`、`fallback` 和明确指定 `strategy: round-robin` 的 `load-balance` 转为既有 Rust IR。
没有 strategy、`consistent-hashing`、`sticky-sessions` 均拒绝，避免改变导入配置的选择语义。

探测 URL、间隔、超时、2xx 精确响应码和 url-test tolerance 严格映射；拒绝不支持的远程 providers、
不安全证书选项、未知语义和无效值。沿用 Rust 上限：128 组、手动深度 16、32 自动组、
每自动组 64 成员、累计 512 个探测成员；自动组仍只接受具体非 REJECT 节点。
全部分支都检测缺失、重复、循环和名称冲突，不能通过未选中的分支藏入循环。

Rust 构建的 Controller 保留完整组 map、默认成员及探测字段，验证后才替换持久化配置；
拒绝删除其他组引用的组。显式编辑无效时旧配置不变。
现有 QML 成员选择器仍只列具体节点和 DIRECT/REJECT；嵌套组使用已有完整配置入口。
现有编辑器没有 strategy 控件，因此未明确指定轮询的负载均衡配置仍不能执行。本轮没有增改 QML 页面。

## 实际验证与待补证据

| 门禁 | 本地已执行结果 |
|---|---|
| Rust fmt / check / clippy | 全部通过，Clippy 使用 `-D warnings`，依赖已缓存并按 Cargo.lock 构建 |
| `cargo test --workspace --locked --offline` | 101 通过、0 失败、0 忽略；新增 11 项 |
| Release `swirl-api` / `swirl-inspect` 构建 | 通过，Rust 1.99.1，Linux x86_64 |
| 新增独立 Python 连接阶段 | 8/8 通过，9.797 秒，实际使用 DNS/TCP/TLS/SS 回环服务端 |
| 全量 Python 回归 | 13 套件共 169 项：132 通过、37 明确跳过、0 失败；各套件退出码均为 0 |
| Qt 新增组数据路径/保存回归 | 本地无 Qt SDK；当前 Windows CI 尚未执行，不能标为通过 |
| 本阶段公网及私有节点 | 尚待固定本轮源码执行；历史通过不代替本阶段证据 |

独立连接测试验证：首地址 TCP 拒绝后的 DIRECT/SS HTTP 混淆实际转发；主机缓存跨大小写复用；
代理侧 DNS 不擅自解析远端目标；CIDR 固定 IP 失败不改走其他答案；DNS/TCP/TLS/协议超时阶段；
不可信证书不能选择另一地址的可信服务端；所有失败不产生目标应用流量。
确定性的 Rust 调度测试另覆盖首地址族卡住、前两地址同时卡住、候选取消、总期限和单地址完整预算。
复审发现合法 100ms 预算在首地址立即拒绝后仍等待 250ms，会错过可用第二地址；
修正为已完成失败后立即接续，新增确定性短预算回归并重跑四个 Rust 门禁。
这与 [Go 官方并行 dial 测试](https://go.dev/src/net/dial_test.go)的快速失败语义一致；
不称为严格完整实现 RFC 8305 的所有最小间隔规则。

Qt 测试使用已有独立 SOCKS5 A/B 出口和 HTTP 源站，要求实际经指定出口转发，
验证轮询、前向手动嵌套、错误配置保持旧会话配置，以及持久化 round-trip。
CI 在 Linux/macOS/Windows 原有协议套件后增加 `test_connection_stages.py`；
App 更新器的 15 项回归通过，更新器为幂等且不改变现有 App/Secrets 或权限。

本地 Python 3.12.14、cryptography 50.0.2、PyYAML 6.0.3。套件数量依次为
rust_core 24、shadowsocks 9、dns_tls 11、dns_https 9、socks4 10、websocket_transport 11、
core_development 15、policy_groups 13、dns_negative 18、native_probe 7、connection_stages 8、
subscription_capture 23、codex_management 11。
37 个跳过为四项 Windows Qt 对端、22 项 Windows DPAPI 采集、10 项 Windows DPAPI 管理和一项可选真实 CLI。
本地运行日志位于忽略的 `core/target/validation/`；需要当前 CI 补齐 Windows 项，不将跳过计为通过。

### 已遇到的失败

- 初次 Rust loopback 测试在创建 socket 时被本执行环境以 `EPERM` 拒绝。
  使用本轮已获自动批准的临时回环网络权限后完整通过，没有跳过网络测试或修改系统设置。
- 初次 Clippy 指出新增错误记录代码的 `collapsible_if`；改为 Rust 2024 let-chain 后通过，没有 lint 豁免。
- 私有 [Windows fixture 39058955854](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39058955854)
  因旧夹具未提供新必需的截止时间而失败。修正必须补明确夹具期限，不能放松真实采集期限；后续结果另记。
- 实现已推送为 [`11eafea6bc58cef32ce2adc8e2fdd0f681175a80`](https://github.com/SOLHK/Swirl/commit/11eafea6bc58cef32ce2adc8e2fdd0f681175a80)，
  本地已测 Git tree 与远端均为 `0488342ec700b15f522bb355af2a15f45bcf3eae`。
  [Automation 39060793624](https://github.com/SOLHK/Swirl/actions/runs/39060793624) 成功；
  [首轮三平台 39060793620](https://github.com/SOLHK/Swirl/actions/runs/39060793620) 中各平台 101 Rust 测试通过，
  Linux 协议及严格公网门禁通过，macOS/Windows 在新增 Python 夹具失败，因此整体不能记为通过。
  macOS 六项因绑定 `127.0.0.2` 得到 `EADDRNOTAVAIL`；macOS 一项和 Windows 两项因为绑定但不监听的 TCP
  端口未立即拒绝，实际是 `UpstreamTcpTimeout`，与夹具期待的 `UpstreamConnectFailed` 不同。
  修正仅涉及独立服务端：使用已配置的 IPv4 `127.0.0.1` / IPv6 `::1`，明确 IPv6-only；
  拒绝端口先关闭 TCP reservation，再用真实 OS 连接验证 `ConnectionRefusedError`，关键用例结束后再次验证。
  两个等待明确 OS 拒绝的用例使用 3 秒夹具预算；原生产品超时规则和 TLS/协议短期限测试不改。
  仍精确断言拒绝错误码、零应用流量、禁止 TLS 后重新选择地址及 CIDR IP 固定，没有接受“任一错误即可通过”。
  关闭端口不能永久占有该 TCP 端口，前后检查缩小并检测占用竞争，不声称消灭所有 TOCTOU。

## 后续边界

完整订阅格式到产品配置的组、路由和 DNS 转换仍需按真实字段逐项接入，不能把节点解析成功当完整配置执行。
私有 SS 超时要先看本轮分阶段结果再定位；三份抽样不能代表整份订阅失效。
Trojan 声明关闭证书校验的配置仍拒绝，不能由此认定实际服务器证书无效，更不能为了联网测试关闭校验。
VMess、SS2022、REALITY/Vision、gRPC/XHTTP、Hysteria2/TUIC/QUIC、Windows TUN 和完整系统接管等仍未完成。
长期稳定性、性能、弱网、用户本机视觉及全应用接管尚无本阶段验收，兼容内核依赖继续保留。
