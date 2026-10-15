# Swirl 字体

Swirl 默认使用随应用加载的 HarmonyOS Sans SC（鸿蒙）。内置字体不可用时，Windows 回退到 Microsoft YaHei UI，macOS 回退到 PingFang SC，随后使用系统字体。手动选择仍单独保存；“恢复自动选择”回到鸿蒙。

“更多 → 字体”可搜索本机字体、查看预览、选择字体，或导入 TTF / OTF / TTC 文件。选择立即应用并保存。“恢复自动选择”按当前平台重新选择默认字体；自选字体不可用时也使用该平台默认字体。切换字体时保留完整字形 Hinting 和抗锯齿设置。

导入文件按 SHA-256 命名，原样保存在 Swirl 的本地应用数据目录 `fonts/` 中，供应用自身使用；原文件移动后仍可使用。导入大小上限 128 MiB，大型 TTC 文件按块读取和保存。无效文件或保存失败不会改变当前界面字体。包含多个地区字族的 PingFang UI TTC 导入后选中 `PingFang UI SC`；这仅是用户主动导入时的选择，不改变鸿蒙默认字体。苹方、MiSans 等字体在本机已安装或由用户导入后可选；软件不附带这些字体。代码编辑器保留等宽字体，便于对齐代码。

## 官方来源与完整性

上游：https://github.com/openharmony/resources

固定提交：`0d79cad76b37ba0f3ccb1323c83833c78e0860de`

| 文件 | SHA-256 |
| --- | --- |
| HarmonyOS_Sans_SC_Regular.ttf | 2deabf97eaf17958dc24746b922779d9913008526daf1c853903547505a8f9ca |
| HarmonyOS_Sans_SC_Medium.ttf | 564b0d89943402e4b90fe764bc5726fee12ddbd7d4f681f5150b5b8271e685e8 |
| HarmonyOS_Sans_SC_Bold.ttf | 9aa37f5edd6bf15af8b8b1655b8455753cd61abaf5d53454d4966261923b6c61 |

文件未修改、未裁剪、未转码，三个字重通过 Qt 资源系统随应用提供。

## 许可声明

Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.

HarmonyOS Sans Fonts License Agreement 允许将未修改的字体随非字体软件嵌入、捆绑与分发，要求保留完整版权与协议，并在软件中显著声明字体使用。该协议不是 MIT 或 OFL。

完整官方文本保存在 `src/Swirl.Quick/assets/fonts/LICENSE_HarmonyOS_Sans.txt` 和 `src/Swirl.Quick/packaging/licenses/HarmonyOS-Sans.txt`，嵌入应用，并可从字体设置查看。“关于 Swirl”同样显示字体使用声明。

## PingFang UI 可变字体

用户提供的 Tahoe TTC 包含 wght（字重）与 wdth（字宽）轴，但没有 TrueType hinting 指令。设置 FullHinting 不能给字体补出缺失的指令。Windows 下统一使用其基本地区字族，合并中文别名与 Thin/Light 等命名实例，避免把固定字重实例当作完整 UI 字族。正文通过真实 wght=500、wdth=100 绘制；显式标题字重仍分别使用 500/600/700。其他字体不应用这些轴。文字继续使用原生渲染，未转换或修改字体文件。

## Windows 字形栅格器

在创建 QGuiApplication 前，为 Windows 平台插件选择 Qt 自带的 `fontengine=freetype`。QML 的 `Text.NativeRendering`、全局 `NativeTextRendering`、FullHinting 和 PassThrough DPI 策略保持启用；底层字形栅格器使用 FreeType，而非 Windows DirectWrite。这样不依赖显示器 RGB/BGR 子像素排列，也不需要安装 MacType 或修改系统字体配置。仅影响 Swirl 进程。

同一 Qt 6.10.3 / 150% DPI 场景的对照中，DirectWrite 原生字形有彩色毛边；仅设置 QFont 的 NoSubpixelAntialias 未能消除 Qt Quick 最终绘制的彩边。FreeType 的灰度字形改善了这一问题。2026-10-15 从 OpenHarmony 上游重新下载的 Regular 与内置文件 SHA-256 一致，因此没有替换、加粗或重写字体文件。Qt 官方平台参数说明：https://doc.qt.io/qt-6/qguiapplication.html#QGuiApplication 。

显式 `QT_QPA_PLATFORM=windows:fontengine=directwrite` 或 `-platform windows:fontengine=directwrite` 可用于开发对照；offscreen 等测试平台不会被覆盖。发布验收须在未设置这些覆盖参数时检查实际页面、输入框、切换字体与不同 DPI，不能用“成功启动”代替清晰度检查。

正文统一使用 Medium（500）：鸿蒙使用随包提供的真实 Medium 文件，苹方使用 wght=500 的可变轮廓。标题保留 600/700 层级，字体二进制不做人工描粗。
