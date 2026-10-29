# Swirl UI V2 阶段 2：原生界面与动效实施契约

基线：`856f11e12a20f992620597fbbddb6eab7d32929d`；产品代码基线仍为 `4c8c9e0` / 0.2.3。本文件为架构提案，不包含产品实现、性能实测或新安装包。只在本独立工作树实施，不改其他窗口。

## 1. 已确定的设计边界

使用 Qt 6/QML 和现有 Theme、SwirlMotion、SwirlPageHost、SwirlDataTable、NodeViewModel。保留 Swirl 字体、浅深色、侧栏结构、图标、窗口行为及功能；只在当前壳内重组内容。默认窗口 914×672、最小 760×672、侧栏宽 168 的现有逻辑尺寸不变。**窗口和侧栏圆角统一 14dp 已由用户确认，不再请求确认。**14dp 为固定逻辑 DIP，不随内容缩放再次放大，Qt/DPR 只换算一次物理像素；最大化/全屏仍使用现有矩形边界。

页面的识别特征是“来源、资源、出口”职责清楚、同一行直接完成主要操作。沿用紧凑文字、平面中性色控件、浅分隔线、单一主操作和克制强调色。没有大节点卡片、右侧常驻详情或占位图片。详情为按需打开的临时层。实际文案由 `qsTr` 提取，技术错误码放“详情”，不占正常流程。

四大 Skills 的具体应用：

- Hallmark：在已有壳内重组应用屏幕，复用品牌/语义 token、清晰焦点、真实内容；不运行 HTML/CSS scaffold/sloplint 来冒充 QML 验收。用户授权移动节点选择职责；旧入口移至策略页，节点资源操作保留。实施文件计划见第 9 节。
- UI UX Pro Max：采用已有 Quick Reference 的虚拟列表、状态保留、错误就地反馈、键盘导航和可取消过渡。两次窄范围 CLI 查询未获得可靠的虚拟列表命中，未将其 Web bundle/image 建议用作 Qt 证据；采用 Qt 官方资料。已读到的 Cancellable State Transitions 原则用于区分语义状态与视觉完成。
- Motion Design：选择沉稳、轻快、无夸张弹性的功能动效；入场减速、退场加速，退出更短，位置/缩放解释来源。不为满足“三层动效”添加 ambient 背景动画，不机械套用网页 400–600ms 页面时长。
- Qt AI Skills：短委托、稳定 ID、复用时清理局部状态、按需 Loader、无重复信号、明确键盘及辅助功能；重逻辑在 C++/Rust，不放 QML hot binding。未连接 QML Preview MCP；现有 Qt 6.10.3 不为预览升级到要求的 6.12+。

## 2. 页面结构和产品文案

### 节点：资源库

沿用 `ProxiesPage.qml` 路由 ID，避免破坏现有导航。顶栏“节点”，右侧“测速”带菜单（“当前筛选结果”“全部节点”）、“导入”“添加节点”。测速进行时显示 `正在测速 8 / 42` 和“取消”；不让用户猜默认测速范围。选中资源时可以“测试此节点”。

次行搜索“搜索名称、地区、服务器或协议”，来源下拉、筛选、排序；第三行仅保留“全部｜最近使用｜收藏”和 `42 / 180 个节点`，不增加仪表盘卡片。主列表来源分区，标题“来源名称 / 42 个节点 / 收起”，节点行约 44dp，分区标题约 32dp；列为“节点名称、协议、地区、出站耗时、状态”，收藏图标靠近名称或行尾。在最小窗口里行尾次要操作收进菜单，基本名称和状态不消失。

“地区”是名称/节点信息得出的提示，不用于国内外路由推断。耗时明确为“出站耗时”；详情显示测试地址、成功/失败、最近测试时间和错误阶段，不把 TCP 可连通或单次成功写成永久可用。

