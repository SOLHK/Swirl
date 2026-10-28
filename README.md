# Swirl

> **当前产品只使用 Swirl Rust Core。** 从 [Windows 构建说明](src/Swirl.Quick/BUILDING.md) 和 [Rust 内核说明](core/README.md) 开始。构建、测试和安装包必须对应同一提交；历史迁移记录中的外部内核、旧构建开关和下载命令不适用于当前源码。

<picture><source media="(prefers-color-scheme: dark)" srcset="src/Swirl.Quick/assets/icons/swirl_knot_dark.svg"><img src="src/Swirl.Quick/assets/icons/swirl_knot_light.svg" width="88" alt="Swirl 祥云结标志"></picture>

Swirl 是面向 Windows 的网络工具，桌面界面使用 **C++23、Qt 6 Quick/QML**，**自研代理内核使用 Rust**，源码位于 [`core/`](core/)。Rust 在进程内负责协议、TCP/UDP、DNS、路由和运行时；Qt 提供界面、导入、操作系统集成及 HTTP 工具。产品没有 Mihomo 或其他外部代理内核的调用、下载或回退路径。Clash/Mihomo 等订阅格式仍可导入，格式兼容不代表执行其内核。

> **当前状态：Windows 开发测试版，版本 0.2.16。** 版本以 `src/Swirl.Quick/PRODUCT_VERSION.txt` 为准。功能是否可用以实际运行状态及同提交验收记录为准；协议可导入、配置可保存，不代表所有远程节点、专用 LAN 或高级功能已经验证。

当前界面使用中性灰白主题、14 DIP 同级卡片、APEC 羽翼背景及 Liquid Glass 悬浮侧栏。共享控件保留悬停、按压、释放和键盘焦点反馈；普通按钮不添加交互描边。界面实现与验证范围见 [0.2.16 修正记录](docs/UI_0216_LOCAL_REFINEMENT.md)。

