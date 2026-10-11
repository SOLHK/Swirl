# 功能模块覆盖清单

以 Surge 官方手册当前 capability map 为基准，建立 56 个功能入口，覆盖桌面和移动平台的主要能力类别。

这是 **模块和配置界面覆盖**，不是 Surge 全协议、全 API 或每个版本私有功能的兼容承诺。新增模块支持编辑、条目增删排序、保存草稿和 JSON 导入导出；不启用网络服务。Windows 无对应系统能力的移动 / Apple 功能保留明确的参考入口。

真实 HTTP 抓包继续可用，其余网络行为尚未接到 Qt 页面。原 WPF 业务代码保持。

| 类别 | 模块 | 页面 / 状态 |
| --- | --- | --- |
| 接管与网络 | 系统代理 | `feature-system` · 独立配置草稿页 |
| 接管与网络 | 增强模式 / TUN | `feature-enhanced` · 独立配置草稿页 |
| 接管与网络 | 按网络设置 | `feature-networks` · 独立配置草稿页 |
| 接管与网络 | 路由与接口 | `feature-routing` · 独立配置草稿页 |
| 代理与策略 | 代理节点 | `proxies` · 现有交互页 / 演示 |
| 代理与策略 | 代理协议配置 | `feature-protocols` · 独立配置草稿页 |
| 代理与策略 | 策略组 | `policies` · 现有交互页 / 演示 |
| 代理与策略 | 高级策略组 | `feature-policyadvanced` · 独立配置草稿页 |
| 代理与策略 | 分流规则 | `rules` · 现有交互页 / 演示 |
| 代理与策略 | 规则集与逻辑规则 | `feature-rulesets` · 独立配置草稿页 |
| 代理与策略 | UDP 与协议控制 | `feature-udp` · 独立配置草稿页 |
| DNS | DNS 解析器 | `dns` · 现有交互页 / 演示 |
| DNS | 加密 DNS | `feature-encrypteddns` · 独立配置草稿页 |
| DNS | Hosts 与本地 DNS | `feature-hosts` · 独立配置草稿页 |
| DNS | Fake-IP 与 DNS 缓存 | `feature-fakeip` · 独立配置草稿页 |
| DNS | DNS 分流与应答 | `feature-dnspolicy` · 独立配置草稿页 |
| HTTP 与调试 | 抓包 | `capture` · 现有交互页 / 真实 HTTP |
| HTTP 与调试 | HTTP 检查器 | `inspector` · 现有交互页 / 演示 |
| HTTP 与调试 | HTTPS 解密 / MITM | `tls` · 现有交互页 / 演示 |
| HTTP 与调试 | 证书管理 | `feature-certificates` · 独立配置草稿页 |
| HTTP 与调试 | URL / 请求响应重写 | `rewrite` · 现有交互页 / 演示 |
| HTTP 与调试 | 正文与头部处理 | `feature-bodyrewrite` · 独立配置草稿页 |
| HTTP 与调试 | Map Local / Remote | `map` · 现有交互页 / 演示 |
| HTTP 与调试 | HTTP 断点 | `breakpoint` · 现有交互页 / 演示 |
| HTTP 与调试 | HTTP 重放与构造 | `replay` · 现有交互页 / 演示 |
| HTTP 与调试 | 本地响应与 Mock | `feature-mock` · 独立配置草稿页 |
| HTTP 与调试 | WebSocket 会话 | `feature-websocket` · 独立配置草稿页 |
| 配置与自动化 | 配置文件 | `profiles` · 现有交互页 / 演示 |
| 配置与自动化 | 托管配置与外部资源 | `feature-managed` · 独立配置草稿页 |
| 配置与自动化 | 订阅管理 | `subscriptions` · 现有交互页 / 演示 |
| 配置与自动化 | 配置模块 | `modules` · 现有交互页 / 演示 |
| 配置与自动化 | 模块条件与参数 | `feature-moduleadvanced` · 独立配置草稿页 |
| 配置与自动化 | JavaScript 脚本 | `scripts` · 现有交互页 / 演示 |
| 配置与自动化 | 脚本触发与 API | `feature-scripthooks` · 独立配置草稿页 |
| 配置与自动化 | 定时与自动化 | `automation` · 现有交互页 / 演示 |
| 配置与自动化 | 自定义面板 | `feature-panels` · 独立配置草稿页 |
| 配置与自动化 | 配置同步与备份 | `feature-sync` · 独立配置草稿页 |
| 设备与服务 | 网关与设备 | `gateway` · 现有交互页 / 演示 |
| 设备与服务 | DHCP 服务 | `feature-dhcp` · 独立配置草稿页 |
| 设备与服务 | 端口转发 | `feature-forwarding` · 独立配置草稿页 |
| 设备与服务 | 设备互联 / Ponte | `feature-ponte` · 独立配置草稿页 |
| 设备与服务 | Snell 服务端 | `feature-snellserver` · 独立配置草稿页 |
| 设备与服务 | MTProto 服务端 | `feature-mtproto` · 独立配置草稿页 |
| 设备与服务 | 远程控制与设备授权 | `feature-remote` · 独立配置草稿页 |
| 工具与系统 | Dashboard 仪表盘 | `dashboard` · 现有交互页 / 演示 |
| 工具与系统 | 连接记录 | `connections` · 现有交互页 / 演示 |
| 工具与系统 | 流量分析 | `traffic` · 现有交互页 / 演示 |
| 工具与系统 | 网络诊断 | `toolbox` · 现有交互页 / 演示 |
| 工具与系统 | 代理测速与基准测试 | `feature-benchmark` · 独立配置草稿页 |
| 工具与系统 | HTTP API / 命令行 | `api` · 现有交互页 / 演示 |
| 工具与系统 | URL Scheme 与快捷指令 | `feature-urlscheme` · 独立配置草稿页 |
| 工具与系统 | Logbook 日志 | `logs` · 现有交互页 / 演示 |
| 工具与系统 | 通知与事件中心 | `feature-notifications` · 独立配置草稿页 |
| 工具与系统 | 平台与移动设备 | `feature-platform` · 独立配置草稿页 |
| 工具与系统 | 设置与偏好 | `settings` · 现有交互页 / 演示 |
| 工具与系统 | 外部工具 | `feature-external` · 独立配置草稿页 |

参考：https://manual.nssurge.com/ · https://manual.nssurge.com/dns/overview.html

入口：侧栏工具分类「全部」、顶部添加菜单「全部功能模块」、Ctrl+K 搜索中文模块名或英文关键词。侧栏维持参考图的 13 个导航项；抓包仍可通过搜索和模块中心进入。

草稿文件位于 `%LOCALAPPDATA%/Swirl/qt-ui/module-drafts.ini`，安装升级和卸载不删除它；不改写原代理配置。草稿不是生产网络配置，避免在草稿填写实际密码或私钥。
