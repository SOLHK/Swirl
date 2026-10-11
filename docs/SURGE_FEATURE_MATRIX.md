# Swirl 与 Surge 功能现状

核对日期：2026-10-11。参考 [Surge 官方能力地图](https://manual.nssurge.com/)。
界面模块已按官方能力图扩展为 56 个入口，详见 [模块覆盖清单](UI_MODULE_COVERAGE.md)。**实际网络功能尚未完整实现。** Qt 页面、旧核心源码与当前安装包的真实能力需要分别看待。

| 功能类别 | 原 WPF/.NET 源码 | 当前 Qt 安装包 |
| --- | --- | --- |
| 系统代理、TUN、规则/全局/直连 | ProxyController、WindowsSystemProxy、MihomoConfig 中存在实现；TUN 实机范围有既有边界 | 页面演示，未连接旧核心 |
| 节点、策略组、订阅、配置 | ProxyProfile、SubscriptionImport、UserRouting 中存在实现 | 选择/编辑演示，没有真实核心节点切换和订阅下载 |
| DNS、规则、连接与流量 | 由 Mihomo 与旧控制器提供部分能力 | 演示数据，未采集真实系统流量 |
| HTTP 会话抓包 | 旧 PluginProxy 有 HTTP 处理能力，未作为 Qt 会话数据源接入 | 本次新增真实本机 HTTP 显式代理、请求/响应查看、过滤、HAR 导出 |
| HTTPS/MITM | PluginProxy 的证书管理及指定域名解密实现 | CONNECT 仅记录目标、字节、耗时；没有 TLS 正文解密或自动信任证书 |
| URL/头/正文改写、本地响应 | Loon 插件兼容层有部分实现和明确限制 | 演示页面，未接入执行器 |
| JavaScript、Cron、网络触发 | PluginScriptRunner、PluginTasks 有部分 Loon API 兼容实现 | 演示编辑器；不能视为完整 Surge 脚本 API |
| HTTP 断点、重放、映射、WebSocket 帧分析 | 未发现完整 Surge 等效工作流 | 原有专门页面是演示；新抓包不支持 Upgrade/WebSocket 明文帧分析 |
| 网关、DHCP、设备级策略、端口转发 | 未发现对应完整实现 | 网关原交互页 + DHCP、端口转发、网络参数独立草稿页 |
| Surge Ponte、内置 Snell/MTProto 服务 | 未发现对应实现 | 已新增独立配置草稿页；服务未接入 |
| Surge 配置/模块/新增协议全兼容 | 以 Mihomo YAML 和部分 Loon 插件为基础，不是 Surge 兼容引擎 | 未实现完整兼容 |
| PCAP/PCAPng、网卡级 TCP/UDP/QUIC 抓包 | 没有完整网卡采集与导出链路 | 未实现；HAR 是 HTTP 会话文件，不是 PCAP |
| 本地 API/CLI、远程 Dashboard、设备控制 | 旧核心内部控制接口不等于 Surge 对外 API | 原有页面是演示，未提供完整对外控制接口 |

这次“增加抓包”指 HTTP 调试工作流：浏览器或工具显式通过本机监听器发起请求，界面显示真实会话，用户主动导出 HAR。
原有总览“连接”开关仍是代理 UI 演示，与抓包页独立。开始抓包不会把演示连接伪装成真实系统代理。

新抓包限制：本机回环监听、最多 64 个活动连接、1000 条历史；上传正文上限 1 MiB，响应上限 2 MiB，正文预览/导出上限 64 KiB；不支持分块上传和 HTTP Upgrade。超过限制明确返回错误，并记录可识别的被拒绝请求。
敏感认证/Cookie 头及部分常见 URL 密钥默认隐藏，正文未做语义脱敏；导出需由用户选择本地文件。

官方参考：

- [Surge 工作原理](https://manual.nssurge.com/getting-started/how-surge-works.html)
- [Surge 能力地图](https://manual.nssurge.com/)
- [Surge General / HTTP 引擎选项](https://manual.nssurge.com/profile/general.html)

本表是源码与官方说明的功能范围核对，不把已有页面或未运行的旧后端代码当成当前 Qt 安装包已完成的功能。
