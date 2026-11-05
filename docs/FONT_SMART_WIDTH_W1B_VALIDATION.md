# Swirl-VF W1-B：智能宽度验证与 Windows 11 交接

记录时间：2026-10-20 UTC。范围仅为 W1 智能宽度；没有开展 W2 智能高度、
HGHT 推荐值、Apple 字体转换或代理内核开发。

## 1. 当前结论

**W1 智能宽度的代码与自动化验收完成，待 Windows 11 物理实机验收。**
最终 Windows 运行实际完成了 Qt 字体测试、完整 Swirl 应用编译与导航检查。
本轮没有访问用户物理屏幕，不能据此宣称整个 W1 最终交付完成。

原有按钮和导航的真实宽度拟合、手动模式优先及静态字体回退继续使用。
本轮修复了历史坐标绕过压缩安全检查、非单调字体被相邻候选错误阻断、
狭窄轴区间采样不充分的问题，补齐主要公共单行控件接入，并增加实际 Qt
整形、度量量化、缓存与多进程模拟缩放验证。
十个候选和 85% 限制在上一轮 W1 已经存在；本轮修正其采样位置、历史
安全检查与实际接入，没有将它们重新列为从无到有的新功能。

这不是把所有文字强制变窄。只有字体实际具备有效标准 `wdth` 轴，组件有
独立空间约束、原有省略规则并满足单行等条件时才启用。达到安全限度仍
放不下时，继续使用该组件原有的省略/布局规则，不缩小字号或改变主题动画。
不含 `wdth` 的静态字体，以及不能改变 advance 的轴，仍保留原排版。
自定义大写 `WDTH` 不被冒认为标准 `wdth`。

## 2. 真实仓库状态与历史核查

本轮开始实时读取 GitHub refs、提交对象、父链、文件和 Actions；没有把
上一轮报告当成验证证据。

