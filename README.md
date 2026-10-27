# Swirl

<picture><source media="(prefers-color-scheme: dark)" srcset="src/Swirl.Quick/assets/icons/swirl_knot_dark.svg"><img src="src/Swirl.Quick/assets/icons/swirl_knot_light.svg" width="88" alt="Swirl Logo"></picture>

Swirl 是 Windows 网络工具。**唯一的桌面程序**是 C++23 / Qt 6.12 Quick/QML（`src/Swirl.Quick/`）；**唯一的产品代理内核**是自研 Rust Core（`core/`）。Qt 的 `EngineController`、`ProxyEngine` 和 `ThreadedEngine` 是控制与线程隔离层，真正的代理监听、转发、协议、DNS 与路由由 Rust 实现。

产品源码和打包链不包含旧 C# / WPF UI、旧 C++ 转发内核、Mihomo 进程或任何外部内核回退。**支持读取 Clash、sing-box、Xray/V2Ray 等配置格式，不代表使用这些项目的代理核心。**不支持的协议/字段应明确报错，不能静默直连或偷换节点。

> 当前为开发测试版，不是正式稳定发行版。APEC V3 的页面、字体初始化、动效及性能仍需按**对应 SHA**逐项验收；Windows CI 通过不代表所有私人订阅、TUN、Codex 或真实设备已验证。最新变更以 GitHub 分支与 Actions 的实际结果为准。

[Qt Preview CI](https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml) · [Actions](https://github.com/SOLHK/Swirl/actions) · [Releases](https://github.com/SOLHK/Swirl/releases) · [Issues](https://github.com/SOLHK/Swirl/issues)

## 架构与源码

| 模块 | 单一现行实现 |
| --- | --- |
| UI / 页面 / 动效 | `src/Swirl.Quick/qml/`，APEC V3 Qt Quick/QML |
| Windows 应用、字体与组件 | `src/Swirl.Quick/main.cpp`、`app/` |
| 控制层与持久化 | `src/Swirl.Quick/engine/`（Qt facade、DPAPI 节点存储、订阅） |
| 唯一网络运行时 | `core/crates/`：`swirl-api` / `swirl-core` / `swirl-protocol` / `swirl-transport` / `swirl-dns` / `swirl-routing` 等 |
| 与内核的唯一连接 | `src/Swirl.Quick/engine/RustCoreLibrary.*`、`RustCoreEngine.*`、`cmake/SwirlRustCore.cmake` |
| 本地抓包及 Windows 集成 | `src/Swirl.Quick/network/`、`app/`、`tools/` |
| 发布程序 | `scripts/Stage-WindowsRustProduct.ps1`、`scripts/Build-WindowsRustProductInstaller.ps1`、`src/Swirl.Quick/packaging/Swirl.nsi` |

Rust 库必须与 EXE 使用同一源码修订和构建 ID；安装包会检查真实 DLL 及 manifest，并拒绝 Mihomo、Clash、Xray、sing-box 等外部代理可执行文件。订阅源中的 YAML、URI、JSON、配置名称属于**输入数据**，不能误删，否则将破坏导入兼容性。具体架构见 [ARCHITECTURE](docs/ARCHITECTURE.md)、[Rust Core](core/README.md) 和 [构建指南](src/Swirl.Quick/BUILDING.md)。

APEC 设计资料：[基线](docs/SWIRL_V3_APEC_BASELINE.md) · [视觉设计](docs/SWIRL_V3_APEC_DESIGN.md) · [动效](docs/APEC_MOTION_FOUNDATION.md) · [性能](docs/APEC_PERFORMANCE_INTEGRATION.md)。`docs/screenshots/` 中的旧版截图是历史验收材料，**不是现行 APEC V3 的视觉基准**。

## Windows 构建

要求 Windows x64、MSVC x64 Developer Shell、Rust MSVC toolchain、CMake、Ninja，以及通过验证的 **Qt 6.12.0 MSVC x64**。不要混用 MSVC/MinGW Qt DLL，不要复用旧构建缓存，也不要从历史安装包手动拷贝 Rust DLL。

```powershell
./scripts/build-quick-windows.ps1 -QtDir 'C:\Qt\6.12.0\msvc2022_64' `
  -BuildDir 'D:\Codex\build\swirl-apec' `
  -DistDir 'D:\Codex\outputs\swirl-apec\app' `
  -OutDir 'D:\Codex\outputs\swirl-apec' -InputTests -PortableOnly
```

`-QtDir` 应替换为实际验证过的 SDK 路径。正式安装包由同一脚本的 NSIS 路径生成，测试与发布必须使用独立构建目录。CI 构建前核对提交、SHA、回归测试和打包产物；不能把测试版视为正式版。系统代理、TUN、DNS、路由或证书设置修改测试只能在隔离机器进行。

## 使用与社区

导入节点后应先单独验证真实连通性，再开启系统代理或 TUN。节点列表用于展示与测速，节点/出口的实际选择由策略控制；海外默认策略与国内直连规则是否真实生效需要按具体版本验收。

[Swirl 官方频道](https://t.me/SwirlUpdates) · [Swirl 交流群](https://t.me/SwirlHQ)

旧 C# / WPF 和已删除的旧内核仅可在 Git 历史或[旧代码备份分支](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012)查看，不属于现行产品。
