# Swirl 原生 SOCKS5 出口 UDP：实现、证据与边界

本阶段在字体系统完成云端验证后，按用户“继续自研 Swirl 内核”的指令推进。
唯一开发分支为 `work/core-completion-20261017`。它增加实际 Rust UDP 出口，
复用现有 Qt 导入、线程适配、路由、统计和生命周期；不改变默认构建选项、
界面布局、动画、系统代理、TUN 或用户的订阅来源。

这是固定验收清单 B05 的**部分实现**。私有提供商、完整订阅链、公网 NAT、
长期吞吐和全部协议组合均不能由本地对端替代，总体已验收分数仍为 10.83%。

## 1. 规范与独立实现

实现前阅读了 [RFC 1928 §6–7](https://www.rfc-editor.org/rfc/rfc1928)
和 [RFC 1929](https://www.rfc-editor.org/rfc/rfc1929)，核对认证协商、CMD 03、
BND 地址/端口、UDP 封装、来源限制、分片以及 TCP 控制连接的关联生命周期。
参考 MIT 项目 [fast-socks5](https://github.com/dizda/fast-socks5/blob/master/src/client.rs)
同时持有控制流与 connected UDP 的架构，也参考
[PySocks](https://github.com/Anorov/PySocks/blob/master/socks.py) 的控制连接生命周期。
未复制这两个项目的代码，没有新增代理内核。首次实现未增加依赖；随后为
修复 macOS 实际发现的大报文缓冲问题，`swirl-transport` 直接使用已由 Tokio
锁定的 `socket2` 0.6.5。`Cargo.lock` 仅增加该直接引用，无新包或版本升级，
也没有增加裸 `unsafe` 操作。

RFC 1928 并不规定所有 `TLS + SOCKS5 UDP` 客户端扩展的安全语义；本阶段明确
拒绝该组合，不能保留 TLS 标签却发送未经相应保护的 UDP。支持范围是标准
SOCKS5 的无认证和 RFC 1929 用户名/密码认证。

## 2. IR 与 Qt 产品路径

```json
{
  "type": "socks5",
  "host": "proxy.example",
  "port": 1080,
  "auth": null,
  "tls": null,
  "udp": true
}
```

`udp` 是严格布尔值，缺省为 `false`，保留原有 TCP 配置语义。`udp: true`
与非空 `tls` 同时出现时，IR 和 inspector 拒绝，诊断为
`Socks5UdpTlsUnsupported`；Qt 在启动前拒绝并保留原始配置。

| 层 | 本阶段真实改动 |
| --- | --- |
| `swirl-subscription` | 严格类型和默认值；能力报告区分声明、候选、UDP 能力与真实联网；保留未知项和原文。 |
| `swirl-protocol/socks5.rs` | 独立 RFC 状态机、TCP/UDP 共用认证、UDP 编解码与控制连接。 |
| `swirl-core/socks5_udp.rs` | 每入站关联拥有的有界出口池、回包队列、取消与关闭墓碑。 |
| `RustCoreEngine.cpp` | 将已有节点的 `udp` 映射到 Rust IR；TLS/证书验证/未知参数继续严格校验。 |
| `SubscriptionNormalizer.cpp` | 修复 `socks5-tls` URI 单独及混合列表的隐式 TLS 语义。 |
| `RustCoreTests.cpp` / `ImportTests.cpp` | 真实导入、映射、启动、转发、关闭及原文保留断言。 |

没有新增 QML 协议按钮。用户现有的 Clash、INI、URI 导入路径继续提供节点参数。
开启 Rust 构建后由 `SwirlProtocolRegistry` 调用同一个 Rust 配置验证入口；
兼容构建保持其原有能力边界，不把 Rust 的新 UDP 能力冒称为旧 C++ 引擎能力。

新增测试还发现了已有 `socks5-tls` 别名在部分导入路径丢失 TLS 的问题。
现在 URI scheme 始终保留 TLS，`security=none` 冲突失败，未映射的 `tls=false`
查询保留原文及差异并阻止原生执行。Rust inspector 对原始 `type: socks5-tls`
也保留该语义。Qt 并未扩大 raw Clash 协议词表；此前拒绝的该 raw type 仍拒绝。

## 3. 网络与生命周期

- 有认证配置时只提供方法 2，不接受服务端降级为方法 0；用户名和密码按字节
  校验 1–255 的边界，临时认证缓冲采用已有 `Zeroizing`。
- TCP 连接、DNS、认证、UDP ASSOCIATE、BND 域名解析共用同一个握手截止时间。
  未知客户端 UDP 地址按实际 TCP 地址族发送全零地址和端口。
- 明确的 BND 地址保持原值；只有未指定 IP 才使用已连接 TCP 对端的实际 IP。
  BND 域名交给既有配置 Resolver，非零端口和有效单播地址必须通过验证。
- UDP socket 连接到返回的 relay 地址与端口，由操作系统约束来源。目标的
  IPv4、IPv6、域名字段编码到 SOCKS5 报文；不额外本地解析目标域名。
- 严格检查 VER、REP、RSV、ATYP、地址、端口和长度；非零 FRAG 不支持，直接
  丢弃。支持空载荷；完整 SOCKS5 UDP 封装报文上限 65,507 字节。
- TCP 控制连接关闭或出现不应存在的数据时，该出口关联关闭；等待发送的
  UDP 操作响应取消，已排队回包随 worker 生命周期失效。关闭入站控制连接或
  停止引擎会释放拥有的任务与 socket。
- 上传/下载计数来自成功发送/交付的实际载荷；失败计入丢弃，不生成虚构回包。
  不隐式改用 DIRECT、其他节点，不重放应用数据。

| 资源 | 明确上限或行为 |
| --- | --- |
| 每入站关联的 SOCKS5 出口 | 最多 16 个，包含已关闭节点的墓碑。 |
| 路由准备、排队、等待发送 | 整个入站 UDP 关联共享 4 个许可，覆盖原 Direct/SS 路径。 |
| SOCKS5 回包队列 | 共享容量 4；满时丢弃并记数。 |
| Direct/SS 最近目标 | 保留原来的最多 64 个目标及 30 秒回包窗口。 |
| SOCKS5 最近活动 | 每个可信 relay 最近发送后 30 秒；这是关联窗口，不是逐目标验证。 |
| 配置更新 | 已建立关联持有原不可变会话计划；新关联使用新配置。 |
| 原生 UDP socket 缓冲 | 固定最低 65,536 字节，发送/接收均读回验证；保留已有更大系统值，不随流量增长。它不代表内核队列恰好只有一个报文。 |

关闭墓碑避免同一入站关联在上游 EOF 后隐式重连。应用可以建立新的入站
关联，新的关联会独立握手。这一限制明确有界，不是无限自动重试。

## 4. 独立测试与当前已执行结果

环境为云端 Linux、Rust 1.99.1、Qt 6.10.3/GCC 13.3，测试只使用公共协议和
合成回环资源。隔离 Rust 工具链安装未修改用户的全局 shell 配置。

| 检查 | 当前实际结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 通过。 |
| `cargo check --workspace --locked --offline` | 通过。 |
| `cargo clippy --workspace --all-targets --locked --offline -- -D warnings` | 通过。 |
| `cargo test --workspace --locked --offline` | 152 通过、0 失败、0 ignored；新增 10 项，原测试保留。 |
| Release CLI 与共享库 | 实际构建成功。 |
| 加强反例后的独立 Python 套件 | 12 通过、1 个缺少完整 Qt 可执行文件的钩子跳过、0 失败；8.810 秒。两个加强目标先单独通过，4.207 秒。 |
| Qt 导入与映射子集 | 原样提取新 slot，链接真实生产解析器/适配器及 Rust `.so`，通过。 |
| 正式 Python Qt 钩子的云端子集运行 | 1 通过、0 跳过；无认证与密码认证两进程，各通过 Clash/INI 两次实际转发。 |
| Qt 参数契约负例 | 全缺参数明确跳过；部分缺失、错误端口、错误认证模式均按预期失败，未计为正向通过。 |
| 既有 `test_rust_core.py` | 23 通过、1 个完整 Qt 钩子跳过、0 失败；26.422 秒。 |
| 既有 `test_shadowsocks.py` | 8 通过、1 个完整 Qt 钩子跳过、0 失败；11.263 秒。 |
| 工作流更新器安全回归 | 25/25 通过，`--check` 不改文件；actionlint 和 diff 检查通过。 |

独立 Python peer 不导入 Rust 编解码器，也不运行其他代理内核。它自行解析
控制握手和 UDP 包，将载荷通过真实 UDP socket 发送到另一个 origin，再转发
origin 的响应。断言同时检查客户端回包、peer `forwarded` 和 origin 收到的
载荷；前缀字符串本身不能证明经过代理。

实际覆盖无认证/密码认证、各 ATYP、空包/大包、BND 地址、坏包/FRAG、非中继
源端口、控制关闭、不重连、不直连、关联隔离、4 个在途任务及 16 个含墓碑
会话上限。独立测试不声称已从外部饱和验证内部的 4 项回包队列。

三种目标 ATYP 验证的是线上的地址字段及载荷保留：Python peer 有意将它们
转到固定 IPv4 origin。单独的 IPv6 BND 用例确实使用 IPv6 relay；这不能
外推为任意 IPv6 最终目标或真实代理侧 DNS 已验收。

## 5. 保留的失败与审查改进

1. 初次回环测试被沙箱以 `EPERM` 拒绝；没有修改测试，获准执行回环 socket
   后重跑。不得把该次失败记为成功。
2. Rust 新反例发现既有 `socks5-tls` 隐式 TLS 丢失，修复后第三次整集达到
   152/152。有效的 URI TLS 查询语义为 `security=tls`；未知 `tls=true` 不能
   为通过测试而当作已支持。
3. Python 三个 BND 子例最初配置了禁止系统 hosts 且没有 DNS 服务，被已有
   `ConfigBounds` 正确拒绝。只修测试 fixture，绑定隔离的 DNS sink 并保留
   hosts 映射，同时要求零 DNS 查询；没有改 Rust 校验。
4. 独立审查发现坏握手后 peer 立即 EOF 会削弱字段拒绝证据，以及 BND 域名
   映射与 TCP peer 同 IP 无法区分忽略域名的错误实现。现已保持错误对端开放，
   观察 Core 主动 EOF/复位且不发送后续 TCP/UDP；截断响应由 1 秒协议期限
   触发失败，其他完整错误使用默认 10 秒期限并在 3 秒内观察拒绝。
   BND 域名映射改为实际 IPv6 relay `::1`，控制 TCP 仍为 IPv4，DNS sink
   必须无查询。目标重跑与完整套件均已通过，旧 7.494 秒结果未覆盖。
5. 前置规则阶段的 Windows CTest 失败及两处 JSON 往返测试类型问题，完整
   保留在 [规则事务报告](RULE_EDIT_TRANSACTION_20261019.md)。新增固定 XML
   报告输出保持原 CTest 退出码，不以日志工具掩盖失败。
6. `8d045ab888e6ed0af6dea87adfb752793c455b5b` 的首次
   [三平台 CI](https://github.com/SOLHK/Swirl/actions/runs/39180142737)
   中，Windows 在工作流自检失败：只应收集三个 Rust 程序预检的测试误收了
   后续完整应用的 EXE 存在检查，得到 `4 != 3`。修复将提取范围限定为各自
   具名 peer step，并在每个平台先检查 Windows 和 Unix 两种脚本。三个预检、
   缺失文件必须阻止套件开始、齐全文件允许开始的实际执行断言，以及后续
   完整应用检查全部保留。修复后本地 25/25 通过；首次 Windows 的 Qt、
   新 UDP peer 和完整应用步骤未执行，没有四份 Qt XML 产物。
7. 同一次 macOS 运行的最大数据报用例，在无认证和密码认证两个子例里由
   Python 客户端 `sendto` 抛出 `EMSGSIZE`，尚未把包发送到 Core。
   该套件结果为 13 项、2 个子例错误、1 个 Qt 钩子跳过，不能记为通过。
   后续修复必须核对测试对端与实际转发 socket 的容量，保留 65,507 字节
   边界；不能通过缩小报文或跳过 macOS 消除失败。

针对第 7 项，已按精确版本读取 Apple 的
[XNU UDP 默认缓冲](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/netinet/udp_usrreq.c)、
[原子发送与 socket 选项处理](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_socket.c)
以及 [接收队列的报文/地址空间计算](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/uipc_socket2.c)。
这份公开源码的默认发送容量为 9,216 字节，原子报文超过发送高水位会返回
`EMSGSIZE`；同一机制约束 Python 和 Core。该源码的默认接收容量已经较大，
修复不会将它降低。公开源码机制与本次错误一致，不把它当作已经读取了
托管运行器的全部内核参数。

共享 `swirl-transport::bind_udp` 仅提高不足 65,536 的发送/接收缓冲，随后
读取实际值；若设置失败或被限制在下限以下，显式返回错误。Core 的入站
relay、Direct/SS 的 IPv4/IPv6 socket，以及 SOCKS5 的 connected relay
共用它。入站成功回复移到这些 socket 初始化之后，避免初始化失败却先回复
成功。独立 Python client、proxy relay、origin 转发和 origin 四跳自行设置
相同固定下限，没有使用 Rust 的函数或缩减大包。

本地新增的两个传输测试实际执行了小缓冲恢复后的 IPv4/IPv6 双向完整
65,507 字节传输，以及保留较大原值；Rust 整集为 154 通过、0 失败、0 ignored，
fmt/check/clippy 通过。独立 peer 的原边界仍要求最终完整响应恰好为 65,507
字节；Linux 本地结果不能替代 macOS/Windows 精确提交复测。
修复后的 Release 实际构建成功，独立 UDP 全套为 12 通过、1 个完整 Qt
钩子跳过、0 失败，8.814 秒；当前 CLI SHA-256 为
`e7135782c474bfc1d18118283c69632a086bef59a9e9f5a2d1511665dcb28bea`。

首次实现的 Release `swirl-api` 本地 SHA-256 为
`13d70f3debaf077673f690c6b557cde73af3bc87daa2c3a2ff5007e85a23eaa0`。
旧 SOCKS5 TCP 认证/TLS、Direct DNS/UDP、三个 SS AEAD 算法、重放保护、
HTTP 混淆、大传输和半关闭通过以上现有独立回归；未修改旧测试。

## 6. Windows CI 与剩余验收

本阶段复用现有 Swirl Core Automation App 和标准 GitHub Actions 运行器。
不创建 App、Token、Secret，不开通付费运行器。Windows Qt 使用 6.10.3 的
`win64_msvc2022_64` 与 Visual Studio 2022 x64；Rust 动态库同为 MSVC ABI。
既有 Linux/macOS/Windows Rust 检查和独立协议套件全部保留。

Windows 作业总上限从 25 分钟调整为 35 分钟，用于新增的完整应用编译；
所有单项测试期限保持不变。已有实测中，同类完整应用编译为 413 秒和
786 秒，前置 Core/Qt 作业约 15 分钟，不能按较快的一次结果假定必定能在
旧总预算内完成。仍使用同一标准 Windows 运行器和两路完整应用编译。

Windows 增加 Qt UDP peer，兼容构建同时执行原 DNS 保护与共享导入边界，
然后实际编译启用原生 Rust 的完整 `Swirl` 目标。固定路径 XML 报告按白名单
保存；用户缓存、配置和私有字体不进入产物。

首次实现 `8d045ab888e6ed0af6dea87adfb752793c455b5b` 的
[Rust 运行 39180142737](https://github.com/SOLHK/Swirl/actions/runs/39180142737)
中，Linux 成功，macOS 和 Windows 失败，原因及未执行步骤见上文。
Linux 的 Rust 为 152 通过；14 个 Python 套件共 202 项，197 通过、5 个
完整 Qt 钩子跳过，其中新 UDP 套件为 12 通过、1 跳过。
[App 验证 39180142599](https://github.com/SOLHK/Swirl/actions/runs/39180142599)
成功，实际 `CORE_TESTED_COMMIT` 与归档身份均为 `8d045ab`；但该 App 步骤
只运行已有的六个独立 peer 文件，不包含新 UDP 整套，不能补算其验收。
Windows 自检和跨平台缓冲修复随后执行了自己的精确提交 CI，结果见下文；
没有借用字体或先前 Core 的绿色记录。

### 修复后的精确提交验证

修复已原子提交为 `dc3ed5ef8ba9d3ec3d8d05e9ae0c7e810f19cfbb`，相关树为
`9078aeb88f993a62a3d380a1bfc840c516d51d99`。新
[Rust CI 39181705419](https://github.com/SOLHK/Swirl/actions/runs/39181705419)
与 [App 验证 39181705430](https://github.com/SOLHK/Swirl/actions/runs/39181705430)
独立于首次失败运行。

| 环境 | 实际结果 |
| --- | --- |
| Linux | Rust 154 通过、0 失败、0 ignored；14 个 Python 套件 197 通过、5 个完整 Qt 钩子跳过；新 UDP 为 12 通过、1 跳过，8.650 秒。 |
| macOS | Rust 154 通过、0 失败、0 ignored，两个新传输用例均实际通过；14 个 Python 套件 197 通过、5 跳过；新 UDP 为 12 通过、1 跳过，9.377 秒。首次失败的两种认证最大报文往返所在用例实际通过。 |
| Windows | Rust 154 通过、0 失败、0 ignored；fmt/check/clippy/Release 均成功。前置 16 个 Python 套件 232 通过、7 跳过；其中新 UDP 为 12 通过、1 Qt 钩子跳过，8.179 秒。随后兼容 CTest 2/2、原生 CTest 3/3、五个独立 Qt peer 钩子均实际通过。完整原生 `Swirl.exe` 编译和存在检查成功，实际编译约 551.20 秒。 |
| App 验证 | Rust 154、更新器自检 25 实际通过；既有六个 Python peer 套件 69 通过、5 跳过。`CORE_TESTED_COMMIT` 和源码归档身份均为 `dc3ed5e`，修复的九个非文档文件与归档逐字节一致，无已跟踪文件差异。此 App 仍不包含新 UDP Python 整套。 |

GitHub App 证据 ZIP 的 SHA-256 为
`9bc65dd4275ea96726beeb5ca0947c02841c7afb73ea38416845d31d9ded4b6d`，
与下载字节和 GitHub 摘要一致。所有跳过均独立列示；没有把三平台执行同一
Rust 测试的次数相加为独立新用例数量。

### Windows 原始 Qt 报告复核

已下载运行 `39181705419` 的四份完整 XML，排除 `initTestCase` 和
`cleanupTestCase` 后逐项解析：

| 报告 | 实际通过 | 跳过 | 失败 |
| --- | ---: | ---: | ---: |
| 原生 `SwirlRustCoreTests` | 45 | 6 | 0 |
| 原生导入边界 | 8 | 0 | 0 |
| 兼容导入边界 | 8 | 0 | 0 |
| 兼容 DNS 保护 | 2 | 0 | 0 |

两种构建的 `socks5TlsUriAliasesPreserveSecurity`、原生
`socks5UdpMappingPreservesTypedOptionsAndTls` 和规则事务的三个新增 slot
均有实际 PASS。六个 standalone peer 跳过保留原始原因；随后五个独立
Python Qt 钩子分别执行，其中 SS 钩子包含普通 SS 和 Loon SS 两个 Qt slot，
合计覆盖这六个入口，不能把它们填回已跳过的 XML 记录。新 UDP 钩子
为 1 通过、0 跳过、1.319 秒，含两种认证各自经过 Clash/INI 导入的四次
真实 UDP 转发。所有 Python 步骤合计 237 通过、7 跳过；这包含支持脚本
自检，并不是 237 个提供商联网用例。

四份 XML 无 Qt warning/critical/fatal。完整原生应用仍有原有的三条
C4834（`ScriptRunner.cpp` 两处、`GatewayChecks.cpp` 一处）和
GuiPrivate 配置提醒，未宣称构建零警告。原生 `Swirl.exe` 确实生成，但
该作业没有发布它的安装包，也没有运行完整原生 GUI 的实机验收。

Qt XML 产物 ID `12157296715` 的下载 ZIP SHA-256 为
`b49c0ed9d7fbe6049a19f0257bb4485034adac89bbe15606b2d2e6b3b09e71ee`，
与 GitHub API 摘要一致，保留至 2026-10-26 01:03:05 UTC。白名单永久摘录为
[跨平台及 App 证据](evidence/RUST_SOCKS5_UDP_PORTABLE_20261019.json) 和
[Windows 原生 Qt／完整应用证据](evidence/RUST_SOCKS5_UDP_WINDOWS_20261019.json)。

提供商 UDP、完整私有档案 0/18、真实目标记录 0/1558、REALITY/Vision、TUN、
长期性能和物理网络变化仍未验收。没有把 Windows 云端构建称为用户 D 盘
安装或 Windows 实机测试。
