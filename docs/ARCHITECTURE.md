# Swirl Qt-only 架构与演进边界

当前仓库的运行与打包链全部基于 **C++23、Qt 6 Quick/QML、CMake 和 Windows NSIS**；不再维护 C#、WPF、.NET 或旧 Inno Setup 项目。

## 当前已经实现

- `src/Swirl.Quick/qml/`：桌面 QML 界面、演示页面、状态交互和功能模块草稿
- `src/Swirl.Quick/app/`：Windows 桌面背景/图标提供者及草稿存储
- `src/Swirl.Quick/network/CaptureService.*`：真实本地 HTTP/CONNECT 会话抓包；独立于代理核心
- `src/Swirl.Quick/tests/`：输入、抓包、窗口回归
- `src/Swirl.Quick/packaging/Swirl.nsi`：Qt 测试版本 Windows 安装包

## 后续建议分层（未实现）

```text
Qt Quick / QML 页面
    ↓
C++23 Application Services（配置、规则、订阅、诊断）
    ↓
ProxyEngine 抽象（启动/停止、选择节点、配置检验、状态、事件）
    ↓
MihomoAdapter（独立进程、控制 API、运行目录/凭据保护）
    ↓
Mihomo 代理引擎
```

`ProxyEngine`、`MihomoAdapter` **目前尚未创建**，不能把演示 QML 状态或 HTTP 抓包服务当成代理引擎。

建议分阶段实现接口、适配层、真实连接与代理切换，再实现规则、订阅、TUN、日志与调试扩展。每一阶段必须在 `test` 分支进行 Windows 构建与实际功能测试，验收后按保护流程晋级 `main`。

## 旧源码退役

2026-10-12 按仓库所有者要求从当前分支删除了 `AdShield/`、`AdShield.Tests/`、旧 `installer/`、对应的 C#/.NET 工作流和旧内核下载脚本。**删除文件不会改变过去的 Git 提交历史**，需要参考旧实现可查看 [备份分支](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012)。当前 Qt 安装程序不包含旧 C# 代理实现，未来网络核心能力需要重新对接或实现。
