# 智能字体系统：实际构建与验证记录

## W1-B 最新记录入口

智能宽度的接续研发位于 `work/vf-smart-width-w1`，本轮未合并或推送集成分支。
四笔历史提交的实时核查、Windows CI 的真实失败与修正、QML 覆盖、性能
数据和未完成的 Windows 11 物理验收，集中记录在
[W1-B 验证报告](FONT_SMART_WIDTH_W1B_VALIDATION.md)。下文保留先前集成阶段
的事实和失败证据，不能用其中的旧成功替代 W1-B 对应提交的测试。

以下历史记录对应从远端 `fcc5937e9121031ac387f120f8c9dc6f242f71b1`
开始的开发，目标分支始终为 `work/core-completion-20261017`。
没有修改 main、强推或更换 GitHub App/Secrets。

## 分阶段 Windows 记录

| 提交 | 字体专项结果 | 完整应用结果 | 运行 |
| --- | --- | --- | --- |
| `142128ea76a67c9d6f80c020e28eca1810398d0c` | Qt 6.10.3/MSVC 编译成功；3 个 CTest 通过；39 个实际 QTest 用例通过，8 跳过，报告错误 0。 | 配置失败：该阶段 CMake 提前引用了尚未提交的三个新 QML 文件。这是真实的阶段拆分错误，未视为通过。 | [39150413627](https://github.com/SOLHK/Swirl/actions/runs/39150413627) |
| `587934dddadc24042e515bc6e5e4467e42f561ad` | 同样 3 个 CTest 通过；39 个实际用例通过，8 跳过，报告错误 0。 | 修复文件登记后配置成功；编译在 Qt 自动 QML 注册处失败：`QQmlElement<FontDisplayContext>` 不能继承 `final` 类，MSVC C3246。 | [39150738774](https://github.com/SOLHK/Swirl/actions/runs/39150738774) |
| `f014feefeb618c43602d9f9fa3df6f459c0ae02e` | 编译成功；策略和原生 D3D11 两组通过，selection 组失败。49 个实际用例通过、1 个失败、8 个跳过；严格报告的 2 个错误均指向同一个重启用例。 | 启用 `SWIRL_BUILD_UI_TESTS=ON` 后完整 Swirl 目标配置、编译及 EXE 存在检查成功。该成功不抵消字体测试失败。 | [39152371090](https://github.com/SOLHK/Swirl/actions/runs/39152371090) |
| `dfae05d07f84694d12223c9fcd4eddd199373dc1` | Qt 6.10.3/MSVC 编译成功；CTest 3/3，5.98 秒；50 个实际用例通过、8 个跳过、0 个报告错误。真实跨进程重启通过。 | 完整 Swirl 编译成功；导入公开可变字体后的导航测试退出 0，61 次请求均等待到路由和过渡就绪，无 Qt 警告。 | [39175245906](https://github.com/SOLHK/Swirl/actions/runs/39175245906) |
| `8d045ab888e6ed0af6dea87adfb752793c455b5b` | Qt 6.10.3/MSVC 重新编译成功；CTest 3/3，8.06 秒；原始 XML 复核为 50 个实际用例通过、8 个跳过、0 个报告错误。 | 完整 Swirl 重新编译成功；公开字体导航测试退出 0，61 次请求、61 条 ready、60 个实际 routeKey，无 Qt 测试或导航警告。 | [39180142727](https://github.com/SOLHK/Swirl/actions/runs/39180142727) |

上述 Windows 编译均实际使用 MSVC **19.44.35229.0**、Qt **6.10.3**、
`win64_msvc2022_64`、Visual Studio 17 2022 x64。独立测试成功不代表
完整应用成功；所有原失败日志与各阶段结果保留在上述 Actions 运行。

后续集成修复将 `FontDisplayContext` 保持为 QML_UNCREATABLE 的可派生
C++ 类型，并在独立测试里改用 `qmlRegisterTypesAndRevisions`，覆盖与
Qt 生成模块注册相同的模板路径。新增 QML 文件及其 CMake 登记作为同一
提交交付，防止阶段文件不完整。新的完整应用构建还启用已有 UI 检查编译，
仅构建 Swirl 目标，不执行其网络、代理或私有字体测试。

`f014feef` 的唯一测试失败是 `automaticProfilesRestartAcrossProcess`：
子进程已经正常退出且返回 0，但 Windows 下父进程的输出管道为空，未能
读取 `qInfo` 的完成短语。Qt 6.10.3 的
[QPlainTestLogger 实现](https://github.com/qt/qtbase/blob/v6.10.3/src/testlib/qplaintestlogger.cpp)
确实存在将 Windows 无控制台的默认文本输出交给 `OutputDebugStringA`
而不写 stdout 的分支；它与本次症状一致，但本轮没有采集控制台句柄，
不将具体分支判断写成实测事实。实际失败的断言和完整 XML 均已保留在该运行的
证据产物中，未视为通过。对应修复让子进程显式写独立 Qt XML 报告，要求
完整解析、init/目标测试/cleanup 恰好各一个 pass、原完成标记存在，同时
保留原来的真实重启、全部配置断言、超时及退出码检查。不以删除断言或
忽略子进程结果来修复。`dfae05d` 的原始 XML 已确认此用例实际通过。

## 最终字体 Windows 集成结果

`dfae05d07f84694d12223c9fcd4eddd199373dc1` 的运行于
2026-10-18 23:17 UTC 完成，已重新读取完整日志、下载并校验原始产物。
不是仅根据工作流绿色状态推断：

- selection：16 个实际用例通过、8 跳过，3.07 秒。
- 纯策略：33 个数据用例通过，0.01 秒。
- Windows 原生字形：1 个用例通过，2.86 秒。实际日志为 D3D11、
  Microsoft Basic Render Driver、Prefer software device 1（WARP）。
- 三份 QTest XML 完整；生命周期不计入通过数；报告错误和 Qt 测试警告均为 0。
- 完整应用实际选择 `Swirl Automation Probe`，软件离屏导航 61 次请求、
  61 条 ready、退出 0。它们是 61 个请求 ID、60 个实际 routeKey，
  不是 61 个独立页面或弹窗的视觉像素验收。
- 完整应用构建保留原有 C4834 警告：`ScriptRunner.cpp` 两处、
  `GatewayChecks.cpp` 一处；另有 Qt GuiPrivate 配置提醒。
  独立字体目标无编译警告，不能因此称整个应用零警告。

原始产物 ID `12154536745`，ZIP SHA-256 为
`10ecc7999bfe941d7a5d91869f1763c7519899832385fb45fead7bfde999daba`。
GitHub 证据产物的保留期为 7 天；已将不含私有字体或用户状态的来源、逐项结果、
阶段及 smoke 摘要保存到
[FONT_AUTOMATION_WINDOWS_20261019.json](evidence/FONT_AUTOMATION_WINDOWS_20261019.json)。
此 JSON 是对下载产物的结构化摘录，不是另一次执行，也不包含安装包。

同一 SHA 的 [三平台 Rust Core 回归](https://github.com/SOLHK/Swirl/actions/runs/39175245900)
和 [Core implementation validation](https://github.com/SOLHK/Swirl/actions/runs/39175245881)
也已成功；后者日志的实际 `CORE_TESTED_COMMIT` 为该 SHA。字体专用完整
应用构建仍使用默认兼容内核，不能代替 Rust 专用产品验收。

## 8d045ab 的 Windows 字体回归复验

`8d045ab888e6ed0af6dea87adfb752793c455b5b` 的
[字体专项运行 39180142727](https://github.com/SOLHK/Swirl/actions/runs/39180142727)
于 2026-10-19 00:31 UTC 完成。已下载该运行的原始产物，核对运行 API、
产物来源与源码 SHA 一致，并使用该提交中的报告脚本重新解析三份完整 XML。
本节是新一次实际执行记录；前面的 `dfae05d` 结果及历史失败继续保留。

| 检查项 | 本次实际结果 |
| --- | --- |
| 工具链 | Qt 6.10.3、MSVC 19.44.35229.0、Visual Studio 17 2022 x64、C++23。 |
| 字体构建与 CTest | 独立目标编译成功；3/3 CTest 通过，总耗时 8.06 秒。 |
| QTest 原始 XML | selection 为 16 通过、8 跳过；纯策略为 33 通过；原生字形为 1 通过。总计 50 通过、8 跳过、0 个报告错误，init/cleanup 不计入通过数。 |
| 原生渲染后端 | 日志实际创建 D3D11 QRhi，选择 Microsoft Basic Render Driver，`Prefer software device: 1`，即 WARP 软件设备。 |
| 完整应用 | 配置及编译步骤耗时 577 秒，Swirl EXE 存在检查成功；仍是默认兼容内核构建。 |
| 应用导航 | 实际选中 `Swirl Automation Probe`，离屏软件后端；退出码 0，61 次导航请求、61 条就绪记录，61 个不同请求 ID 对应 60 个实际 routeKey。 |
| 警告 | QTest 与导航诊断中没有 Qt warning/critical/fatal。完整应用构建仍有 `ScriptRunner.cpp` 两处、`GatewayChecks.cpp` 一处 C4834，以及 Qt GuiPrivate 配置提醒。 |

Qt 安装、独立配置、字体构建、CTest、严格汇总、完整应用构建和导航步骤
均为 success。8 个跳过项保持独立列示；原生字形项在 selection 离屏进程
中跳过，在独立 Windows D3D11 进程中实际通过。导航就绪检查覆盖路由
构造和转场状态，不代表 61 个独立页面、所有弹窗或最终视觉像素验收。

原始产物 ID 为 `12156730169`，ZIP SHA-256 为
`edcd6023e6ae2c892db2a1bc9cabf5b68ea928c45c6f50eb053989f9b375c1ef`，
本地计算值与 GitHub 产物摘要一致。产物保留至 2026-10-26 00:31:13 UTC；
已将来源、工具链、阶段、逐项结果和导航摘要按白名单保存到
[FONT_AUTOMATION_WINDOWS_8D045AB_20261019.json](evidence/FONT_AUTOMATION_WINDOWS_8D045AB_20261019.json)。
该摘录不包含私有字体、用户状态或安装包，也没有把物理 DPI 或 240 Hz
标为通过。同一 SHA 的 Rust Core 回归有独立失败，字体结果不抵消该失败；
对应问题与后续修复见 [SOCKS5 UDP 实际验证记录](RUST_SOCKS5_UDP_20261019.md)。

## 云端本地真实测试

使用官方安装的 Linux **Qt 6.10.3**、GCC **13.3.0**，Release 构建。
没有用系统另一版本 Qt 或 echo 替代编译。QML 集成运行在
`offscreen`/`software`；这些结果不能证明 Windows D3D11 或物理显示器。

本次验证过程中实际修复并保留了以下失败：

- QFont 的完整值作为轴绑定的直接依赖时，真实 QML 发生反馈回环。
  共享 helper 改为事件排队、比较后发布坐标，最终无此 warning。
- QML 双单位 getter 不能代表原始字号。测试通过 C++ QFont 验证像素
  sentinel 与真实 18 pt；原像素基础组件的默认值和正文 400 不作改变。
- Qt 同值 screenChanged 强制 polish 导致预览额外光栅化。dirty 标记
  修复后零次 idle-raster 断言通过，没有放宽断言。
- 原先只检查 QObject 树遗漏 Repeater 的视觉子项；测试改为查找真实
  QQuickItem 子项并等待就绪，不忽略实际控件。
- 手动数值仅聚焦失焦就可能被四位小数显示回写。最终测试验证保存的
  `623.123456` 不因只读显示变成 `623.1235`，主动编辑仍可提交，关闭
  手动模式不会由 editingFinished 再次激活。

最终本地 `integration-03` 的真实结果：Qt 6.10.3 Release 编译成功，
2/2 CTest 通过，耗时 2.64 秒；严格 XML 汇总 **49 个实际用例通过、
8 个跳过、0 个失败/报告错误**，不计 init/cleanup。该构建已包含真实
`qmlRegisterTypesAndRevisions` 注册模板、子进程重启和最终数值输入保护。
没有发现 Qt QWARN 或编译 warning/error。92 个生产 QML 文件只读解析
成功；报告解析器 8 个 Python 单测及 actionlint 1.7.7 检查通过。

在中间的 `integration-02` 中，CTest 的文本结果为成功，但 Qt XML
尾部截断，严格报告器正确拒绝并报告 17 个错误。原因尚未确定，不能声称
已修复该截断问题。原截断 XML/错误记录留在本轮本地测试证据中；最终
integration-03 文件已直接核查闭合、进程退出 0、严格报告错误 0。
Windows CI 对缺失或截断报告继续判失败。

修复 Windows 子进程报告读取后的 `restart-04` 本地验证也已实际执行：
Qt 6.10.3 增量编译成功；真实跨进程重启目标通过；完整 CTest 2/2，
耗时 2.52 秒，严格汇总仍为 **49 通过、8 跳过、0 错误**。子报告要求
恰好三个 pass、完整 XML 和原完成描述，未发现编译 warning/error 或
QML QWARN。这是 Linux 复验，不能提前替代后续 Windows 运行结果。

已执行的集成检查包括 33 个纯策略数据用例、原有公共字体测试，以及 11
个新增公共集成用例：设计字重/DPI、手动家族配置、真实子进程重启、旧版
设置迁移、真实多轴字形/fallback、缓存限制、显示上下文生命周期、真实
QML 自动/手动和输入状态、附加上下文生命周期、预览资源失效与空闲稳定。

私有字体/子进程专用项以及离屏进程中的 Windows 原生专用项单独标为跳过，
不计为通过。Windows 原生专用项在 Windows CI 的独立 D3D11 WARP 进程
中必须实际通过。结果脚本要求 11 个新增公共用例必须存在且通过，不能
通过不登记 slot、意外 skip 或缺失 XML 报告获得绿色结果。

最终集成提交的实际执行次数和 Windows 状态以本文后续记录及对应 SHA
的 Actions 产物为准；上述初始阶段的绿色字体结果不能替代集成验收。

## 后续核对的用户实机原始报告

本轮接续时重新读取了用户此前提供的
`FINAL_FONT_DPI_ACCEPTANCE_20261019.json` 和
`PERFORMANCE_60_REAL_RETEST_20261019.md`。两份报告均针对旧基线
`fcc5937e9121031ac387f120f8c9dc6f242f71b1`，不是本轮智能字体提交。
以下为报告中的实际结果；本轮没有代为执行这些实机测试，也没有提交其
私有字体、字体哈希、可执行文件哈希或本机状态文件。

- DPI 报告：实际系统为 150%、120 Hz；DPR 1/1.25/1.5/1.75/2 各
  32 例，合计 160/160 通过，像素容差仍为 2。旧 case-0100/0388
  的 delta 3 来自参考图原点差异，更正参考后 delta 为 0；测试域内
  未观察到生产渲染缺陷。报告保留历史真实系统缩放/首次平移问题未复现、
  未完成验收的状态，不能把模拟 DPR 矩阵当成系统实际改到 125%/200%。
- 60 Hz 报告：2026-10-19 01:09:29 +08:00，实际 2560×1600、
  60 Hz、150%/144 DPI、DPR 1.5、FreeType/D3D11，未设置 Qt DPI
  覆盖；9/9 阶段及页面/输入检查通过。静态、滑块、三轴模式的排队呈现
  间隔 p95 分别最高为 17.300、18.638、18.741 ms，仍超出 60 Hz
  的约 16.667 ms 周期，不能宣称所有帧达到 60 fps。该检查不测 GPU
  完成或物理面板扫描，也没有验证 240 Hz。

这些新证据更正了早期文档把旧 delta 3 个例笼统列为当前缺陷的描述；
历史失败原件保留。新智能字体提交仍须用同一严格标准在实机复验。

## 明确保留的未完成项

本阶段没有 Windows 11 用户实机连接，也没有访问 `D:\Codex`。GitHub
交付和云端构建不等于已更新该目录里的应用。没有下载、上传或改写私有 TTC。

新智能字体代码的私有字体完整质量矩阵、真实系统 125%/200% 缩放与
首次平移/同窗口跨屏 DPI，以及稳定 240 fps 均没有因本次云端测试获得
实机通过。旧 60 Hz 复测的阶段成功也不是新版本所有帧 60 fps 的证明。
源码、测试、布局和动画不通过降低这些标准来换取成功结果。

后续实机步骤见 [Windows 字体 CI 与交接](FONT_SYSTEM_CI.md)；算法与
模式行为见 [系统说明](FONT_AUTOMATION_SYSTEM.md)，接入路径见
[覆盖表](FONT_AUTOMATION_QML_COVERAGE.md)。
