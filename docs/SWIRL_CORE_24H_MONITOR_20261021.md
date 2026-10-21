# Swirl Core Windows 全天候验收工具

这是独立的每用户安装包，不替换正在运行的 Swirl，也不包含节点库、私人订阅、Mihomo 或 Swirl 程序。安装后启动后台 PowerShell 监控，登录 Windows 时继续启动；开始菜单可启动、停止并打开本地 HTML 报告。脚本不更改系统代理、TUN、路由、DNS 或防火墙。数据在 `D:\Codex\SwirlCoreMonitorData`，卸载保留历史与配置。

默认每 30 秒被动检查监听 PID、系统代理、保存的路由模式和 Swirl/Mihomo 当前 TCP 连接归属；每 30 分钟使用已选节点作 3 次 HTTPS 204 请求，观察 Swirl/Mihomo TCP 连接归属并检查已知透明转发迹象。规则模式启用时，再用独立的 IPv4 与 IPv6 本机 HTTP 目标确认私有地址 DIRECT 能把唯一请求送到目标。每次受控请求都有超时；不能抓到出站、请求失败或状态变化时结果为证据不足。每日 JSONL 仅含状态、计数、PID 和时间；不记录节点、目标 IP、私人规则内容、请求正文或订阅。历史保留 30 天。30 秒快照仍可能错过更短的连接，不是全流量抓包。

报告按用户约定命名“国内 DIRECT”“海外 PROXY”“REJECT 域名”“REJECT 规则名”，并另列“内网 DIRECT”“默认 PROXY”“DNS 与 HTTPS”“Mihomo 后续路径”。**命名不是规则命中的证据。** 当前外部工具无法读取正式版 Swirl 的进程内逐连接规则名与 Rust 字节计数；没有明确可安全访问的国内/广告目标时，自定义国内 DIRECT、REJECT 不会自动访问任意用户域名。它们会显示“规则模式未启用”“未配置目标”或“无法观察”，不会被记作通过。默认 PROXY 只报告 Swirl 进程出站，并不冒称匹配了某条海外规则。

本机实施时，`HKCU\Software\SOLHK\Swirl\Proxy\routingMode` 是 `global`。因此目前真实联网和默认代理可验收，国内直连、海外规则和 REJECT 规则均尚不能称为规则分流成功。启用原生规则模式后，监控会在下一次被动检查发现模式变化并立即重测本机 IPv4/IPv6 DIRECT；自定义公网规则仍需要受控目标和进程内命中证据。

验证记录：本机 `Test-SwirlPrivateDirect.ps1 -SelfTest` 的 IPv4/IPv6 独立 HTTP 目标均通过，未使用 Swirl；在当前 `global` 模式运行时正确返回 `RULE_MODE_OFF`，没有把其记为 DIRECT 通过。`Monitor-SwirlCore.ps1 -Once` 对当前 Swirl PID 24804 得到 3/3 HTTPS 204、3 条新 Swirl 非回环连接、0 条 Swirl→Mihomo 本地连接，规则项目显示关闭。后台启动/停止测试在独立数据目录写入两次记录并正常退出，未注册开机启动。NSIS 隔离安装/卸载均退出 0、无开机启动项且用户系统代理和 Swirl PID 未变。正式安装的后台报告与开机启动项也实测出现，随后只停止本工具并卸载；系统代理与 Swirl PID 未变。最终提交安装包将再次检查。

微软官方资料：[TCP 连接 PID](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection)、[WFP 可透明重定向连接](https://learn.microsoft.com/en-us/windows-hardware/drivers/network/using-bind-or-connect-redirection)。因此“未观察到 Mihomo 本地链路”仍不等于排除所有 WFP/TUN 干预。