单击行只高亮；双击/Enter/行尾“详情”打开现有临时详情层，Esc 返回原行。详情只保留资料、收藏、单节点测速、复制安全信息、已有允许的编辑/删除；去掉“连接/断开”。页面代码中不再调用 `chooseNode`、`connectNode` 或 `selectNode`。用户若要指定出口，可以使用清晰的“前往策略”导航，但该导航也不隐式设置出口。

### 策略：服务分配｜策略组

顶栏“策略”，两个原生分段标签“服务分配｜策略组”，右上主操作随标签为“添加策略”或“添加策略组”。两个标签保留各自搜索、滚动和选中状态。

服务分配页顶部固定一行“默认策略”，尾部是当前出口名称的选择器。辅助文案：“未命中其他规则的流量使用此出口；国内规则仍直连。”默认策略没有删除/停用动作。没有出口时显示“请选择默认出口”；若被引用节点失效，显示“出口不可用 / 选择出口”，不显示已启用或悄悄直连。停机保存显示“已保存，下次启动生效”，运行后按实际确认显示“已生效”。

下方为服务策略密集列表：名称、匹配摘要、出口、启用状态、更多菜单。内置服务模板只是添加表单的起点，未配置不得显示“OpenAI 已分流”。自定义表单用“名称”“匹配方式”“匹配内容”“出口”；匹配方式是“网站域名”“应用程序”“应用与网站”。多域名按条添加，类型使用“仅此域名”“包含子域名”，不自动把 keyword 当 suffix。应用+网站组合必须明确显示满足条件逻辑，不能由前端自己猜 OR/AND。

当前系统代理/TUN能力不满足时，“应用程序”“应用与网站”禁用并邻近显示“当前模式无法可靠识别应用程序，请使用网站域名”；已有这类规则显示“未生效：当前模式不支持”，不丢失原数据。能力由 Rust/平台接口返回，不通过按钮是否可点击推断。

保存前显示内核返回的冲突：例如“与‘Google’重叠；本策略优先级更高”。只有可明确解析的冲突给出具体结论；无法判定显示“需要手动检查”，不宣称全面无冲突。优先级只在允许的层级内用“上移/下移”控制，不能拖过固定的本地/中国规则层。用户能从“查看规则”进入既有规则视图，显示内核的规则顺序和稳定 ruleId；真实连接详情复用规则、策略、实际节点三项。

策略组页每组一行：名称、类型、候选数量、当前实际出口、状态；创建/编辑弹窗显示名称、四类类型和可搜索候选，候选标签“节点｜策略组”，选择记录稳定 ID。当前组不在候选中，环路由 Rust 校验并展示具体引用链。高级设置折叠为“健康检测和自动切换”，包括检测地址、间隔、超时、自动切换条件；仅显示所选组类型支持的字段。默认值、范围、单位和负载均衡服务粘性由核心契约提供，UI 不另造算法。删除被引用组必须列出引用方，并由用户先改引用；不得自动替换 DIRECT。

出口选择器共用 `PolicyTargetPicker`：节点、策略组；DIRECT 只对允许直连的自定义策略出现。默认代理出口不接受 DIRECT/REJECT。列表使用实际节点名/组名展示，以 `kind + stableId` 提交；不通过展示名称反查。打开选择器不会改运行配置，选择并确认才发候选命令。

### 订阅：只管理来源

顶栏“订阅管理”，右侧“更新全部”“添加订阅”；搜索下面是紧凑来源列表。每行展示名称、节点数、最近成功更新时间、状态、刷新及更多操作。展开区仅显示更新计划、格式检测结果、最近错误/兼容说明。地址默认隐藏，只有编辑时输入；保留旧地址的行为继续明确。

新增/编辑的普通表单只需名称、HTTPS 地址、自动更新和周期。“请求格式”保留为可折叠高级兼容设置，默认“自动”，不恢复“完整配置/仅节点”开关。

自动刷新固定节点事务。成功文案“已更新 42 个节点”；失败“更新失败，保留上次成功节点”。检测到完整配置显示“已导入节点；其中的 DNS、规则和策略组未应用”，可选“查看配置差异”。显式应用外部配置若保留，进入独立确认流程并展示实际变更；它不成为自动刷新授权，用户关闭后仍可正常使用节点。节点数和更新时间只在成功持久化后更新。

