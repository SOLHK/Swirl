# Swirl

<img src="src/Swirl.Quick/assets/icons/swirl_wave_mark.svg" width="88" alt="Swirl 波浪标志">

**Swirl** 是面向 Windows 的专业网络工具项目，使用 **C++23 + Qt 6 Quick/QML** 开发统一的桌面界面、HTTP 调试与后续代理管理功能。界面设计借鉴 macOS 应用的简洁布局与细腻材质，运行于 Windows。

> **🧪 当前状态：Swirl 1.0 UI Preview（`1.0.0-preview`）。** 仓库当前仅保留 C++23 / Qt 6 代码和构建链；原 WPF/.NET 项目与安装器已退出当前源码树。**这仍是功能预览，不是已完成代理核心的正式客户端。**

[![Qt UI 测试构建](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml/badge.svg?branch=test)](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) · [测试版安装程序（EXE）](https://github.com/SOLHK/Swirl/releases) · [test 分支](https://github.com/SOLHK/Swirl/tree/test) · [Qt 1.0 验收记录](docs/UI_1_0_VALIDATION.md)

## 最新界面截图

以下图片来自 [Qt 1.0 UI 验收提交 `0fb2ad8`](https://github.com/SOLHK/Swirl/commit/0fb2ad8b2779ae0f621b8dd4f3f69c12eaf95585) 安装后的 Windows EXE 实机合成截图，不是设计概念图。节点、流量、延迟和连接状态的示例值**不能当作真实联网数据**。

### 浅色总览

![Swirl 1.0 Qt 浅色总览](docs/screenshots/ui-1-0-Swirl-overview.png)

### 暗色与连接演示

| 暗色界面 | 连接演示（示例数据） |
| --- | --- |
| ![Swirl Qt 深色总览](docs/screenshots/ui-1-0-Swirl-dark.png) | ![Swirl Qt 连接演示](docs/screenshots/ui-1-0-Swirl-overview-demo.png) |

[截图索引](docs/screenshots/README.md) · [验收与限制](docs/UI_1_0_VALIDATION.md)

## 当前真正实现的功能

- **Qt 原生桌面界面**：统一圆角与主题，浅色/深色总览、导航与工具页，Windows DWM Desktop Acrylic 条件式合成和不透明回退。
- **HTTP 会话抓包**：用户手动启动本机显式 HTTP 代理后，可查看 HTTP 请求与响应、记录 CONNECT 隧道、按条件过滤并导出 HAR；不会自动修改系统代理，**不会解密 HTTPS 正文**。
- **工具目录和草稿**：56 个模块入口、32 个可编辑配置草稿页，支持本地保存及 JSON 导入导出；这不意味着对应服务已能执行。
- **测试安装程序**：从 Qt 源码打包为 Windows x64 NSIS `Swirl-Setup.exe`，支持覆盖更新和保留用户设置，当前未签名。

## 仍在开发

| 领域 | 当前状态 |
| --- | --- |
| Mihomo 代理引擎、节点/订阅/策略组 | **尚未接入**，目前为 Qt 演示交互 |
| 系统代理、TUN、真实流量/延迟与连接分析 | **尚未实现**实际接管，界面相关数字是演示 |
| DNS 分流、真实规则执行、脚本扩展、请求改写 | 保留界面/草稿，后续接入引擎和服务 |
| HTTPS MITM、WebSocket 帧检查、PCAP 抓包 | 当前 HTTP 抓包不具备这些能力 |

**架构方向：** 未来在 C++23 中增加独立的 `ProxyEngine` 抽象和 Mihomo 适配层，再逐步接入 Qt 页面，避免将代理内核与 UI 绑定。**此抽象目前是规划，未在代码中实现。** 详见 [架构说明](docs/ARCHITECTURE.md)、[Surge 功能对照](docs/SURGE_FEATURE_MATRIX.md) 和 [Qt 抓包说明](src/Swirl.Quick/CAPTURE.md)。

## 下载和构建

测试版 Windows 安装程序在 [Releases](https://github.com/SOLHK/Swirl/releases) 的预发布版本中，以 `Swirl-Setup.exe` 提供。安装前退出已运行的 Swirl。预览版没有代码签名，请仅在信任项目及发布者时运行。

自行构建需要 Windows x64、Qt 6.8+、CMake、C++23 编译器及 NSIS。Qt 6.10.3 已用于验收，详细操作见 [Windows 构建说明](src/Swirl.Quick/BUILDING.md)。`test` 分支的 [Qt CI](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) 负责实际编译、交互、抓包、页面 smoke、截图和打包；[源码结构校验](https://github.com/SOLHK/Swirl/actions/workflows/build-windows.yml) 负责拒绝旧 .NET 文件，它不是另一个 Windows 应用构建。

Qt 1.0 的既有本机验收记录：39 项输入、32 项 HTTP 抓包、41 项 Windows 原生窗口、61 页面启动及 28 项隔离安装/更新/卸载检查。跨系统、多物理显示器与长时间压力测试未充分验证；删除旧代码后的 CI 结果请以对应 GitHub run 为准。

## 仓库结构

| 位置 | 内容 |
| --- | --- |
| [`src/Swirl.Quick/`](src/Swirl.Quick/) | C++23、Qt Quick/QML、网络抓包、交互测试、NSIS 打包 |
| [`scripts/`](scripts/) | Qt Windows 构建及 GitHub 分支保护辅助工具 |
| [`docs/`](docs/) | 架构、功能边界、截图与验收报告 |
| [`.github/workflows/`](.github/workflows/) | Qt 实际构建、源码结构检查、正式分支保护 |

新开发先进入 [`test`](https://github.com/SOLHK/Swirl/tree/test) 验证，正式分支 [`main`](https://github.com/SOLHK/Swirl/tree/main) 仅在仓库所有者授权并通过保护检查后更新；不自动创建正式版 Release。旧 C# / WPF 项目不再位于当前分支，但可在删除前的 [备份分支](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012) 和 Git 历史中查阅。
