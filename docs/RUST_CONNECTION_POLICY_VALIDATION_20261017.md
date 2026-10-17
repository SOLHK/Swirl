# Rust 多地址连接、失败阶段与 Qt 策略组验收

本阶段从 `work/core-completion-20261017@d27fcc74ed549f2219f97da1f5c56a83bace3ac1`
继续。日期和采集时间统一使用 UTC。保留 C++23/Qt/QML 界面和兼容构建，
没有调用完整第三方代理内核，也没有修改 GitHub App 或 Secrets。当前实现不等于全量迁移完成。

**本阶段已经完成代码、三平台 Rust/协议 CI、Windows Qt 和严格公网验收。**
实际被测源码为 [`99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63`](https://github.com/SOLHK/Swirl/commit/99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63)，
[Swirl Rust Core #32](https://github.com/SOLHK/Swirl/actions/runs/39061540612) 于 19:25:24 UTC 整体成功。
私有有效正文已经解密、校验并安全合并；三个 SS 抽样均在 TCP 建连阶段超时，**私有联网通过为 0**。

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
| [`78a7808`](https://github.com/SOLHK/Swirl-Private-Tests/commit/78a7808a383d8a3cea02d466822864c23c6ca5a5) | 恢复仅公共夹具的 push 自检；手动 capture 必须提供真实绝对期限 |
| [`870c7b0`](https://github.com/SOLHK/Swirl-Private-Tests/commit/870c7b0c51048bed700da70bfbb16a803b7adf23) | 已有窗口的离线合并、完整性检查及固定公开源码的原生诊断 |
| [`ff9b187`](https://github.com/SOLHK/Swirl-Private-Tests/commit/ff9b187065e633db94fbd67773ae4062a1b81d59) | 19:18:03 保存校验后的正式密文及完整窗口统计，早于节点联网 |
| [`aa690e4`](https://github.com/SOLHK/Swirl-Private-Tests/commit/aa690e40c9d8d12b0639fd6ac76c56e6b21ada8d) | 19:18:35 持久保存白名单原生联网失败报告 |
| [`5820fda`](https://github.com/SOLHK/Swirl-Private-Tests/commit/5820fda2242c9a5d53ed1e35fa8589fe5abc14fa) | 私有 README 记录实际窗口、密文/正文哈希和下一次接手约束 |

Windows 复用了原有自托管 runner 的 C 盘目录。用户在本轮明确追加“可以在C盘，速度”，
因此允许继续使用该已配置位置。云端 GitHub 保存不能表述为已写入用户 `D:\Codex`。
未把明文订阅、解密密钥或节点配置写入公开仓库、日志或 Actions Artifact。

### 真实解密、合并及格式核验

[离线合并报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/ff9b187065e633db94fbd67773ae4062a1b81d59/reports/subscription-window-20261017.json)
已由固定源码 `99ad9b3` 的 inspector 对旧、新正文分别验证，记录来源身份、索引、状态、大小、SHA-256 及原生能力。
复用现有 Fernet Secret，在内存解密和解析；临时密文回读后原子替换，替换后失败可恢复原密文。
`decrypt_verified=true`、`body_hashes_verified=true`、`window_archive_unchanged=true`。
合并后的 `secure/subscriptions.enc` SHA-256 为
`95be7a1a2e8c15a88afc9d3e348c6dba4f8101c861268794707b239fa97dd96b`。
独立窗口密文仍在，旧正文仍保留于私有 Git 历史，密钥未改变。`retained=0` 表示两个旧入口均被有效刷新，
不表示丢弃历史；本次仍为 `new=0 / refreshed=2 / failed=14 / archived=2`。

| 入口 | 当前正文原生识别 | 可执行条件 |
|---|---|---|
| #9 | Clash YAML，90 个 SS，aes-128-gcm / TCP / HTTP obfs | 90 个 TCP 候选；该混淆组合不支持当前原生 UDP |
| #10 | Clash YAML，90 个 Trojan，TCP / TLS | 0 个候选；90 项均 `CertificateVerificationDisabledUnsupported` |

共 180 个节点条目，不代表 180 台不同服务器。两个完整配置的
`complete_configuration_execution_supported` 仍为 false，不能将节点解析当成完整组、路由和 DNS 产品导入完成。
Windows 最后一个成功检查点只记录了此前八个失败入口，不能用它漏报后六个 403；
完整 14 项失败明确取自已核对的完整采集日志，报告标记 `checkpoint_failure_list_incomplete=true`。

### 本轮缓存节点联网：故障定位到 TCP

[私有运行 39061700091](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39061700091)
固定源码 `99ad9b3`，没有请求订阅入口，先保存合并密文再测试节点。其
[原生报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/aa690e40c9d8d12b0639fd6ac76c56e6b21ada8d/reports/native-core.json)
实际记录如下。

| 样本 | 结果 | 整体耗时 | 代理应用流量 |
|---|---|---:|---|
| #9 节点 1 | `UpstreamTcpTimeout` / `tcp_connect` | 10007 ms | 上传 0、下载 0 |
| #9 节点 2 | `UpstreamTcpTimeout` / `tcp_connect` | 10005 ms | 上传 0、下载 0 |
| #9 节点 3 | `UpstreamTcpTimeout` / `tcp_connect` | 10005 ms | 上传 0、下载 0 |

每项内核身份已核验、会话已收敛，`accepted=1 / active=0 / failed=1`。
`accepted` 是入站计数，报告 `native_connect_accepted=false`，不能当上游 TCP 成功。
该阶段表示已得到可拨号地址，TCP 尚未在统一期限内成功；地址可能来自字面值、hosts、缓存或 DNS。
报告没有 DNS 耗时和逐地址结果，整体约十秒不能当精确 TCP 单阶段时长，也不能称每个地址已尝试。
尚未进入 HTTP 混淆、SS 初始帧/认证或源站 HTTPS，不能用本次失败判定这些协议层有问题。
零代理应用流量不表示没有 DNS 或 SYN 网络包；三个标签也未证明是三个独立端点。

Trojan 因配置声明关闭证书验证而不执行，未曾试连真实 TLS，不能声称真实服务器证书无效。
**私有网络通过为 0**。工作流因此如实 failure；其中离线合并、密文推送和失败报告推送均 success。
只抽取每协议前三个合格候选，没有增加超时、扩大抽样、刷新订阅或把失败改成跳过。

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

## 实际验证

| 门禁 | 本地已执行结果 |
|---|---|
| Rust fmt / check / clippy | 全部通过，Clippy 使用 `-D warnings`，依赖已缓存并按 Cargo.lock 构建 |
| `cargo test --workspace --locked --offline` | 101 通过、0 失败、0 忽略；新增 11 项 |
| Release `swirl-api` / `swirl-inspect` 构建 | 通过，Rust 1.99.1，Linux x86_64 |
| 新增独立 Python 连接阶段 | 原始实现 8/8；跨平台夹具修正后本地 8/8，9.040 秒，实际使用 DNS/TCP/TLS/SS 回环服务端 |
| 全量 Python 回归 | 13 套件共 169 项：132 通过、37 明确跳过、0 失败；各套件退出码均为 0 |
| Qt 新增组数据路径/保存回归 | 本地无 Qt SDK；下列 Windows #32 编译与 CTest 实际通过 |
| 本阶段公网及私有节点 | 固定源码 `99ad9b3`：公网 3/3 通过；私有 SS 三个 TCP 超时，Trojan 安全拒绝 |

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
本地运行日志位于忽略的 `core/target/validation/`；Windows 项按下列实际远端结果补齐，跳过不计为通过。

### 三平台最终门禁及源码身份

源码实现为 [`11eafea6bc58cef32ce2adc8e2fdd0f681175a80`](https://github.com/SOLHK/Swirl/commit/11eafea6bc58cef32ce2adc8e2fdd0f681175a80)，
其后的 [`99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63`](https://github.com/SOLHK/Swirl/commit/99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63)
只修正跨平台独立 TCP 夹具并记录原因，没有改动 Rust/Qt 实现。
最终 [Rust Core #32](https://github.com/SOLHK/Swirl/actions/runs/39061540612) 和
[App #29](https://github.com/SOLHK/Swirl/actions/runs/39061540617) 均实际 checkout `99ad9b3` 并成功。

| 平台/项目 | 实际结果 |
|---|---|
| Linux、macOS、Windows Rust | 各 fmt、check、Clippy `-D warnings`、release 全通过；各 101 测试通过、0 失败/忽略 |
| Linux Python | 11 套、135 项：131 通过、4 Qt 跳过、0 失败；连接阶段 8/8，9.030 秒 |
| macOS Python | 11 套、135 项：131 通过、4 Qt 跳过、0 失败；连接阶段 8/8，9.657 秒 |
| Windows 初次 Python | 13 套、169 项：163 通过、6 跳过、0 失败；连接阶段 8/8，26.080 秒 |
| Windows Qt/MSVC | `SWIRL_USE_RUST_CORE=ON` 编译成功；CTest `swirl-rust-qt-integration` 1/1 通过，suite 6.92 秒、总 6.95 秒 |
| Windows 补充 Qt Python | SS HTTP-obfs、VLESS、SOCKS4/4a、VLESS WS 四项各 1/1 通过，补齐初次四项 Qt 跳过 |
| Windows 去重后 Python | 原 169 个独立用例中 167 通过、2 个可选项跳过、0 失败；不把补跑重复加成 173 个独立用例 |
| 私有工具本地合成回归 | 33/33（capture 9、merge 13、native 11）；不计作真实订阅成功 |
| 私有固定源码 workflow 合成回归 | merge 13/13、native 11/11、公开 probe 7/7，通过后才处理真实归档 |

Windows 两个可选跳过为 C++ importer (`SWIRL_CAPTURE_INSPECTOR` 未配置) 与真实 Codex CLI opt-in。
Linux/macOS 四个 Qt 用例没有执行，不将 Windows 成功外推为它们的桌面验收。
CTest 成功日志只显示 suite 1/1，不显示 QtTest 内部用例 Totals，故不虚构内部通过项数。
Windows 四个补充用例分别耗时 0.652、0.660、2.457、1.155 秒。
未测试用户本机的完整 GUI、系统接管、性能或长期稳定性。

最终证据补记只修改 `docs/` 与 `core/README.md`，不改 Rust、Qt、Cargo、Python 或 workflow。
被测源码 SHA 固定为 `99ad9b3`；接手时读取分支真实 HEAD，保留其后的文档提交，不能回退分支。
工作流更新文件 SHA-256 为 `19af2d6ced279a77e3c0975719fdd15d27977a8b49209b24fc798d53c7a1160f`，
App/Secrets 未改变。

### 严格公网证据

最终 Linux 原始 [VERIFIED JSON](evidence/RUST_PUBLIC_NETWORK_20261017_CONNECTION_VERIFIED.json)
记录时间 19:17:46 UTC、干净工作区、源码 `99ad9b3`。三项均完成证书验证的 TLS 1.3、正常关闭、
双向非零代理流量，每项 `accepted=1 / active=0 / failed=0`、连接记录 1，错误和阶段均为空。

| 实际请求 | DNS | HTTP | 耗时 |
|---|---|---:|---:|
| example.com HEAD / | 系统解析 | 200 | 122 ms |
| www.rust-lang.org HEAD / | 系统解析 | 301 | 129 ms |
| example.com HEAD / | Rust 原生 DoH，Cloudflare，显式 bootstrap 1.1.1.1:443 | 200 | 266 ms |

上述都经过明确的原生 DIRECT 出站。通过范围是公网 HTTPS 及原生 DoH，不是 SS/Trojan 服务商、UDP、TUN 或性能验收。
公共与私有运行的 Linux `swirl-api` SHA-256 相同：
`9a9eb67ecc634b05128c0fd1a9653f11e4c7ba34f35e53e081871b6008c78e22`。
私有 `swirl-inspect` SHA-256：`18d82a5f4ab4782b9c0fb82fe135ae3fd6b5abc180de3f8d26265d6a091755be`。

已下载并校验 GitHub artifact ZIP 摘要：最终 artifact `12110819683` 为
`a866a1d219094981f4eb1ea309673a3e3a306c26975384c0aba5bb5b4d49d138`。
仅提取其原始 `CORE_PUBLIC_NETWORK.json`，未改写报告。
首轮整体 CI 失败时的 Linux [INITIAL JSON](evidence/RUST_PUBLIC_NETWORK_20261017_CONNECTION_INITIAL.json)
也保留，固定 `11eafea`；artifact `12111595710` ZIP SHA-256 为
`d5adf47e0b1b464f8eef3313ed1d7fc419caca853ad036503c2751d96eb12f02`。
首轮 Linux 三项通过不能把首轮整体 CI 改记为成功。

### 已遇到的失败

- 初次 Rust loopback 测试在创建 socket 时被本执行环境以 `EPERM` 拒绝。
  使用本轮已获自动批准的临时回环网络权限后完整通过，没有跳过网络测试或修改系统设置。
- 初次 Clippy 指出新增错误记录代码的 `collapsible_if`；改为 Rust 2024 let-chain 后通过，没有 lint 豁免。
- 私有 [Windows fixture 39058955854](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39058955854)
  因旧夹具未提供新必需的截止时间而失败。补充明确夹具期限，没有放松真实采集期限。
- 私有 [云端 smoke 39058955843](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39058955843)
  在 Windows 已推进分支后推送旧 checkout，得到 non-fast-forward 拒绝，旧/新有效归档均未被覆盖。
  恢复后的 [云端 smoke](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39061217426)、
  [Windows smoke](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39061217459) 和
  [Windows 夹具](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39061217439) 全部通过，
  仅访问公共夹具，不请求服务商订阅，也不再推送 smoke 密文。
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
最优先下一项是对同三个缓存 SS 候选做独立 DNS 和逐地址 TCP 对照：不刷新订阅、不增加抽样，
匿名记录解析来源类别、地址族/数量、DNS 耗时、各匿名地址的固定 TCP 结果和未尝试数。
单候选仍不超过 10 秒、DNS 不超过 3 秒、最多两个待完成连接、每地址一次；内存去重重复端点。
不记录域名/IP/端口/凭证或原始异常，不先发送混淆/认证数据。独立 TCP 成功而 native 失败时再查调度，
两者均超时时再比较出口网络；不能直接归咎于服务器停机或封禁。三份抽样不能代表整份订阅失效。
Trojan 声明关闭证书校验的配置仍拒绝，不能由此认定实际服务器证书无效，更不能为了联网测试关闭校验。
VMess、SS2022、REALITY/Vision、gRPC/XHTTP、Hysteria2/TUIC/QUIC、Windows TUN 和完整系统接管等仍未完成。
长期稳定性、性能、弱网、用户本机视觉及全应用接管尚无本阶段验收，兼容内核依赖继续保留。
