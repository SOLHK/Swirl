# Swirl UI V2.0：阶段 1 审计

审计日期：2026-10-24（Asia/Shanghai）。本阶段完成源码、技能、分支、接口与既有交付证据核对；没有修改产品功能，没有生成 V2.0 安装包，也没有宣称新路由或真实联网通过。

## 基线与隔离

- 远端与本机最新开发基线一致：`4c8c9e076976e5cfb62f103daecdf2afc121eeb3`，产品版本 `0.2.3`，原分支 `work/swirl-019-subscription-regression-20261024`。
- 新工作树：`D:/Codex/work/Swirl-ui-v2-20261024`；独立分支：`work/swirl-ui-v2-20261024`。当前聊天不是 Git 项目，应用 worktree 工具返回 `Not a git repository` 后，使用 Git 在已核实的仓库创建了独立 worktree。
- 原工作树干净；不切换、不覆盖其他窗口分支。`main` 保持 `87409c0bf9c957ef113f84c176c5a1529c27b9df`，`test` 保持 `e19dc9f663ac326b6654953db212b97177a56966`。
- 系统代理、Clash、TUN、路由、DNS、Codex 进程和私人订阅未改动；本次不重新下载私人订阅。
- **用户在本聊天已明确确认：窗口和侧栏圆角统一改为 14dp。** 当前源码分别为 24dp、16dp；窗口默认 914×672、最小 760×672、侧栏宽 168，尺寸和结构继续保留。14dp 是下一阶段实施要求，本阶段尚未改动。

## 四大 Skills 已检查并用于审计

