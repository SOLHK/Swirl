# Swirl 截图索引

## 当前 APEC 界面

首页展示当前源码实际构建并运行的 Windows 程序，包含浅色与深色活动页。两张图片使用各自全新的隔离配置，处于未连接状态。没有加载私有订阅、添加演示节点，或虚构出口 IP、流量与性能数据。运行中的五色丝绳祥云结由真实代理状态驱动，因此不在这些离线截图中强制展示。

| 截图 | 内容 |
| --- | --- |
| [apec-activity-light.png](apec-activity-light.png) | 当前浅色网络活动主窗口，未连接 |
| [apec-activity-dark.png](apec-activity-dark.png) | 当前深色网络活动主窗口，未连接 |

截图只展示 UI，不能证明远程节点、TUN、LAN 或 Codex 会话已经通过验收，也不能据此推断动画帧率。截图与本次构建源码配套，修改界面后重新构建与截图，不复用历史图片充当当前版本。来源、版本和文件哈希见[拍摄记录](apec-capture-manifest.json)。

拍摄使用程序既有的 `--ui-preview --preview-page=activity` 和浅色/深色主题参数，并设置新的 `SWIRL_TEST_ROOT`。等待实际羽翼入场动画完成后，在受控纯色背景中只截取本程序窗口区域，不使用用户桌面截图，不改写界面数据。保留正常主题、字体及控件绘制，未通过图像重绘或合成替换软件外观。

## 历史记录

以下文件保留用于历史比较，不是当前首页截图。

| 文件 | 历史范围 |
| --- | --- |
| `current-activity.png`、`current-settings.png`、`current-settings-detail.png` | 此前的窗口与设置页面；文件名中的 `current` 是原始命名，不表示当前版本 |
| `ui-1-0-Swirl-overview.png`、`ui-1-0-Swirl-dark.png` | [Qt 1.0 UI 验收提交 `0fb2ad8`](https://github.com/SOLHK/Swirl/commit/0fb2ad8b2779ae0f621b8dd4f3f69c12eaf95585) 的 Windows 合成截图 |
| `ui-1-0-Swirl-overview-demo.png` | 同期连接演示，示例数据不表示真实联网 |
| `overview-qt-light.png`、`overview-qt-dark.png`、`background-*.png` | 更早的 Qt 视觉迭代，见 [历史 UI 验收](../UI_VISUAL_VALIDATION.md) 与 [背景历史](../UI_BACKGROUND_VALIDATION.md) |
| `pr12-*.png`、`pr12-*.gif` | PR12 阶段的界面与文字对照，按其原始报告理解 |

历史文档中的 Mihomo 引擎、兼容内核和旧 C++ 转发路径只描述当时版本。**当前产品只运行进程内的 Swirl Rust Core**，Clash/Mihomo 等配置导入属于数据格式兼容，不会调用外部内核。当前功能和限制见[首页](../../README.md)、[Rust 内核说明](../../core/README.md)与 [HTTP 捕获说明](../../src/Swirl.Quick/CAPTURE.md)；旧验收结果保留其原始范围。