删除确认写“删除此订阅及所属节点”，同时列出受影响策略数量与运行影响，由核心提供候选结果。取消或最终commit前的明确失败保持原列表。最终commit后还须等待Rust finish及撤销屏障ACK，才能播放成功退出并移除；若删除已保存但撤销尚未确认，显示“已保存删除，连接撤销待恢复”和只读占位，不能恢复已删除凭据或伪报普通成功。

### 活动：保留四列，只替换出站模式值

在 `ActivityPage.qml:141-144` 保留“网络 / 配置 / 出站模式 / 外部 IP”现有位置与宽度。出站模式使用 `OutboundModeControl`，外观仍为该列一行文本加小下箭头；不增加大按钮。

菜单固定三项：

| 标签 | 菜单内短说明 |
|---|---|
| 规则分流 | 国内直连，其余按专属或默认策略 |
| 全局代理 | 普通流量走默认出口，保留必要本地例外 |
| 直连模式 | 受接管流量不经过代理节点 |

值取 `appliedMode`，不是 QML 当前选项。提交时值保持原模式，旁边小进度标记，提示“正在切换到全局代理”；同一模式切换 pending 时防重复提交，页面其余操作不冻结。成功确认后更新勾选和值；失败保持原值，显示“切换失败，仍使用规则分流”及可展开原因。停机时只能表示“已保存，下次启动生效”，不能声称实际网络已切换。

## 3. 状态和页面接口

核心返回的 policy/group/rule/node UUID 和 generation/revision 是数据身份。建议 UI 适配层以下名义属性，最终名字对齐总架构契约：

| 层 | 数据 | 责任 |
|---|---|---|
| Rust/EngineController | `savedRevision`, `appliedRevision`, `pendingCommandId`, `appliedMode`, `requestedMode`, `capabilities`, `lastApplyError` | 校验、保存/应用、实际确认；不可由动画完成回调伪造 |
| 策略 ViewModel | 按稳定 ID 的记录/候选/错误，`pending`、`configuredTarget`、`effectiveTarget` | 翻译 UI 字段、保存草稿，调用核心事务 |
| 节点 ViewModel | `focusedNodeId`, `inspectedNodeId`, `selectedTestIds` | 纯资源浏览及测速；与全局 `selectedNodeId/activeNodeId` 无绑定写入 |
| 页面缓存 | query/filter/sort/collapsedSources/scrollAnchor/focusId | 页面重访恢复；不持有真实连接状态副本 |
| 委托 | hover/press/visualOffset/visualProgress | 可丢弃视觉态；被复用时必须清理 |

仅匹配当前 commandId/revision 的完成消息能结束该命令；旧成功不能覆盖新失败，旧失败不能回滚更新的 appliedRevision。失败原因与草稿保留，用户可以修复重试。运行组成员或配置变更必须用核心事务，不复用现有直接改 `m_options` 的同步返回值冒充生效。

节点检查不得 fallback 到 `engineController.selectedNodeId`：详情关闭或节点删除后 `inspectedNodeId` 为空；筛选只隐藏行不改变运行出口。选中行被过滤后清理可见焦点或保留稳定资源选择，规则在产品中保持一致；建议清理可见焦点但保留已打开详情，来源实际删除则关闭详情并提示“此节点已从来源移除”。

## 4. 来源分区：一个 ListView，兼容现有表格

选定 **NodeViewModel + NodeSectionModel**，不嵌套 ListView、不使用每个来源一个 Repeater。保留 NodeViewModel 的搜索、筛选、收藏、源节点模型和 API，新 `NodeSectionModel : QAbstractListModel` 消费其筛选后结果，在展示层插入虚拟分区行，仍提供现有 `entry` 角色。

