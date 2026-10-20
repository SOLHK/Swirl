# Swirl Core 固定验收与进度基线（baseline-v1，冻结范围）

## Vision 正式组合联网本地通过（2026-10-20）

REALITY P0 源码 `169e0cad` 已推送，其精确 Linux 与 App CI 已成功并核对原始工件。
后续源码保留原始 `xtls-rprx-vision`，完成具体认证流到 Vision 的方向所有权交接，
完整官方 Xray 组合菜单 **9/9 通过、0 失败/错误/跳过**，实际证明双向 Direct、
512 KiB TLS 1.3 数据与认证关闭、TLS 1.2 不进入 Direct。297 项 Rust 测试含 1 项
doctest 全通过。Qt 参数/加密恢复及组合门禁已接线，需精确 Windows CI 实际验证；
新增公网代理路径本地被 DNS EAI_AGAIN 阻塞，未宣称公网或供应商成功。
详见[当前 Runtime 交接](CORE_REALITY_RUNTIME_20261020.md)。
**冻结验收仍为 79 项 / 6 项完全通过 / 加权 10.83%。**

## REALITY 正式 Runtime 本地互通（2026-10-20）

本轮将已有 REALITY 握手接入正式 Rust 异步出站、VLESS 与 Runtime 转发，
补齐原生 IR/订阅及 Qt 配置的严格映射。固定完整官方 Xray 的本地 P0 菜单
**7/7 通过，0 失败/错误/跳过**，实际访问独立 HTTP 与验证证书的 HTTPS 目标，
覆盖认证拒绝、路由、并发分段、A/B 切换、半关闭、取消和超时。
此处是带源码/二进制身份的本地受控测试；精确提交 CI 与 Windows Qt 尚待执行。
Vision 所有权组件准备已测试，但正式非空 flow 仍被拒绝，未计组合联网通过。
仅显式 `fingerprint=rustls` 可用，未更改既有私人节点指纹、未访问私人订阅或供应商。
详情及失败原因见[当前 Runtime 交接](CORE_REALITY_RUNTIME_20261020.md)。
**冻结验收仍为 79 项 / 6 项完全通过 / 加权 10.83%。**

## S6 精确 CI 与 S7 产品分流证据（2026-10-20）

