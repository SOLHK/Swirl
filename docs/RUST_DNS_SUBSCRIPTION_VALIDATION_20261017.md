# Rust DNS 负缓存与私有订阅验证阶段记录

日期：2026-10-17 UTC。开发分支：`work/core-completion-20261017`。
接续基线：`8c172186761743c9d32a42f75e338ae798645f18`。
本轮在既有 Rust 内核上增加 DNS 缓存语义及原生订阅抽样验证，没有改变 UI 或接管用户系统网络。

**本轮实现、三平台 CI、Windows Qt 和严格公网门禁均已通过；私有归档解析通过，三个 SS 样本联网失败。**
下表分别记录实际源码和工作流身份，不能沿用旧 #25 的通过结果。

| 本轮远端证据 | 当前状态 |
|---|---|
| 公共源码提交与远端树核对 | [`95b4fbc`](https://github.com/SOLHK/Swirl/commit/95b4fbc8f58b166a93fcc10b648bef39d396c4d6)；远端树与本地验收暂存树均为 `28f61004b0be45a81c678be01d4863631eedfc0f` |
| App 工作流提交 | [`95b46f4`](https://github.com/SOLHK/Swirl/commit/95b46f4e3494feede242650324ac6ea542912c4a)，仅 `rust-core.yml` +6；[App #24](https://github.com/SOLHK/Swirl/actions/runs/39054255346) 成功 |
| 初次完整新增门禁 | [Swirl Rust Core #28](https://github.com/SOLHK/Swirl/actions/runs/39054282502)，`95b46f4`；Linux/macOS 成功，Windows 在既有 SOCKS4 密码拒绝测试收到 reset 后失败，尚未运行新增 DNS/probe 套件 |
| Windows 拒绝测试修正 | [`fa37637`](https://github.com/SOLHK/Swirl/commit/fa376375bd67e77b8253eee4bcf40d4633b08c3d)，仅修改一项测试；[#29](https://github.com/SOLHK/Swirl/actions/runs/39055082063) Windows/macOS 成功，Linux 在 DNS 对端分配端口时失败 |
| DNS 对端配对分配修正与最终门禁 | [`f13c695`](https://github.com/SOLHK/Swirl/commit/f13c695ab1747e84de8594bfe208bd278b6149a6)，仅两个测试文件；[Swirl Rust Core #30](https://github.com/SOLHK/Swirl/actions/runs/39055991802) 三平台、Windows Qt 与严格公网全部成功 |
| 私有 workflow 固定公共源码 SHA | [`6cc5556`](https://github.com/SOLHK/Swirl-Private-Tests/commit/6cc5556e0a43f76d34d1825a12115a8c5f334bd7)，固定 `95b4fbc8f58b166a93fcc10b648bef39d396c4d6` 构建 |
| 现有加密归档的原生 SS/Trojan 联网抽样 | [首次私有运行](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39054318056) 和 [补充错误码后的诊断运行](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39054949401) 均如实失败；两份解析通过，三个 SS 样本均未联网通过 |
| 私有持久证据 | [完整白名单报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/ae7ebe3e409c254012aa82cb47117b7620c87e9f/reports/native-core-95b4fbc-20261017.json)，仅保存在私有仓库 |

App 实际工作流 SHA-256 为 `0acdae7abbc46f294f1a848f9db042ce93ddc143c306130c4212cb52b97c4a65`，
与本地受限更新器预览一致；本轮沿用已有 App、权限与 Secrets。

上一策略、SOCKS4、WS 的 #25 证据保留在 [历史阶段报告](RUST_POLICY_VALIDATION_20261017.md)；
更早的 [WS/DoT 与公网记录](RUST_WS_VALIDATION_20261017.md) 也保持其原始范围。

## 最终公共 CI 与公网证据

[Swirl Rust Core #30](https://github.com/SOLHK/Swirl/actions/runs/39055991802)
实际 checkout 为 `f13c695ab1747e84de8594bfe208bd278b6149a6`。
三平台于 2026-10-17 18:08:08 UTC 全部完成且成功，以下计数来自该运行的实际日志。
后续证据提交仅保存两份文档和原始 JSON；通过结论绑定上述实测源码，不把文档提交当成另一次构建。

| 平台与步骤 | 当前实际结果 |
|---|---|
| Linux | fmt/check/clippy/release 全部成功；90 Rust 通过；125 Python 中 121 通过、4 Qt 跳过、0 失败；DNS 18/18、native probe 6/6 |
| macOS | fmt/check/clippy/release 全部成功；90 Rust 通过；125 Python 中 121 通过、4 Qt 跳过、0 失败；DNS 18/18、native probe 6/6 |
| Windows | fmt/check/clippy/release 全部成功；90 Rust 通过；初次 159 Python 中 153 通过、6 跳过、0 失败；DNS 18/18、native probe 6/6 |
| Windows Qt | CTest 1/1 通过（单项 3.14 秒，总计 3.17 秒）；SS、VLESS、SOCKS4、WS 四项独立 Qt 对端补跑全部通过 |
| Linux 严格公网验证 | 3/3 通过；实际报告时间为 `2026-10-17T18:01:05.647353+00:00` |

四项 Qt 补跑覆盖 Windows 初次全套中的四个 Qt 跳过项；按独立 Python 用例统计，最终为
159 项中 **157 通过、2 个可选项跳过**。余下两项分别需要 `SWIRL_CAPTURE_INSPECTOR` 的
C++ importer 和明确 opt-in 的真实 Codex CLI。Linux/macOS 的四项 Qt 测试仍未运行，
不能把 Windows Qt 结果当成其他平台桌面验收。三个平台的失败和错误均为零。

同一提交的 [App #27](https://github.com/SOLHK/Swirl/actions/runs/39055991875) 已成功，
90 项 Rust 与 14 项受限更新器回归通过；基础 Python 菜单共 74 项，69 通过、5 跳过。
没有产生额外工作流修改。App 菜单不替代上表完整门禁，也不把不同工作流的重复执行相加为覆盖数。

公网原始 JSON 已按下载时的字节保存到
[RUST_PUBLIC_NETWORK_20261017_DNS_VERIFIED.json](evidence/RUST_PUBLIC_NETWORK_20261017_DNS_VERIFIED.json)。
来源为同一运行的 [artifact 12109860848](https://github.com/SOLHK/Swirl/actions/runs/39055991802/artifacts/12109860848)，
ZIP 的 SHA-256 为 `c708dfb5458dfc962a5a37f710e4dceae414ef875b8eb0d23af0aee2513e5a16`，
与 GitHub artifact digest 一致；JSON 的 SHA-256 为
`28e2636eb5407185a449c4d3e624de533a851d944e8bb61b91f6131c352b9a3e`。

| 固定公网路径 | HTTP | 原生会话上传/下载（字节） | 单次耗时 |
|---|---:|---:|---:|
| `example.com`，DIRECT + 系统 DNS | 200 | 700 / 4788 | 89 ms |
| `www.rust-lang.org`，DIRECT + 系统 DNS | 301 | 690 / 5385 | 139 ms |
| `example.com`，DIRECT + 原生 DoH | 200 | 700 / 4790 | 200 ms |

三项均为验证证书的 TLS 1.3、正常关闭、双向流量非零、恰好一条已结束连接，
每项 `accepted=1 / active=0 / failed=0`、`last_error` 为空。DoH 使用
`https://cloudflare-dns.com/dns-query`，显式 bootstrap 为 `1.1.1.1:443`。
报告记录工作区干净，harness SHA-256 为
`1e3c4abcbb03d0fa73f176629e29c6b955fbbd14979c1fd2fc2fa0146638efda`。
该证据只覆盖上述公网 DIRECT/DoH 路径；单次耗时不是性能基准，也不证明私有提供商、UDP 或 TUN 已通过。

Windows 工作流另保留 [Swirl-Rust-Core-Windows 构建产物](https://github.com/SOLHK/Swirl/actions/runs/39055991802/artifacts/12109742000)。
上传清单包括 `swirl_api.dll`、`swirl-api.exe`、`swirl-inspect.exe`、`Cargo.lock` 及已有管理脚本/说明。
GitHub 元数据报告该 ZIP 的 SHA-256 为
`05e6f31259d163c7f7a52ed600d8582b402796f3b193c10322024f6b4e745087`；此处没有声称独立下载校验该 ZIP。
它是供开发验证的内核构建产物，本轮尚未生成完整桌面安装包。

## DNS 实际增量与边界

`swirl-dns` 缓存键改为规范化的小写主机名，缓存 IP 集合，返回时附加当前请求端口。
同一主机的不同端口可共享查询结果；配置代隔离、精确 hosts 优先级、容量和地址数量上限继续保留。

UDP/TCP、DoT、DoH 共用严格响应解析与 A/AAAA 合并。NXDOMAIN 和合并后的 NODATA
仅在 authority section 存在结构有效、类别为 IN、覆盖实际 CNAME 终点的 SOA 时取得负缓存寿命。
寿命受 SOA TTL、SOA MINIMUM、相关 CNAME TTL、已耗时间及本地 300 秒上限约束；
DoH 继续应用 HTTP Age 和缓存限制。SOA RNAME 按 DNS 标签结构解析，允许邮箱标签内的字面点号。

TTL 为零的有效负结果不进入可复用缓存。有 SOA 的有效 NODATA 保持终止语义，即使 TTL 为零也不改查
其他服务器；没有 SOA 的空 NOERROR 回复保留原有显式服务器重试行为。无 SOA 的 NXDOMAIN
仍终止本次查询，但不能建立负缓存。无关 SOA、错误问题/ID、截断异常、尾随垃圾及不一致的 A/AAAA
结果不能污染缓存；合法 UDP 截断继续通过 TCP 完整校验。

当前仍要求两个地址族查询均按既有严格策略完成；某一族失败可使另一族已有正结果的查询整体失败。
超时、SERVFAIL、REFUSED 和传输错误保持失败，不能归为 NXDOMAIN/NODATA。
**RFC 9520 的解析失败缓存尚未实现**；DNS 分流、自动域名 bootstrap、经代理的加密 DNS、
EDNS 协商及 DNSSEC 验证也不在本轮完成范围。详见 [DNS 当前说明](RUST_LOCAL_DNS.md)。

## 首轮完整本地执行结果

本轮本地证据来自 Linux 候选工作区和 release harness。原始汇总位于
`core/target/validation/local-rust.json`、`core/target/validation/local-python.json`，
它们属于本地构建目录；下表记录实际统计，远端通过状态另行核对。

| Rust 检查 | 实际结果 |
|---|---|
| fmt、workspace check、clippy（警告作为错误） | 全部退出 0 |
| workspace test | 90 通过、0 失败、0 ignored |
| release 构建 | 最终退出 0 |

| Python 套件 | 总数 | 通过 | 跳过 |
|---|---:|---:|---:|
| `test_rust_core.py` | 24 | 23 | 1 |
| `test_shadowsocks.py` | 9 | 8 | 1 |
| `test_dns_tls.py` | 11 | 11 | 0 |
| `test_dns_https.py` | 9 | 9 | 0 |
| `test_socks4.py` | 10 | 9 | 1 |
| `test_websocket_transport.py` | 11 | 10 | 1 |
| `test_policy_groups.py` | 13 | 13 | 0 |
| `test_dns_negative.py`（新增） | 15 | 15 | 0 |
| `test_native_probe.py`（新增） | 6 | 6 | 0 |
| `test_core_development.py` | 14 | 14 | 0 |
| `test_subscription_capture.py` | 23 | 1 | 22 |
| `test_codex_management.py` | 11 | 0 | 11 |
| **公开仓库本地合计** | **156** | **119** | **37** |

12 套件全部退出 0，失败为 0。37 个跳过分别是四项需要 Windows Qt 可执行文件的真实对端测试、
22 项 Windows DPAPI 采集测试、10 项 Windows DPAPI 管理测试，以及一项需要明确 opt-in 的真实
Codex CLI 测试。跳过不计作通过。私有仓库 `test_native_core_unit.py` 首次 **8/8 合成测试通过**，
补充静态错误码白名单后 **9/9 通过**；两者单独记录，不加进公开仓库总数，合成测试未使用真实归档或节点。

新增 DNS 15 项独立测试覆盖跨端口/大小写共享、实际两个目标端口的转发、SOA/CNAME TTL 到期恢复、
SOA 归属与格式拒绝、零 TTL、A/AAAA 分歧及失败、DoH Age/no-store、TCP 重试、显式后备服务器、
配置代与容量边界。新增 probe 六项包含实际 release Rust harness 连接独立拒绝 SS 对端的失败证据，
并检查单出口配置、拒绝 DIRECT/规则注入、配置复制及命令大小限制。

### Windows 早拒绝测试的实际失败与修正

#28 Windows 的既有 `test_password_protected_inbound_rejects_socks4` 读取拒绝回复时出现
`ConnectionResetError: [WinError 10054]`。这一运行的 Windows 仅执行了 63 项 Python：
59 通过、3 Qt 跳过、1 错误；不能把后续尚未执行的新增套件或 Qt 写为通过。
同一 Rust 源码的初始 #27 Windows 通过了该测试，说明关闭表现存在平台/时序差异。

内核在读完版本字节后立即按密码策略拒绝 SOCKS4；请求其余部分可能尚未读完。
[Go 官方 TCP 关闭处理说明](https://github.com/golang/go/blob/master/src/net/http/server.go)
讨论了未读数据关闭导致 RST 和最终回复截断的情形。因此 `fa37637` 只修正这项策略测试：
允许 EOF/reset 提前结束，已收到字节必须是完整 `91` 拒绝报文的正确前缀，超时或其他异常仍失败。
同时严格断言原生 `accepted=1 / active=0 / failed=1`、`last_error=InboundAuthentication`、
连接记录为空及目标接受数为零。其他精确 `91` 断言继续保留，没有修改认证、运行时或增加网络重试。
本地专项使用同一次 release 构建：10 项中 9 通过、1 Qt 跳过、0 失败，5.131 秒。
此修正证明密码策略被执行，不声称改善 Windows 上拒绝帧的完整交付。

### DNS 测试对端端口碰撞的实际失败与修正

#29 Linux 的 `test_inconsistent_families_and_failed_families_never_create_negative_cache`
在创建独立对端时发生 TCP `EADDRINUSE`：先获得空闲 UDP 端口，并不保证同号 TCP 端口可用。
该子例的 DNS 查询尚未发出；随后对未关闭 UDP socket 的 ResourceWarning 也被保留。
这轮 Linux 为 116 项 Python 中 111 通过、4 Qt 跳过、1 创建错误；后续 native probe 与公网步骤未执行。
#29 Windows 则完成 90 Rust、初次 156 Python 中 150 通过/6 跳过、Qt CTest 1/1 和四项独立 Qt 对端，
不能用 Windows 成功覆盖 Linux 的实际失败。

`f13c695` 在启动线程前配对获取 UDP/TCP 服务器，通过标准库 `ExitStack` 管理部分创建失败的释放。
仅 `EADDRINUSE` 有界重试，最多 8 次；其他异常原样传播，不启用端口共享，不重试 DNS 查询结果。
参考 [CPython socketserver](https://github.com/python/cpython/blob/main/Lib/socketserver.py) 的构造/上下文关闭语义，
只使用其公开资源管理接口。清理范围是配对创建/绑定失败，不声称处理任意线程启动故障。

新增三项确定性分配回归覆盖 UDP/TCP 首次碰撞恢复、持续碰撞封顶、EACCES/非 socket 异常的清理。
原 15 项 DNS 语义断言保持不变。现有 Release 上 **18/18 DNS 与分配测试通过（36.361 秒）**，
另有 **5/5 旧 DNS 对端回归通过（17.164 秒）**，均零跳过/失败。
这些是首轮完整回归之后的定向验证，不把重复执行的测试重复累加为新覆盖数。

### 一次 release 链接异常

一次构建在 cc/lld 链接阶段报告 `core::panicking` / `core::fmt` 未定义符号，退出 101。
原始失败输出仅在会话中出现，没有保存为本地日志附件。工作目录为 `Swirl/core`，失败及原样重试的命令为：

```sh
env CARGO_HOME=/workspace/scratch/23d9b638e0cb/swirl-toolchain/cargo RUSTUP_HOME=/workspace/scratch/23d9b638e0cb/swirl-toolchain/rustup /workspace/scratch/23d9b638e0cb/swirl-toolchain/cargo/bin/cargo build --release --locked --offline -p swirl-api -j4
```

原命令重试成功，随后完整 release 门禁也通过；没有增加链接器或优化设置覆盖，保留既有 thin LTO 和
`codegen-units=1`。**原因尚未确定**，不能把重试成功写成已查明或修复根因。

## 私有归档事实、授权和验证方式

既有私有 [脱敏格式报告](https://github.com/SOLHK/Swirl-Private-Tests/blob/3c3fa41/reports/subscription-formats.json)
显示：16 项订阅中，#9 和 #10 已取得 Clash YAML 正文，分别包含 90 个 SS 和
90 个 Trojan。固定版本的 [私有采集说明](https://github.com/SOLHK/Swirl-Private-Tests/blob/3c3fa41b09d1120cda81969a1ac3892b8c458f75/README.md)
另外记录 2/16 成功、14/16 为 HTTP 403；结合两次原生归档检查，现有缓存没有其余 14 项的正文可供解密。
本轮原生 inspector 重新读取了两份实际归档，确认上述条目数量与格式，结果如下。

| 缓存 | 原生解析与转换 | 实际网络证据 |
|---|---|---|
| #9：90 个 SS 条目 | 全部为 `aes-128-gcm`、TCP、HTTP 混淆；90 个 TCP 候选、0 个未识别字段 | 前三个候选两轮均失败；补充诊断后三项均为 `UpstreamTimeout`，耗时 10005–10006 ms |
| #10：90 个 Trojan 条目 | 解析通过；全部声明关闭证书校验，按既有严格规则标为 `CertificateVerificationDisabledUnsupported`，0 个 TCP 候选 | 没有发起节点连接；这不证明实际服务器证书无效 |
| 其余 14 项 | 没有已下载正文 | 没有解析或节点网络证据 |

两份完整客户端配置的 `complete_configuration_execution_supported` 均为 false。
条目转换不代表整份配置/策略接管；180 条目也不代表 180 台独立服务器。
每次 SS 失败均为 `accepted=1 / active=0 / failed=1`、一条已结束记录、上传/下载均为 0。
没有目标 TLS/HTTP 响应，`network_verified=false`，私有工作流保留退出失败状态。
`UpstreamTimeout` 覆盖整个上游建立预算，包括 DNS、TCP 和协议握手；现有证据不能认定密码错误、
节点失效或特定网络层故障。前三个顺序样本不具代表性，GitHub runner 的网络也不等于用户 Windows 网络。

诊断提交 [`ae31749`](https://github.com/SOLHK/Swirl-Private-Tests/commit/ae317492e82eb355e34068b9d884a1b7f868fe80)
只增加固定原生错误码白名单和必要脱敏回归，未改变采样与成功标准。
两次私有构建的 harness SHA-256 均为
`1e3c4abcbb03d0fa73f176629e29c6b955fbbd14979c1fd2fc2fa0146638efda`，inspector 均为
`18d82a5f4ab4782b9c0fb82fe135ae3fd6b5abc180de3f8d26265d6a091755be`。
最终私有 JSON SHA-256 为 `b55030bcc0fb44f5fbeca324f0404f6911f5464498e028ca7aef833b8c495de9`。
已核对最终候选 `f13c695` 的 `core` 树及共享 verifier 与私有固定源码 `95b4fbc` 完全相同。

用户已授权使用 `Swirl-Private-Tests` 的现有加密归档：仅在该私有 Actions 中于内存解密，
只向原生子进程的 stdin 传入所需正文/节点参数，只保存白名单报告。这是旧文档“私有缓存一概不进 CI”
的授权例外；原始 URL、密钥、节点凭据、解密配置不能进入公开仓库、日志、报告或外部转换服务。
现有授权不包含刷新订阅 URL，不需要为缓存验证重新开启订阅下载窗口。

私有工具删除密钥环境变量后才启动子进程；报告只保留固定枚举、布尔、计数和匿名索引。
全局选取前 3 个可执行 SS 与前 3 个 Trojan，最多 6 个，明确标记抽样不具代表性。
每个样本只有一个原生出口，没有 DIRECT 或组后备；目标固定为 `example.com:443` 的 `HEAD /`。
成功同时要求原生身份、认证 TLS、200–399 状态、正常关闭、恰好一条已结束连接、双向实际流量、
零失败和空会话错误。结果范围仅为选中样本的 HTTPS TCP，不代表全部订阅、协议、UDP 或 TUN 已通过。

workflow 固定公共源码 SHA、执行全新 checkout 和当次 `cargo --locked` release 构建；脚本核对 HEAD、
相关工作区干净状态并记录 inspector/harness SHA-256。单独的二进制哈希不是独立构建来源证明。
脚本异常生成固定枚举失败报告并退出 1；artifact 只上传新生成的 `reports/native-core.json`，
不上传归档。前置构建/测试失败而未生成该文件时，只产生无文件告警，不生成联网成功结论。

## 参考与复现入口

实现前核对成熟项目和规范，只参考设计与可观察测试行为，未复制第三方代理实现：

- [shadowsocks-rust](https://github.com/shadowsocks/shadowsocks-rust)（MIT）与
  [sing-box](https://github.com/SagerNet/sing-box)：协议能力分层、独立对端及真实 TLS/数据传输验收；
  某个协议样本通过不能外推为所有版本、传输或完整订阅配置兼容。
- [RFC 2308](https://www.rfc-editor.org/rfc/rfc2308.html)：NXDOMAIN/NODATA、SOA 与负缓存寿命。
- [RFC 9520](https://www.rfc-editor.org/rfc/rfc9520.html)：解析失败缓存与负答案缓存分开；本轮尚未实现前者。

在仓库根目录使用同次 release 构建的 harness 和 inspector 运行新增套件：

```sh
export SWIRL_RUST_HARNESS="$PWD/core/target/release/swirl-api"
export SWIRL_RUST_INSPECTOR="$PWD/core/target/release/swirl-inspect"
python3 tools/tests/test_dns_negative.py
python3 tools/tests/test_native_probe.py
```

完整回归和 Windows Qt 命令见 [续接入口](CONTINUE_DEVELOPMENT.md)。用户 Windows 机器上的仓库、
SDK、工具链和生成文件统一放在 `D:\Codex`；当前 Linux 工作区路径不表示用户 D 盘已收到文件。
默认产品仍保留兼容构建，`SWIRL_USE_RUST_CORE=ON` 才选择原生 Rust；本轮不宣称全项目迁移完成。