节点行 `entry` 继续包含真实 `id`、名称、协议、延迟等，补 `rowKind=node`、`sectionKey`。分区行有独立的 `displayKey=section:<kind>:<sourceUUID>`、`rowKind=section`、来源名、结果数/来源总数、expanded；不伪造 nodeId、不进入测速列表。节点 `displayKey=node:<UUID>`，真实 nodeId 不加前缀。手动、历史未归属、订阅三个来源类型使用互不冲突的命名空间。

来源顺序按来源列表保存顺序稳定排列，手动和历史未归属有固定位置；选定排序只在来源内生效，菜单提示“按来源分组，组内按延迟排序”。来源筛选仍可只看一个区；搜寻时只显示有匹配的区，并临时展开，清空查询后恢复用户折叠状态。没有查询时可展示已存在的零节点来源。结果数取节点数量，不把分区标题算作节点。

`NodeSectionModel` 维护 `displayKey → row` 和 `nodeId → filtered index` 映射；使用 beginInsert/Remove/MoveRows、dataChanged，保留持久索引。监听 source 行变更/layoutChanged/reset，并按 generation 合并一次 projection；排序变化按 key diff，不每条触发全表重置。合法 source reset 可全量重建，但正常搜索/排序/测速更新不得滥用 reset。仅受影响行和分区计数改变；格式化/筛选数据预处理留在 C++，不用每帧 QML `.map/.filter` 扫描全集。

`SwirlDataTable` 增加 opt-in 扩展，默认值完整保留现有其他页面行为：

- `rowKindRole` / `sectionDelegate` / `sectionHeight`；只在启用来源分区时产生额外委托，普通行仍用原表格。
- 对 section 行使用 `sectionActivated(sectionKey)`；不触发 rowSelected/Activated/Edited，不进入复制节点菜单。分区头可键盘聚焦，但 Enter/Space 只展开收起；上下键在可交互行间移动，node 行 Enter 只开详情。
- 可选 `rowActions` 委托承载收藏/测速/详情，事件不得冒泡为运行选择。旧表格不传这些属性即保持原样。
- 新稳定 `displayKey` 和 viewport anchor 接口；现有 `saveViewport` 的 `index * itemHeight` 假设不适用于分区变高。保存首个可见 key、其实际 y 与 contentY 差；用 `positionViewAtIndex` 后修正 offset，不猜固定行高。不对未实例化委托强取对象。
- 外部模型继续 `reuseItems:true`。复用时同步 rowKind、清除 hover/pressed/动画/临时菜单 payload，关闭旧节点菜单，清掉 selectedItem 裸指针；收藏/测试/选中由 ID 模型恢复。