S6 `598a8a7` 的 [Rust CI](https://github.com/SOLHK/Swirl/actions/runs/39297859906)
已完成 Linux、macOS、Windows 三平台成功；[App/Core validation](https://github.com/SOLHK/Swirl/actions/runs/39297859893)
成功。Windows 实际完成 Qt/DPAPI 订阅导入、保存恢复、四协议 Rust 原生出站、
独立 HTTP/HTTPS 目标与 `Swirl.exe` 编译；[原始产品报告](evidence/subscription-product-chain/s6-ci-windows/)
保留四协议各 7 条 HTTP 路径、A/B 5/4、每项 1 次 HTTPS 正常关闭及 0 目标错误。

S7 `19afd34` 的 [Rust CI](https://github.com/SOLHK/Swirl/actions/runs/39300230774)
已通过 Linux/macOS/Windows，Windows Qt/DPAPI 产品测试与完整 `Swirl.exe` 编译均执行成功；
[App/Core validation](https://github.com/SOLHK/Swirl/actions/runs/39300230656) 成功。
[S7 原始报告](evidence/subscription-product-chain/s7-ci-windows/)显示四协议各
10 条 HTTP 路径、A/B 6/6、HTTPS 完整关闭各 1 次、0 目标错误，新增规则覆盖
DOMAIN-SUFFIX、DOMAIN-KEYWORD、DST-PORT。全部为合成订阅和独立 loopback
对端。用户重新提供的私人订阅只在仓库外 DPAPI 加密缓存并内存检查：59 条 VLESS/REALITY、
55 条 Vision，59 条原始 URI 精确保留，可执行候选 0；未发生供应商代理连接或降级。
因此不满足 A08/F03 与完整协议档案验收。
正式分子保持 **79 项 / 6 项 / 10.83%**。

## S7 本地产品分流复核（2026-10-20）

在 S6 `598a8a7` 基线上扩展 Windows Qt 真实产品链测试：新增 DOMAIN-SUFFIX、
DOMAIN-KEYWORD、DST-PORT 的独立 A/B 出口及实际 HTTP 目标断言，并用另一目标端口
确认终结 MATCH 拒绝。HTTP CONNECT、SOCKS5、SS AEAD、普通 VLESS TCP 四个子项
在本机 Qt/DPAPI → Rust → 独立对端 → 目标测试中通过；每项 TLS 验证与正常关闭仍保持。
原始本地记录见 `docs/evidence/subscription-product-chain/s7-local/`。S6 的 Windows
完整 CI 尚未终结；本地结果不能代替精确提交的 CI 或私人订阅验收。正式进度保持
**79 项 / 6 项 / 10.83%**。

## S6 Windows policy fixture checkpoint (2026-10-20)

S5 source 0416fe09: Linux/macOS/App success; Windows independent SS policy fixture failed before Qt/DPAPI and full Swirl.exe. New scoped S6 patch selects TCP/UDP jointly allowed candidates and preserves immediate access-denial errors; exact-source CI is pending. Read `docs/CORE_SUBSCRIPTION_S6_HANDOFF_20261020.md`. Frozen 79 / 6 / 10.83% unchanged.

本基线固定 A–F 的 79 项验收范围和权重。**已验收进度 10.83%（6 项），不是代码实现率、可联网节点比例或剩余工期比例。** 大量已有实现仍未满足整项门禁，不能给部分实现随意加分。

基线最初核对来源为 `4e993d62884b138d4ee5bbe604e90d85cde6bb33` 的 Rust 实现及精确提交三平台 CI、已加密保存的 `capture-20261018-065548` 语料和 Qt 事务修改。2026-10-19 新增 E11/E12：规则编辑事务已通过精确提交 Windows/三平台验证；`8d045ab` 已实现 SOCKS5 出口 UDP，B05 从“未实现”更新为“部分实现”。首次新增 UDP CI 的 Windows/macOS 失败继续保留；修复提交 `dc3ed5e` 已独立通过三平台、Windows Qt 和完整原生应用编译。本轮供应商刷新次数仍为 0。

同日较早阶段的 E13–E16 保留 Qt REALITY/uTLS 与 sing-box 导入保护、REALITY 握手基础和 Windows 对端修复证据；B13 当时从“未实现”变为“部分实现”。本次新增 E17–E19：已有 R2/R1 精确证据、正式 REALITY R3 成熟对端 CI、Vision R2 异步 framing/内层 TLS 识别子阶段。B13 继续部分实现，B14 从“未实现”变为“部分实现”；两项均未满足完整产品/供应商门禁，79 项、6 项已验收和 10.83% 权重完全不变。

R3 源码 `5ad68bcb22a23573d462cbfd972c7120093f504a` 的 [Rust 39239280852](https://github.com/SOLHK/Swirl/actions/runs/39239280852) 已在 Linux/macOS/Windows 完整成功，Windows Qt/原生应用编译亦成功；[App 39239280949](https://github.com/SOLHK/Swirl/actions/runs/39239280949) 成功，成熟对端 12 项/13 会话、0 失败/跳过与精确归档源码已核对。常规 Qt 的 6 个 peer hook 跳过保留，随后 5 个独立 wrapper 分别执行六槽，不把跳过改写为通过。

Vision 初次源码 `f3ce257f14e59e82977d89ac4be436d08926c6b8` 在 [Rust 39243009089](https://github.com/SOLHK/Swirl/actions/runs/39243009089) 的 Linux 成功、macOS/Windows 失败，Windows 后续 Qt/原生应用门禁未运行；[App 39243009132](https://github.com/SOLHK/Swirl/actions/runs/39243009132) 成功。第 4 项 Direct 拒绝先返回 InvalidData 的原失败没有改写。

record 修复 `0be68231b15c1e4f69b138cda7bae0a3930d956b` 的 [Rust 39246770262](https://github.com/SOLHK/Swirl/actions/runs/39246770262) 已在 Linux/macOS 成功，[App 39246770049](https://github.com/SOLHK/Swirl/actions/runs/39246770049) 成功；这些环境实际通过 272 Rust + 1 doctest、5 项新 record 回归、41 guard 与成熟 R3/Vision 测试。Windows 则在旧 DNS fixture 的 UDP 保留段绑定处失败，R3/Vision/Qt 未执行；[原失败](evidence/vision-r2/record-ci-windows-failure.json) 单独保留，不按其他环境结果补算通过。

已推送 Windows 端口 fixture 修复 `7c8affbaeb0a32aa9dbf08f1eff5a7221ab4c167`：只读 netsh 查询 TCP/UDP 保留段并集之外的候选，显式选择且同时持有两种 socket；未知 10013/查询失败不吞、8 次冲突预算不变，新增 6 项选择器回归。最终本地 DNS 37 / `test_policy_groups.py` 16 / guard 41 共 94 项通过、无失败/跳过；[本地证据](evidence/vision-r2/port-pair-local.json) 保留四文件哈希，精确 [Rust 39250098899](https://github.com/SOLHK/Swirl/actions/runs/39250098899) 的 Linux/macOS/Windows 完整作业与 [App 39250098637](https://github.com/SOLHK/Swirl/actions/runs/39250098637) 均成功，包括 Windows Qt、独立 wrapper 与完整应用编译。最终 [Linux](evidence/vision-r2/ci-linux.json)/[macOS](evidence/vision-r2/ci-macos.json)/[Windows](evidence/vision-r2/ci-windows.json)/[App](evidence/vision-r2/ci-app.json) 保存精确源码、原始结果和跳过原因；App 265 个归档文件均匹配该 tree。并发字体提交 aab06bf/501099da/7dfbdda/b3ac464/6cba41ff/d175d817 均保留，固定验收不因此加分。

独立核对将 A02 降为部分实现：18/18 parsed 仅证明外层格式与节点解析，INI 非节点节正文未全部语法/语义验证。没有为提高百分比缩窄该项范围。详细可重复核对依据见证据索引和 `evidence/SELF_DEVELOPMENT_PROGRESS_V1.json`。

本轮新增 E20：修复 Rust/Qt 订阅字段转换边界及 Windows 端口分配单元测试隔离；
详见 [订阅产品链交接](CORE_SUBSCRIPTION_PRODUCT_CHAIN_20261019.md)。六项新的 Rust 回归
先复现原缺陷，再通过修复；Qt 新增真实加密 NodeStore 销毁/重建的参数往返测试，需由新源码
Windows CI 验证。用户另行授权的新订阅为 59 个 REALITY 节点，其中 55 个含 Vision；仅保留并
明确拒绝当前不支持的执行，没有将其计为联网成功。**79 项 / 6 项已验收 / 10.83% 不变。**

S1 实际源码为 [`292df3ba9763414947ec9b5dffa7886c45a00879`](https://github.com/SOLHK/Swirl/commit/292df3ba9763414947ec9b5dffa7886c45a00879)。
S2 补齐同一订阅内规则节点引用、原生选择失败回滚、等待确认期间重连隔离、选择丢失不得默认直连及
退出显式 DIRECT 的模式一致性。新增独立 Python 代理 A/B 与单独 HTTP/HTTPS/echo 目标，分别设置
Rust 测试宿主持久化菜单和 Windows 真实 Qt/DPAPI/控制器菜单，并加入三平台与 App 适用 CI。
新增测试的数量不改变冻结验收；Windows 实际执行和精确源码 CI 终态须另行记录。

S2 已推送 `593e7cddc360cf7f51d9fdc988e6cf8fd99aea96`，本地新版整链 8 通过 / Windows Qt 1 明确跳过，
44 项 CI 防退化通过；[Rust 39281808343](https://github.com/SOLHK/Swirl/actions/runs/39281808343) /
[App 39281808355](https://github.com/SOLHK/Swirl/actions/runs/39281808355) 于 16:03 UTC 仍排队。
S3 继续修复显式 DIRECT 绕过候选节点能力检查及空值 SNI 别名覆盖，Qt 回归尚待实际 Windows 执行；
GitHub 官方 Actions 事故不能当作测试通过，也不修改任何冻结验收状态。
S2 [完整本地菜单与原始日志](evidence/subscription-product-chain/s2-existing/summary.json) 24/24 命令成功，
包含五项 Rust 门禁、278 个测试加 1 doctest、两组独立向量与现有 Python 261 通过 / 5 Qt 跳过；
新增整链 8 通过 / 1 Qt 跳过另行保留。与并发字体 83efbaac 的变更无重叠，后者已保留。

## 1. 固定范围、状态和计算规则

E20 最新 S5：S4 已推送 `a066f7d4c8acb96f5d6a46cee5700b2590328b64`。后续真实 Qt HttpProxy → Rust
对照发现直连 Qt 诊断未覆盖的 TLS 关闭失败，因此 S5 为 Qt 产品菜单明确由测试客户端发起关闭；
独立目标禁用 ragged EOF 隐藏，依次要求认证 TLS EOF、unwrap 和原始 TCP EOF，完成后才计数。
便携菜单保留服务端主动关闭，裸 TCP FIN 对照仍产生 SSLEOFError 并失败。最终本地四协议 Qt 客户端/
Rust 代理诊断、8 项便携菜单通过，但不冒充 Windows C++/DPAPI 产品验收。
S4 Windows 精确 CI 已证实四次 unwrap SSLEOFError、完整关闭计数为零，完整应用构建跳过；
该失败保留，S4 Linux/macOS/App 为成功，不能用来替代 S5 结果。

App 旧协议菜单此前缺 Inspector 环境而跳过一个订阅用例，现增加已有 Release Inspector 的导出与
可执行文件检查；新增 guard 先复现失败，修复后 45 guards、生成器一致性及 SOCKS4 9 通过 / 1 Qt
明确跳过均通过。新版精确 CI 与 Windows 完整应用仍须实际执行；详见[统一 S5 交接](CORE_SUBSCRIPTION_PRODUCT_CHAIN_20261019.md#s5-verify-the-qt-clients-close-exchange-through-the-real-proxy-path)。
**79 项 / 6 项已验收 / 10.83% 完全不变。**

E20 此前 S4 接续：S3 已推送 `41555465b72fd59d42bc473f0d097c93e210c240`；S2/S3 的 Linux、macOS、
Windows 与 App 新整链原始附件均已核实各 8 通过 / 1 Qt 明确跳过。此前 Actions API 排队状态存在
传播延迟，不能据其推断实际未执行。S1 的 Linux 双地址族端口竞争及 Windows SS TCP 10013 失败保留；
49666 不在日志排除范围内，未推测具体占用者。S2/S3 Windows 四种协议 Qt 槽实际转发成功，但独立 HTTPS
目标关闭检查失败，整项仍失败，其后完整应用构建跳过。

S4 修复测试对端实际端口预留所有权，改用显式正常关闭、严格证书验证的 QSslSocket HTTPS 测试客户端；
没有修改产品代理安全策略。独立目标继续要求 TLS unwrap、原始 EOF，新增每协议 TLS 完整关闭计数及
安全错误定位。本地双地址族菜单 12/12、SS 策略菜单 20/20、新版便携整链类 8/8 通过（该命令未选择
Windows Qt 类），新 Windows/完整应用和精确源码 CI
仍须实际验证。[统一交接](CORE_SUBSCRIPTION_PRODUCT_CHAIN_20261019.md) 记录失败来源与限制；并发字体
5cb42619 已保留。**冻结 79 项、6 项已验收、10.83% 完全不变。**

状态只能是：**已验收 / 部分实现 / 未验证 / 未实现**。已验收必须满足该行明确范围的全部契约，并有可定位源码、环境、命令或独立对端、结果和未解决问题；部分实现、跳过、未验证和未实现都不计入通过分子。未知不是通过，也不等于已经证明失败。

本基线已验收分子经逐项核对：A01、C01、C02、C03、C04、C06。公式为 `20×1/8 + 20×5/12 = 10.833333…%`，显示为10.83%。其余73项不计入完成分子。

| 阶段 | 固定条目数 | 固定权重 | 阶段内计分 |
|---|---:|---:|---|
| A | 8 | 20% | 每项等权 20/8；仅已验收计1，其余计0 |
| B | 31 | 25% | 每项等权 25/31；仅已验收计1，其余计0 |
| C | 12 | 20% | 每项等权 20/12；仅已验收计1，其余计0 |
| D | 8 | 15% | 每项等权 15/8；仅已验收计1，其余计0 |
| E | 10 | 10% | 每项等权 10/10；仅已验收计1，其余计0 |
| F | 10 | 10% | 每项等权 10/10；仅已验收计1，其余计0 |

总计 **79项，100%权重**。总体公式：`Σ阶段权重 ×（该阶段已验收项 / 该阶段固定项数）`。不对“部分实现”任意给0.3或0.5分。即使达到100分，仍须通过第7节全部最终门禁才可宣布完成。

冻结方法：本清单已固化为 `baseline-v1`；条目ID、最低支持档案、等权规则和验收门禁不得为改善数字而删除/拆分/合并。每次状态变更保存：旧状态、新状态、源码SHA/相关树哈希、证据路径、环境、日期、失败/跳过和继承依据。发现新的真实必要协议/格式时追加ID并发布v2，同时保留v1同口径趋势；不得静默改变分母。专有语义无法实现则保留阻塞，不以DIRECT或删范围计完成。

用户的“其他实际语料确认的必要协议/传输”是范围扩展规则，不是一个可以自动判通过的空白项。B阶段固定覆盖当前明确目标；新确认项必须按上述版本规则扩展。性能阈值、时长、负载矩阵也须在运行前冻结，不能看结果后降低。

## 2. 证据索引与优先级

最新专项结构化证据 > 对应源码/产物身份 > 最新交接顶部 > 历史说明。本轮 E13–E16 的精确 SHA、失败、跳过和后续修复结果见 [统一证据](evidence/REALITY_FOUNDATION_AND_IMPORT_20261019.json)。2026-10-19 的 E11/E12 已在线核对 GitHub 精确提交、运行与实际日志；其他历史证据保留原环境和日期，不视为本轮重测。

| ID | 来源 | 使用边界 |
|---|---|---|
| E00 | [用户最新A–F总指令 + 仓库合并约束](../docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md) | 以本会话最新A–F排序为准；旧文档A–G字母不是本基线阶段定义 |
| E01 | [当前INI结构验证阶段](../docs/RUST_INI_STRUCTURE_20261018.md) | 源码4e993d6；本机136 Rust/11导入/Qt集成成功；UI超时未解决；无新供应商节点实测 |
| E02 | [新窗口采集与离线证据](../docs/evidence/RUST_CAPTURE_065548_20261018_VERIFIED.json) | 18入口/17响应；全配置执行未验证；新真实节点测试0 |
| E03 | [本任务离线完整性审计](D:/Codex/outputs/capture-065548-integrity.json) | 原始/解码哈希、DPAPI往返、18映射和时间范围通过；无网络 |
| E04 | [Loon SS历史精准来源验收](../docs/evidence/RUST_LOON_SS_20261018_VERIFIED.json) | 产品4ea4139，测试d7e79df；两组各3个固定SS样本的证据不得外推 |
| E05 | [Rust能力和边界说明](../core/README.md) | 含历史段落：旧16份语料/失败缓存未实现/真实节点未测等必须由较新专项证据覆盖 |
| E06 | [原生策略与基础路由证据](../docs/RUST_NATIVE_POLICIES.md) | 同时参照RustCoreTests.cpp中独立实际路由测试；不以测试数量计分 |
| E07 | [当前完整导入代码事实](../src/Swirl.Quick/engine/NodeImportService.cpp) | NodeImporter/Normalizer/NodeStore/EngineController/RustCoreEngine：当前单文件事务及有限Clash整文档profile；见RUST_ATOMIC_SUBSCRIPTION_20261018.md |
| E08 | [DNS失败缓存精准验收](../docs/RUST_DNS_FAILURE_CACHE_20261018.md) | b903b8b已验收；不能沿用旧README称其未实现 |
| E09 | [最近取得的CI离线快照](D:/Codex/outputs/ini-ci-final-check.json) | 最新核实4e993d6三平台和Core implementation validation均success；新Qt代码须独立CI |
| E10 | [当前交接入口](../docs/CONTINUE_DEVELOPMENT.md) | 顶部最新阶段优先，以下历史段落不能覆盖新证据 |
| E11 | [SOCKS5 出口 UDP 实现与独立证据](RUST_SOCKS5_UDP_20261019.md) | `8d045ab` 实现及 `dc3ed5e` 修复；后者三平台和 Windows Qt/完整原生应用编译通过，原生 Qt 45 通过/6 钩子跳过且另跑五个独立钩子；首次 Windows/macOS 失败保留，真实提供商与完整档案未验收 |
| E12 | [规则编辑事务 Windows 证据](evidence/RULE_EDIT_TRANSACTION_WINDOWS_20261019.json) | `6dcc212` 三平台通过；Windows 44 实际通过、5 独立 peer 钩子跳过，三项新事务测试实际通过 |
| E13 | [REALITY/uTLS 导入保护](REALITY_IMPORT_SECURITY_20261019.md) | `4d73f65` 三平台、Windows 原生/兼容 Qt、五个独立 Qt 对端与完整原生应用通过；拒绝不完整安全配置，未启用 REALITY/Vision |
| E14 | [REALITY 握手认证基础](REALITY_HANDSHAKE_FOUNDATION_20261019.md) | `daad7a0`；34 项新 REALITY 测试、独立 Python/OpenSSL 向量、实际 rustls verifier/provider 集成；TLS 后端 transcript 接口和完整 REALITY 对端仍缺失；原 Windows DNS 对端失败保留 |
| E15 | [sing-box 传输语义](SINGBOX_TRANSPORT_SECURITY_20261019.md) | `e0534f4`；本地同组 Qt 旧实现 2 项失败、修复 5 项通过；包含相同 Qt 源码的 `a429d5b` 已通过原生/兼容 CTest、导入持久化、独立钩子和完整原生应用；旧 SS fixture 失败保留 |
| E16 | [Windows 测试对端修复](LOOPBACK_PAIR_ALLOCATION_20261019.md) | `a429d5b`；DNS 先选 TCP，SS 保留原错误/清理；本地 31 DNS、16 policy 通过；精确 CI 三平台各 189 Rust、201 Python/5 跳过，Windows Qt 四 XML 71 实际通过/6 跳过，完整原生应用成功 |
| E17 | [REALITY R2](REALITY_TLS_ENGINE_20261019.md)、[Vision R1](VISION_FRAMING_FOUNDATION_20261019.md)及[历史精确 CI](CORE_REALITY_VISION_HANDOFF_20261019.md#保留的上一阶段证据) | `611edcff` / `5b55ab33` 各自三平台与 App 已成功；是已入库 TLS/R1 framing 证据，本次未重做，不能替代新提交 CI |
| E18 | [REALITY R3 专项](REALITY_XRAY_INTEROP_20261019.md)、[本地结果](evidence/reality-r3/local-xray-final-summary.json)及[精确 CI](CORE_REALITY_VISION_HANDOFF_20261019.md#本次源码与精确-ci) | `5ad68bcb`；固定官方 Xray/REALITY/Go、重复构建身份；12 项/13 会话，严格 EOF/凭据隔离/回收。Linux/macOS/Windows 与 App 全部 success，含 Windows Qt/原生应用；仅受控 TLS 组件互通 |
| E19 | [Vision 专项](VISION_ASYNC_INSPECTION_20261019.md)、[record 本地](evidence/vision-r2/record-boundary-local.json)、[Linux](evidence/vision-r2/record-ci-linux.json)/[macOS](evidence/vision-r2/record-ci-macos.json)/[App](evidence/vision-r2/record-ci-app.json)、[Windows DNS 失败](evidence/vision-r2/record-ci-windows-failure.json)、[端口本地](evidence/vision-r2/port-pair-local.json) | 初始 f3ce257f macOS/Windows 失败保留；0be68231 Linux/macOS/App 成功、Windows DNS 失败且协议/Qt 未运行。当前端口源码 7c8affbaeb0a32aa9dbf08f1eff5a7221ab4c167，本地 94 项通过；该精确 SHA 三平台 Rust 与 App 完整成功，272 Rust + 1 doctest、R3 12 项/13 会话与 Vision 4 项通过。DirectReady/所有权/HRR/组合/产品链未完成 |
| E20 | [订阅产品整链](CORE_SUBSCRIPTION_PRODUCT_CHAIN_20261019.md)、[S1 本地原始证据](evidence/subscription-product-chain/s1-local.json) | S1 参数转换修复已推送 292df3ba；S2 节点切换/规则叶子与独立目标菜单区分便携测试宿主和 Windows 产品对象范围。REALITY/Vision 供应商节点仍无联网验收；新源码 CI 不得引用旧结果替代 |

## 3. A–F固定验收清单

### A：订阅完整执行链（权重20%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| A01 | 授权采集、逐份加密、哈希、截止和原始入口映射 | 已验收 | E02/E03；本轮18入口、17响应全部HTTP200、落盘/解密/哈希匹配 | 仅本轮固定清单；未授权引用不应自动下载 |
| A02 | 冻结语料的完整正文结构与节点解析 | 部分实现 | E01/E02；18/18外层格式及节点解析通过，INI所有节头先校验 | 非节点节正文语法/客户端语义未完成，不能称完整正文通过 |
| A03 | 全部10个格式档案的字段语义与错误输入兼容 | 部分实现 | E01/E05/E07；已有Clash、sing-box、URI/Base64和若干INI适配 | 逐格式版本/未知项/异常输入验收矩阵未完成 |
| A04 | 完整原文、来源、未知字段及转换诊断进入可持久化IR | 部分实现 | E01/E07；Rust保留原始正文，Qt目前主要保留节点级来源 | Qt完整文档来源及全局字段尚未统一加密保存 |
| A05 | 节点到原生IR的无损转换与稳定身份 | 部分实现 | E02/E07；450候选记录，NodeStore按来源/名称/协议稳定UUID | 其余记录的执行阻塞仍在；跨文档完整引用转换未验收 |
| A06 | 订阅策略组、DNS、顺序规则到Qt产品配置 | 部分实现 | 当前阶段接入自包含Clash组/规则和原生严格图校验；其余格式与DNS未完成 | 候选节点引用、严格DNS语义、未知全局字段和直接节点规则目标需接入 |
| A07 | 完整文档导入、刷新、失败及崩溃的原子持久化与恢复 | 部分实现 | 当前阶段采用稳定UUID准备及单个DPAPI/QSaveFile快照；保留旧sidecar只读迁移 | 所有格式、进程崩溃/掉电和恢复矩阵仍需完成 |
| A08 | 18份冻结文档的导入→选组/DNS/路由→Rust→联网整链 | 未验证 | E01/E02 complete_configuration_execution_supported=false | 逐文档完成整链；不能由节点解析或少量SS成功替代 |

### B：协议与传输（权重25%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| B01 | HTTP/HTTPS CONNECT及对应原生入口档案 | 部分实现 | E05/E06；独立协议/Qt证据 | 当前固定矩阵的全门禁与真实出口覆盖未完成 |
| B02 | SOCKS4 TCP档案 | 部分实现 | E05/E06；独立对端和Qt映射/转发 | 全部门禁/真实节点覆盖未完成 |
| B03 | SOCKS4a TCP档案 | 部分实现 | E05/E06；远端域名解析语义已独立测试 | 全部门禁/真实节点覆盖未完成 |
| B04 | SOCKS5 TCP与用户名密码认证档案 | 部分实现 | E05/E06；原生入口/出口已有实现 | 全部门禁/真实节点覆盖未完成 |
| B05 | SOCKS5出口UDP档案 | 部分实现 | E11；真实出口关联、认证、UDP双向转发、关闭、隔离、有界资源与Qt导入路径 | 标准无认证/用户名密码范围；TLS+UDP明确拒绝，真实提供商/NAT/长期负载与完整七门禁未验收 |
| B06 | Shadowsocks传统AEAD TCP（三种已列密码套件） | 部分实现 | E04/E05；独立认证/边界/Qt和两组历史严格HTTPS样本 | 全目标节点/本轮语料/长期稳定性尚未验收 |
| B07 | Shadowsocks传统AEAD UDP | 部分实现 | E05；有界关联及独立Python对端 | 供应商真实UDP未验收 |
| B08 | Shadowsocks 2022档案 | 未实现 | E05明确拒绝 | 独立状态机、重放/认证、传输和产品验证 |
| B09 | SSR档案 | 未实现 | E05 Rust Outbound不提供 | 先冻结公开可验证协议/混淆组合；不能将识别当执行 |
| B10 | Trojan TLS档案 | 部分实现 | E01/E05；严格TLS独立对端 | 不安全源配置被正确阻止；真实严格TLS节点覆盖待补 |
| B11 | VLESS v0 TCP/通用TLS档案 | 部分实现 | E05/E06；独立协议和Qt转发 | 真实提供商及完整目标范围未验收 |
| B12 | VMess档案 | 未实现 | E04/E05明确缺项 | 独立状态机、版本、认证、数据流与互操作 |
| B13 | VLESS REALITY扩展 | 部分实现 | E17/E18；原生 REALITY TLS 1.3、双方 Finished 与官方 Xray/REALITY 的 12 项/13 会话独立互通，保留 EOF、凭据隔离与回收证据 | 生产异步 REALITY、浏览器指纹/任意伪装站点、完整 VLESS/REALITY/Vision 组合、订阅 IR/路由/Qt 与真实提供商仍未验收 |
| B14 | VLESS Vision扩展 | 部分实现 | E17/E19；R1 framing、增量内层 TLS、有界异步 framing；0be68231 的 Linux/macOS/App 实际通过 272 Rust + 1 doctest、成熟 4 项，Windows DNS fixture 失败导致协议/Qt 未执行；当前端口修复 7c8affbaeb0a32aa9dbf08f1eff5a7221ab4c167 本地 94 项通过，精确三平台 Rust 与 App 完整成功；此前原失败均保留 | DirectReady、原始 socket/缓冲所有权交接、HRR、真实 REALITY+Vision 组合及订阅 IR/路由/Qt/供应商整链仍未完成 |
| B15 | WebSocket/WSS传输及已承诺VLESS/Trojan组合 | 部分实现 | E05/E06；分片、背压、关闭预算和Qt已有证据 | 组合矩阵与真实提供商/长连接覆盖未完整 |
| B16 | gRPC传输 | 未实现 | E04/E05明确缺项 | HTTP/2基础依赖可用但代理传输状态机需自研 |
| B17 | XHTTP传输 | 未实现 | E04/E05明确缺项 | 版本/模式矩阵、取消、复用与真实互操作 |
| B18 | Hysteria v1档案 | 未实现 | E00既定协议范围，E05无原生执行 | 资料/样本/必要范围固定后实现，未验证不得删除 |
| B19 | Hysteria 2档案 | 未实现 | E04/E05明确缺项 | QUIC认证、TCP/UDP、拥塞/关闭与产品接入 |
| B20 | TUIC档案 | 未实现 | E04/E05明确缺项 | 明确版本、QUIC会话、TCP/UDP与互操作 |
| B21 | QUIC/HTTP3必要传输组合 | 未实现 | E04/E05明确缺项 | 采用审查后的基础库，Swirl拥有代理会话执行逻辑 |
| B22 | AnyTLS档案 | 未实现 | E00既定协议范围，E05无原生执行 | 协议版本/认证/复用/互操作 |
| B23 | Naive档案 | 未实现 | E00既定协议范围，E05无原生执行 | 明确HTTP2/3组合与认证/互操作 |
| B24 | Snell档案 | 未实现 | E00既定协议范围，E05无原生执行 | 专有或未公开语义必须明确阻塞，不虚构实现 |
| B25 | Mieru档案 | 未实现 | E00既定协议范围，E05无原生执行 | 版本/传输/认证与互操作 |
| B26 | WireGuard档案 | 未实现 | E00既定协议范围，E05无原生执行 | 协议执行、路由/DNS和Windows产品整链 |
| B27 | SSH代理档案 | 未实现 | E00既定协议范围，E05无原生执行 | 严格主机身份/认证、转发与产品接入 |
| B28 | 代理多路复用及链式代理执行 | 未实现 | E00范围；E05 VLESS multiplexing明确拒绝；Qt只保留部分detour | 绑定协议的已冻结组合、背压、取消和防循环 |
| B29 | HTTP/2代理传输扩展 | 未实现 | E00范围，E05无原生执行 | 不把库依赖或h2配置识别当协议执行 |
| B30 | HTTPUpgrade传输扩展 | 未实现 | E00范围，E05无原生执行 | 握手校验、边界、Qt和实际对端 |
| B31 | ShadowTLS扩展 | 未实现 | E00范围，E05无原生执行 | 版本、身份/认证和安全负面测试 |

### C：DNS、规则与策略（权重20%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| C01 | 原生UDP/TCP DNS及严格DoT/DoH协议与Qt映射（不含分流/bootstrap） | 已验收 | E05/E06；独立DNS对端、严格证书和Qt映射证据 | 历史精准范围可继承；不能代表本机所有公网DoH成功 |
| C02 | A/AAAA/CNAME与TTL正缓存、大小写规范化、有界资源 | 已验收 | E05/E06已有实现及独立DNS验证 | 保留配置更换和资源上限契约 |
| C03 | SOA证明的NXDOMAIN/NODATA负缓存 | 已验收 | E05/E06独立负缓存证据 | 不能把未证明空答案当负缓存 |
| C04 | 上游失败恢复、备用解析器及有界失败缓存 | 已验收 | E08；b903b8b完成一秒失败缓存、原错误码与配置换代清理 | 此前README仍称未实现的段落已过时 |
| C05 | DNS分流、Fake-IP、bootstrap与防泄漏完整策略 | 未实现 | E05明确缺项 | 三者须逐项验收，不得退化成系统/明文解析 |
| C06 | 现有基础规则的顺序与优先级 | 已验收 | E05/E06；domain/suffix/keyword、CIDR、source CIDR、port、MATCH独立路径 | 仅列举的基础匹配；高级规则不在本项冒领 |
| C07 | 复杂策略组及配置/健康更新 | 部分实现 | E05/E06；嵌套手动、url-test/fallback/显式round-robin | 默认哈希、更多自动嵌套及完整订阅整合待补 |
| C08 | GEOIP/GEOSITE/MRS执行及更新 | 未实现 | E05/RustCoreEngine明确拒绝智能MRS会话 | 导入、规则执行、数据更新失败与回滚 |
| C09 | 进程分流 | 未实现 | E05明确未迁移 | Windows进程归属、生命周期和权限边界 |
| C10 | IPv4/IPv6全目标兼容 | 部分实现 | E05；多地址拨号/部分独立IPv6证据 | 所有协议、DNS、UDP/TUN和实际网络矩阵未覆盖 |
| C11 | 网络切换、超时、重试与流量统计 | 部分实现 | E05；有界TCP竞速、静态错误阶段、快照统计 | 真实网络切换、恢复及统计一致性待验收 |
| C12 | 断开清理、失败不降级DIRECT、不重放与隐私保护 | 部分实现 | E05/E06；不可变会话、失败保留旧计划已有证据 | 整产品/TUN/异常退出的全路径审计与泄漏测试待补 |

### D：Windows TUN与系统接管（权重15%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| D01 | Windows虚拟接口生命周期 | 未实现 | E01/E05；Rust TUN尚未接入 | 驱动/API权限、创建/关闭/残留恢复 |
| D02 | TUN TCP数据路径 | 未实现 | E01/E05 | 独立内核转发、并发、MTU与取消 |
| D03 | TUN UDP数据路径 | 未实现 | E01/E05 | 映射、DNS、分片/MTU、超时与回收 |
| D04 | TUN DNS接管与防泄漏 | 未实现 | E01/E05 | IPv4/IPv6、不同解析协议与绕过探测 |
| D05 | 系统路由安装、所有权及恢复 | 未实现 | E01/E05原生TUN未完成 | 与用户/其他软件修改冲突的恢复契约 |
| D06 | Rust模式系统代理开关及所有权保护 | 部分实现 | E05；既有C++SystemProxySession保留 | 完整Windows实际接管、他人接管保护和恢复证明 |
| D07 | 网络变化和休眠唤醒恢复 | 未验证 | E01/E05没有当前原生完整证据 | 切网/断网/唤醒真实测试 |
| D08 | 崩溃退出、防火墙与系统状态保护 | 未验证 | E00契约；E01未执行系统修改 | 异常退出恢复，不覆盖用户后续更改；敏感操作需批准 |

### E：稳定性与性能（权重10%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| E01 | 节点连接耗时及延迟分布 | 部分实现 | E04有少量固定SS DNS/TCP耗时 | 预定样本规模、P50/P95/P99及同环境可复现 |
| E02 | TCP吞吐 | 未验证 | E05有Benchmark工具；本次未核验正式报告 | 固定硬件、负载、时间与阈值 |
| E03 | UDP吞吐与丢包 | 未验证 | E05有独立功能测试，不等于性能 | 固定包长/速率/丢包/抖动/正确性阈值 |
| E04 | 高并发与资源上限 | 部分实现 | E05有并发及有界资源设计/回归 | 长期压力下正确性、耗尽恢复与公平性 |
| E05 | DNS查询/缓存性能 | 未验证 | E08功能与恢复证据不等于性能 | 缓存命中/未命中/失败P50/P95/P99 |
| E06 | CPU、内存及泄漏 | 未验证 | E01本阶段未执行完整性能验收 | 空闲、活跃、长期运行的基准与资源回收 |
| E07 | 长时间运行 | 未验证 | E01/E04明确未执行长跑 | 冻结时长、负载、错误率与泄漏阈值 |
| E08 | SSE/WebSocket及Codex登录和持续输出 | 部分实现 | E05有WS协议/关闭测试；真实Codex CLI仍可选跳过 | 当前Rust模式真实持续输出、登录、恢复与长连接 |
| E09 | 弱网、丢包、断线恢复 | 未验证 | E01/E04未给完整实测 | 冻结损伤参数，不延长产品超时掩盖问题 |
| E10 | 启动、停止、退出与资源回收压力 | 部分实现 | E05/E06有生命周期及取消测试 | Windows重复启停、负载中退出和异常退出矩阵 |

### F：产品接管与交付（权重10%）

| ID | 固定验收项 | 当前状态 | 证据 | 缺口/边界 |
|---|---|---|---|
| F01 | 完整Windows Rust Swirl构建 | 部分实现 | E08历史完整应用构建；E01当前Qt集成构建通过 | 最终候选完整应用/依赖包精准SHA与可重复构建 |
| F02 | 完整Qt产品真实运行 | 未验证 | E01有测试程序但未完成完整GUI产品验收 | 实际启动、导入、操作、退出；不能替代为CTest |
| F03 | 真实订阅、选节点、分流与联网产品链 | 未验证 | E01/E02 full configuration=false | 依赖A08与当前真实网络矩阵 |
| F04 | 完整产品TUN和系统代理验收 | 未验证 | E01/E05 TUN未完成 | 依赖D01-D08及用户批准的实际系统操作 |
| F05 | 现有UI/动画/设置/用户数据回归 | 部分实现 | 修正进程局部DLL路径和D盘测试隔离后，原45秒上限外观测试5.68秒通过，设置跨进程恢复通过 | 全部UI/动画/用户数据和安装生命周期矩阵仍未完成 |
| F06 | 升级、卸载、异常退出及配置恢复 | 未验证 | E00最终目标；当前未给完整安装生命周期证据 | 版本迁移、用户修改保护、失败恢复 |
| F07 | Rust为默认且无必要Mihomo运行依赖 | 部分实现 | E05 Rust显式模式无外核回退，但默认仍兼容构建 | 功能验收后才改默认/移除依赖，检查包内容/进程/流量路径 |
| F08 | 依赖许可证、必要署名与供应链记录 | 部分实现 | E05/E14；130 包库存、29 个新增依赖版本与 58 份完整许可证/notice；ML-KEM 上游未声称独立安全审计 | 对最终依赖及实际安装包逐项核验 |
| F09 | 同一候选的三平台CI、Windows Qt及安全门禁 | 未验证 | E13–E16 分别记录开发提交的精确三平台/Qt结果，保留失败与未执行步骤 | 最终全协议候选及完整安全门禁仍未验证；开发阶段 CI 不代表全目标验收 |
| F10 | 最终安装包与源码、证据、交接的一致交付 | 未实现 | E01/E04明确未做完整应用包装 | 安装包构建/哈希/安装卸载验收、开发分支SHA和交接一致 |

## 4. 协议百分比单独计算

协议能力采用固定“档案”而非广告中的协议名称数量；同一协议TCP/UDP分开，不把共享TLS库或解析识别计为执行。**协议档案21项**：B01–B12、B18–B20、B22–B27；**传输/扩展10项**：B13–B17、B21、B28–B31。B阶段合计31项，两个子指标分别显示，不能称为31种协议。

每个档案冻结以下七道门禁：①源参数/版本/支持组合与未知项处理；②独立对端的认证/握手；③双向数据及对应TCP/UDP语义；④分片/背压/取消/正常与异常关闭；⑤错误/超时/重放等适用安全负面测试；⑥Qt产品转换和实际转发；⑦已授权真实目标验证及其覆盖边界。所有适用项通过才将该档案标已验收；不适用项必须在测试前有可复核的协议理由，不能因为缺样本而写N/A。真实节点无可用样本时该门禁为未验证。

公式：协议档案验收率=`通过全部门禁档案/21`；传输扩展验收率=`通过全部门禁扩展/10`。当前源码证明若干协议已有原生实现与独立证据，但未建立完整逐档案七门禁表，**两个整档案验收率均为0%（协议0/21，传输0/10），不是没有原生代码。协议9项已有部分实现，传输3项已有部分实现；未满足全部门禁不计完成**。不能从支持HTTP/SS/Trojan等名单推算“协议已完成X%”。

## 5. 订阅的两个固定分母

### 格式语义档案：10项

| ID | 格式档案 | 当前状态 | 缺口 |
|---|---|---|---|
| S01 | Clash/Mihomo | 部分实现 | 节点与部分字段可转换；完整DNS/组/规则产品链未完成 |
| S02 | sing-box | 部分实现 | 节点适配存在；selector/urltest等完整文档语义未整合 |
| S03 | Loon | 部分实现 | 历史SS/Trojan节点兼容及SS真实样本；非节点节仍未验证 |
| S04 | Surge | 部分实现 | 有共同INI节点路径；专有字段与完整语义矩阵未验收 |
| S05 | Shadowrocket | 部分实现 | 通用URI/状态头适配；完整客户端语义未验收 |
| S06 | Quantumult X | 部分实现 | server_local节点路径；其余节语义未验收 |
| S07 | Stash | 未验证 | 共享Clash语法不代表Stash专有语义通过 |
| S08 | V2Ray/Xray JSON | 部分实现 | 原生inspector可识别/保留；完整配置执行未支持 |
| S09 | 独立URI列表 | 部分实现 | 已有若干协议参数严格解析；所有目标协议与未知字段矩阵不全 |
| S10 | Base64/YAML/JSON/INI封装及格式检测 | 部分实现 | 有有界/严格路径；各客户端正文语义与全部错误输入矩阵未完整 |

格式验收率=`完整语义及产品整链通过档案/10`，当前完整档案通过数为0/10（0%验收覆盖，并非所有输入都失败）。S10仅封装层、S01–S09为客户端或URI语义层，二者不能互相替代；这10项是A03/A08的子证据，不重复加入总体79项计分。

### 本轮固定语料：18个原始入口

语料标识 `capture-20261018-065548`，18个原始入口、17个采集身份、1558条节点记录（包含重复导出）；保留原入口映射，不以去重抹掉原订阅覆盖。语料与密文哈希参照E02/E03。

- 采集及加密持久化：**18/18 = 100%**；独立响应HTTP200/完整性：**17/17 = 100%**。
- 外层格式与节点解析：**18/18 = 100%**。这里的“解析”明确不含DNS、规则、脚本、改写和策略组的全语义执行。
- 全配置执行支持声明：**0/18已支持，18份待完成/未验收**。可写“完整配置执行验收覆盖0/18”，不能写“18份真实联网全部失败”。
- TCP候选记录占比：**450/1558 = 28.88%**；这只是含重复导出的转译候选比例，**不是订阅完成率、协议完成率、唯一节点比例或联网成功率**。
- 完整语义/Qt原子导入/实际联网三者必须独立逐入口记录，不能用前两项100%替代全链。

## 6. 真实联网：覆盖率与成功率分开

本轮固定分母有两层：18份来源整链、1558条原始节点记录。节点记录保留输入序号及来源映射；可在私有环境以规范化参数证明记录等价并复用同一实测证据，但必须保存等价依据，不准直接把重复记录当独立测量。唯一节点数U尚未从受保护数据建立，本任务禁止读取明文，故**唯一节点口径暂不发布**。

冻结目标的记录级验收覆盖=`与本轮确切配置匹配、完成严格实际验证的记录/1558`；来源整链覆盖=`完成实际整链的入口/18`；实测成功率=`通过记录/实际执行过记录`。未测、协议未实现、凭据过期、要求不安全TLS、供应商不可达分别列原因，均不能进入通过分子，也不能从总目标分母移除。样本本轮未执行时成功率是N/A（0/0），不是0%。

当前最新两个阶段明确没有新真实提供商节点测试，因此本轮新语料可直接追溯的实际测试覆盖为 **0/1558**，整链覆盖 **0/18**；这是证据覆盖，不是断言所有节点无法连接。历史证据若后续证明与本轮规范化参数完全一致，可带原环境和时间继承并更新覆盖，不在本草案猜测一致。

历史窗口已有两个固定SS样本组，各自3/3通过Windows严格HTTPS（证书/TLS、实际响应、双向流量、正常关闭）；每组在自己的固定样本上是100%。仍保留较早托管Linux同样固定样本TCP超时的失败证据。不能把两组样本成功推广到1558记录、18份完整配置、Trojan/VLESS、UDP、TUN或另一环境。旧样本重复复测不增加唯一节点分母。

## 7. 用户最终11项门禁（均为必须条件）

| 门禁 | 对应条目 | 当前判断 |
|---|---|---|
| G01 原生执行不依赖完整第三方代理核 | F07 | Rust显式模式已有证据；默认产品接管仍未完成 |
| G02 全计划协议独立互操作 | B01–B31 | 未完成 |
| G03 真实语料格式验收与不支持原因 | A02–A04、S01–S10 | 结构解析已过；完整语义未完成 |
| G04 目标范围真实网络验证 | A08、第6节 | 当前只有历史限定SS样本；全量未完成 |
| G05 DNS/路由/组/TUN完整打通 | A06、C、D | 未完成 |
| G06 Windows完整应用与退出恢复 | F02、F04、F06 | 未完成 |
| G07 同一源码三平台/Qt/安全门禁 | F09 | 规则阶段6dcc212已成功；UDP修复dc3ed5e三平台、Windows原生/兼容Qt、独立peer和完整原生应用编译均成功，范围及跳过见E11，不等于全产品安全验收 |
| G08 长连接/弱网/性能/资源实测 | E01–E10 | 未完成 |
| G09 无重大数据丢失/泄漏/安全问题 | A07、C12、D08及安全审计 | 未验证；没有发现不等于证明没有 |
| G10 完整安装包及验收记录 | F10 | 未完成 |
| G11 GitHub最新代码/证据/交接一致 | F09/F10、E10 | 本轮已在线核对开发分支和精确SHA；各阶段失败、跳过和待验收范围见E10/E11/E12，安装包仍未交付 |

## 8. 本阶段报告口径

- 已验收进度：**10.83%**。首次冻结基线，没有可比的上一正式百分比；当前Qt事务改进仍是A06/A07的部分实现，不把局部profile完成冒领为整项完成。
- 协议档案：**0/21完成全门禁，9/21部分实现**；传输扩展：**0/10完成全门禁，3/10部分实现**。已有HTTP、SOCKS、SS、Trojan、VLESS等原生执行能力，具体范围见B表。
- 格式档案：**0/10完成完整语义及产品整链**；本轮采集18/18、响应完整性17/17、外层格式/节点解析18/18。三个口径不可互换。
- 新语料实际联网验收覆盖：记录0/1558、完整来源链0/18；成功率N/A（0/0）。历史固定SS样本只按其各自窗口、源码和环境引用。
- 本轮新增：REALITY R3 正式固定成熟对端、严格 EOF/身份及回收 CI；Vision R2 子阶段新增内层 TLS 检查、有界异步 framing 与完整 Xray 正例/Direct 拒绝测试。B13/B14 都保持未整项验收，不增加完成数和权重；新源码/CI 绑定状态见 E18/E19。
- 下一步：先完成本次精确 CI 取证，再实现 DirectReady/原始所有权与剩余字节交接、HRR、生产异步 REALITY 和真实组合对端；随后贯通订阅→IR→路由→Rust→通道→Qt。既有 UDP/真实提供商、全量语料、TUN、长跑/弱网、物理网络和安装包缺口全部保留；订阅更新继续关闭。任何新增范围必须版本化并保留 v1 趋势。

检查点需要同时保存源码SHA、相关树/产物哈希、命令、通过/失败/跳过、联网来源、当前阻塞和下一具体任务。实际日期/CI/阶段结果更新不能改变上述固定分母。
