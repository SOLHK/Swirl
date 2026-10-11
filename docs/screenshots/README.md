# Swirl 截图索引

本目录同时保存最新测试版展示截图和历史阶段的视觉验收证据。**项目首页只展示当前 Qt 1.0 UI 测试版**；历史图片留存是为了让验收报告里的相对路径继续有效。

## 当前测试版：Qt 1.0 UI Preview

来源：`test` 分支提交 [`0fb2ad8`](https://github.com/SOLHK/Swirl/commit/0fb2ad8b2779ae0f621b8dd4f3f69c12eaf95585)，从安装后的真实 Windows EXE 获取的原生合成截图，而非概念效果图。

| 截图 | 说明 |
| --- | --- |
| [ui-1-0-Swirl-overview.png](ui-1-0-Swirl-overview.png) | 浅色总览与断开状态，Windows 实际前景合成 |
| [ui-1-0-Swirl-dark.png](ui-1-0-Swirl-dark.png) | 暗色总览 |
| [ui-1-0-Swirl-overview-demo.png](ui-1-0-Swirl-overview-demo.png) | 连接演示状态，流量、节点与延迟为示例数据 |

注意：当前 Qt 前端没有接入实际 Mihomo 连接、规则执行、系统代理和 TUN。活动网卡信息与独立的显式 HTTP 抓包功能是真实实现。详细依据请看 [Qt 1.0 验收记录](../UI_1_0_VALIDATION.md)。

## 历史截图（不代表最新界面）

- `overview.png`：旧 WPF 主窗口，见 [旧版说明](../LEGACY_WPF.md)。
- `overview-qt-light.png`、`overview-qt-dark.png`：较早的 Qt 视觉迭代，见 [视觉验收](../UI_VISUAL_VALIDATION.md)。
- `background-hierarchy-before.png`、`background-hierarchy-after.png`：历史背景层次前后对比。
- `background-windows-before.png`、`background-windows-after.png`：历史 Windows offscreen 背景对比；见 [背景层次验收](../UI_BACKGROUND_VALIDATION.md)。

不要用这些历史图片替换当前 1.0 展示截图，也不要将演示网络数字表述为实时采集数据。
