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
未复制这两个项目的代码，没有新增代理内核、依赖包或修改 `Cargo.lock`。

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

Release `swirl-api` 的本地 SHA-256 为
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
保存；用户缓存、配置和私有字体不进入产物。本文件随实现提交时，该精确
源码的新阶段 CI 尚待执行；最终提交与运行结果须在完成后追加，不能借用
字体或先前 Core 的绿色记录。

提供商 UDP、完整私有档案 0/18、真实目标记录 0/1558、REALITY/Vision、TUN、
长期性能和物理网络变化仍未验收。没有把 Windows 云端构建称为用户 D 盘
安装或 Windows 实机测试。
