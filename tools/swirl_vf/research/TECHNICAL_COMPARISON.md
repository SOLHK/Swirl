# Swirl-VF 技术参考对照

审阅日期：2026-10-19。以下结论区分公开资料、仓库实际内容和本工程设计判断。上传字体的字形、轴范围、表结构以单独审计报告为准，不套用参考项目的旧版本数据。

## 1. ACT-02/PingFangUI-VF：有技术经验，没有现成完整转换源码

实际打开了 [项目文件树](https://github.com/ACT-02/PingFangUI-VF) 和 README，并使用 `git ls-remote` 记录 `main` 为 `8a901f9d8820bf8752fa20ca9903a33c9f225bbc`。可见文件为 `README.md` 和 `Animation.gif`；未见可直接运行的完整转换器。README 本身也把重建步骤留给读者实现。

| 参考项目的做法 | 本工程是否采用 | 原因 |
| --- | --- | --- |
| 通过 CoreText 提取实例轮廓和前进宽度 | 保留为独立基准/备选提取路线 | 可以实际观察 Apple 字体引擎输出；必须控制 tracking 和实例坐标 |
| 选择某个 avar 良好的字体面作为提取入口 | 仅作为定位思路 | 新上传 TTC 必须逐字体面核对，不能把其他面的映射替换为同一张 |
| 以少量轴端点作为插值母版 | 不可据此声明无损 | 必须另外验证未采样内部点和多轴混合点 |
| 兼容母版之间合并部分重叠轮廓 | 严格保真默认不采用 | 合并会改变轮廓拓扑，采样兼容不等于整个设计空间始终兼容 |
| 将 WDTH 改成 wdth，并标定 80/100/120 | 不直接照搬 | 只有坐标转换、实际宽度含义和全部联动均可证明等价时才允许重标 |
| 删除 HGHT、修正部分西文字形位置 | 不采用 | 用户要求保留本次原版行为，不以“看起来更好”替代原始数据 |

依据：[README 对应固定修订](https://github.com/ACT-02/PingFangUI-VF/blob/8a901f9d8820bf8752fa20ca9903a33c9f225bbc/README.md)。README 对 HVF 尚无公开说明的描述反映其写作时点；如今 Apple 已公开表规范和 C API。

## 2. Apple 公开规范与原生基准

[hvgl](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html) 说明了 little-endian、自然对齐、shape/composite 层级、稀疏增量及旋转/平移数据；[hvpm](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvpm.html) 说明 TTC 字体面可通过内部 part 映射共享轮廓。映射不能只作用于顶层 glyph；替代 part 必须具有相容的树结构和轴语义。

公开格式为边界检查、结构解码和 tangent blend 的实现提供了依据。原件的 Type 2 并非标准不支持或原则上无法实现；准确的工程状态是：当前研究渲染器尚未完成经过原件独立原生对照的 Type 2 求值，所以明确拒绝该路径。不能把“本轮未实现、未验证”写成“格式没有定义”。含旋转的层级参数可能产生非线性几何，不能先验断言有限个线性 gvar 支持区间能够精确表示全部行为。

Apple 还公开了 [hvf C/Swift 接口](https://developer.apple.com/documentation/hvf)。本工程实现 `platform/hvf_oracle.c`，从用户指定 TTC 字体面读取表，然后直接调用 Apple renderer；以未缩放、17 位有效数字 JSON 记录真实回调，作为将来的独立几何基准。`HVF_set_axis_value` 接受设计空间归一化坐标，不能把用户 wght/WDTH/HGHT 原值直接传入。参见 [轴值 API](https://developer.apple.com/documentation/hvf/hvf_set_axis_value) 和 [renderer 初始化](https://developer.apple.com/documentation/hvf/hvf_open_part_renderer)。

[FreeType 官方提交 03bb58f7c](https://lists.gnu.org/archive/html/freetype-commit/2025-11/msg00038.html) 展示的是调用 Apple `libhvf` 的 macOS 驱动集成，并不是一份可在 Linux 上独立运行的 HVF 算法。该提交用于核对 `<hvf/Scaler.h>` 和链接方法，没有复制其实现。此次使用两个检索系统研究后，没有找到可核实的成熟、独立、通用 HVF 解码库；这是检索结果，不等于断言互联网上绝不存在这种实现。

## 3. 字体构建工具的具体分工

本地使用 `fonttools 4.61.1`，实际读取了本地 `FontBuilder.setupFvar` 源码，并用合成字体运行相应构建接口。

| 工具 | 合理用途 | 不能替代的工作 |
| --- | --- | --- |
| [ttLib / TTFont](https://fonttools.readthedocs.io/en/latest/ttLib/index.html) | 检查、读取、编译标准 OpenType 表 | 从未知 HVF 数据自动恢复正确几何 |
| FontBuilder | 按明确给定的数据创建字体表和 fvar | 猜测原版未说明的映射和主设计 |
| [varLib](https://fonttools.readthedocs.io/en/latest/varLib/index.html) | 从相容母版构建标准变体数据，实例化验证 | 保证采样重建等于 Apple 的层级插值 |
| [designspaceLib](https://fonttools.readthedocs.io/en/latest/designspaceLib/index.html) | 记录轴、来源、坐标转换和实例设计空间 | 修复原版 avar 语义歧义 |
| [interpolatable](https://fonttools.readthedocs.io/en/latest/varLib/interpolatable.html) | 检测母版轮廓顺序、点类型等插值问题 | 单独证明真实字形没有误差 |
| [cu2qu](https://fonttools.readthedocs.io/en/latest/pens/cu2quPen.html) | 出现 cubic 输出时，在显式误差范围内转成 quadratic | 将近似结果表述为数学无损 |
| [TTCollection](https://fonttools.readthedocs.io/en/latest/ttLib/ttCollection.html) | 保留 TTC 字体面与合法共享表 | 任意合并不同 glyph order 的共享表对象 |

TTCollection 的文档特别提醒，读取时共享表对象若遇到不同 glyph order 可能产生错误。因此，字形身份和每面对应关系先于文件体积优化。

## 4. HGHT 和 WDTH 不需要因“大写”而被删除

OpenType 允许自定义轴，要求自定义 tag 以大写字母开头并仅使用大写字母/数字。`WDTH` 和 `HGHT` 具备合法的自定义轴标签形式；“非注册轴”不等于“非法轴”。这使保留原始 tag 和坐标有一条标准路线。依据：[Microsoft 轴标签注册规范](https://learn.microsoft.com/en-us/typography/opentype/spec/dvaraxisreg)。

`wdth` 是注册宽度轴，拥有约定的数值含义。把 WDTH 简单转小写并不自动证明等价，尤其不能用一个字体面的比例代替全部字体面。`avar` 还可能影响坐标归一化。Microsoft 对其记录顺序、重复 from 值、必需锚点给出了规则；遇到不规范原数据，应记录原始顺序并实测 Apple 的解释，不能偷偷排序/去重后声称完全保留。依据：[avar 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)。

## 5. Windows 与 Qt 必须分别验证

用户指定的 DirectWrite 概述中，关于任意实例不受支持的段落描述的是较早的 Windows 10 Creators Update。现代 [Factory6 按物理面创建资源](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefactory6-createfontresource) 和 [FontResource 按轴值创建实例](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface) 支持任意轴值；缺省轴用默认值，越界值会被钳制，所以必须 [回读实际轴值](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontface5-getfontaxisvalues)，并检查 [真正输出的轮廓](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphrunoutline)。

Qt 从 6.7 提供 [QFont::setVariableAxis](https://doc.qt.io/qt-6/qfont.html#setVariableAxis)，支持自定义轴；可选 Windows GDI 字体后端不支持这一能力。[addApplicationFont](https://doc.qt.io/qt-6/qfontdatabase.html#addApplicationFont) 接受 TTC 并返回注册 ID，再由 `applicationFontFamilies(id)` 查询实际字体家族列表；“加载成功”“变量已设置”“实际匹配到了该文件”“曲线正确变化”仍是不同证据层级。

本工程 native DirectWrite probe 与 Swirl 的 Qt 运行测试分开记录。已有 Qt FreeType 后端若经过此前渲染优化，不因为新增 DirectWrite 验收工具就直接替换它。合成字体 CI 只验证代码路径；原版/转换字体、系统安装、真实 UI、物理显示器和性能基线仍需要对应环境的真实记录。
