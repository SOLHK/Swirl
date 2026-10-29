# Swirl 当前架构 — APEC V3 + 单一 Rust Core（2026-10-27）

## 产品运行路径

```text
Qt 6.12 Quick/QML  (src/Swirl.Quick/qml)
  -> C++23 UI / services / EngineController / NodeStore
  -> ThreadedEngine  [QObject worker-thread facade, no independent network core]
  -> RustCoreEngine + RustCoreLibrary  [checked C ABI and source/build ID]
  -> swirl_api.dll
  -> Rust crates: swirl-core / swirl-protocol / swirl-transport / swirl-dns / swirl-routing ...
```

仅 `core/` 负责代理监听、网络转发、协议实现与 DNS/路由运行时。Qt 层负责产品 UI、状态、订阅节点格式解析、持久化、诊断和 Windows 系统集成。部分本地 HTTP 捕获、网关/代理设置工具是产品辅助模块，**不是**第二套代理内核。

旧 WPF/C#、C++ 转发引擎、MihomoAdapter 和 `stage-mihomo.ps1` 已从当前源码树退役；不要从历史分支重新引入。CMake 使用内部恒定值 `SWIRL_RUNTIME=rust`；旧 `SWIRL_USE_RUST_CORE` 缓存和条件编译已移除，旧 OFF 请求会明确报错。安装包验证检查唯一 Rust 运行时及同源 EXE/DLL 身份。

## 输入格式 != 网络运行时

可以继续解析 Clash YAML、sing-box、Surge/Shadowrocket/Loon/URI、Xray/V2Ray JSON 等允许的节点和配置数据。格式解析只将**已验证可支持**的语义映射到 Swirl 的 Rust 原生策略与节点。未知项、无法完整投影的规则、凭据、TUN、脚本、MITM、重写等不可静默执行或回退到外部引擎。保留订阅来源与加密数据；旧数据迁移逻辑仍属于当前产品兼容需求。

## 构建与验证边界

- `src/Swirl.Quick/CMakeLists.txt` 只构建一个 `Swirl.exe` 产品；`cmake/SwirlRustCore.cmake` 配对唯一 Rust `swirl_api`。
- `scripts/Stage-WindowsRustProduct.ps1` 验证 Release/源码/构建 ID、Rust 自检及安装文件清单；`scripts/RustProductPackagePolicy.ps1` 拒绝各类外部代理可执行文件和测试/私密文件。
- APEC V3 的 Qt 6.12 Windows CI、Rust Core CI、网络安全测试和安装包验证需逐提交独立核对。未验证的字体许可弹窗、实际设备 DPI/GPU 帧率和私有节点不能因架构清理被标记通过。

`docs/` 中的旧版截图、Phase 2/MihomoAdapter 架构和早期 Core 迁移日志是可追溯的**历史记录**，不是当前实现或后续代码准则。旧源码备份：[pre-qt-only-20261012](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012)。