| 项目 | 本轮开始时的真实值 |
| --- | --- |
| 仓库 | [SOLHK/Swirl](https://github.com/SOLHK/Swirl) |
| 集成分支 | `work/core-completion-20261017` |
| 集成分支 HEAD | `6b9628e6a9a5a864e5a7e210cd916868804564c8` |
| W1 专用分支 | `work/vf-smart-width-w1` |
| W1 起始 HEAD | `134298b2ea9576b6bccd6c60592e89b7d5e6c6e1` |
| 共同基点 | `50d2a8e8bac702abb2cdc0212f43953b8b78ffef` |
| 当时分支差异 | W1 独有 4 笔、集成独有 2 笔；没有直接合并集成分支 |

集成独有的 `b266022ef291ffd1429a467ed201b2c80975c0ce` 和
`6b9628e6a9a5a864e5a7e210cd916868804564c8` 是原生手动路由、连接诊断及
Rust 构建范围修正，涉及 Core/engine/ConnectionsPage，未纳入本轮字体改动。
收尾重新读取时集成 HEAD 仍为上表值。

以下四笔均真实存在于 W1 父链，且顺序相连：

| 原检查点 | 完整 SHA |
| --- | --- |
| W1 算法审计 | `6bc2faef3bfa2463151d3d78e85e7043671d11bd` |
| 宽度求解修复 | `5e06537bf8ef83f99b5eef33d87d255a135a9993` |
| 宽度边界测试 | `c9fb34a6fcf86ad9f2f4cd49351a4eb065d6b871` |
| Windows CI 接入 | `134298b2ea9576b6bccd6c60592e89b7d5e6c6e1` |

每次推送前重新读取远端 HEAD，使用正常 fast-forward 更新并要求匹配已读
父 SHA；上传树与本地索引树逐字节一致后才更新分支。推送后再次读取远端
并同步相同本地树。没有强推、rebase、重写共享历史或覆盖其他窗口的提交。

## 3. Windows CI：通过、失败和取消分别保留

运行链接均指实际 push 触发的运行。数量为 QTest 测试执行记录，不包含
`initTestCase`/`cleanupTestCase`；同一测试在不同后端重复执行会分别计数，
不能把总数当成同样数量的独立功能。报告/门槛错误与测试失败也分别记录。

| 源 SHA | 运行 | QTest 通过 / 失败 / 跳过 | 完整流程状态 |
| --- | --- | --- | --- |
| `134298b2ea9576b6bccd6c60592e89b7d5e6c6e1` | [39471340589](https://github.com/SOLHK/Swirl/actions/runs/39471340589) | 62 / 0 / 9 | 起始 CI 已成功；3/3 CTest、完整应用和导航 smoke 成功，没有需要臆造的起始 CI 故障 |
| `127e9fc229bc090cebdb2710745bc78486261900` | [39474297331](https://github.com/SOLHK/Swirl/actions/runs/39474297331) | 63 / 0 / 9 | 字体阶段成功；后续 push 按既有并发规则取消完整应用阶段，整体不计成功 |
| `82541d4033dc444697a0786192cdcd3e7960629f` | [39476067462](https://github.com/SOLHK/Swirl/actions/runs/39476067462) | 79 / 4 / 9 | 失败：同一不对称字体断言在四个进程失败；完整应用/smoke 跳过 |
| `a64f1d0de47fb5eb82246356dcc4a8200a787499` | [39476884151](https://github.com/SOLHK/Swirl/actions/runs/39476884151) | 79 / 4 / 9 | 同一量化假设导致失败；Unicode 单行修正没有消除这项独立失败 |
| `eb8249b96732949b5449d6882e1b5abc8a8d426e` | [39477546182](https://github.com/SOLHK/Swirl/actions/runs/39477546182) | 83 / 0 / 9 | 五个字体 CTest 和严格报告成功；必要 CI 合同文档更新触发后续运行，整体取消 |
| `11ea18336b3176616672a004ad2a71e17ed65dc6` | [39477948417](https://github.com/SOLHK/Swirl/actions/runs/39477948417) | 83 / 0 / 9 | 完整成功：5/5 CTest、严格报告、完整应用编译、61 次导航请求/61 次 ready、证据上传均成功 |

最终验收源 `11ea1833` 与代码修正 `eb8249b9` 的源码、测试和工作流相同，
两者之间仅更新 `docs/FONT_SYSTEM_CI.md`。本记录的后续文档提交不改变这些
受测文件；不能声称工作流是在一个实际上未触发的文档 SHA 上运行。

### Windows 实际工具链与执行分组

运行于 **2026-10-20 19:06:39 UTC** 完成。实际工具链是 Qt **6.10.3**、
MSVC **19.44.35229.0**、Visual Studio 2022 **x64**、C++**23**，使用
`windows-2022` 托管 runner。CMake 配置和编译均实际成功。

| 原始 XML 分组 | 通过 | 失败 | 跳过 |
| --- | ---: | ---: | ---: |
| `font-selection.xml` | 29 | 0 | 9 |
| `font-axis-policy.xml` | 34 | 0 | 0 |
| `font-native-raster.xml` | 10 | 0 | 0 |
| `font-width-simulated-125.xml` | 5 | 0 | 0 |
| `font-width-simulated-200.xml` | 5 | 0 | 0 |
| **合计** | **83** | **0** | **9** |

五个 CTest 总耗时 **38.74 秒**，报告门槛错误 **0**。原生和两种模拟进程
实际窗口 DPR 分别为 **1 / 1.25 / 2**，逻辑 DPI 都为 96；读取的是测试
记录的 QWindow 上下文，而不是仅根据环境变量推断。完整应用 smoke 的
退出码为 **0**，实际字体为 `Swirl Automation Probe`，61 次请求均 ready，
涉及 60 个 routeKey；这不等于 60 或 61 个页面均完成逐项视觉验收。

已下载并检查原始 artifact **12290372611**（25,237 字节），其 SHA-256
与 GitHub 摘要一致：
`46bee2b7cd4de6ef7050d391a79df5311523a47a5dc357fe2d75c3c857294e72`。
原始 artifact 保留至 **2026-10-27 19:06:34 UTC**；逐项结果、关键原始
消息、XML 及摘要另存随文 evidence JSON，避免短期产物过期后失去本轮证据。

Windows 原生字体后端使用 Swirl 原有的 `windows:fontengine=freetype`
配置，场景图请求 D3D11 WARP；不能把这个结果称为 DirectWrite 字体引擎
或用户显卡测试。离屏选择组和完整应用导航 smoke 使用 software/offscreen。

九个跳过均保留原名及原因：

| 测试 | 跳过原因 |
| --- | --- |
| `importOptionalPingFangUiCollection` | 没有提供合法本机私有字体 |
| `optionalVariableAxesAndLivePreview` | 没有提供本机可变字体夹具 |
| `optionalRestartRead` | 仅供原有私有恢复测试的独立子进程调用 |
| `optionalRenderMatrix` | 没有本机字体及私有证据目录 |
| `optionalNativePointSizes` | 没有本机 Windows 字体夹具 |
| `optionalPaintedPreviewAxes` | 没有本机字体夹具 |
| `optionalRasterQualityMatrix` | 没有授权本机字体及证据目录 |
| `optionalPhysicalFontIdentity` | 没有本机源字体及证据目录 |
| 选择组内的 `nativeGlyphsHaveNoColourFringes` | 离屏进程不满足原生 Windows 条件；独立 native 组必须实际通过 |

公共测试的跨进程重启 `automaticProfilesRestartAcrossProcess` 仍实际执行，
不能把私有 `optionalRestartRead` 跳过误写成整个重启功能未经测试。
新公开宽度测试、原生测试或模拟组缺失/跳过均使严格报告失败。失败数据行
也不能被同槽的另一个成功数据行掩盖。Python 报告器回归实际 13/13 通过。

### 本轮实际 Windows 失败的最小复现与修正

失败来自本轮新增测试，不是原有生产编译问题。原创不对称字体范围为
96 / 100 / 100，在 50 px 下，测试原先要求严重不足时必选 `wdth=96`。
Windows 实际选择 `96.40000152587891`。

最小 Qt `QTextLayout` probe 在 Linux 已复现完整 hinting 的等宽平台：

| 同一原创字体、同一字符串 `AAAAAAAA` | wdth 96.4 实际宽度 | wdth 96 实际宽度 | 正确选择 |
| --- | ---: | ---: | ---: |
| Linux 50 px，默认 hinting | 235.125 | 231.875 | 96 |
| Linux 50 px，完整 hinting | 232 | 232 | 96.4 |
| Linux 125 px，完整 hinting | 592 | 584 | 96 |

`eb8249b9` 的 Windows 原始 XML 同样记录 50 px 两种 hinting 下均为
232 / 232，选择 96.4。选择较靠默认的等宽坐标符合产品行为，生产求解器
无需为此改成更激进的压缩。修正同时测试两种 hinting，严格要求所选 advance
等于实际最小 advance，并验证等宽时的坐标偏好；在 125 px 相邻候选可被
实际度量区分时，仍保留原来的严格 `wdth == 96` 端点断言。没有删除失败
槽、跳过后端、放宽压缩下限或栅格容差。

## 4. 求解器：本轮修复和可证明的边界

`FontAxisPolicy` 的通用宽度契约不变，仍保留真实设计默认值。新增
`FontWidthFit.h` 只是把独立宽度求解从管理器中提取出来，便于直接回归；
QML 仍统一调用 `SwirlFontBinding → FontManager`，没有页面级算法副本。

| 已证实的问题 | 修复及对应证据 |
| --- | --- |
| 历史坐标可能来自旧文本、字体或字号，旧早返路径绕过 85% 和实际改善检查 | 所有历史/新候选走相同有效性检查；七类不安全历史、精确 85% 边界与紧邻下界值均有确定性回归，另有真实 steep 字体反例 |
| 相邻更宽坐标放不下，并不能推出其他更宽坐标也放不下 | 扫描有限候选后再判断历史；非单调函数要求 98 取代历史 94，即使邻近 96 不适合 |
| 原按默认值百分比的步长在窄轴区间重复夹到端点 | 在真实允许区间均匀取十点；合成字体 98.5 / 100 / 140 的 99.1 局部谷由真实 Qt 找到，旧 99/98.5 样本不能找到 |
| float 量化可能使候选重复或落到下界外 | 使用实际可表示 float 并向区间内收；单个 float 间隔的测试只执行一次候选测量 |
| 多行/多长度字符串可以从 C++ 入口绕过 QML 排除 | 两层都排除 LF、CR、U+2028、U+2029、U+009C；直接调用断言保持默认且零测量 |

执行有严格上界：每次最多十个新坐标和一个有效历史坐标；计入自然宽度
最多十二个不同的真实测量，重复坐标由原缓存命中。若无需进入拟合，仍
保留自然测量/缓存查询，没有无限搜索或基于单调性的二分搜索。

**这是有界近似求解器，不保证全局最优。** 测试明确构造了 95.5 附近极窄
的可行谷，十点采样没有命中时保留默认值；这条用例证明了限制，而不是
证明所有局部最优都会被找到。多个新候选适合时偏向设计默认；没有可完全
容纳的候选时可以选择安全的部分改善，剩余文字由原控件省略。
`fitted=true` 表示轴发生安全调整，不承诺全文已完全容纳。

原有进入/退出 4 逻辑像素和保持 2 像素的滞回规则保留。小于进入边界的
轻微不足可能继续使用默认值；恢复边界附近也可能暂时保留已收窄坐标。
这项稳定性选择有测试，但不是“只差任意小宽度就立即改变轴”的规则。

### 85% 的独立评估

没有找到 OpenType、Qt、HarfBuzz 或 FreeType 将自然 advance 的 85% 定义为
普适可读性下限的依据。[OpenType 的 wdth 定义](https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_wdth)
描述设计坐标的语义，不保证每段文字或每个汉字的实际宽度与轴坐标线性对应。

因此保留上一轮的 **85% 整段实测 advance 下限**和 **90% 默认轴坐标下限**，
在代码中集中命名并明确标为暂定产品选择。本轮没有改成另一个没有证据的
数字，也没有新增用户需要理解的实验滑块。历史坐标现在也必须受其约束。
这些限制能阻止已构造的过度压缩，却不能证明中文笔画比例、组合字符、
所有字号或所有字体都更容易阅读。真实字体的主观验收仍未完成；后续若
需要调整，应以明确字体/字号/语言的授权样本和物理观察为依据。

## 5. 回归矩阵与稳定性证据

下面区分新测试、已有测试的重新执行，以及尚未覆盖的物理情形。

| 要求 | 实际自动化证据 | 能证明的范围 |
| --- | --- | --- |
| 足够、略紧、严重不足 | `automaticWidthUsesRealAdvances`、纯 solver 边界 | 默认恢复、有限收窄、安全部分改善及原有滞回 |
| 轴最小/默认/最大、不对称与退化范围 | 原有真实 `verifyVariableAxes` 的端点栅格、`FontAxisPolicyTests`、新增 asymmetric 用例 | 标准轴真实端点/默认、非法元数据排除、受限搜索区间；自动收窄本来不向最大宽度扩张 |
| 无 wdth、静态、只变轮廓不变 advance | 公开真实字体回归、CFF/静态导入和 QML 家族切换 | 不凭空生成标准轴，不能节省 advance 时保持默认 |
| 复杂文字、组合字符、中英、数字标点、短/长字符串 | `automaticWidthShaping`：8 类文字 × 3 字号 × 2 字重 × 2 逻辑 DPI = 96 组合，另 3 个点字号/DPI 组合 | 使用真实 `QTextLayout` 对照完整字符串测量；Arabic、Hebrew 和 CJK 通过实际 Qt fallback 路径，不是私有字体质量认证 |
| 自动/手动切换 | 既有 profile/跨进程重启测试；QML 手动 107.25 在 30 px 容器仍保持原值 | 自动拟合不覆盖手动坐标，未确认预览与已应用设置隔离 |
| 连续 Resize 与边界往返 | 同一真实字体 400 次往返，保留 history；QML 24 次交替 0.2 px 抖动 | 前者零新增真实测量且安全下限保持；后者稳定后零字体变更通知 |
| 字体/字号/字重/内容变化 | 8 类缓存键差异；QML 四轮静态/可变字体切换 | 不同文本、字号、字重、间距、斜体、feature、家族不错误共享测量 |
| DPI/DPR | 96/144/192 逻辑 DPI 测量；窗口观察者；独立 1.25/2 模拟进程 | 测量设备和上下文行为；不是物理系统缩放或真实跨屏 |
| 页面切换 | 完整应用导航 smoke 与既有缓存对象身份检查 | 路由/过渡就绪；不承诺每页均零重新计算或已经逐屏视觉验收 |
| 弹窗开关 | 同一 Dialog/header 六次完整 open/close；零 QML warnings | 公共弹窗有限循环，不覆盖全部 popup 状态或 Gateway 专用菜单开关 |
| 字体资源失效/重导入 | 字体数据库 add/remove 同步清空宽度缓存；已有 metadata replacement、预览资源失效与恢复测试 | 资源通知与替换链路；不承诺任意未发通知的外部文件修改自动生效 |
| 内存与无效重复更新 | 测量缓存最多 256 条；策略缓存 256、元数据 64；窗口观察者生命周期、idle 检查 | 有界缓存和对象生命周期；不是长期 RSS/private bytes 无增长证明 |

最后一次本地 Release 全回归针对 `eb8249b9`：Qt 6.10.3、Linux x86_64、
GCC 13.3.0，2/2 CTest，9.25 秒；63 通过、0 失败、9 跳过，报告错误 0。
Windows 专项在本地没有执行，另由上表准确 SHA 的 Windows CI 证明。
所有 92 个生产 QML 文件也通过 Qt 6.10.3 只读 parser，没有格式重写。

## 6. QML 覆盖范围

源码共 92 个生产 QML 文件、386 个 `SwirlText` 定义/用法。原始 `Text`
只有公共基类一处；这些是源码统计，不是 386 项实际拟合或视觉通过率。
完整逐类证据见 [QML 覆盖清单](FONT_AUTOMATION_QML_COVERAGE.md)。

| 类别 | 本轮状态 |
| --- | --- |
| 侧栏导航、普通按钮和复用按钮的工具栏 | 保留已有公共单行省略标签接入，重新执行真实控件检查 |
| `SwirlListRow` 列表/设置菜单标题 | 新增 label 角色接入 |
| `SwirlMetricCard` 卡片名称 | 新增；data 角色数值保持原行为 |
| `SwirlComboBox` 选中显示值 | 新增独立内容宽度接入；弹出选项保持原规则 |
| `SwirlDataTable` 列标题 | 新增固定单元格空间接入；混合数据单元格没有统一压缩 |
| `SwirlDialog` 标题、`SwirlWindowTitleBar` | 新增，真实公共组件已加载、缩窄和恢复 |
| Gateway 固定 175 dp 菜单的省略标签 | 源码接入与 parser 通过；具体 popup 开关仍待实机补查 |
| 其他页面/大标题 | 只沿用满足原有约束的标签；许多无省略、可换行或无外部宽度约束的标题保持原行为 |

公共 `fitInFixedWidth` 只用于容器宽度由外部拥有的控件；Layouts 仍获得
自然 advance 加 padding 的 preferredWidth。宽度计算扣除左右 padding，
padding 单独变化也触发原有合并更新。不向只读的 `Text.implicitWidth`
写值，不让压缩后的宽度反过来缩小容器形成反馈。

正文、富文本、多行文字、输入/密码/编辑器、代码视图、data 数值显示、
无原有省略规则的普通 context menu/segmented control/下拉选项，以及
共享动画 hero title 不自动收窄。不是按字符串内是否含数字一刀切：普通
标签内的编号/年份仍按标签用途处理。显式 QtRendering 路径保持原行为，
避免与 NativeRendering 使用不同度量策略。Windows 自己的系统 UI 不在
Swirl QML 的控制范围内。

## 7. 性能：新增检查有成本，缓存有可核验的作用

测量缓存键继续使用完整 `QDataStream << QFont << text << dpi`，包括真实
字体值、变量轴、feature 和间距。仅将 wdth 或文本摘要当键会遗漏条件，
本轮没有这样简化。DPR 不重复作为实际 advance 的缩放因子；上游有影响
的字体/逻辑 DPI 值仍会进入完整键。字体数据库通知同步清除缓存。

### 生产 FontManager 的实际微基准

`automaticWidthCacheAndResize` 测量同一原创字体、24 px、`AAAAAAAA`。
首次严重不足的拟合执行 11 次真实 Qt 测量；随后 400 次双向 Resize，
DPR 参数交替 1/2，新增真实测量为 0。计时只包围单次 manager 调用，不
包括测试外部对照 `QTextLayout`、页面布局或绘制。

| 真实运行条件 | 单次调用中位数 | P95 | 首次真实测量 / 后续 400 次新增测量 |
| --- | ---: | ---: | ---: |
| 本地 Linux Release，offscreen | 10.826 μs | 11.538 μs | 11 / 0 |
| 最终 Windows native，DPR 1 | 28.8 μs | 49.9 μs | 11 / 0 |
| 最终 Windows，模拟 DPR 1.25 | 28.3 μs | 31.1 μs | 11 / 0 |
| 最终 Windows，模拟 DPR 2 | 28.8 μs | 29.4 μs | 11 / 0 |
| 最终 Windows，offscreen | 28.1 μs | 29.1 μs | 11 / 0 |

Windows 数值全部取最终 `11ea1833` 原始 XML。特别保留原生组较高的
49.9 μs P95，没有拿前一轮较低的数值替换。Linux/Windows 并非同一机器，
这里不将两行之差解释为平台性能结论。

这不是 240 Hz 帧时间、完整页面耗时或长期内存测试。超过缓存容量、改变
字体/文本、资源重载等仍会执行必要的新测量；“这 400 次为零”不能推广成
“Resize 或切页永远没有测量”。

### 旧五步与当前十样本的同环境比较

另用隔离 probe 从 Swirl 自己的 `50d2a8e8` 提取原五步决策逻辑，与当前
helper 共用真实 QFontMetricsF 测量和相同 QCache。Qt 6.10.3、GCC 13.3
`-O2 -DNDEBUG`、offscreen、96 DPI、24 px、wght 500，五轮交替先后顺序。
“冷”指应用测量缓存为空，共享 Qt 字体引擎已经同样热身。

| 指标 | 旧五步 | 当前十样本 |
| --- | ---: | ---: |
| 首次真实测量 | 6 | 11 |
| 每轮后续 400 次 Resize 的新增真实测量 | 0 | 0 |
| 五轮单次调用中位数范围 | 4.517–4.687 μs | 7.932–8.223 μs |
| 五轮 P95 范围 | 4.607–5.769 μs | 8.412–13.560 μs |
| 严重不足时选择的坐标 | 90 | 92 |

这个 probe 包含求解、QImage 测量设备、缓存键及查询，不含完整 manager
配置/元数据分派、QML 或绘制。旧算法没有同样的安全检查，输出序列也不同；
不是等质量算法的速度竞赛。本轮明确接受更多有界检查的成本，没有宣称
性能提升百分比。原始数值、实际执行的隔离 probe 源文本及资源指纹保存在
随文证据 JSON；其中临时 SDK/工作区路径记录本次执行环境，重跑需换成
操作者自己的路径。完整 UI 性能、长期 RSS 与真实 Windows 字体/GPU 负载
仍为未测量。

相对于本轮起始的 `134298b2` 十样本代码，候选数量没有再增加。按源码的
冷测量调用上界计算，原路径是自然宽度 + 十候选 + 最多两个历史相关坐标，
现为自然宽度 + 十候选 + 最多一个历史坐标，即最多 13/12 个不同测量。
实际重复坐标会被缓存合并。旧路径有早返，本轮为非单调正确性先完成有限
扫描；该上界不是耗时实测，不能推导本轮比起始十样本版本更快。

## 8. 开源研究、复用与许可证记录

先检查成熟实现，再独立修改 Swirl 已有代码。复用现有 Qt 整形、字体引擎、
缓存与 QML 公共路径，没有新增应用运行依赖。fontTools 4.61.1 是原有测试
生成依赖。所有新公开字体几何从项目原创测试笔画生成，没有读取、转换、
复制或上传 Apple 私有字体。

| 一手参考 | 本轮采用的设计依据 | 审查到的许可及处理 |
| --- | --- | --- |
| [Qt 6.10.3 QFontMetricsF](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfontmetrics.cpp)、[QFont](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfont.cpp) | 完整字符串整形 advance；完整 QFont 序列化含轴/特性；不逐字符相加 | Qt 对应文件商业/LGPL/GPL 多重许可；继续调用已有 Qt API，未复制实现 |
| [Qt Quick Text](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/items/qquicktext.cpp)、[Text 文档](https://doc.qt.io/qt-6.10/qml-qtquick-text.html) | NativeRendering 度量、自然尺寸与外部宽度、padding、hard-line/multi-length 语义 | 同上；独立实现公共桥接保护 |
| [HarfBuzz 字体轴](https://harfbuzz.github.io/fonts-and-faces-variable.html)、[字体 API](https://harfbuzz.github.io/harfbuzz-hb-font.html)、[源码](https://github.com/harfbuzz/harfbuzz) | 整形后 glyph advance 取决于完整字体和变体坐标，复杂文字不能简单累计孤立字符宽度 | HarfBuzz 主体旧式 MIT，子目录许可另列；未引入或复制源码 |
| [FreeType multiple masters](https://freetype.org/freetype2/docs/reference/ft2-multiple_masters.html)、[源码](https://github.com/freetype/freetype) | 设计坐标/归一化坐标、真实范围与默认值；hinting 可造成 advance 平台 | FTL 或 GPLv2（依文件及例外）；使用项目原有 Qt 后端 |
| [fontTools variation models](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/varLib/models.py)、[glyph set](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/ttGlyphSet.py) | 变体区域/phantom point 与 advance；可构造有效非单调 gvar 反例 | MIT；只调用现有公开测试 API，无实现拷贝 |
| [OpenType avar](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)、[wdth](https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxistag_wdth) | 合法 avar v1 映射不能倒退；wdth 语义不提供 85% 阅读标准 | 规范作为引用；非单调夹具使用合法 gvar 区域，不伪造非法 avar |
| [Flutter TextPainter](https://api.flutter.dev/flutter/painting/TextPainter/layout.html)、[源码](https://github.com/flutter/flutter/blob/master/packages/flutter/lib/src/painting/text_painter.dart) | 分离内容/排版输入与容器约束，合理复用缓存 | BSD-3-Clause；借鉴约束分离思想，无代码移植 |
| [AutoSizeText](https://github.com/simc/auto_size_text/blob/master/lib/src/auto_size_text.dart) | 有界可用空间和明确回退 | MIT；未将字号二分查找照搬到非单调 wdth，也未引入依赖 |

以上为本轮参考文件/项目的许可证审查记录，不是对所有未来第三方代码的
授权结论。项目既有 Qt/字体许可证义务继续由现有分发规则处理。本轮的
gvar 夹具和 fallback 测量也不能认证所有 HVAR/avar 字体、全部系统字体引擎
或用户私有字体的跨平台兼容性。

## 9. Windows 11 物理实机：全部保留为未完成

本轮只有 Linux 工作区与 GitHub Windows Server 2022 托管 runner，没有
访问用户 Windows 11 或 `D:\Codex`。以下项目没有执行，不能计入通过：

| 后续本机项目 | 应保留的证据 |
| --- | --- |
| 同一 W1 源码与 Qt 6.10.3/MSVC 2022 x64 的真实 EXE | 完整 Git SHA、工具链、启动版本和实际加载字体 |
| 真实 Windows 系统缩放 125% / 200% | Windows 设置、实际 QWindow/DPI/DPR、每轮原始截图；不能使用 QT_SCALE_FACTOR 代替 |
| 同一窗口的混合 DPI 跨显示器移动 | 保持同一窗口/页面对象，记录恢复、抖动、裁切与原始显示上下文 |
| 用户授权原版苹方/其他字体的实际字形与可读性 | 原字体身份、字重/字号/语言、默认与有限收窄对照；私有文件只留本机 |
| 全部关键页面和 popup，含 Gateway 菜单 | 自动/手动、静态/可变字体、大小窗口、反复开关、原省略规则的人工观察 |
| 长时间 Resize、切页和重导入后的进程内存 | RSS/private bytes 时序与对象/缓存数据；256 条缓存上限不能代替此测试 |
| 240 Hz 物理屏幕、帧间隔和主观阅读 | 真实显示刷新率、GPU/scanout 与逐帧证据；托管 WARP 微基准不能替代 |

具体本机命令沿用 [Windows 实机交接](FONT_AUTOMATION_WINDOWS_HANDOFF.md)，
新文件优先保存在 `D:\Codex` 的独立 W1 工作区/证据目录，不覆盖其他窗口
工作。原有像素容差、动画和失败证据保持。完成上述物理项目之前，只能
称为 W1 自动化验收完成、待 Windows 11 物理实机验收，不能宣称整个 W1
最终交付完成。

## 10. 本轮提交与可重跑入口

| 新提交 | 实际修改文件/范围 | 提交前或随后实际验证 |
| --- | --- | --- |
| `127e9fc229bc090cebdb2710745bc78486261900` | `CMakeLists.txt`、`SummarizeFontTests.py`、`test_font_ci_reports.py`：原生 Windows 必须执行宽度测试 | 当时报告器 10/10；Windows 字体 63/0/9，完整应用被后续 push 取消 |
| `82541d4033dc444697a0786192cdcd3e7960629f` | `FontManager.{h,cpp}`、`FontWidthFit.h`、QML 公共控件/绑定/Gateway、真实和纯函数测试、原创字体生成、CI 门槛与覆盖文档，共 21 文件 | 本地 Release 63/0/9、parser 92、QML 三种模拟环境通过；首次 Windows 发现量化断言失败 |
| `a64f1d0de47fb5eb82246356dcc4a8200a787499` | `FontManager.cpp`、`FontWidthChecks.h`：C++ 单行分隔符检查与零测量回归 | `automaticWidthShaping` 通过；Windows 仍保留独立量化失败 |
| `eb8249b96732949b5449d6882e1b5abc8a8d426e` | `FontWidthChecks.h`：hinted 等宽候选及可区分的严格端点 | 最小 Qt probe、目标槽、完整本地 63/0/9；Windows 字体 83/0/9 |
| `11ea18336b3176616672a004ad2a71e17ed65dc6` | `FONT_SYSTEM_CI.md`：当前分支、五组门槛、模拟和量化边界 | 报告器 13/13；完整 Windows 状态见本报告第 3 节 |

最后的证据与交接更新为仅文档提交；准确完整 SHA 由该文件的 Git 提交记录
提供，避免在文件内自引用尚未生成的提交 SHA。全部交付保存到 W1 分支，
没有推送集成分支。

安装匹配 Qt SDK 并生成原创夹具后，可重跑原有入口：

```bash
python src/Swirl.Quick/tests/generate_font_metadata_fixtures.py <fixture-directory>
cmake -S src/Swirl.Quick -B <build-directory> -DSWIRL_FONT_TESTS_ONLY=ON -DCMAKE_BUILD_TYPE=Release
cmake --build <build-directory> --config Release --parallel 2
# 先将 SWIRL_FONT_METADATA_FIXTURES 指向上面实际生成的目录。
ctest --test-dir <build-directory> -C Release -R '^swirl-font-' --no-tests=error --output-on-failure
python tools/SummarizeFontTests.py --build <build-directory> --output <result.json> --require-windows
python -m unittest discover -s tools/tests -p test_font_ci_reports.py
```

Windows 使用 MSVC generator/x64 和匹配 Qt 前缀；Linux 不传
`--require-windows`。严格 Windows 命令与环境以已提交工作流为准。这里的
尖括号是操作者需要填写的本机路径，不是已经执行成功的命令参数。
机器可读证据见 [W1-B evidence JSON](evidence/FONT_SMART_WIDTH_W1B.json)。
