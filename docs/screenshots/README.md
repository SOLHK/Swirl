# Swirl 截图索引

## 当前版本

首页展示本次修复后实际构建并运行的 Windows 程序截图，包含完整应用窗口，处于未连接状态。没有添加演示节点、虚构流量或性能数据。图片用于展示界面，不代表远程节点、TUN、LAN 或 Codex 会话已经通过验收。

| 截图 | 内容 |
| --- | --- |
| [current-activity.png](current-activity.png) | 网络活动主窗口 |
| [current-settings.png](current-settings.png) | 设置首页九宫格 |
| [current-settings-detail.png](current-settings-detail.png) | 设置卡片详情窗口 |

截图与同次提交中的源码配套，重新修改界面后应重新构建与截图，不复用历史图片充当当前版本。

## 历史记录

以下文件保留用于历史比较，不是当前首页截图。

| 文件 | 历史范围 |
| --- | --- |
| `ui-1-0-Swirl-overview.png`、`ui-1-0-Swirl-dark.png` | [Qt 1.0 UI 验收提交 `0fb2ad8`](https://github.com/SOLHK/Swirl/commit/0fb2ad8b2779ae0f621b8dd4f3f69c12eaf95585) 的 Windows 合成截图 |
| `ui-1-0-Swirl-overview-demo.png` | 同期连接演示，示例数据不表示真实联网 |
| `overview-qt-light.png`、`overview-qt-dark.png`、`background-*.png` | 更早的 Qt 视觉迭代，见 [历史 UI 验收](../UI_VISUAL_VALIDATION.md) 与 [背景历史](../UI_BACKGROUND_VALIDATION.md) |
| `pr12-*.png`、`pr12-*.gif` | PR12 阶段的界面与文字对照，按其原始报告理解 |

历史 Qt 1.0 文档中“尚未接入 Mihomo”的说明仅描述当时版本。当前源码已有 Swirl 原生与 Mihomo 兼容引擎、真实系统代理和网络工具；具体功能边界见 [首页](../../README.md)、[引擎验收记录](../PR12_NATIVE_ACCEPTANCE.md) 与 [HTTP 捕获说明](../../src/Swirl.Quick/CAPTURE.md)。
