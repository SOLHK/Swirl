# Windows Swirl Core 受控联网核对（2026-10-21）

## 源码和产品身份

- `git fetch origin work/core-completion-20261017` 后，本地干净分支从 `c1c9af2` 快进到远端 `5ee610d4433be13fdc6a61ec301bd76a7cb79050`，没有覆盖并发提交。
- 当前安装目录 `D:\Codex\SwirlRust` 的 `PRODUCT.json` 声明同一完整源码 SHA、`rustCore=true`、`mihomoBundled=false`。实际 `Swirl.exe` SHA-256 为 `A424A7D9749A944EF4ECD4EB86D95742BD6C1D75FE1510F03DEF29CB211DC30E`，`swirl_api.dll` 为 `70A65199C8292398D0E9F1D42CEBA9EB249D2527B6A094420A119200B1480727`，均与产品清单吻合。`BUILD.txt` 声明 `SWIRL_USE_RUST_CORE=ON`。
- `main.cpp` 在 Rust 构建中创建 `ThreadedEngine`，它在工作线程创建 `RustCoreEngine`；`RustCoreEngine` 加载同目录 `swirl_api.dll`，配置本机混合 HTTP/SOCKS5 监听，并显式给内部 `QNetworkAccessManager` 设置 `NoProxy`。此源码分支没有运行时兼容内核回退。

## 本机只读实测

测试时 `Swirl.exe` PID 37700（`D:\Codex\SwirlRust\Swirl.exe`）加载了 `swirl_api.dll`，没有加载名字包含 Mihomo、Clash 或 sing-box 的 DLL。PID 37700 监听 `127.0.0.1:7898`，Windows 当前 WinINET 系统代理启用并指向同一地址。`verge-mihomo.exe` PID 35488 同时运行，监听独立的 `127.0.0.1:7897` 等端口。检查到的活动适配器里没有名称或描述含 TUN/TAP/Wintun/Clash/Mihomo 的适配器；此筛查不能排除 WFP 或其他透明转发。

- 使用 `WebRequest.GetSystemWebProxy()` 确认 Windows 的代理目标为 `127.0.0.1:7898`，再用该代理的 .NET `HttpClient` 请求 `https://www.gstatic.com/generate_204`：HTTP 204、零正文、约 358 ms。
- `curl.exe --proxy http://127.0.0.1:7898 --noproxy ''` 对同一 HTTPS URL 返回 204、CONNECT 200、TLS 验证结果 0、总耗时 313 ms；连接的近端为回环地址。
- 同一 .NET 客户端关闭代理后的直连控制请求返回 204，约 103 ms。这仅是直连客户端对照，没有切换运行中的 Swirl 路由模式。

上述 PID、DLL、构建身份、监听端口与真实请求联合支持“该受控系统代理请求进入了 Swirl Rust 监听并成功收到公网 HTTPS 响应”。仍缺少这一次请求对应的 Rust 上传/下载计数增量、出站节点远端的同步套接字采样，以及 Mihomo 无法执行时的独立对照；所以 **Mihomo 独立性未证实**。不能把系统代理覆盖范围称作 TUN 或全设备接管。未停止正在运行的 Swirl/Mihomo，也未改动系统代理、TUN、路由或用户配置。

## 可重复的完整独立验收

使用 `docs/WINDOWS_RUST_ACCEPTANCE.md` 与 `tools/Invoke-WindowsRustAcceptance.ps1` 在隔离的加密 NodeStore 副本上记录 Rust 收发字节、请求与 PID。若需要排除 Mihomo 干扰，按 `docs/WINDOWS_RUST_INDEPENDENT_ACCEPTANCE.md` 的独立工作进程流程进行；该流程要求用户亲自挂起和恢复 Mihomo。即使该流程通过，系统代理仍只覆盖遵循 Windows 代理设置的应用；无代理应用和 TUN 路径需分别验收。

身份跟踪设计参考 [Clash Verge Service 的 PID 跟踪](https://github.com/clash-verge-rev/clash-verge-service/blob/main/src/service/core.rs)，请求分段计时参考 [curl write-out 文档](https://curl.se/docs/manpage.html#-w)。仅借鉴观测方法，未复制外部内核代码。

## 本阶段源码验证

在 `D:\Codex\work\Swirl` 的新构建目录 `D:\Codex\build-swirl-core-20261021` 配置 Release、`SWIRL_USE_RUST_CORE=ON`、`SWIRL_BUILD_UI_TESTS=ON`。Windows 原生 `Swirl.exe` 和 `SwirlRustCoreTests.exe` 均编译成功；`ctest -R ^swirl-rust-qt-integration$` 为 1/1 通过。Rust 工作区的 `cargo fmt --all -- --check`、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`cargo test --workspace --locked --quiet` 均退出 0。首次构建缺少 Qt 运行库 PATH，图标生成器返回 0xc0000135；补齐 Qt bin 后原命令重跑成功。构建产物尚未替换当前运行的已安装应用。
