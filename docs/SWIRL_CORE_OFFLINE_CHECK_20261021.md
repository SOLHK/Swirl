# Windows 当前 Swirl 内核离线检查

双击与脚本放在同一目录的 `Run-SwirlCoreOffline.cmd`，或运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Test-SwirlCoreOffline.ps1
```

默认检查 `127.0.0.1:7898`，可用 `-Port` 指定另一个 Swirl 本地端口。只访问本机回环地址，不发送 SOCKS CONNECT、目标域名、凭据或公网请求；不挂起 Mihomo，不读节点库，不修改系统代理、TUN、路由或 DNS。结果只输出到终端，不保存配置或私人内容。

`PASS` 要求同一个 PID 拥有监听端口且进程名为 `Swirl.exe`；旁边的 `PRODUCT.json`、`BUILD.txt` 与当前 EXE/Rust DLL 哈希一致，构建参数为 `SWIRL_USE_RUST_CORE=ON`；该进程已经加载同目录 `swirl_api.dll`，未加载其他常见代理内核模块；最后该端口正确回应仅在本机进行的 SOCKS5 方法协商。还会单独显示当前 WinINET 静态系统代理是否指向这个端口。检查前后 PID 必须一致。

这能核对**正在监听的 Swirl 进程是 Rust 构建且本地代理入口能响应**。产品清单与文件哈希是本机一致性检查，不是防恶意篡改的远程证明；外部程序无法直接读取此产品的进程内 Rust 计数器。因此离线 `PASS` 不证明某次公网请求经 Shadowsocks 出站，也不证明与同时运行的 Mihomo 完全独立，更不证明 TUN 或全设备流量接管。联网出站仍以独立的公网流量验收为准。

`FAIL` 表示可观察身份或握手不符；`BLOCKED` 表示端口未监听、元数据缺失、权限不足、进程在检查期间变化等，不能据此判断是否使用 Rust。`publicEgressIndependence` 始终是 `NOT_TESTED`。

2026-10-21 本机实测：当前系统代理端口 7898 由 `Swirl.exe` PID 24804 监听；源码 SHA `6b9628e6a9a5a864e5a7e210cd916868804564c8`，清单/文件哈希、Rust 构建开关、进程内 DLL 和本地 SOCKS5 协商均通过，结果为 `PASS`。对照端口 7897 属于另一进程，正确报告为 `FAIL`，未向它发起握手。上述测试没有发送公网请求，也没有取得 Rust 流量计数。

参考实现与规范：[curl SOCKS 实现](https://github.com/curl/curl/blob/master/lib/socks.c)、[Windows Get-NetTCPConnection 文档](https://github.com/MicrosoftDocs/windows-powershell-docs/blob/main/docset/winserver2025-ps/NetTCPIP/Get-NetTCPConnection.md)。本工具独立实现，只复用仓库已有的产品清单和 Rust SOCKS5 行为约定。
