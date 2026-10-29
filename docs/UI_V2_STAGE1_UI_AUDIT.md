# Swirl UI V2 阶段 1：界面、交互与数据流审计

审计基线：`4c8c9e076976e5cfb62f103daecdf2afc121eeb3`，产品 `0.2.3`。此 UI 子审计只读检查真实源码；未修改产品代码，未运行编译、联网、UI 或性能测试。原工作区保持不变；父审计运行的源码边界检查另见阶段 1 总表。

已读取仓库 `AGENTS.md` 与 Qt AI Skills 的 `qt-qml/SKILL.md`。工具清单未发现 `run_qmlPreview`；Qt Installer 提供的 QML Preview MCP 需 Qt 6.12+，本审计不依赖它，不把工具缺失视为开发阻塞。

## 已确认的尺寸约束

- 当前源码默认窗口 `914 × 672`，最小 `760 × 672`，侧栏宽 `168` 个逻辑单位：`src/Swirl.Quick/qml/Theme.qml:114,130-133`。`Main.qml:21,50-51,109` 消费这些统一值。
- 当前窗口轮廓为 `24`、侧栏为 `16`，不是提示词提到的 `14`：`Theme.qml:98-100`。卡片 `20`、控件 `10` 是其他独立层级：`Theme.qml:102,112`。
- 用户已进一步明确：**下一阶段将窗口及侧栏圆角统一为 14dp，保持窗口尺寸和侧栏结构不变**。这已是确认要求，不再等待确认；本阶段只记录，不实施。

## 已实现、应复用的能力

| 能力 | 当前实现与证据 | 处理 |
|---|---|---|
| 订阅添加、编辑、删除、刷新、定时更新和失败提示 | `SubscriptionsPage.qml:13,25-28,62-67,82-92`；`NodeImportService.cpp:143-218` | 保留现有事务/调度，调整产品边界 |
| 自动识别、去掉完整配置/仅节点手动开关 | `SubscriptionsPage.qml:135-138` 只保留请求格式偏好；`NodeImportService.cpp:218,353-376` 自动解析内容 | 不重新实现识别器；请求格式偏好与导入作用域不是一回事 |
| 来源所有权、失败保留、删除关联节点 | `NodeStore.cpp:482-488` 只删该 sourceId 节点；`NodeStore.cpp:586-675` 准备完整候选；`NodeStore.cpp:318-323,677` 加密原子写入 | 保留，补策略引用验收 |
| 稳定节点 ID | `NodeStore.cpp:357` 新手动节点 UUID；`NodeStore.cpp:602-662` 按来源与节点身份重用 ID，并映射解析 ID | 不以显示名称替代引用 |
| 节点密集列表、搜索、来源/地区/协议/可用状态筛选、排序、收藏 | `ProxiesPage.qml:29-40,65-93,154-163,207`；`NodeViewModel.cpp:65-97` | 核心可复用，来源分区和资源库职责未完成 |
| 单个与批量真实内核测速 | `ProxiesPage.qml:65,206` → `EngineController.cpp:539-540` → `NodeTestService.cpp:31,52-68,71-88` 的隔离 ThreadedEngine/Rust 请求 | 不是单纯 TCP 探测。成功状态取实际请求结果；不代表每个真实供应商节点都可用 |
| 测速并发、取消、旧回调隔离 | `NodeTestService.cpp:71-88` 最多三个 worker；`:49-59` 校验节点身份；`:117` 起取消队列 | 保留，不能用 UI 假结果替代 |
| 大列表复用、增量更新 | `SwirlDataTable.qml:113,129-130` delegate pooling；`NodeViewModel.cpp:12-36` 按 ID 增删及合并 dataChanged；`:43,49-59` 50ms 合并刷新 | 继续扩展现有模型，不整页 Repeater/卡片化 |
| 统一动画、系统减少动态效果、可中断导航与缓存 | `SwirlMotion.qml:8-22`；`MotionPolicy.cpp:37-45`；`SwirlPageHost.qml:10,49-54,89-100,107-122` | 保留已有架构，补缺失场景 |
| Esc 和焦点回归 | `Main.qml:184-195`；`SwirlDialog.qml:24-45`；`SwirlComboBox.qml:82,91` | 复用，不另建全局键盘层 |
| 请求规则/策略/实际节点查看入口 | `ConnectionsPage.qml:95-98` | 已有显示槽位；真实 Rust 数据正确性由内核审计/联网验收确认 |

表中 `*.qml` 的完整前缀为 `src/Swirl.Quick/qml/pages/`，但 `Theme.qml`、`SwirlMotion.qml`、`Main.qml` 在 `qml/`；控件文件在 `qml/controls/`；`NodeViewModel.cpp`、`MotionPolicy.cpp` 在 `app/`；其他 C++ 文件在 `engine/`。

## 必须修复或补齐

### P0：自动订阅仍会覆盖用户 DNS、规则和策略组

`EngineController.cpp:146-168` 中，完整配置投影成功后直接调用 `importNodesAndConfiguration`；仅不兼容时才退回提取节点。`NodeImportService.cpp:450` 明确报告“已自动应用兼容的 DNS、规则和策略组”。订阅页面 `SubscriptionsPage.qml:83,135` 也沿用自动应用语义。

