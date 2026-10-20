# Windows Rust 独立联网对照（离线运行）

此对照只使用 Git 外的 DPAPI 加密 NodeStore 副本。测试版 Swirl 以隔离会话启动，进程内加载 swirl_api.dll；脚本不结束、挂起或恢复 Mihomo，不修改系统代理、WinHTTP、TUN、路由或 DNS。用户自己决定何时挂起和恢复 Mihomo。Codex 连接断开后，独立 PowerShell 进程继续运行并把脱敏结果留在 D 盘。

## 运行前

1. 用 tools/Invoke-WindowsRustIndependentAcceptance.ps1 的 PreflightOnly 模式检查 Swirl.exe、同目录 swirl_api.dll、加密副本和 .selected sidecar、当前 Mihomo PID/端口及 17988 空闲。预检还要求 Mihomo 代理对公共 HTTPS 控制目标返回证书已验证的 204，并记录当时的 EXE/DLL 哈希与预期源码 SHA。预检无法读取 EXE 内嵌 SHA；正式运行时必须由测试版进程回报完整源码 SHA，与 ExpectedSourceSha 一致。
2. 保留运行中的 Mihomo。现有 WinINET 和 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 可能把普通应用请求引到 Mihomo；显式 curl 使用 proxy 127.0.0.1:17988、空 noproxy 并清除自己的代理环境。测试版 Swirl 启动时也不继承这些代理环境变量。
3. 当前验收使用的公共目标为 www.msftconnecttest.com 的固定明文响应和 www.gstatic.com 的 HTTPS 204。私有节点、订阅、原始运行时状态和远端地址不进入报告。Windows OS DNS 控制查询单列，不能当成 Rust 上游 DNS 证明。

启动器示例（PowerShell 7，路径均在 D 盘；把 PID 和 SHA 换成本轮核对值）：

~~~~powershell
& 'D:\Codex\Swirl-core-identity-20261020\tools\Start-WindowsRustIndependentAcceptance.ps1' -SwirlExe 'D:\Codex\Swirl-core-identity-20261020\build\rust-qt\Swirl.exe' -EncryptedStore 'D:\Codex\Swirl-acceptance-private-20261020\nodes.dpapi' -ExpectedSourceSha '<40 位本轮程序源码 SHA>' -MihomoPid <本轮 PID> -MihomoProxyPort 7898
~~~~

启动器做只读预检，返回独立工作进程 PID 和本轮私有目录。只有返回 ARMED、目录中的 status.json 显示 WAITING_FOR_MIHOMO_SUSPEND 时，才进入人工操作。工作进程默认最多等待 600 秒；等待超时会写 complete.marker 和 result.json，状态为 BLOCKED。

## 人工挂起与恢复

在 Windows“资源监视器”（resmon）的 CPU 进程列表按本轮 PID 找到 mihomo.exe，选择“挂起进程”。**不要选择“结束进程”**：当前 SwirlProxyGuard 在 Mihomo 退出时会恢复系统代理。脚本要求原 PID 和启动时间不变、各线程显示挂起，并要求原 Mihomo 代理控制请求超时且没有 HTTP 响应；否则不会启动独立对照。

脚本随后自动完成 Windows OS DNS 控制查询、Rust 进程/DLL/17988 身份检查、六项显式代理请求，以及测试 Swirl PID 的非回环 TCP 出站采样和 Rust 收发计数。每项 curl 最多 20 秒，Rust 就绪等待最多 20 秒，结束等待最多 10 秒，DNS 子进程最多 8 秒，基础验收子进程总上限 270 秒。每项结束后写脱敏进度，即使后续超时也保留已完成项。结果写入本轮目录的 events.jsonl、result.json；complete.marker 出现说明工作进程已结束。若 Codex 断线，可在文件资源管理器查看这些本地文件。**看到 complete.marker 后立即在资源监视器恢复同一 Mihomo PID**；若迟迟没有标记，最迟 20 分钟后先恢复 Mihomo，再联系 Codex 分析。

恢复后核查原 PID、7898 监听、系统代理哈希及 Codex 连通性。脚本仅停止它自己启动的测试 Swirl；它不尝试恢复用户手工挂起的 Mihomo，也不“修复”非脚本造成的网络设置变化。

## 结果边界

- rustFrontEnd=PASS：六项请求均进入本轮 17988 所属的 Swirl Rust 进程，正文/状态/TLS 检查通过。此项本身不证明独立性。
- controlledRequestIndependence=PASS：还要求 Mihomo 全程被采样为挂起且原代理失去响应、六项请求各有 Swirl PID 非回环 TCP 采样和 Rust 收发字节增量、OS DNS 控制查询成功、无已知活动 TUN/透明驱动迹象、身份和配置前后核对一致。这只支持本轮受控请求在 Mihomo 无法执行期间由 Swirl Rust 转发。
- mihomoIndependent 和总状态仍为 BLOCKED：OS DNS 控制查询不等于 Rust 上游 DNS 路径证明，PID 套接字采样也不能穷尽 Windows WFP 透明路径。任何受控请求证据缺失均为 BLOCKED，请求失败为 FAIL；不把 Shadowsocks 结果推广到 59 条 VLESS/REALITY 节点、UDP、TUN 或全配置。
- curl 52 作为每次请求的失败保留，新增 CONNECT 码、TCP/代理协商/TLS/首字节累计耗时及收发字节数供分析；后续重试 PASS 不会抹掉此前 FAIL，也不能单独确定 curl 52 根因。

实现只参考 [Clash Verge Service 的内核 PID 跟踪](https://github.com/clash-verge-rev/clash-verge-service/blob/main/src/service/core.rs)、[curl 的 write-out 字段](https://curl.se/docs/manpage.html#-w) 和 [PowerShell Start-Process](https://learn.microsoft.com/powershell/module/microsoft.powershell.management/start-process) 的公开接口，未复制其代码。
