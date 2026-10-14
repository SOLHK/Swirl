# Swirl

<picture><source media="(prefers-color-scheme: dark)" srcset="src/Swirl.Quick/assets/icons/swirl_knot_dark.svg"><img src="src/Swirl.Quick/assets/icons/swirl_knot_light.svg" width="88" alt="Swirl 祥云结标志"></picture>

Swirl 品牌图标以 SVG 为唯一设计源：浅色为黑色祥云结、灰白底，深色为白色祥云结、深灰底。Windows 安装器与 EXE 所需的 ICO 会在构建时由同一 SVG 自动生成。

**Swirl** 是面向 Windows 的专业网络工具项目，使用 **C++23 + Qt 6 Quick/QML** 开发统一的桌面界面、HTTP 调试与后续代理管理功能。界面设计借鉴 macOS 应用的简洁布局与细腻材质，运行于 Windows。

> **当前状态：Swirl 开发预览版（`1.0.0-preview`）。** 保留 C++23 / Qt 6 与 Mihomo，正在按参考截图重绘界面并逐模块接入真实功能。尚非正式发布版本，也未完成全部高级模块。

[![Qt UI 测试构建](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml/badge.svg?branch=test)](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) · [测试版安装程序（EXE）](https://github.com/SOLHK/Swirl/releases) · [test 分支](https://github.com/SOLHK/Swirl/tree/test) · [Qt 1.0 验收记录](docs/UI_1_0_VALIDATION.md)

## 当前实现

- C++23 自研 ProxyEngine 抽象、MihomoAdapter、EngineController，独立 Mihomo 生命周期、完整性校验、认证控制 API、Windows Job 进程管理。
- 手动添加、编辑、删除、DPAPI 保存和选择 SOCKS5、Shadowsocks、Trojan 节点；真实本机代理端口、节点切换和请求测试。
- 真实 HTTP 捕获、CONNECT 隧道、按主机名解密的 HTTPS HTTP/1.1 / HTTP/2；Windows CA 生成和 PKCS #12 导入。
- Windows 系统代理、Mihomo TUN、局域网认证代理、DNS 与规则/策略组、计费网络进程白名单。
- URL/Header/Body 重写、静态 Mock 与 TCP 端口转发；本地 JavaScript、配置模块覆盖和配置切换。
- 自研 DHCP 与 Mihomo TUN 网关转发控制；专用 LAN 端到端实机验证尚待完成。
- 保留 Qt 界面、主题、圆角、SVG、HDR 和窗口交互；移除演示数据与模拟成功，未实现功能显示空数据并禁用执行。
- 56 个模块入口和实际本地配置草稿，草稿不代表对应网络服务已经实现。

详见 [第二阶段使用、测试和限制](docs/PHASE2_REAL_NODES.md)、[抓包说明](src/Swirl.Quick/CAPTURE.md)。

当前支持订阅与节点导入。远程节点的完整互通需要实际凭据。WireGuard 等通过 Mihomo 节点配置提供 Windows 对应路线，尚未验证完整的私有组网互通；不兼容 Surge Ponte 私有协议。自动屏蔽 QUIC、断点编辑、HTTP 脚本挂钩和部分高级工具仍未实现。详见 [捕获边界](src/Swirl.Quick/CAPTURE.md) 与 [本地扩展格式](docs/LOCAL_EXTENSIONS.md)。

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
