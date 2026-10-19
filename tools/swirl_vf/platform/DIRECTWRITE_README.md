# Windows DirectWrite 原生验证工具

`directwrite_probe.cpp` 直接使用 Windows 的 `IDWriteFactory6`、`IDWriteFontResource`、`IDWriteFontFace5` 和 Direct2D/WIC。它不依赖 Qt，也不经过系统字体名称匹配来猜测输入文件。

Linux 的占位入口只返回 77 / `NOT_RUN`，不能用于字体兼容性证明。原生结果以记录了操作系统、输入 SHA-256 和源码提交的 Windows 日志为准；公开 CI 仅使用原创几何字体。Windows Server CI、Windows 11 桌面和用户原字体的验收分别记录。

## 运行方法

在有 Visual Studio 2022 C++ 桌面工具、Windows SDK、CMake 和 PowerShell 7 的 Windows 11 电脑上运行：

```powershell
.\run_directwrite_probe.ps1 -Font "D:\Codex\Swirl-VF\Swirl-VF.ttc" -OutputDirectory "D:\Codex\Swirl-VF\evidence\windows-first" -Render
```

每次选择新的输出目录。没有 `Swirl-VF.ttc` 就记录尚未运行，不会把原版重命名成 Windows 字体。`-Binary` 可以指定已编译的程序；`-AllGlyphs` 会把每个字体面、每个测试坐标位置的检查扩展到所有 glyph ID，可能明显增加运行时间。

轴标签区分大小写。实际 DirectWrite 实例可同时报告自定义 `WDTH` 与内建 `wdth`，脚本使用 `ConvertFrom-Json -AsHashtable` 完整保留二者。首轮原生 CI 在 C++ 检查成功后暴露了默认 PowerShell JSON 对象不能容纳这两个键的问题；修复处理方式，没有删除或改名任何轴。

## 实际检查

| 检查 | 执行方式 | 证据 |
| --- | --- | --- |
| 输入身份 | 持有禁止写入/删除共享的文件句柄，BCrypt SHA-256 | C++ 和 PowerShell 双重哈希一致 |
| TTC 字体面 | `Analyze` 获取物理字体面数量；按索引 `CreateFontResource` | 每个 face 的名称、glyph 数量、失败状态 |
| 字体内的轴 | 读取实际 `fvar`，与资源轴范围和默认值比较 | 轴标签、上下限和默认值 |
| 原版三轴 | 要求 `wght`、`WDTH` 或 `wdth`、`HGHT` 存在 | 缺轴立即失败 |
| 接受轴值 | `CreateFontFace` 设置任意坐标；`GetFontAxisValues` 回读 | 请求/实际值，检测忽略或钳制 |
| 曲线发生变化 | `GetGlyphRunOutline` 获取实际几何，结合设计度量形成摘要 | 连续内部点及端点的真实摘要变化 |
| 多轴组合 | 最多四轴的 3 点笛卡尔网格、单轴扫点、16 个内部 Halton 点 | 每个坐标位置的结果 |
| DPI | face 0、默认实例、12/16/24/36 DIP、100/125/150/175/200%、浅/深背景 | 10 张真实 Windows PNG，须另行审阅 |

默认 glyph 集合包括等距取样和中英数字符号、地区汉字探针。字体原本不覆盖的 Unicode 探针会明确记录 glyph 0；这些探针不是一份新增加的字符覆盖要求。全量 Unicode 覆盖是否保留仍由原始/转换字体结构差异报告确定。

## 结果边界

`PASS_NATIVE_PROBE` 的意思是上述原生入口检查通过。它不意味着字形与苹果相同，也不意味着所有未采样轴位置没有异常。以下项目必须另列证据，报告里保持 `NOT_TESTED` / `NOT_EVALUATED`：

- 与 Apple HVF/CoreText 原始轮廓、前进宽度及 avar 用户坐标映射的相等性。
- AAT 与 OpenType 的 GSUB/GPOS shaping 等价性、缺字回退策略。
- Windows 系统安装后的字体缓存/家族枚举。当前工具只执行应用级文件加载，不修改注册表、不安装字体；系统安装必须在有相应许可的测试机上独立完成并复核。
- Qt 实际字体后端、真实 Swirl 页面和窗口交互、动画/滚动性能。
- ClearType 个体设置和屏幕像素级清晰度。PNG 使用软件 Direct2D 灰度抗锯齿，不能冒充物理屏幕 ClearType 的照片或实际 Swirl 截图。
- 其他字体面的截图：它们都做加载/轴值/曲线检查，但自动 PNG 只覆盖 face 0 默认实例。

这个区分尤其重要：DirectWrite 支持不是要求 Swirl 改成 DirectWrite。Swirl 若已选择 Qt 的 FreeType 后端，应独立验证该后端，不能用这里的结果取代 Qt 测试。

## 官方接口依据

- [现代 DirectWrite：按 TTC 索引创建 FontResource](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefactory6-createfontresource)
- [使用任意轴值实例化](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-createfontface)
- [回读实例实际轴值](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontface5-getfontaxisvalues)
- [资源默认值](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontresource-getdefaultfontaxisvalues)
- [实际字形轮廓](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getglyphrunoutline)

这些现代接口的官方最低版本是 Windows 10 build 16299。用户指定的 [Variable Fonts 概述](https://learn.microsoft.com/en-us/windows/win32/directwrite/opentype-variable-fonts) 中关于不能使用任意实例的段落描述的是更早的 Creators Update，不能作为今天 Windows 11 不支持自定义轴的结论。
