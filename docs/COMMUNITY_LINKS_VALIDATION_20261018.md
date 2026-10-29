# 官方社区入口验证（2026-10-18）

README 介绍后与“关于 Swirl”加入官方社区入口，发布文档补充公告/反馈分工。原有 Markdown 内容全部保留；无独立英文 README、Issue 模板或贡献指南需要同步。GitHub Issues 仍用于正式 Bug 和功能请求跟踪。

| 名称 | 固定 HTTPS 地址 | 界面按钮 |
| --- | --- | --- |
| Swirl官方频道 | https://t.me/SwirlUpdates | 官方频道 |
| Swirl交流群 | https://t.me/SwirlHQ | 用户交流群 |

界面复用 `SwirlButton`、现有主题/圆角/焦点/动画；窄区域纵向排列。通过 `Qt.openUrlExternally` 交给系统默认 HTTPS 处理程序，沿用项目主页的启动路径；不接收用户拼接地址，不添加协议处理器、独立窗口或依赖。现有预览的 `scrollToBottom` 钩子补到设置页，用于检查滚动区域底部，正常导航不调用。

验证：

- Qt 6.10.3 / MinGW 增量构建 `Swirl` 成功，含修改后的 QML 缓存编译。
- 现有 `swirl-all-pages` CTest 通过。
- 实际150% DPI下，1100×900及900×650逻辑窗口各运行浅色/深色，四次独立启动退出0，未后处理的Qt窗口截图中社区按钮完整可见。
- 检查两个按钮各只有一个固定HTTPS点击处理器，项目主页原入口保留；Markdown链接与用户提供地址一致，原文保持插入式修改。
- 使用Windows默认TLS校验，两个Telegram页面均HTTP200；返回名称分别为“Swirl官方频道”和“Swirl交流群”。没有加入群组或发送消息。
- 原生桌面输入工具不可用，因此不声称已人工点击验证默认浏览器启动。已验证QML编译、隔离启动与固定URL调用路径；真实桌面点击仍为人工复核项。

GitHub About只读检查：现有中文项目描述保留，网站字段为空。仓库响应报告admin/maintain/push权限，但当前连接提供的仓库工具没有设置写入操作；此能力不等同于可调用的仓库管理写入权限，因此未修改About、描述或网站字段。

实现参考：

- [qBittorrent About实现](https://github.com/qbittorrent/qBittorrent/blob/master/src/gui/aboutdialog.cpp)：在现有关于界面区分主页、交流及正式问题跟踪；仅参考组织方式，未复制代码。
- [Qt外链接口](https://doc.qt.io/qt-6/qml-qtqml-qt.html#openUrlExternally-method)：按桌面关联打开URL；返回成功只说明提交打开请求，不证明外部浏览器已完成加载。

本机原始记录位于 `D:\Codex\outputs\Community-20261018`。本阶段只提交社区相关文件；字体阶段保持独立历史，未改代理/订阅/内核，也未合并或推送main。CI必须按本阶段实际提交SHA核对，不能沿用字体阶段绿色结果。