| Skill | 使用的实际来源 | 本次应用 |
|---|---|---|
| Hallmark 2.0.0 | `C:/Users/sysfr/.agents/skills/hallmark/SKILL.md`；[官方仓库](https://github.com/Nutlope/hallmark) | 已读主文件、redesign 与 app-screen 指南；先盘点真实页面、品牌 token 和既有交互，保护壳层结构，避免卡片套卡片、无依据指标与网页模板化重建。 |
| UI UX Pro Max | 仓库 `.agents/skills/ui-ux-pro-max/SKILL.md`；[官方来源](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 复用已装副本，执行本地 `rapid animation interruption --domain ux -n 3` 查询；将可打断状态、键盘焦点、紧凑列表、异步反馈和渐进展开用于现状检查。 |
| Motion Design 1.0.0 | `D:/Codex/skills/motion-design/SKILL.md`；[固定官方提交](https://github.com/LottieFiles/motion-design-skill/tree/f9a8a041b85185ee4881b3471d3415e939aac772/skills/motion-design) | 缺失技能已安装，读取主文件及平台/质量参考；复用现有时长、进入减速/退出加速、轻微位移缩放、可中断和减少动态效果。 |
| Qt AI Skills / qt-qml 1.2 | `C:/Users/sysfr/.codex/skills/qt-qml/SKILL.md`；[官方仓库](https://github.com/TheQtCompanyRnD/agent-skills) | 核对 Loader、delegate pooling、稳定角色、绑定、焦点、动画生命周期与渲染成本；沿用原生 Qt 6/QML。 |

Hallmark 的 CSS/浏览器检查器不支持原生 QML，本次未运行、未声称通过。Motion 的常驻三层装饰、网页预算与长页面时长不机械套用到桌面工具。现有 SwirlMotion 已满足统一系统的基础，不另造动画框架。网络审计还使用了 `network-protocol` 与 `rust-skills` 的错误处理、边界和真实协议验证原则。

Motion 的 D 盘安装目录没有注册为全局自动发现位置，交接通过绝对路径读取即可。当前无 `run_qmlPreview` 工具；Qt Installer 的 QML Preview MCP 需要 Qt 6.12+，本机已有构建缓存使用 Qt 6.10.3，因此继续使用现有原生测试工具，不以此阻塞开发。详细版本、哈希和适配说明见 [技能记录](UI_V2_SKILLS.md)。

## 已有能力不重复实现

- 自动识别订阅、有效节点提取、加密来源保存、来源所有权、事务更新、失败保留上次数据、按来源删除节点。
- 稳定 node UUID、密集节点列表、搜索、来源/地区/协议/状态筛选、排序、收藏、大列表复用及增量通知。
- Rust 完整出站探测、目标 TLS/HEAD 校验、有界并发和取消；当前列表耗时是 `http_headers`，不是 RTT，也不是只有 TCP 连通。
- Rust 中国域名/IP MRS 资产及哈希校验、IPv4/IPv6 匹配、DNS 与实际拨号地址一致性、未知目标兜底和无健康节点时报错。
- 四类策略组核心、循环/深度校验、不可变运行计划、已建立会话快照、真实规则/实际节点记录。
- 已有统一动效 token、系统减少动态效果、可中断导航、页面缓存、Esc 和焦点回归。
- 已完成的增量构建图优化和安装包源码身份校验。

以上仅指源码实现可复用；各自的产品边界或覆盖范围仍须按新需求调整。详细位置见 [UI 审计](UI_V2_STAGE1_UI_AUDIT.md) 与 [Rust 路由审计](UI_V2_STAGE1_ROUTING_AUDIT.md)。

## 阻止 V2.0 成立的具体问题

| 优先级 | 已确认的问题 | 代码证据与影响 |
|---|---|---|
| P0 | 添加自定义规则会关闭中国分流 | `EngineController.cpp:321-323` 仅在 `customRules.isEmpty()` 时开启 smartRouting；专属服务规则与国内分流不能按需求并存。 |
| P0 | 自动兼容完整配置未经确认覆盖网络策略 | `EngineController.cpp:146-168,769-783` 自动应用 DNS/rules/groups，并关闭内建 smart/private 分流；不符合“订阅仅管理来源”。 |
| P1 | 当前顺序不满足五层优先级 | `RustCoreEngine.cpp:129-184` 用户规则排在私网规则前；Rust CN 检查晚于其他显式规则。仅打开 smartRouting 开关不足以修复。 |
| P1 | 默认出口不能选择策略组 | `RustCoreEngine.cpp:230-236` 将 selectedNodeId 作为具体节点查询；没有不可删除的默认策略实体。 |
| P1 | 全局模式丢失必要本地例外 | `RustCoreEngine.cpp:27-28` 跳过所有规则；新需求需要保留明确的本地例外。 |
| P1 | 节点库仍控制运行出口 | `ProxiesPage.qml:42-46,205`，`EngineController.cpp:479-485`；点击节点看详情也会 chooseNode，运行中就可能切换出口。 |
| P1 | 服务分配及自定义服务模型缺失 | 现有策略页仍是模式、节点卡片和简单组编辑；没有服务/组双标签、永存默认策略、启停与冲突控制。 |
| P1 | 策略组 UI/核心范围不一致 | 自动组拒绝嵌套，负载均衡缺跨连接服务粘性；UI 新建负载均衡组没有写入核心必需 strategy；高级探测参数不能编辑。 |
| P1 | TUN 和应用进程匹配不可用 | `RustCoreEngine.cpp:225,411` 拒绝 TUN/网关，进程记录为未知；不能把系统代理当全系统流量或伪造应用策略。 |
| P2 | 活动页模式仅文本 | `ActivityPage.qml:141-144` 四列布局已有；需接已有真实模式接口，加入 pending/实际生效状态与失败反馈。 |
| P2 | 动画场景和性能验收未齐 | 节点行过渡被关闭，普通下拉/部分弹窗仅透明度；需有意义的空间过渡，保留打断与复用，并实际测量帧时间。 |

模式接口并非纯 UI 模拟：Rust configure 成功后更新 engine status，运行时 getter 读取实际模式，已有 routingBusy 接口和失败回滚。但当前 Rust/ThreadedEngine 模式切换路径未设置 routingBusy=true（`ThreadedEngine.h:68`，`ProxyEngine.h:89` 默认 false），尚缺覆盖异步请求期间的完整 pending 契约。阶段 2 要核定保存偏好先于异步应用的时序，复用已有接口补齐活动页交互和实际状态确认；不重新发明已有模式实现。

现有连接记录有 matched_rule 和实际 leaf node，但 Qt 用 node 填 policy/chain，尚缺真实“服务策略 → 策略组 → 实际节点”完整解析链。服务集合也缺少 Google/YouTube 等重叠治理。

## 阶段状态

| 阶段 | 审计状态 | 后续处理 |
|---|---|---|
| 1 审计 | 本次完成 | 保存独立分支与交接，进入阶段 2。 |
| 2 架构 | 未完成 | 固定规则层级、默认策略、ID 迁移、事务应用和 Qt/Rust 契约。 |
| 3 节点页 | 部分基础已实现 | 复用筛选/测量/收藏/模型；实现资源库职责、来源分区与过渡。 |
| 4 策略与路由 | 核心基础存在，产品闭环未完成 | 先修 P0 数据流，再补服务/组模型、路由层级及可观测性。 |
| 5 订阅页 | 自动识别和生命周期已实现 | 保留解析器，改为节点来源事务；配置覆盖必须显式确认。 |
| 6 活动模式/动画 | 基础存在，需求未完成 | 模式入口、真实应用状态、14dp、完整动效及实际性能测量。 |
| 7 测试/安装包 | 仅有 0.2.3 历史诊断包 | 按独立可用阶段构建新版本，V2.0 验收尚未进行。 |

不能把阶段 3–6 整体跳过，也不重写表中已有基础。本次遵循“每次只集中当前阶段”，没有越过阶段 2 的设计确认直接重构。

## 测试与安装包证据

本次在新工作树运行：

- `tools/tests/test_portable_core_boundary.py`：7 项通过。
- `tools/Verify-S4UiBoundary.py`：99 个受保护文件，changed 为空。只证明源码边界未改变，不证明视觉或帧率。
- 文档修改的 `git diff --check` 与受控文件范围检查在提交前完成；产品代码没有改动，无需重复全量编译。

已重新从 GitHub 查询 [0.2.3 的 CI](https://github.com/SOLHK/Swirl/actions/runs/40102559890)：rust-safety 与 windows-candidate 均成功，产物 head_sha 精确为基线 `4c8c9e0…`。本机 EXE 重新计算 SHA-256 为 `82AC974CE496C3EE9E3E8254392D7909F600CAB9B0D7F3741BBDA0954657506D`，与原交付记录一致。

原交付记录记载：734 个 Rust 测试、7 个边界检查、3 个 VMess、18 个 REALITY 受控回归、13 套 Windows 检查，1509 个包文件核验。这些是 **0.2.3 同一基线的历史证据**，不是本阶段重新运行，更不是后续修改提交的通过证明。

[现有 0.2.3 诊断安装包](https://github.com/SOLHK/Swirl/actions/runs/40102559890/artifacts/12563338792)仍可下载，但真实抽测两个节点的成功数为 0，Google/YouTube/Codex、TUN 和私人供应商验收未通过或未验证。用户后来报告部分网页可用，不足以推翻记录中的失败或证明 Codex 已恢复。本阶段不重新包装、不提升其交付等级，不要求为纯审计重复安装。

早期 S4 的性能记录不是本次提交的性能验证；稳定 60FPS、长时间稳定性、当前 UI 视觉和实际路由仍需在实施后测量。100%–200% 的人工 DPI 视觉验收由用户负责。

## 下一阶段入口

见 [简洁交接](UI_V2_HANDOFF.md)。阶段 2 应先固定五层规则计划、不可删除默认策略、服务与组的稳定 ID、节点来源事务、应用识别能力标记、requested/applied/revision 接口，再确认页面和动效结构。窗口与侧栏 14dp 已确认，不再询问。

阶段 1 完成，建议继续使用 Astra Ultra 进行架构设计。本次没有自行切换模型。
