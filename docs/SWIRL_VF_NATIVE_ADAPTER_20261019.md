# Swirl VF 本地字体适配：实现与验收边界

## 当前结论

本阶段交付的是 Swirl 的字体加载、来源验证及标准可变轴接入代码。
原版 Apple HVGL 字体的转换与保留性验收是独立门槛；不能用下面的合成字体
测试证明 Apple 字形已经转换成功，也不能把文件重命名为 `Swirl-VF.ttc`
视为移植完成。此文不宣称已产出或验收了最终 Apple 衍生字体。

开发前审查的分支是 `work/core-completion-20261017`，基线提交为
`5ad68bcb22a23573d462cbfd972c7120093f504a`。该提交已包含另一个开发阶段的
Xray 互通测试。本改动不涉及 Rust Core、网络协议、UI 布局、导航或动画。
仓库当时没有 `PRO_HANDOFF.md` 和 `FINAL_FONT_WINDOWS_ACCEPTANCE.md`；
已读取实际存在的 `FONT_AUTOMATION_WINDOWS_HANDOFF.md`、
`FONT_AUTOMATION_SYSTEM.md`、`FONT_SYSTEM_CI.md` 及相关原生渲染交接资料。

## 技术依据与保留决策

| 已核对的资料 | 本次采用方式 |
| --- | --- |
| [Qt 6.10.3 QFont](https://doc.qt.io/qt-6.10/qfont.html#setVariableAxis) | 原生 `setVariableAxis()` 接收四字节标签与浮点坐标。`WDTH`、`HGHT` 作为自定义轴保留原坐标，不能把它们解释成字号或百分比。 |
| [Qt 6.10.3 QFontInfo](https://doc.qt.io/qt-6.10/qfontinfo.html#variableAxes) | 从实际匹配字体读取家族与可变轴，而不是把 `QFont::family()` 的请求值当作匹配证据。 |
| [Qt QFontDatabase](https://doc.qt.io/qt-6.10/qfontdatabase.html#addApplicationFont) | 应用级注册 TTC，并读取返回的实际家族列表；所有地区字体面保持可选择。 |
| [QtBase v6.10.3 字体数据库源码](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/text/qfontdatabase.cpp) | 已阅读注册、注销、家族枚举与缓存失效流程。导入只注册最终保存副本一次，取消旧实现的“注册原件、注册副本、注销原件”。没有复制 Qt 实现。 |
| [OpenType avar](https://learn.microsoft.com/en-us/typography/opentype/spec/avar) | 检查轴数、完整记录、输入坐标严格排序、输出单调性，以及 `-1→-1`、`0→0`、`1→1` 锚点。重复坐标不会被字典悄悄合并。 |

既有 `FontAxisPolicy` 已按真实轴范围处理字重和自定义轴，本次没有用假设的
百分比或字体专属经验公式替换它。标题、正文、按钮、导航等沿用组件已有的
字号与字重语义。`wght` 按组件设计字重限制在该字体面的真实范围；
`WDTH`、`HGHT` 在自动模式保留字体默认值。已有标准 `wdth` 单行标签拟合
继续有效，`WDTH` 不进入百分比拟合。自定义轴的自动优化应等待原版行为和
Windows 渲染证据，不能仅因标签相似而套用原转换版参数。

## 本地加载和名称冲突

用户取得适用授权且持有**已验证的标准 OpenType 转换结果**后，可以把文件
放在 `Swirl.exe` 同级的 `fonts/Swirl-VF.ttc` 或 `Swirl-VF.ttc`。
应用字体存储目录内同名文件也能被发现。没有此文件时沿用现有字体选择。
字体本体不会随公开仓库或发布包分发。

启动时和手动导入时均先检查字体容器；HVGL-only 文件在调用字体引擎前
被拒绝，给出需要完成转换的明确说明。现有导入仍先改变预览，用户确认后
才应用；通过上述本地文件放置方式提供的字体允许作为首次启动默认字体。
已有用户保存的家族选择优先。

默认家族候选为内部名称 `Swirl VF UI Text SC`，对应当前简体中文 UI。
TC、HK、MO、JA、Display、Watch 等面不合并成 SC，也不按字体文件名猜测
家族。默认候选只有在 `QFontInfo` 匹配家族、引擎报告全部轴及正确范围，且
`QRawFont` 实际字体表与本地字体面一致时才生效。同名旧字体造成不一致时会报告冲突。选择已导入的
`Swirl VF ` 家族时同样检查来源；检测失败不会写入新的已应用选择。
重启恢复已保存的家族时也复核同一门槛，不能用旧设置绕过检查。

`FontManager::sourceIdentityForFont()` 是按需诊断接口，报告请求/实际家族、
是否匹配本地来源、TTC 面索引、源文件 SHA-256、源轴定义、引擎报告的轴
（`engineAxes`）、轴元数据是否一致（`axisMetadataMatchesSource`）、Qt 版本与平台。
它比较字体表的存在性和字节内容，包括名称、字符映射、轮廓、变量数据、
主要度量及 OpenType 排版表；缺少 fvar/gvar 的静态回退不能靠其余几张表
碰巧相同而通过。轴元数据一致仅证明引擎识别了轴，不代表实际轮廓变化正确；
同样，物理字体来源证据仍不能代替字形行为和视觉验收。
`fontEngineRequest` 字段只表示环境请求，不宣称已经测出实际后端。

字体保存副本仍用 SHA-256 命名，重启和重复导入均复核内容；损坏副本不会
因文件名相同就被信任。导入通过临时文件原子保存，保持用户提供的原件不变。
本阶段保留既有的 128 MiB 单文件上限，并对容器检查采用 4096 面资源上限；若完整转换结果超过大小
上限，应根据真实文件和内存测试调整上限，不能裁剪字体来通过检查。

## Windows 渲染路径

Swirl 的既有默认 Windows 路径是 Qt 6.10.3 的 FreeType 字体后端与现有
Qt Quick NativeRendering。先前交接记录了采用该路径的分数 DPI 彩边依据，
本阶段保留它。Qt 官方指出可选 GDI 后端不支持变量轴；代码没有切换到 GDI。
明确的诊断环境覆盖继续可用，不会被强行覆盖成声称已验证的后端。
即使后端能读取原始 fvar 表，只要 `QFontInfo` 未报告完整轴及一致的范围，
Swirl VF 自动选择和预览确认仍会被阻止；这可避免把 GDI 的表读取当成轴支持。

DirectWrite 对字体本体的原生解析和轴读取需要独立执行 DirectWrite 验收工具。
Qt FreeType 通过、Windows 可以安装字体和 DirectWrite 正确采用全部轴，是
三个不同结论。公开 CI 的 Windows Server 运行器也不等于用户的 Windows 11
实机，更不能证明 100%、125%、150%、175%、200% 物理屏幕清晰度已经验收。

## 已执行的验证

本地实际使用 Qt 6.10.3 GCC SDK，在 Linux 执行完整既有字体 CTest；
结果为 **57 个实际用例通过，9 个明确跳过，0 个报告门禁错误**，生命周期
回调不计入通过数。跳过项是原有私有转换版字体/图像矩阵、独立重启入口及
Windows 原生窗口检查，不被算作通过。

新增的原创建模测试字体只有一个角形 A 字形，不含 Apple 字形数据。三面
TTC 使用 `WDTH`、`wght`、`HGHT`，分别测试 501、499、500 的字重默认值，
以及 900/600 的最大字重。新增检查覆盖：

- 原始标签、隐藏标记、地区面、各自范围和默认值；自定义宽度不被当成百分比。
- TTC 自动发现、实际面索引、完整源文件哈希、人工选择和重启保持。
- 多轴角点和内部小数坐标下真实路径发生变化，轮廓点数保持一致。
- 静态假冒字体缺少变量表，或同名同 cmap 字体改动轮廓时，来源核验失败。
- 一个静态字体即使与自身源文件完全匹配，也因缺少引擎轴元数据而无法应用；
  独立子进程验证旧设置不能绕过检查，避免用两个同时注册同名字体的管理器
  代替真正重启。
- HVGL-only、重复/非单调/错误锚点 avar、损坏缓存被拒绝；首次导入只有一次
  字体数据库注册，重复导入不增加注册。

还实际将本次上传的 `PingFangUI.ttc` 输入同一个加载预检，观察到 32 个面、
61,473,880 字节，在引擎注册前因 HVGL-only 被拒绝。原件 SHA-256 为：

`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`

保留了一次初始测试失败：要求微小 0.5 字重差在 128 px 下必然产生不同的
FreeType 路径，这个测试前提不成立，合成字体的小位移会量化为相同路径。
测试改为精确浮点坐标读取加上超过该量化步长的不同小数位置；未修改字体
转换保留性门槛或视觉误差容差。最初失败日志与后续完整运行日志均保留。

新增的旧设置回归测试初稿曾在同进程多管理器运行时出现一次恢复断言失败。
当前测试已隔离成真实子进程，验证持久化设置、物理来源、空轴元数据及回退
结果，并要求子进程完整测试报告。旧日志保留；没有把该次失败的底层缓存原因
宣称为已查明，也没有把一次偶然重跑通过视为修复依据。

现有 Windows 字体 CI 将继续运行以上公开测试；原生 Windows CTest 也增加
物理来源和自定义轴路径检查。是否通过必须查看这次实际提交对应的 Actions。
此处 Linux 结果不预先替代 Windows 结果。

## 重复运行

```powershell
python -m pip install fonttools==4.61.1
python src/Swirl.Quick/tests/generate_font_metadata_fixtures.py D:\Codex\Swirl-VF\fixtures
$env:SWIRL_FONT_METADATA_FIXTURES = 'D:\Codex\Swirl-VF\fixtures'
cmake -S src/Swirl.Quick -B D:\Codex\Swirl-VF\qt-build `
    -DSWIRL_FONT_TESTS_ONLY=ON -DCMAKE_PREFIX_PATH='<Qt 6.10.3 MSVC SDK>'
cmake --build D:\Codex\Swirl-VF\qt-build --config Release --parallel 2
ctest --test-dir D:\Codex\Swirl-VF\qt-build -C Release -R '^swirl-font-' --output-on-failure
python tools/SummarizeFontTests.py --build D:\Codex\Swirl-VF\qt-build `
    --output D:\Codex\Swirl-VF\qt-results.json --require-windows
```

原版 HVGL 拒绝检查可额外设置 `SWIRL_TEST_SOURCE_HVF` 为用户本地原件路径，
该可选检查只读取文件并记录哈希。不要将它设置成旧私有转换版测试参数
`SWIRL_TEST_TTC`；后者有其原有的五面、标准 wdth 基准，不能冒充本次新源。

加载、扫描和完整来源比对没有进入每帧文字布局或动画绑定。此阶段没有
原版转换字体的启动、内存或帧率基线，因此不声称性能提升比例。
