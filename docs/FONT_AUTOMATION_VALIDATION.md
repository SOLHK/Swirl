# 智能字体系统：实际构建与验证记录

本记录对应本次从远端 `fcc5937e9121031ac387f120f8c9dc6f242f71b1`
开始的开发，目标分支始终为 `work/core-completion-20261017`。
没有修改 main、强推或更换 GitHub App/Secrets。

## 分阶段 Windows 记录

| 提交 | 字体专项结果 | 完整应用结果 | 运行 |
| --- | --- | --- | --- |
| `142128ea76a67c9d6f80c020e28eca1810398d0c` | Qt 6.10.3/MSVC 编译成功；3 个 CTest 通过；39 个实际 QTest 用例通过，8 跳过，报告错误 0。 | 配置失败：该阶段 CMake 提前引用了尚未提交的三个新 QML 文件。这是真实的阶段拆分错误，未视为通过。 | [39150413627](https://github.com/SOLHK/Swirl/actions/runs/39150413627) |
| `587934dddadc24042e515bc6e5e4467e42f561ad` | 同样 3 个 CTest 通过；39 个实际用例通过，8 跳过，报告错误 0。 | 修复文件登记后配置成功；编译在 Qt 自动 QML 注册处失败：`QQmlElement<FontDisplayContext>` 不能继承 `final` 类，MSVC C3246。 | [39150738774](https://github.com/SOLHK/Swirl/actions/runs/39150738774) |
| `f014feefeb618c43602d9f9fa3df6f459c0ae02e` | 编译成功；策略和原生 D3D11 两组通过，selection 组失败。49 个实际用例通过、1 个失败、8 个跳过；严格报告的 2 个错误均指向同一个重启用例。 | 启用 `SWIRL_BUILD_UI_TESTS=ON` 后完整 Swirl 目标配置、编译及 EXE 存在检查成功。该成功不抵消字体测试失败。 | [39152371090](https://github.com/SOLHK/Swirl/actions/runs/39152371090) |

两次独立字体编译均实际使用 MSVC **19.44.35229.0**、Qt **6.10.3**、
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
忽略子进程结果来修复。修复后的实际 Windows 结果必须另行记录。

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

## 明确保留的未完成项

本阶段没有 Windows 11 用户实机连接，也没有访问 `D:\Codex`。GitHub
交付和云端构建不等于已更新该目录里的应用。没有下载、上传或改写私有 TTC。

历史实际 200% DPI 的 delta 3 / 容差 2 失败、相关平移断言、同一真实
窗口跨屏 DPI、私有字体完整质量矩阵和稳定 240 fps 均没有因本次测试获得
通过。源码、测试、布局和动画不通过降低这些标准来换取成功结果。

后续实机步骤见 [Windows 字体 CI 与交接](FONT_SYSTEM_CI.md)；算法与
模式行为见 [系统说明](FONT_AUTOMATION_SYSTEM.md)，接入路径见
[覆盖表](FONT_AUTOMATION_QML_COVERAGE.md)。