不采用 native `ListView.section` 作为本轮实现：它适合连续同类标题，但当前单 `entry` 角色、折叠后空分区、明确键盘标题操作和多种来源计数需要额外适配；虚拟行能统一处理。后续不同时维护两套分区路径。Qt 官方确认 ListView 只实例化可见范围并提供 pooling/reused 信号；本方案在其上复用现有实现：[ListView](https://doc.qt.io/qt-6.10/qml-qtquick-listview.html)。

## 5. 键盘、空态和忙态

| 场景 | 行为和文案 |
|---|---|
| 零节点 | “还没有节点”与“添加订阅 / 导入节点”；不是画空行充数 |
| 搜索无结果 | “没有匹配的节点”与“清空筛选”；保留搜索框焦点 |
| 未测/失败 | “未测速”“测试失败”；详情给真实原因，不能用 0ms 代替失败 |
| 更新/测速 | 保留可用旧数据，可取消的工作提供取消；不可取消的原子提交说明“正在保存” |
| 服务/组为空 | 简短说明和添加入口；默认策略仍在 |
| 策略失效 | 显示引用失效和修复入口；actual 路由以核心为准，不自动显示 DIRECT |
| 对话框保存失败 | 草稿不清空，首个错误聚焦；多个错误提供可聚焦摘要 |
| 删除成功 | finish/撤销ACK后焦点转下一同行或标题；commit前失败留原行，commit后待恢复显示只读占位、不恢复凭据 |

Tab 按视觉顺序，Ctrl+F 聚焦当前页搜索；上下/Home/End/PageUp/PageDown 操作列表，Enter 打开详情/确认明确选择，Space 切换复选框或折叠，Esc 只关闭最上层菜单/对话框/详情，随后才走原页面返回。Ctrl+A 只在节点列表获得焦点且启用多选时选择可见匹配节点，在文本框仍选择文本。多选节点只用于批量测速/既有允许操作，不设置运行出口。

图标按钮有 `Accessible.name`，装饰图标 ignored；选中/展开/忙/禁用用原生属性与必要 QAccessible 事件发布，文本状态不只靠颜色。Tooltip 也可键盘焦点触发。操作完成不抢走用户已移开的焦点；回归焦点检查原 owner/generation 仍有效。

## 6. 统一动效契约

沿用 SwirlMotion 的 80ms 按压、140ms 释放、190ms 页面、220ms 选择/对话框、160ms 退出和现有 spring/damping。新增 token 仅补需要区分的菜单入/出与列表重排，不另建第二套 Motion singleton。所有持续值以当前视觉值为起点 retarget，不在重复点击时回零；语义状态正确性不等待动画完成。

| 交互 | 视觉和时间预算 | 中断/复用 |
|---|---|---|
| 侧栏导航 | 保留现有位置追随与页面空间切换，不重做 | 同路线反向、第三路线接管保留当前进度 |
| 下拉/出口选择 | 从触发边缘位移约 4–6dp、scale 0.98→1、opacity；160–180ms 入、100–120ms 出 | 反向从当前 transform 开始；不要 scale 文本超过必要时间 |
| 策略标签 | 单一滑动选择背景约180–220ms；内容小位移约8dp+透明度 | 命令与标签状态独立，快速返回不销毁草稿 |
| 订阅展开 | 保留 SwirlHeroCard 单一表面及内容 reveal；更新不自动展开 | 当前 progress 反向；不增加每行阴影层 |
| 来源折叠/删除 | 子行短距离退出，邻行自然归位，整体约160–220ms | 仅已提交删除可触发退出；取消/失败不伪移除 |
| 搜索/排序 | 可见保留行从旧位置平滑到新位置，消失/出现行做小位移+短淡化；总约160–200ms，无全量 stagger | 新查询 generation 替换旧过渡，当前视觉 offset 接续，最多保留一轮 outgoing 可见行 |
| 收藏/选择确认 | 图标轻微 scale 0.94→1 与填充/颜色，约140ms | 语义收藏立即由模型确认；无持续弹跳 |
| 测速反馈 | 现有 render-thread spinner；数值只对同一节点的连续有效值插值 | pooled/换ID立即归位，不把上一节点成功值滑入新节点 |

Native ListView 的 move/displaced 负责真实模型移动；搜索造成大量索引重排时，不假设 `layoutChanged` 自动提供完整动画。NodeSectionModel 发明确变更，视图在一次变更前缓存可见节点 key→位置；变更后对仍可见的**内容包装层**应用 Translate 残差再收敛到零，避免与 ListView 管理的 delegate.y 竞争。只保存可见行及一屏缓存的轻量信息，不创建 N 行快照或常驻图像。首次创建无历史位置时用轻微入场，不能让整页从远处飞入。

几何变化只触发一次布局后对平移/缩放做呈现；避免每帧更改复杂子树宽高。保留真实滚动惯性，不在滚动手势中启动全列表排序动画；后台测速结果合并后只更新必要排序变化，显式稳定的排序节流以实际 profile 为准，不通过永远禁用排序过渡解决性能。

减少动态效果时直接应用最终位置、保持清晰焦点与状态文本，可保留必要短颜色反馈；这是用户/系统明确选择，不是性能退化时擅自砍动画。动画 offscreen/pooled 必须停止，缓存页不可因 Loader 仍存在而持续跑 spinner。

## 7. 14dp 的实际路径与验证

`Theme.qml:98-100` 两个 ShellMetrics 改为统一 14 的逻辑值。保持现有连续轮廓指数和抗锯齿，不把圆角换成新的圆形曲线。

| 消费路径 | 实施动作 |
|---|---|
| `Main.qml:42-45,57,275-282` | `swirlWindowRadius`、shellRadius、背景/outline/WindowEdge 同源；最大化/全屏为0 |
| `SwirlSidebar.qml:19-39` | floatingBackground、SwirlShellOutline、transmission/shadow shader 同源14；保持浮动边距/宽高/selection胶囊不变 |
| `app/WindowEdge.cpp` + `shaders/window-edge.frag` | 继续消费 radius 和 DPR，检查四角 coverage，无额外倍率 |
| `app/WindowsBackdrop.cpp:215-246,317-338,424-431` | 软件 HWND region、兼容阴影、blur helper inset 都读同一逻辑半径；只在值变化时重建，保留2.5曲线 |
| `SwirlShellOutline`/sidebar shaders | 确认 uniform 与父轮廓一致，不能出现阴影比主体多一圈或玻璃漏角 |
| `tests/WindowRadiusChecks.h` / `tests/WindowChecks.cpp` | 清理历史16/13.333硬编码，改成明确14的独立期望；保留外角透明、四角对称、内侧不裁内容、DPR/恢复最大化验证 |
| `tools/Verify-S3UiBaseline.py` + `docs/handoffs/s3-ui-baseline.json` | 现有hash冻结规则不再适合全部V2文件。记录用户授权的精确变更清单，保留旧清单作来源证据；为不允许变化的尺寸/侧栏结构继续守卫，不通过全面重录hash把任何变更当成批准 |

这一项虽为视觉修改，触及 HWND 和 shader 路径，必须做聚焦几何自动检查。100/125/150/175/200% 的最终人工视觉仍由用户验收；自动几何按所触及路径覆盖代表性整数与分数 DPR，不把人工 DPI 全矩阵作为每次安装包前置条件。

## 8. 性能预算、场景和证据

以下是实施目标和失败触发线，**不是已测结果**。保持真实动画/阴影/缓存，先用同一发布构建、Qt版本、硬件、刷新率、数据和脚本测前后。60Hz的帧预算约16.67ms；分别报告 CPU QML/binding/layout、render/GPU、frameSwapped 间隔和输入到可见反馈，不能用一次函数耗时代替整个帧。Qt 官方建议异步重处理、短主线程任务和先 profiling：[Qt Quick performance](https://doc.qt.io/qt-6/qtquick-performance.html)。

- 输入视觉反馈目标≤100ms，100ms搜索去抖单独报告，不能隐藏在渲染指标里。
- 常见 warmed 场景 P95 帧间隔目标≤16.67ms，P99目标≤33.3ms；记录>16.67、>33.3、>50ms帧数及总帧数。任何持续掉帧或>50ms停顿进入定位；不能只报均值或“稳定60FPS”。高刷新屏按实际周期单独归一，不拿240Hz数据比60Hz。
- 典型小批节点更新的 UI 线程处理目标≤4ms；完整查询/重排目标一个帧预算内。超预算先检查通知合并/索引/分配，再把纯数据预计算送 worker（不可在线程外操作 QAbstractItemModel）；按 generation 只应用最新结果。
- 实例化 delegate 数应随可见窗口与有限 cacheBuffer 变化，与100→5000节点总量基本无关；不强行减少缓存换取表面内存下降。复访200次的工作集/私有字节/对象数要与现有基线和波动比较，使用已有24MiB复访警戒作定位信号，不宣称30分钟无泄漏。

针对性场景：100/500/2000节点（5000仅作超出现有2000目录上限的合成模型探索，不表示生产导入支持），含10–32来源、长中文名和不同状态；连续输入/清空筛选、排序切换、折叠来源、滚动时批量测速更新；订阅删除成功/失败/取消；快速策略切换/回退；侧栏A-B-A-C点击和弹窗开关/反向；应用模式成功/失败/超时/过期ack；运行期间来源失效；减少动态效果、深浅色、最大化恢复。冷创建与暖重访分开，记录运行采样时是否 profiler 附加。

保留 profiler trace、场景脚本、机器/图形后端/DPR/刷新率、源SHA及结果JSON。若卡顿，先 Qt QML Profiler 判断绑定、JS、加载和布局，再结合渲染 trace；数据不能证明 GPU 限制时不编造GPU结论。历史S4 P99约63ms、内存降低约0.24%不可替代当前版本60FPS验收。长时稳定、真实网络、DPI人为观感均单独标注。

## 9. 阶段 3–6 文件计划与退出条件

所有新增类型进入 `src/Swirl.Quick/CMakeLists.txt` 的既有QML/C++注册；没有删除路由或产品功能。新增类名是本方案建议，最终和核心总架构对齐后实施。

| 阶段 | 主要文件（相对 src/Swirl.Quick） | 独立可验收结果 |
|---|---|---|
| 3 节点资源库 | 修改 `qml/pages/ProxiesPage.qml`、`app/NodeViewModel.{h,cpp}`、`qml/controls/SwirlDataTable.qml`；新增 `app/NodeSectionModel.{h,cpp}`、`qml/components/NodeSourceHeader.qml`，必要时提取 `NodeDetails.qml` | 来源分区/折叠、搜索筛选排序、单批测速和收藏可用；点击/键盘/详情从不改运行出口。测试 `NodeViewModelTests`、新增分区模型契约、`NodeUiChecks` 的真实信号/动作；既有选择出口入口仍在策略页 |
| 4 策略与内核联动 | 重组 `qml/pages/PolicyGroupsPage.qml`；新增 `ServiceAssignments.qml`、`PolicyGroupList.qml`、`ServicePolicyDialog.qml`、`PolicyGroupDialog.qml`、`PolicyTargetPicker.qml`；修改 `engine/EngineController` 及既有 `RulesPage`/连接详情适配 | 两标签、永存默认策略、专属服务/组编辑消费真实ID与原子应用结果；无UI模拟路由，无失效后默认DIRECT；所有关键联网证据由核心阶段给出 |
| 5 订阅来源 | 修改 `qml/pages/SubscriptionsPage.qml`、`engine/NodeImportService`、`engine/NodeStore` 和 Controller 导入入口；必要时提取 `SubscriptionRow.qml`、`SubscriptionDialog.qml`、`ConfigurationReviewDialog.qml` | 自动更新只改来源节点，完整配置需独立确认；失败保留、删除引用处理、取消与busy语义正确；用现有导入/事务测试补业务断言 |
| 6 活动模式/统一动效/14dp | 修改 `qml/pages/ActivityPage.qml`、`qml/Theme.qml`、`qml/SwirlMotion.qml`、`qml/controls/SwirlComboBox.qml`、`SwirlDialog.qml`、`SwirlDataTable.qml`、必要的 `SwirlPageHost.qml`；新增 `OutboundModeControl.qml`；按第7节改相关轮廓/聚焦测试 | 四列原位下拉、实际ack后更新、失败不误显示；菜单/排序/弹窗可打断空间过渡、OS减少动态效果；14dp所有轮廓一致；同场景性能报告，未达项保留 |

阶段3的增量表格API不得破坏连接/规则等已有表格；只跑受影响的验证。阶段4–5之间应有短期安全依赖：在策略重构启用前，先完成“自动订阅不得覆盖已有配置”的后端保护；可以作为阶段4前置小提交，完整订阅页面仍归阶段5，不允许阶段3的新资源库与危险自动覆盖长期并存。

各阶段结果都记录完整SHA和提交后适用测试，新增或变更行为才扩回归；不把不同SHA混合成一次全绿验收。UI架构阶段不发可用安装包；实现后若真实核心网络严重故障未解决，仅可明确诊断包，普通测试版交付条件由总验收契约约束。
