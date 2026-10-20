# Windows Rust 便携联网测试包

此包是 `SWIRL_USE_RUST_CORE=ON`、`SWIRL_BUILD_UI_TESTS=ON` 的开发验收预览，供同一台 Windows 11 电脑断开 Codex 时双击运行。它不是普通用户正式发行版。包内有 `Swirl.exe`、进程内的 `swirl_api.dll`、Qt/QML 和 MinGW 运行库、辅助 EXE、许可证、固定哈希清单和一键脚本；不含 `mihomo.exe`、私有订阅、NodeStore 或原始运行时状态。

双击 `TEST-SWIRL-NETWORK.cmd`。脚本默认读取 Git 外的 `D:\Codex\Swirl-acceptance-private-20261020\nodes.dpapi` 和 `.selected`，每次只在 D 盘私有目录生成隔离副本，并把 `SWIRL_TEST_ROOT` 仅设置给测试子进程。可直接看的中文结果在 `D:\Codex\Swirl-acceptance-private-20261020\portable-runs\run-*\结果-直接看.txt`，同目录还有脱敏 `summary.json`。包可移动，但这台电脑上的 DPAPI 副本和 PowerShell 7、Windows curl 是运行条件；缺失时报告 BLOCKED。

黑色窗口分开显示：

- **电脑当前代理控制请求**：仅当 WinINET 指向本机 Mihomo 7898 时，显式通过该端口请求固定 HTTPS 204。它不是“所有应用都能上网”的证明。
- **Swirl Rust 显式代理**：隔离测试版 Swirl 的进程、源码 SHA、EXE/DLL 哈希、`17988` 监听 PID，六项显式代理 HTTP/HTTPS 请求、Rust 收发增量及非回环 TCP PID 采样。PASS 只属于这些请求。
- **完整 Mihomo 独立性**：恒为 BLOCKED，直到 Rust 上游 DNS 和可能的 Windows 透明路径得到更强的排除或追踪。不能从 Codex/browser 在 Mihomo 挂起时断网，推断 Swirl Rust 显式请求失败；也不能从 Swirl 六项成功，推断普通应用已经切换到 Swirl。

一键脚本不会暂停、结束、恢复或启动 Mihomo，也不会修改 Windows 系统代理、WinHTTP、TUN、路由或 DNS。每项 curl 请求最多 20 秒，整轮测试子进程最多 270 秒。它只停止自己启动的测试版 Swirl，并清理该轮原始状态与临时加密副本；异常退出时保留脱敏进度并明确报告清理失败。先在 Mihomo 正常运行时执行一次；以后若用户自行停用 Mihomo，也可在 Codex 断线时直接从本地包重测并查看两行结果。

打包方式：在最终干净源码 SHA 上配置/构建 Release Rust 测试版，运行 `scripts/Build-WindowsRustPortableAcceptance.ps1 -QtDir <Qt 6.10.3 mingw_64>`。脚本只在 D 盘新目录输出，调用 Qt 的 `windeployqt --release --qmldir`，验证运行库和包内文件，再压缩 ZIP。历史 `build-current-portable.ps1` 面向 Mihomo 兼容构建，不能用于此包。

参考的现有实现：[Swirl 自有 Windows Qt 部署工作流](https://github.com/SOLHK/Swirl/blob/93750941ef712d436ccdc642c59a92a68fd599f6/.github/workflows/build-qt-quick-ui.yml) 和 [Qt 6.10 Windows Deployment](https://doc.qt.io/qt-6.10/windows-deployment.html)。此包的脚本独立编写；没有复用兼容构建的 Mihomo 暂存步骤。
