# 6A 网络连接修复与验证边界

本轮网络修复不修改 QML。同一工作区此前按 6A 要求完成的交互、弹窗和退出修改予以保留。

## 已确认的源码问题

- `NodeTestService` 复制主会话选项，使测速内核可能继承 TUN、网关、计费模式、LAN、入口认证和用户 DNS/规则。改为从默认选项按白名单构建独立测速会话，只保留内核身份、节点及拨号依赖；释放测试进程期间仍计入并发和 busy 状态。
- `MihomoAdapter::setRoutingMode` 将控制响应失败当作整个内核失败，可能关闭全部现有 TCP 连接。改为保留内核、读取实际模式并核实。控制请求已生效但响应丢失，以及请求被拒绝两种回归，在旧代码失败、新代码通过。监听端口、LAN、TUN 等安全检查继续生效。
- 原生转发原先与 GUI 共用事件循环。生产入口现在使用 `ThreadedEngine`，在独立线程运行内核和网络对象；GUI 只接收排队的状态快照。兼容引擎降级判断同时计入已接入但仍在握手的连接，避免一个新连接失败引发其他连接被停止。

## 路由和连接策略

- 默认 OpenAI/ChatGPT 域名路由指向 SWIRL；默认智能 DNS 对 chatgpt.com、openai.com、oaistatic.com、oaiusercontent.com 及子域使用同一 SWIRL 出口。GLOBAL 包含 SWIRL，避免默认选择器分离。
- 用户自定义规则、hosts、DNS 仍保留。命中部分已知 Codex 域名/进程且覆盖默认选择器时记录诊断；复杂规则仍需根据实际连接链核对。这不是对所有用户覆盖规则的一致性保证。
- 测速、导入更新不重启主内核、不调用清空连接接口。主动切换同类节点影响新连接；旧节点上的健康流继续传输，已失败的连接按真实 socket 结果结束。跨内核且仍有活动连接时提示需要显式断开重连。
- 未添加 Clash Verge 的 `auto_close_connection` 配置键，未修改 Codex、Clash 或 Windows 全局设置，未通过无限重试或延长超时隐藏失败。
- 原生连接日志记录关闭方、错误码、上游 CONNECT/SOCKS 返回码、握手/传输时间和字节数，不记录载荷或密码。HTTPS CONNECT 内部的 WS/SSE 应用语义仍是加密内容，不能仅凭 TCP EOF 判定响应完整。

## 自动化测试

使用 Qt 6.10.3 / MinGW 13.1 / Release；开启 `SWIRL_BUILD_UI_TESTS` 构建测试目标。Mihomo 通过仓库锁定的 manifest 校验。以下命令在已配置的构建目录运行：

```powershell
ctest --test-dir <build> -R 'swirl-(native|stream-regression|node-real-chain|engine-contract)' --output-on-failure
<build>/SwirlEngineTests.exe routingResponseFailurePreservesProcess
<build>/SwirlNodeTests.exe probesNeverInheritNetworkOwnership isolatedBatchNeverChangesMainSelection
$env:QTEST_FUNCTION_TIMEOUT='1500000'
$env:SWIRL_LONG_STREAM_SECONDS='1200'
<build>/SwirlNativeTests.exe threadedTunnelSurvivesUiStallAndIdle
```

测试覆盖真实本地 TLS、RFC6455 Upgrade/帧/ping/close、分块 SSE、服务端拒绝、截断流、慢接收、测速、节点切换、失败的新拨号与仍健康的旧流、规则/全局模式、实际导入服务更新。20 分钟 CONNECT 回环测试包含 135 秒空闲及 1.8 秒 GUI 线程阻塞。它们不等于真实 Codex 会话验收。

## 只读现场诊断

```powershell
./tools/Collect-CodexNetworkEvidence.ps1 -OutputPath ./network-path.json
python ./tools/Probe-CodexProxyPath.py --ports 7897 7898 --output ./reachability.json
```

第一项记录进程路径、PID、TCP 端点、Windows/WinHTTP 代理、代理环境变量是否配置及相关 DNS 缓存。Process 环境仅属于采集进程，不代表已运行 Codex 的环境。第二项仅检查未认证 HTTP CONNECT/TLS/HTTP；403、404 不能视为 Codex 流成功，也不能据此断言代理认证错误。

## 2026-10-16 现场结论与未验收项

00:17:49（UTC+8），当前会话记录 `error decoding response body` 并重试 1/5。附近的路径快照显示 Codex app-server 经 Clash 的 7897；旧 Swirl 运行在 7898，修复版仍在构建目录。另有远程控制 WebSocket 10060 超时，它与模型 Responses 输出通道不同，不能合并归因。现有记录不足以确定断开由服务端、节点、Clash 或本地网络哪一层触发。

两代理生成配置均关闭 TUN；Clash 使用 fake-ip，Swirl 使用 redir-host。没有实证证明本次发生 Fake-IP 缓存污染或双重接管，也没有通过清缓存伪装修复。当前执行器没有代理环境变量，不代表运行中的所有 Codex 子进程均如此。

真实 Codex 经新版 Swirl 的长流、Windows 系统代理接管/恢复、真实 TUN、UAC 取消、真实订阅定时 HTTPS 更新、用户商业节点切换、不同出口 IP 下的会话行为仍未完成验收。需要在明确授权的切换窗口进行；不能从回环测试推导这些场景已修复。

参考案例是排查线索，不是通用配置处方：
- https://github.com/openai/codex/issues/18647
- https://github.com/openai/codex/issues/24045
- https://github.com/clash-verge-rev/clash-verge-rev/issues/7613
- https://github.com/yq6666-66/codex-reconnecting-troubleshooting
