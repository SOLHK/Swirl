# Swirl 与 Surge：Qt-only 功能范围

更新时间：2026-10-12。仓库目前仅维护 Windows C++23 + Qt 6 Quick/QML 项目。对比基于 [Surge 官方手册](https://manual.nssurge.com/) 的能力类别；**UI 入口不等于功能已经实现**。

| 功能类别 | 当前 Qt 版本状态 |
| --- | --- |
| 系统代理、TUN、规则/全局/直连 | 演示页面；没有实际代理引擎接管 |
| 节点、订阅、配置与策略组 | 演示选择/编辑；没有真实 Mihomo 节点连接或订阅下载 |
| DNS、连接与流量 | 界面演示；没有真实系统流量采集/规则执行 |
| HTTP 会话抓包 | **已实现**本地显式 HTTP 代理、请求响应查看、过滤与 HAR 导出 |
| HTTPS/MITM | CONNECT 仅记录目标、字节与耗时；不解密 TLS |
| URL/头/正文改写与本地响应 | Qt 页面存在，尚无对应实际执行器 |
| JavaScript、Cron 与脚本 API | 演示编辑器；未实现 Surge/Loon API 执行兼容 |
| HTTP 断点、重放、映射、WebSocket | 对应工具页为演示，未提供完整实际工作流 |
| 网关、DHCP、设备策略、端口转发、Ponte 等 | 配置草稿/导航入口，不提供服务端功能 |
| Surge 协议、配置与模块全兼容 | 未实现 |
| PCAP/PCAPng 与网卡级 TCP/UDP/QUIC 抓包 | 未实现，HAR 不是 PCAP |
| 对外 API/CLI 与远程控制 | 演示页面，未实现完整管理接口 |

当前真实 HTTP 抓包的边界：回环监听、最多 64 活动连接和 1000 条历史；请求正文限制 1 MiB，响应限制 2 MiB，预览/导出限制 64 KiB；不支持分块上传或 HTTP Upgrade。认证/Cookie 头及部分 URL 密钥默认隐藏，正文尚未做通用语义脱敏，导出前需核查敏感信息。

未来计划为 Qt 应用增加 C++23 的 `ProxyEngine` 接口及 Mihomo 适配层，逐步实现网络接管、真实流量、规则与订阅；**这些仍是计划，不能从页面外观推断功能可用**。参见 [架构说明](ARCHITECTURE.md)、[模块清单](UI_MODULE_COVERAGE.md) 与 [抓包说明](../src/Swirl.Quick/CAPTURE.md)。
