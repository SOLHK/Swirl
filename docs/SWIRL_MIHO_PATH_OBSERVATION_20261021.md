# Windows Swirl 与 Mihomo 后续路径观察

将 `Run-SwirlMihomoPath.cmd`、`Test-SwirlMihomoPath.ps1` 和 `Test-SwirlCoreOffline.ps1` 放在同一目录，双击 `.cmd`；也可运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-SwirlMihomoPath.ps1
```

默认使用 `127.0.0.1:7898`，向固定的 `https://www.gstatic.com/generate_204` 发起 8 次 HTTPS 请求。每次都指定 Swirl 为唯一 curl 代理，要求代理确实使用、HTTP 204、TLS 证书验证成功。工具先调用本机 Rust 身份检查，再在请求期间按 Windows TCP 连接的归属 PID 采样：新的 Swirl 非回环出站连接、Swirl 到 Mihomo 本地监听端口的连接、Mihomo 自己的新非回环连接。采样只输出计数，不输出节点、服务器地址、密码、订阅或请求正文。它检查已知 TUN/透明转发适配器、默认路由和驱动迹象，但无法穷举所有 WFP callout。

工具不会停止、挂起或重启 Mihomo/Swirl；不会修改系统代理、路由、DNS、TUN、Windows 防火墙、节点或私人配置。测试会消耗少量当前所选节点的代理流量。`changedNetworkSettings=false` 表示脚本本身没有修改这些设置；另有 `systemProxyUnchanged`、`mihomoPidsUnchanged` 和 `swirlListenerUnchanged` 对照。

## 怎样解读结果

- `SWIRL_NATIVE_EGRESS_OBSERVED`：所有受控 HTTPS 请求通过 Swirl，捕获到新 Swirl 自有的非回环 TCP 连接，未观察到它连 Mihomo 本地监听端口，也未发现已知透明转发迹象。这是自研进程出站的强证据。
- `MIHOMO_PATH_OBSERVED`：在观察窗口内捕获到 Swirl 新连接 Mihomo 拥有的本地端口，不能宣称本轮路径独立；并发背景流量仍需核对因果关系。
- `INCONCLUSIVE`：请求失败、采样不足、可疑 TUN/驱动、状态变化等，不能据此断言谁负责公网出站。

无论结果如何，`publicEgressIndependence=UNPROVEN` 都是刻意保留的边界：短时 TCP 采样可能漏掉连接；Windows Filtering Platform 可以通过驱动透明重定向，普通进程套接字列表无法排除所有此类路径；同时运行的其他应用可能造成背景连接。此工具补足**不中断 Mihomo**时的可观察证据，但不能替代受控的进程隔离实验。系统代理也不覆盖所有应用或 TUN 流量。

2026-10-21 本机实测（当前安装版源码 `6b9628e6a9a5a864e5a7e210cd916868804564c8`）：Swirl PID 24804、Mihomo 相关进程 2 个，本地监听端口 4 个；8/8 次 HTTPS 204 与 TLS 验证通过，13 次 TCP 采样捕获 8 条新 Swirl 非回环连接、0 条 Swirl→Mihomo 本地连接、0 条新 Mihomo 非回环连接；已知透明转发迹象未发现，系统代理和相关 PID 均未变。输出状态为 `SWIRL_NATIVE_EGRESS_OBSERVED`，独立性仍标记 `UNPROVEN`。没有保存或上传原始私人端点。

实现参考：[Microsoft Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection)、[Microsoft WFP 连接重定向说明](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection)、[curl 命令文档](https://curl.se/docs/manpage.html)。
