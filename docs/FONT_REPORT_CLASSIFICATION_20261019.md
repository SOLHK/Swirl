# 并发字体提交的报告分类修复与精确 CI（2026-10-19）

## 真实失败与并发保留

Core 四阶段完成到 `a429d5bc2efe31f10cfb61d16b16ffbde2a8fc40` 后，重新读取
开发分支发现 `8371eb804b6d3f240090388c4bec90c926904119` 与
`927079e93e2a6830b615c030d51379dfa348cd23` 两个并发字体提交。两者均已按
原顺序保留；本次 Core 任务没有重写其字体拟合、QML、DPI 或物理字体实现。
`a429d5b` 的绿色结果仍只属于那个精确源码。

[8371 字体运行 39204032634](https://github.com/SOLHK/Swirl/actions/runs/39204032634)
及 [927 字体运行 39204734246](https://github.com/SOLHK/Swirl/actions/runs/39204734246)
均实际失败。三个 CTest 均通过，原始 XML 各为 51 个实际通过、9 个跳过、
0 个测试失败，排除初始化和清理。报告器唯一错误是：

```text
Unexpected public font case skip: optionalPhysicalFontIdentity
```

新增的 `optionalPhysicalFontIdentity` 从源码上明确要求本地源字体与证据
路径；缺件时产生显式跳过。公开 Actions 没有这些私有材料。报告器没有
同步该已明确的本地测试分类，因此阻断了后续完整应用与导航步骤。
这两次原始运行、原始 XML 和失败结论全部保留，不因后续修复改写。

## 最小修复

修复提交为 `5adcfcf158a4eb99f56e78d0997af5dbc25bd3d0`，父提交是
`927079e93e2a6830b615c030d51379dfa348cd23`，tree 为
`5f553cf264256b83f10b74d1535b02d9f1dba631`。只修改两个文件：

- `tools/SummarizeFontTests.py`：将这个明确命名的本地测试加入已有的私有
  字体缺件分类，继续原样展示其 skip；物理 DPI 和 240 Hz 标志保持 false。
- `tools/tests/test_font_ci_reports.py`：验证该 skip 不会计入通过、实际
  private identity failure 仍阻断报告，以及必须执行的公开宽度测试
  `automaticWidthUsesRealAdvances` 不允许跳过。未知公开测试跳过、缺失报告、
  生命周期失败、Windows 原生检查缺失和 policy 跳过的原有门禁全部保留。

没有删除测试、修改 QTest 断言、添加 QSKIP、降低像素标准或改变执行菜单。
本地私有字体测试的跳过不是物理设备验收，不能用于增加固定验收分子。

## 独立红绿与原始报告重放

同一组 10 个 Python 报告器测试先对旧实现运行：9 通过、1 失败；失败正是
上述被误分类的 private identity skip。修复后 10 通过、0 失败、0 跳过。
Python 编译检查和 `git diff --check` 通过。

另下载 8371 原始 artifact `12165295964`，ZIP SHA-256 为
`6b4a3f240febd6f6da3cc9d960846b792bedc544f59af545841ba92e820710c0`。
对同一份未修改的三份 XML 分别运行旧、新报告器，并逐项断言结果：

| 比较 | 旧报告器 | 修复报告器 |
| --- | --- | --- |
| 排除生命周期后的通过 / 跳过 | 51 / 9 | 51 / 9 |
| 每条函数、数据行、状态和说明 | 原始记录 | 与旧结果逐条完全相同 |
| 报告错误 | 一个误分类错误 | 0 |
| 物理 DPI / 240 Hz 已验证 | false / false | false / false |

这是报告器重放，没有重新运行 Qt，也没有把 8371 的失败运行改为成功。
真实修复验收以新源码自己的 Actions 为准。

同一修复工作区另外完成 Rust fmt、check、Clippy、188 项单元/集成测试、
1 项 doctest 与实际 Release 构建，均成功；Rust 生产源码未改变。

## 修复源码自己的 CI

以下运行均指向完整 `5adcfcf158a4eb99f56e78d0997af5dbc25bd3d0`：

- [Rust 三平台及原生 Qt/应用 39205098742](https://github.com/SOLHK/Swirl/actions/runs/39205098742)。
- [Font Windows Qt 6.10.3 39205098558](https://github.com/SOLHK/Swirl/actions/runs/39205098558)。
- [App 验证 39205098810](https://github.com/SOLHK/Swirl/actions/runs/39205098810)。

截至 `2026-10-19T06:00:59Z`，三条运行均为 `completed / success`。
每条运行的完整 `head_sha` 已重读；日志、原始 XML 和新 artifact 均已核对。

| 验证范围 | 实际结果与边界 |
| --- | --- |
| Linux、macOS、Windows Rust | 每个平台 188 项单元/集成测试 + 1 项 doctest 通过，0 失败、0 ignored；fmt、check、Clippy、Release 和独立 REALITY 向量成功 |
| 每个平台公共 Python 菜单 | 201 通过、5 个 Qt-hook 明确跳过；未将跳过记为通过 |
| Windows 附加 Python | capture 25 通过 / 1 跳过，management 10 通过 / 1 跳过，五个独立 Qt hooks 5 通过 / 0 跳过；全 job 合计 241 通过 / 7 跳过，是执行次数而非去重测试数 |
| Windows Qt | 原生 CTest 3/3、兼容 CTest 2/2 成功；四份 XML 共 71 个实质通过、0 失败、6 跳过，排除初始化/清理 |
| 完整原生应用 | `SWIRL_USE_RUST_CORE=ON`、Release `Swirl.exe` 成功，日志时间 `2026-10-19T06:00:52.2358626Z` |
| Font | 51 个实质通过、0 失败、9 跳过；报告器 10 通过；完整兼容应用构建成功；导航 61 次请求全部 ready，退出码 0 |
| App 验证 | 精确测试提交为 `5adcfcf…`；189 Rust、25 guard、69 network 通过，5 跳过；源码 tar 的 187 个 regular members 逐字节匹配，0 差异 |
| 公开联网 | 3 个现有 DIRECT HTTPS / native DoH 检查通过；没有 REALITY、Vision、私有节点或完整订阅证据 |

新 Qt artifact `12166167989` 的原始报告细分为：

| 原始 XML | 通过 | 失败 | 跳过 |
| --- | ---: | ---: | ---: |
| 原生 Rust Qt integration | 47 | 0 | 6 |
| 原生 import boundaries | 11 | 0 | 0 |
| 兼容 import boundaries | 11 | 0 | 0 |
| 兼容 native DNS guard | 2 | 0 | 0 |

后续五个 Python hooks 实际执行六个 Qt 对端函数，其中 Shadowsocks hook
同时覆盖 Loon Shadowsocks。它们是独立执行证据，不改变上述原始 XML 的
六个 skip，也不抵消公共 Python 菜单在 Qt 编译前记录的五个 skip。
配对端口的八个回归均实际通过；条件式 netsh 诊断因对端步骤成功而跳过，
这不是测试通过数的一部分。

新 Font 原始 XML 中 `automaticWidthUsesRealAdvances` 实际通过，
`optionalPhysicalFontIdentity` 仍是 skip。`physicalDpiVerified` 与
`refresh240HzVerified` 仍为 false。此工作流的完整应用属于 compatibility
mode；上表 Rust Windows job 才是完整原生 Core 应用的构建证据。

App 的既有源码归档菜单包含 `tools/tests/test_font_ci_reports.py`，但不包含
`tools/SummarizeFontTests.py`。187 个文件逐字节匹配的结论只适用于实际归档
菜单；报告器实现另由提交 blob 与精确源码的 Font 运行验证。

| 原始证据 | SHA-256 |
| --- | --- |
| Windows 日志，289,189 bytes | `5a0dd676a09722a20329e26467caa73dfcd2a8830e8f50d7954196a9fc10cfcd` |
| Qt ZIP `12166167989` | `6d0fbbed44d36bb825fc48551fd2577b807895e8d9290d4d27e995fcbb5611bf` |
| Font ZIP `12165388862` | `7e2c78b3df1f83a8608c41f16fa645129000002bfcedfed6b007ac4f883b87da` |
| App ZIP `12165556755` | `93b96051a9f3abc97481adef64308ce022a6424e1a0ea00cc7fa10284f261f3f` |
| 公网 ZIP `12165566160` | `e712cb1aeeafcace825535fa2cff47fd66db8fc613ca2c189d4bb63c8ef257cc` |

最终逐平台结果、源码归档字节核对、XML/导航和历史失败/跳过由
[结构化证据](evidence/FONT_REPORT_CLASSIFICATION_20261019.json)记录。
其独立复核摘要为 64,211 bytes，SHA-256 为
`7361c6959d8ebe8c5f11d537613d9afe43cc9d07eb331c3cfe7c4c0a6533163b`。
`5adcfcf` 之后的本轮交接提交只改文档/证据，没有把源码运行冒充成文档
提交新触发的 CI，也没有借用旧提交的绿色结果。

固定范围仍为 79 项、6 项已验收、10.83% 已验收权重。REALITY/Vision
仍未启用，完整私有订阅与 Windows 物理设备结果没有因报告分类而改变。
本次修复没有刷新私有订阅、请求供应商节点或访问用户电脑的字体/DPAPI 数据。