[![Windows Qt 构建与测试](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml/badge.svg?branch=main)](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) · [测试版安装程序](https://github.com/SOLHK/Swirl/releases) · [测试分支](https://github.com/SOLHK/Swirl/tree/test)

## 官方社区

| 入口 | 用途 |
| --- | --- |
| [Swirl官方频道](https://t.me/SwirlUpdates) | 版本更新与官方公告 |
| [Swirl交流群](https://t.me/SwirlHQ) | 使用交流与经验分享 |

Bug 和功能请求请提交到 [GitHub Issues](https://github.com/SOLHK/Swirl/issues)，便于正式跟踪；社区讨论不替代 Issue 记录。

## 主要功能与边界

| 功能 | 当前实现 |
| --- | --- |
| 代理连接 | `ThreadedEngine` 通过配套 Rust DLL 执行原生转发。仅支持经过校验的协议、传输与安全参数组合；不支持的能力明确拒绝，不切换到外部内核或绕过节点直连。 |
| 节点与订阅 | 手动管理节点、订阅导入与定时刷新；节点凭据及订阅地址由当前 Windows 用户的 DPAPI 加密保存。多种格式经过归一化，未知选项保留并明确提示。具体节点能否联网仍需测试。 |
| 路由与 DNS | 规则、全局、直连模式，自定义 DNS、规则与策略组。默认 OpenAI 相关域名使用同一代理选择器；用户自定义覆盖需结合诊断核查。 |
| Windows 系统代理 | 通过明确操作启用当前用户的系统代理。接管前保存恢复快照，正常退出或守护检测到进程退出时按归属恢复；外部软件改动后不会覆盖其设置。 |
| 网络活动 | 从真实引擎采集连接、进程、流量与延迟，支持活动、节点、连接和进程详情。没有采样或未连接时显示空状态。设备信息依赖实际网络采样，不代表已完成所有 LAN 场景验收。 |
| HTTP 工具 | 本机 HTTP 捕获、CONNECT 隧道、按主机名解密的 HTTPS HTTP/1.1 与 HTTP/2，以及 HAR 导出、URL/Header/Body 重写、静态 Mock、TCP 端口转发。HTTPS 内容处理需要配置 CA 并成功解密。 |
| 设置与本地扩展 | 主题、字体、减少动态效果、配置草稿、本地 JavaScript 手动执行与配置模块覆盖。设置卡片与详情保留当前交互状态；草稿入口不等于对应网络服务已实现。 |
| TUN、LAN 与网关 | 当前 Rust 产品不提供已验收的 TUN、LAN 代理或网关数据平面。保留的设置、草稿及归属恢复代码不构成能力通过；不支持的启用操作会拒绝。 |

配置更新经过验证后发布到 Rust 运行时，既有流与新连接的应用范围通过回执区分。节点测试和订阅资料操作不应改变当前出口。**受控回归不能证明所有 Codex、WebSocket 或 SSE 会话已通过真实远端验收**；主动断开、退出程序或明确要求重连的操作仍会关闭对应连接。

HTTP/3 解密、完整断点暂停/编辑、WebSocket 帧检查、HTTP 脚本挂钩及完整私有组网能力尚未获得产品验收。不支持的 WireGuard、TUN 或其他源配置不会交给兼容内核执行，也不会静默改写为另一条网络路径。

详见 [Rust 运行时边界](docs/R1_RUNTIME_CAPABILITIES.md)、[HTTP 捕获说明](src/Swirl.Quick/CAPTURE.md) 和 [本地扩展格式](docs/LOCAL_EXTENSIONS.md)。日期较早的迁移及验收文档保留其原始提交和验证范围，不能作为当前提交的通过证据。

## 历史界面截图

以下截图保留此前 Windows 界面迭代的记录，来源见截图索引；不代表当前 0.2.16 的外观或验收结果。当前界面、任务栏和动态效果应以同提交实际运行的交付证据为准。

### 网络活动

![Swirl 当前网络活动窗口](docs/screenshots/current-activity.png)

### 设置首页

![Swirl 当前设置九宫格](docs/screenshots/current-settings.png)

### 设置详情

![Swirl 当前设置卡片详情](docs/screenshots/current-settings-detail.png)

[截图来源与历史索引](docs/screenshots/README.md)

## 安装与使用

[Releases](https://github.com/SOLHK/Swirl/releases) 中的预发布版本提供 Windows x64 `Swirl-Setup.exe`。下载安装前核对对应提交与构建结果，并退出已运行的旧版 Swirl。当前安装程序未签名。

添加或导入节点后，先检查节点能力说明并完成实际联网测试，再在活动页按需要启用系统代理。TUN、LAN 与网关设置不能因保存草稿就视为可用；HTTPS 解密的证书信任需要明确授权。不同应用读取系统代理或环境变量的方式不同，应通过实际连接路径诊断确认代理是否生效。

安装包包含独立 `SwirlCodexLauncher.exe`（开始菜单“通过 Swirl 启动 Codex”），仅为新进程设置代理环境，不修改持久设置；已有桌面进程会被拒绝。使用前先连接 Swirl 并启用系统代理，再自行完全退出 Codex，通过启动器打开。历史 CLI 请求、长时间输出及 OAuth 诊断分别保存在 [登录诊断记录](docs/CODEX_LOGIN_WINDOWS.md) 和 [网络可靠性记录](docs/NETWORK_RELIABILITY_6A.md#仅为新-codex-桌面进程设置代理)。这些记录中的 HTTP 状态和成功请求仅属于原始测试来源，不代表当前 Codex Desktop 登录、工作区及长连接已经验收。

## 开发与构建

需要 Windows x64、Qt 6.12.0、CMake 3.25+、Cargo 和匹配 Qt 的 C++23 编译器。当前 UI 构建使用 Qt 6.12.0 的 GCC 15.1.0 MinGW kit，配对 Rust `x86_64-pc-windows-gnu`；MSVC kit 配对 `x86_64-pc-windows-msvc`。不能混用 Qt 库、编译器或另一构建目录的 Rust DLL。制作安装程序另需 NSIS。

```powershell
# 在匹配 Qt kit 的编译环境中运行；Cargo 必须在 PATH 中。
cmake -S src/Swirl.Quick -B D:/Codex/build/swirl-qa -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=D:/Codex/toolchains/Qt-6.12.0/6.12.0/mingw_64 -DSWIRL_BUILD_UI_TESTS=ON
cmake --build D:/Codex/build/swirl-qa --parallel 4
ctest --test-dir D:/Codex/build/swirl-qa -E "^swirl-system-proxy-recovery$" --output-on-failure
```

系统代理恢复测试需要可丢弃的独立环境，不能在用户正在使用的代理、TUN、路由或 DNS 上执行设置变更。其余网络回归使用隔离的本机服务；真实远程节点、Codex 登录及长时间输出、TUN 和专用 LAN 验收需另行记录。生产构建使用独立目录，并关闭 `SWIRL_BUILD_UI_TESTS` 与 `SWIRL_BUILD_CORE_TESTS`，不携带测试入口。完整步骤见 [Windows 构建说明](src/Swirl.Quick/BUILDING.md)。

[Windows Qt CI](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) 执行编译、关键回归、截图与打包，触发分支和发布条件以当前工作流为准。CI 生成的离屏截图是渲染检查，不代表真实网络或物理显示性能。构建状态请以对应提交的 GitHub Actions 结果为准。

## 仓库结构

| 位置 | 内容 |
| --- | --- |
| [`src/Swirl.Quick/`](src/Swirl.Quick/) | C++23、Qt Quick/QML、代理引擎、HTTP 工具、测试与 NSIS 打包 |
| [`scripts/`](scripts/) | Windows 构建、配套 Rust DLL 校验、打包与安装维护 |
| [`tools/`](tools/) | 连接路径诊断与本机取证工具 |
| [`docs/`](docs/) | 架构、功能边界、截图与验收记录 |
| [`.github/workflows/`](.github/workflows/) | Windows Qt 构建、源码检查及正式分支保护 |

`test` 用于开发验证，`main` 更新需仓库所有者授权并遵守分支保护。更新主分支不代表发布正式版。旧 C# / WPF 代码保留在 [备份分支](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012) 与 Git 历史中。
