Swirl Core 全天候验收工具

安装后自动开始后台监控，并在登录 Windows 时自动启动。开始菜单有“启动监控”“停止监控”“查看报告”。默认每 60 秒检查本机监听、系统代理和保存的规则模式；每 30 分钟做 3 次真实 HTTPS 请求及本机 IPv4/IPv6 DIRECT 目标检查。监控数据与配置保存在 D:\Codex\SwirlCoreMonitorData；安装、停止和卸载不会修改 Swirl、Mihomo、系统代理、TUN、DNS 或路由。卸载保留历史记录。

这会使用当前选定节点的少量代理流量。配置文件是 D:\Codex\SwirlCoreMonitorData\config.json，可将主动间隔调到 5-1440 分钟。不要把私人订阅或节点密码写进配置。报告在同目录 report.html，日志是按日期分开的脱敏 JSONL。

报告明确区分：内核身份、系统代理、Mihomo 本地链路、默认 PROXY、保存的规则模式、内网 IPv4/IPv6 DIRECT、国内 DIRECT、海外 PROXY、REJECT 域名、REJECT 规则名、DNS/HTTPS。当前普通 Swirl 不向外部程序提供实时命中规则名和字节计数；缺少真实目标或规则模式未启用时，相关项目只会显示“未配置/未启用/无法观察”，不会显示假通过。

“没有观察到 Mihomo 本地链路”不排除所有 WFP/透明转发。系统代理也不覆盖所有应用或全设备 TUN 流量。要证明自定义国内直连/广告拦截的具体命中，还需要可测试的目标和 Swirl 进程内路由诊断接口。
