# Swirl 字体

Swirl 默认使用 HarmonyOS Sans SC。字体与应用一起加载，无需联网或安装到 Windows。

“更多 → 字体”可搜索本机字体、查看预览、选择字体，或导入 TTF / OTF / TTC 文件。选择立即应用并保存。恢复鸿蒙字体后重新使用默认字体。自选字体不可用时自动回到鸿蒙字体。

导入文件按 SHA-256 命名，原样保存在 Swirl 的本地应用数据目录 `fonts/` 中，供应用自身使用；原文件移动后仍可使用。导入大小上限 64 MiB。无效文件或保存失败不会改变当前界面字体。苹方、MiSans 等字体在本机已安装或由用户导入后可选；软件不附带这些字体。代码编辑器保留等宽字体，便于对齐代码。

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
