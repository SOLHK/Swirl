# 当前源码与 Windows 交付

Swirl 当前桌面产品使用 C++23 / Qt 6.12 Quick/QML 和进程内的 Swirl Rust Core。现行入口为[项目首页](../README.md)、[Rust 内核说明](../core/README.md)与[Windows 构建指南](../src/Swirl.Quick/BUILDING.md)。

## 运行时与兼容范围

- `ThreadedEngine` 通过 `RustCoreEngine` 和受校验的 C ABI 加载配套 Rust DLL；产品不选择、下载、调用或回退到外部代理内核。
- Clash/Mihomo YAML、sing-box 与 Xray/V2Ray JSON 等仍是可导入的数据格式。原始配置、节点来源及凭据保留，执行能力由 Rust 校验；不支持的参数明确拒绝。
- Windows 系统代理由既有 `SystemProxySession` 和归属恢复守护负责。配置草稿或导入成功不等于已完成真实连接、TUN、LAN 或网关验收。
- HTTP 捕获、字体、设置、脚本及操作系统集成仍在 Qt 应用层；架构与边界见[架构说明](ARCHITECTURE.md)和[HTTP 捕获说明](../src/Swirl.Quick/CAPTURE.md)。

## 构建与来源

版本以 [`PRODUCT_VERSION.txt`](../src/Swirl.Quick/PRODUCT_VERSION.txt) 为准。Windows EXE、Rust DLL、构建 ID 与包清单必须来自配套源码；不能将另一构建目录的二进制或旧外部运行时混入安装包。

使用[当前构建指南](../src/Swirl.Quick/BUILDING.md)及现行打包脚本。`scripts/build-current-portable.ps1` 是现有 Rust 产品构建与打包流程的入口，应随其实际实现使用，不能套用退役内核的旧命令。

当前界面展示与源码记录见[截图索引](screenshots/README.md)。空配置截图、受控本机测试、安装包完整性和真实私有网络验收是不同证据，不互相替代；分支更新、CI 结果与发行状态分别以对应提交的实际记录为准。

## 历史记录

本文件原先记录旧 PR12 双运行时整合及便携包，涉及的旧引擎选择项、外部可执行文件和旧 Qt 构建步骤已退役，现行源码不提供这些操作路径。原始正文仅在 [Git 历史记录](https://github.com/SOLHK/Swirl/blob/05da189c860b7ec84fe1c1da55dc7b4ebf3214d5/docs/CURRENT_SOURCE_INTEGRATION.md)中保留用于追溯，不作为当前安装或构建指南。