这与新要求“订阅仅管理来源、未经确认不得覆盖既有规则/策略”直接冲突。下一阶段应把自动刷新固定为节点来源事务；如允许应用外部完整配置，必须独立显式预览/确认，定时刷新不能重放确认。已有安全投影和节点保留功能不能删掉。

### 节点页不是纯资源库，点击列表本身就可能切换运行节点

`ProxiesPage.qml:42-46` 的 `selectRow` 调用 `engineController.chooseNode(row.id)`。`EngineController.cpp:479-485` 在当前引擎运行时直接 `selectNode(id)`。此外 `ProxiesPage.qml:205` 有连接/断开按钮。因此不仅要删除显眼按钮，还要把详情选择与实际出口选择彻底分离。

已有 44dp 表格和全页临时详情覆盖层（`ProxiesPage.qml:89,99-112`），不是常驻右侧面板。来源目前为下拉筛选（`:29-31,73`），没有按订阅来源分区标题/折叠列表。收藏存在；排序/筛选动画被该表明确关闭 `animateRowChanges:false`（`:89`），须在不破坏复用与快速更新的前提下补齐过渡。

### 策略页面仍是旧模式选择、节点卡片和组编辑器

`PolicyGroupsPage.qml:24-77` 尚无“服务分配｜策略组”双标签，也无永存默认策略、OpenAI/Claude/Google 等专属分配、自定义服务多域名/应用组合表单、启停、优先级或冲突说明。

组编辑器已有四种类型（`:67`），保存的是节点 ID（`:70-71`）。但候选只含 DIRECT/REJECT/节点，没有候选策略组；没有健康地址、间隔、超时、自动切换条件和折叠高级区域。`EngineController.cpp:870` 新组写死 gstatic URL、300 秒间隔；`:871-873` 编辑时保留不可见的已有参数，这是应保留的兼容保护。当前组以 `name` 为标识（`PolicyGroupsPage.qml:17-18,64-66`；`EngineController.cpp:869`），应在架构阶段确定稳定 group ID 和迁移规则。

独立 `RulesPage.qml:48-52` 可逐条编辑 DOMAIN / DOMAIN-SUFFIX / IP / PROCESS-NAME 等规则，但没有产品级服务结构，且 PROCESS-NAME 选项未在此处说明系统代理/TUN识别限制。`EngineController.cpp:622-625` 只允许停机编辑网络配置；不能把现有保存按钮视为运行时策略事务完成。

### 活动页模式切换：有内核接口，缺所需入口和严格确认时序

`ActivityPage.qml:141-144` 已是“网络 / 配置 / 出站模式 / 外部 IP”四列，`:143` 的出站模式只是 `Fact` 文本，不能点击。现有模式控件在策略页 `PolicyGroupsPage.qml:25`。

`EngineController.cpp:543-559` 已校验候选并调用内核 `setRoutingMode`，失败回滚在 `:180-186`。运行时 `EngineController.h:132` 的 getter 读取真实 engine status，`:134` 已提供 `routingBusy` 接口；不能误称现有接口只改文字。不过当前 Rust/ThreadedEngine 切换路径未将 routingBusy 设为 true（`ThreadedEngine.h:68`，`ProxyEngine.h:89` 默认 false）。Controller 还在异步调用前更新 `m_options.routingMode` 并写 QSettings（`:555-558`）。阶段 2 应完善异步应用期间的 pending 契约，复用已有 getter、busy 接口和回滚；活动页接入后必须验证失败时显示旧模式及原因。

### 动画和性能不能按已有文档直接宣告达标

现有导航支持反向与第三次点击接管，值得保留（`SwirlPageHost.qml:107-122`）。但下拉菜单 `SwirlComboBox.qml:99-105` 当前只有透明度过渡；普通无 heroSource 弹窗 `SwirlDialog.qml:81-87` 也只有透明度过渡。需按触发位置增加克制的空间运动，同时保留中断和减少动态效果逻辑。订阅展开已有 HeroCard；删除有退出和位移过渡（`SubscriptionsPage.qml:45-47`）。

节点搜索虽有 100ms 去抖（`ProxiesPage.qml:40`），但 `QSortFilterProxyModel::invalidateFilter()` 在 UI 线程执行（`NodeViewModel.cpp:65`）；不能据此声称任意规模不阻塞。应以目标节点规模测量后决定是否需 worker 预计算，不直接重写。

`docs/S4_PERFORMANCE_BENCHMARK.md:91-101` 是早期 S4 对比：P99 仍约 63ms、长帧未显著改善、工作集只降低约 0.24%。这是历史证据，不能证明当前 SHA 稳定 60FPS。本阶段没运行性能测试；后续保留已有动画，用同机同场景测量和 QML Profiler 定位。

## 下一阶段建议

阶段 2 先确定：订阅节点事务与配置确认边界；只读节点检查 ID 与运行出口 ID 分离；服务规则/永存默认策略/group ID 结构；requested/applied/revision 错误契约；窗口与侧栏 14dp；既有动画组件的扩展方式。节点页、策略页、订阅页和活动模式均存在新增需求，不能将阶段 3–6 整体标记已完成或跳过。

后续最小验证应覆盖：点击节点只打开详情不调用 chooseNode；刷新完整配置保持用户规则；来源删除只清理其节点且显式处理失效引用；策略失败不回退 DIRECT；模式应用失败恢复状态；大列表排序/筛选及快速反向交互。真实联网、安装包、60FPS、长时稳定性和各 DPI 人工视觉仍须独立标记。
