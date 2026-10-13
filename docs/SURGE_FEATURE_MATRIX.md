# Surge 官方能力与 Swirl 第三阶段对应矩阵

核对日期：2026-10-13。已读取官方手册 88 页；原有 56 个模块，现有 69 个模块，新增 13 个入口。细项 924 条。

矩阵逐项归属由 JSON/CSV 提供，QML 功能目录使用同一生成数据。UI 可达是实现设计断言，需以导航验收结果确认。`部分实现` 仅指说明中的真实 Swirl 接口；官方细项默认待开发。没有承诺 Surge API、模块格式或专有协议兼容。

Windows 基础能力与 Swirl 完成度分别记录。Apple 专用 API 标注平台受限；网关、DHCP、Ponte 类能力、MITM 和脚本引擎只预留入口，未进入第四阶段。Map Remote、断点、请求构造等用户要求保留为产品扩展项，引用所属 HTTP 章节，不声称该章节单独定义该功能。

| Surge 功能 / 细项 | 官方出处 | Swirl 中文归属 | 模块 ID | UI 入口 | 实现程度 | Windows 能力 | 未来开发 | 重复模块 |
|---|---|---|---|---|---|---|---|---|
| Advanced DNS Topics | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · Advanced DNS Topics | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| The Fake-IP DNS Responder | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · The Fake-IP DNS Responder | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hijack-dns | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · hijack-dns | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| always-real-ip | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · always-real-ip | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allow-dns-svcb | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · allow-dns-svcb | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT at DNS Time | https://manual.nssurge.com/dns/advanced.html | Fake-IP 与 DNS 缓存 · REJECT at DNS Time | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS Servers | https://manual.nssurge.com/dns/dns-server.html | DNS 解析器 · DNS Servers | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS over TCP iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/dns/dns-server.html | DNS 解析器 · DNS over TCP iOS 5.21.0+ Mac 6.8.0+ | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Per-Network Overrides | https://manual.nssurge.com/dns/dns-server.html | DNS 解析器 · Per-Network Overrides | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Encrypted DNS | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS · Encrypted DNS | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Supported Protocols | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS · Supported Protocols | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Use Encrypted DNS for Specified Domains | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS · Use Encrypted DNS for Specified Domains | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-skip-cert-verification | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS · encrypted-dns-skip-cert-verification | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-follow-outbound-mode | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS · encrypted-dns-follow-outbound-mode | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Local DNS Mapping | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Local DNS Mapping | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP Address Mapping | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · IP Address Mapping | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Wildcards | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Wildcards | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Alias | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Alias | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Assigning DNS Servers | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Assigning DNS Servers | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| System Resolution | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · System Resolution | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Script-Based Resolution | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Script-Based Resolution | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Referencing Rule Sets Mac 5.10.0+ | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Referencing Rule Sets Mac 5.10.0+ | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| /etc/hosts (macOS) | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · /etc/hosts (macOS) | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Use Local DNS Items for Proxied Requests | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts 与本地 DNS · Use Local DNS Items for Proxied Requests | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS Overview | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · DNS Overview | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Concurrent Querying | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · Concurrent Querying | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| A and AAAA Queries | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · A and AAAA Queries | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Empty Answers | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · Empty Answers | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Caching | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · Caching | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Special Hostnames | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 · Special Hostnames | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DHCP Mac Only | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · DHCP Mac Only | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DHCP Section Mac 6.5.0+ | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · DHCP Section Mac 6.5.0+ | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-lease-time | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · max-lease-time | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| default-lease-time | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · default-lease-time | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| min-lease-time | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · min-lease-time | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| one-lease-per-client | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · one-lease-per-client | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ping-check | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 · ping-check | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Enhanced Mode | https://manual.nssurge.com/features/enhanced-mode.html | 增强模式 / TUN · Enhanced Mode | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| How the VIF Works | https://manual.nssurge.com/features/enhanced-mode.html | 增强模式 / TUN · How the VIF Works | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Related [General] Options | https://manual.nssurge.com/features/enhanced-mode.html | 增强模式 / TUN · Related [General] Options | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Gateway Mode Mac Only | https://manual.nssurge.com/features/gateway.html | 网关与设备 · Gateway Mode Mac Only | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Device Management | https://manual.nssurge.com/features/gateway.html | 网关与设备 · Device Management | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Per-Device Policies | https://manual.nssurge.com/features/gateway.html | 网关与设备 · Per-Device Policies | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Access Restriction | https://manual.nssurge.com/features/gateway.html | 网关与设备 · Access Restriction | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| UDP Fast Path Mac 6.4.0+ | https://manual.nssurge.com/features/gateway.html | 网关与设备 · UDP Fast Path Mac 6.4.0+ | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP Rewrite iOS 5.23.0+ Mac 6.10.0+ | https://manual.nssurge.com/features/ip-rewrite.html | IP 重写 · IP Rewrite iOS 5.23.0+ Mac 6.10.0+ | feature-iprewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| reflect | https://manual.nssurge.com/features/ip-rewrite.html | IP 重写 · reflect | feature-iprewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| reject | https://manual.nssurge.com/features/ip-rewrite.html | IP 重写 · reject | feature-iprewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| drop | https://manual.nssurge.com/features/ip-rewrite.html | IP 重写 · drop | feature-iprewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Example: On-Device Developer Services | https://manual.nssurge.com/features/ip-rewrite.html | IP 重写 · Example: On-Device Developer Services | feature-iprewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| MTProto Proxy Server iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · MTProto Proxy Server iOS 5.21.0+ Mac 6.8.0+ | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Why MTProto Instead of SOCKS5 | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Why MTProto Instead of SOCKS5 | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interface: Required, IPv4 or IPv6 address | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · interface: Required, IPv4 or IPv6 address | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port: Required, 1–65535 | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · port: Required, 1–65535 | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| secret: Required, 32 hexadecimal characters | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · secret: Required, 32 hexadecimal characters | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ipv6: Optional, Boolean, default: false | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · ipv6: Optional, Boolean, default: false | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dc-config-url: Optional, HTTP or HTTPS URL | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · dc-config-url: Optional, HTTP or HTTPS URL | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rule Evaluation and Outbound Policies | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Rule Evaluation and Outbound Policies | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Telegram DC Resolution | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Telegram DC Resolution | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DC Configuration, Cache, and Updates | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · DC Configuration, Cache, and Updates | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Hosting a Custom DC Configuration | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Hosting a Custom DC Configuration | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Request Records and Traffic Statistics | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Request Records and Traffic Statistics | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Connection Lifecycle and Performance | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 · Connection Lifecycle and Performance | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Surge Ponte | https://manual.nssurge.com/features/ponte.html | 设备互联 / Ponte · Surge Ponte | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| How It Works | https://manual.nssurge.com/features/ponte.html | 设备互联 / Ponte · How It Works | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| client-proxy-name: Optional, policy name | https://manual.nssurge.com/features/ponte.html | 设备互联 / Ponte · client-proxy-name: Optional, policy name | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| server-proxy-name: Optional, comma-separated policy names | https://manual.nssurge.com/features/ponte.html | 设备互联 / Ponte · server-proxy-name: Optional, comma-separated policy names | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Port Forwarding iOS 5.14.3+ Mac 5.10.0+ | https://manual.nssurge.com/features/port-forwarding.html | 端口转发 · Port Forwarding iOS 5.14.3+ Mac 5.10.0+ | feature-forwarding | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| policy | https://manual.nssurge.com/features/port-forwarding.html | 端口转发 · policy | feature-forwarding | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Use Cases | https://manual.nssurge.com/features/port-forwarding.html | 端口转发 · Use Cases | feature-forwarding | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Built-in Snell Server | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · Built-in Snell Server | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interface | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · interface | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · port | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| psk | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · psk | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| version | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · version | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| mode | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · mode | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Snell v6 Mac 6.8.0+ | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · Snell v6 Mac 6.8.0+ | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Client Configuration | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · Client Configuration | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Using a Module iOS 5.23.0+ Mac 6.10.0+ | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 · Using a Module iOS 5.23.0+ Mac 6.10.0+ | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Subnet Settings | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · Subnet Settings | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| suspend | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · suspend | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| cellular-fallback iOS Only | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · cellular-fallback iOS Only | feature-networks | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| cellular-mode Mac Only | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · cellular-mode Mac Only | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tfo-behaviour | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · tfo-behaviour | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-server | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · dns-server | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-server | https://manual.nssurge.com/features/subnet-settings.html | 按网络设置 · encrypted-dns-server | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Platform Differences | https://manual.nssurge.com/getting-started/platform-differences.html | 平台与移动设备 · Platform Differences | feature-platform | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Surge Mac Only | https://manual.nssurge.com/getting-started/platform-differences.html | 平台与移动设备 · Surge Mac Only | feature-platform | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Metered Network Mode | https://manual.nssurge.com/getting-started/platform-differences.html | 计费网络应用限制 · Metered Network Mode | feature-metered | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Surge iOS Only | https://manual.nssurge.com/getting-started/platform-differences.html | 平台与移动设备 · Surge iOS Only | feature-platform | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Body Rewrite iOS 5.10.0+ Mac 5.6.0+ | https://manual.nssurge.com/http/body-rewrite.html | 正文与头部处理 · Body Rewrite iOS 5.10.0+ Mac 5.6.0+ | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| JQ Body Rewrite iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/http/body-rewrite.html | 正文与头部处理 · JQ Body Rewrite iOS 5.14.0+ Mac 5.9.0+ | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Interaction with scripts | https://manual.nssurge.com/http/body-rewrite.html | 正文与头部处理 · Interaction with scripts | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Header Rewrite | https://manual.nssurge.com/http/header-rewrite.html | 正文与头部处理 · Header Rewrite | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| header-add | https://manual.nssurge.com/http/header-rewrite.html | 正文与头部处理 · header-add | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| header-del | https://manual.nssurge.com/http/header-rewrite.html | 正文与头部处理 · header-del | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| header-replace | https://manual.nssurge.com/http/header-rewrite.html | 正文与头部处理 · header-replace | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| header-replace-regex | https://manual.nssurge.com/http/header-rewrite.html | 正文与头部处理 · header-replace-regex | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Map Local | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · Map Local | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| URL Pattern | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · URL Pattern | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| data-type: Optional, default: file | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · data-type: Optional, default: file | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| data | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · data | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| header: Optional | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · header: Optional | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| status-code: Optional, 200–999, default: 200 | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · status-code: Optional, 200–999, default: 200 | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| About Content-Type | https://manual.nssurge.com/http/map-local.html | Map Local / Remote · About Content-Type | map | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTPS Decryption (MITM) | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · HTTPS Decryption (MITM) | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| CA certificate | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · CA certificate | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hostname: Host List | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · hostname: Host List | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hostname-disabled: Optional, Host List | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · hostname-disabled: Optional, Host List | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ca-p12: Optional, string | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · ca-p12: Optional, string | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ca-passphrase: Optional, string | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · ca-passphrase: Optional, string | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ca-keystore-name: Optional, string | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · ca-keystore-name: Optional, string | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| skip-server-cert-verify: Optional, Boolean, default: false | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · skip-server-cert-verify: Optional, Boolean, default: false | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| h2: Optional, Boolean, default: false | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · h2: Optional, Boolean, default: false | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| client-source-address: Optional, list | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · client-source-address: Optional, list | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| auto-quic-block: Optional, Boolean, default: true iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 / MITM · auto-quic-block: Optional, Boolean, default: true iOS 5.8.0+ Mac 5.4.0+ | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTP Processing | https://manual.nssurge.com/http/overview.html | 抓包 · HTTP Processing | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Which traffic can be processed | https://manual.nssurge.com/http/overview.html | 抓包 · Which traffic can be processed | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Processing pipeline | https://manual.nssurge.com/http/overview.html | 抓包 · Processing pipeline | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Inspecting the results | https://manual.nssurge.com/http/overview.html | 抓包 · Inspecting the results | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| URL Rewrite | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · URL Rewrite | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Header Mode | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · Header Mode | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| 302 Mode | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · 302 Mode | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| 307 Mode | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · 307 Mode | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Reject Mode | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · Reject Mode | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Matching details | https://manual.nssurge.com/http/url-rewrite.html | URL / 请求响应重写 · Matching details | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| AnyTLS iOS 5.17.0+ Mac 6.4.3+ | https://manual.nssurge.com/policies/anytls.html | 代理协议配置 · AnyTLS iOS 5.17.0+ Mac 6.4.3+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/anytls.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| reuse | https://manual.nssurge.com/policies/anytls.html | 代理协议配置 · reuse | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Built-in Policies | https://manual.nssurge.com/policies/built-in.html | 代理协议配置 · Built-in Policies | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DIRECT | https://manual.nssurge.com/policies/built-in.html | 代理协议配置 · DIRECT | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| CELLULAR iOS Only | https://manual.nssurge.com/policies/built-in.html | 蜂窝与 Apple 网络扩展 · CELLULAR iOS Only | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| CELLULAR-ONLY iOS Only | https://manual.nssurge.com/policies/built-in.html | 蜂窝与 Apple 网络扩展 · CELLULAR-ONLY iOS Only | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| HYBRID iOS Only | https://manual.nssurge.com/policies/built-in.html | 蜂窝与 Apple 网络扩展 · HYBRID iOS Only | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| NO-HYBRID iOS Only | https://manual.nssurge.com/policies/built-in.html | 蜂窝与 Apple 网络扩展 · NO-HYBRID iOS Only | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Alias | https://manual.nssurge.com/policies/built-in.html | 代理协议配置 · Alias | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| External Proxy Program Mac Only | https://manual.nssurge.com/policies/external.html | 外部工具 · External Proxy Program Mac Only | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| exec | https://manual.nssurge.com/policies/external.html | 外部工具 · exec | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| local-port | https://manual.nssurge.com/policies/external.html | 外部工具 · local-port | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| args | https://manual.nssurge.com/policies/external.html | 外部工具 · args | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| addresses | https://manual.nssurge.com/policies/external.html | 外部工具 · addresses | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-relay | https://manual.nssurge.com/policies/external.html | 外部工具 · udp-relay | feature-external | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTP, HTTPS, and HTTP/2 CONNECT Proxy | https://manual.nssurge.com/policies/http.html | 代理协议配置 · HTTP, HTTPS, and HTTP/2 CONNECT Proxy | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username / password | https://manual.nssurge.com/policies/http.html | 代理协议配置 · username / password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| always-use-connect | https://manual.nssurge.com/policies/http.html | 代理协议配置 · always-use-connect | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| headers Mac 6.6.0+ | https://manual.nssurge.com/policies/http.html | 代理协议配置 · headers Mac 6.6.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-streams Mac 6.6.0+ | https://manual.nssurge.com/policies/http.html | 代理协议配置 · max-streams Mac 6.6.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-relay iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/policies/http.html | 代理协议配置 · udp-relay iOS 5.22.0+ Mac 6.9.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Hysteria 2 iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · Hysteria 2 iOS 5.8.0+ Mac 5.4.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| download-bandwidth | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · download-bandwidth | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · port-hopping | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping-interval | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · port-hopping-interval | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| salamander-password Mac 6.4.3+ | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · salamander-password Mac 6.4.3+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| gecko-password iOS 5.20.0+ Mac 6.7.0+ | https://manual.nssurge.com/policies/hysteria2.html | 代理协议配置 · gecko-password iOS 5.20.0+ Mac 6.7.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| MASQUE iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/policies/masque.html | 代理协议配置 · MASQUE iOS 5.22.0+ Mac 6.9.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username / password | https://manual.nssurge.com/policies/masque.html | 代理协议配置 · username / password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping | https://manual.nssurge.com/policies/masque.html | 代理协议配置 · port-hopping | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping-interval | https://manual.nssurge.com/policies/masque.html | 代理协议配置 · port-hopping-interval | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Policies | https://manual.nssurge.com/policies/overview.html | 代理协议配置 · Policies | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Referencing Policies | https://manual.nssurge.com/policies/overview.html | 代理协议配置 · Referencing Policies | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Supported Proxy Protocols | https://manual.nssurge.com/policies/overview.html | 代理协议配置 · Supported Proxy Protocols | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Common Policy Parameters | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · Common Policy Parameters | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Egress Parameters | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · Egress Parameters | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interface | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · interface | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allow-other-interface | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · allow-other-interface | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-follow-interface iOS 5.15.2+ Mac 5.2.0+ | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · dns-follow-interface iOS 5.15.2+ Mac 5.2.0+ | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| no-error-alert | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · no-error-alert | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ip-version | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · ip-version | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hybrid iOS Only | https://manual.nssurge.com/policies/parameters.html | 蜂窝与 Apple 网络扩展 · hybrid iOS Only | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| tfo | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · tfo | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tos | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · tos | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ecn iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · ecn iOS 5.8.0+ Mac 5.4.0+ | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| block-quic iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/policies/parameters.html | 路由与接口 · block-quic iOS 5.8.0+ Mac 5.4.0+ | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Testing Parameters | https://manual.nssurge.com/policies/parameters.html | 代理测速与基准测试 · Testing Parameters | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-url | https://manual.nssurge.com/policies/parameters.html | 代理测速与基准测试 · test-url | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-timeout | https://manual.nssurge.com/policies/parameters.html | 代理测速与基准测试 · test-timeout | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-udp | https://manual.nssurge.com/policies/parameters.html | 代理测速与基准测试 · test-udp | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Proxy Chain | https://manual.nssurge.com/policies/parameters.html | 高级策略组 · Proxy Chain | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| underlying-proxy | https://manual.nssurge.com/policies/parameters.html | 高级策略组 · underlying-proxy | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT Policy | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · REJECT Policy | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · REJECT | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT-TINYGIF | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · REJECT-TINYGIF | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT-DROP | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · REJECT-DROP | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REJECT-NO-DROP | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · REJECT-NO-DROP | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Pre-matching Reject iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · Pre-matching Reject iOS 5.14.0+ Mac 5.9.0+ | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Pre-matching Technical Details | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · Pre-matching Technical Details | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| For DNS queries | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · For DNS queries | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| For TCP requests using IP | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · For TCP requests using IP | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| For UDP packets | https://manual.nssurge.com/policies/reject.html | 规则集与逻辑规则 · For UDP packets | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Shadowsocks | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · Shadowsocks | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypt-method | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · encrypt-method | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-relay | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · udp-relay | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-port iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · udp-port iOS 5.14.0+ Mac 5.9.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · obfs | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs-host | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · obfs-host | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs-uri | https://manual.nssurge.com/policies/shadowsocks.html | 代理协议配置 · obfs-uri | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Snell | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · Snell | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| psk | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · psk | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| version | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · version | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| reuse | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · reuse | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · obfs | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs-host | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · obfs-host | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| obfs-uri | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · obfs-uri | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-port | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · udp-port | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| mode | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · mode | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| UDP Relay | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · UDP Relay | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Snell v6 iOS 5.20.0+ Mac 6.7.0+ | https://manual.nssurge.com/policies/snell.html | 代理协议配置 · Snell v6 iOS 5.20.0+ Mac 6.7.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SOCKS5 Proxy | https://manual.nssurge.com/policies/socks5.html | 代理协议配置 · SOCKS5 Proxy | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username / password | https://manual.nssurge.com/policies/socks5.html | 代理协议配置 · username / password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-relay | https://manual.nssurge.com/policies/socks5.html | 代理协议配置 · udp-relay | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SSH | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · SSH | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · username | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| private-key | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · private-key | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| idle-timeout | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · idle-timeout | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| server-fingerprint | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · server-fingerprint | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Algorithm Requirements | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · Algorithm Requirements | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Pinning the Server Fingerprint | https://manual.nssurge.com/policies/ssh.html | 代理协议配置 · Pinning the Server Fingerprint | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Tailscale iOS 5.20.0+ Mac 6.7.0+ | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · Tailscale iOS 5.20.0+ Mac 6.7.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| section-name | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · section-name | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| underlying-proxy | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · underlying-proxy | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-url | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · test-url | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-timeout | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · test-timeout | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Tailscale Section | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · Tailscale Section | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| auth-key | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · auth-key | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interactive-login iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · interactive-login iOS 5.21.0+ Mac 6.8.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| control-url | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · control-url | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hostname | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · hostname | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| derp-only | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · derp-only | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| auto-add-magic-dns-rule iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · auto-add-magic-dns-rule iOS 5.21.0+ Mac 6.8.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| exit-node | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · exit-node | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| idle-keepalive iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · idle-keepalive iOS 5.21.0+ Mac 6.8.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| prefer-ipv6 | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · prefer-ipv6 | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-server | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · dns-server | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| mtu | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · mtu | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| More Examples | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · More Examples | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Routing and Transport | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · Routing and Transport | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS and MagicDNS | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · DNS and MagicDNS | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Policy Testing | https://manual.nssurge.com/policies/tailscale.html | 代理协议配置 · Policy Testing | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| TLS Parameters | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · TLS Parameters | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| skip-cert-verify | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · skip-cert-verify | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| sni | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · sni | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| server-cert-verify-name iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · server-cert-verify-name iOS 5.21.0+ Mac 6.8.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| server-cert-fingerprint-sha256 | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · server-cert-fingerprint-sha256 | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| alpn iOS 5.20.0+ Mac 6.7.0+ | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · alpn iOS 5.20.0+ Mac 6.7.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| client-cert | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · client-cert | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Shadow TLS | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · Shadow TLS | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| shadow-tls-password | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · shadow-tls-password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| shadow-tls-sni | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · shadow-tls-sni | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| shadow-tls-version | https://manual.nssurge.com/policies/tls.html | 代理协议配置 · shadow-tls-version | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trojan | https://manual.nssurge.com/policies/trojan.html | 代理协议配置 · Trojan | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/trojan.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws | https://manual.nssurge.com/policies/trojan.html | 代理协议配置 · ws | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws-path | https://manual.nssurge.com/policies/trojan.html | 代理协议配置 · ws-path | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws-headers | https://manual.nssurge.com/policies/trojan.html | 代理协议配置 · ws-headers | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trust Tunnel Mac 6.4.4+ | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · Trust Tunnel Mac 6.4.4+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · username | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| headers Mac 6.6.0+ | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · headers Mac 6.6.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-streams Mac 6.6.0+ | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · max-streams Mac 6.6.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| h3 iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/policies/trust-tunnel.html | 代理协议配置 · h3 iOS 5.22.0+ Mac 6.9.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| TUIC | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · TUIC | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| token | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · token | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| uuid | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · uuid | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · password | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| alpn | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · alpn | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · port-hopping | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| port-hopping-interval | https://manual.nssurge.com/policies/tuic.html | 代理协议配置 · port-hopping-interval | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| UDP Relay | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · UDP Relay | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Protocol Support | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · Protocol Support | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-relay | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · udp-relay | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-port iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · udp-port iOS 5.14.0+ Mac 5.9.0+ | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Behavior for Unsupported Policies | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · Behavior for Unsupported Policies | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| UDP Testing | https://manual.nssurge.com/policies/udp.html | UDP 与协议控制 · UDP Testing | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| VMess | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · VMess | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| username | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · username | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypt-method | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · encrypt-method | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| vmess-aead | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · vmess-aead | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tls | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · tls | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · ws | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws-path | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · ws-path | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ws-headers | https://manual.nssurge.com/policies/vmess.html | 代理协议配置 · ws-headers | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| WireGuard | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · WireGuard | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| section-name | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · section-name | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| underlying-proxy | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · underlying-proxy | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-url | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · test-url | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-timeout | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · test-timeout | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| WireGuard Section | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · WireGuard Section | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| private-key | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · private-key | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| self-ip | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · self-ip | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| self-ip-v6 | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · self-ip-v6 | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-server | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · dns-server | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| prefer-ipv6 | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · prefer-ipv6 | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| mtu | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · mtu | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| peer | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · peer | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Peer Fields | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · Peer Fields | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| public-key | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · public-key | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allowed-ips | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · allowed-ips | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| endpoint | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · endpoint | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| preshared-key | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · preshared-key | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| keepalive | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · keepalive | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| client-id iOS 5.3.1+ Mac 4.10.3+ | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · client-id iOS 5.3.1+ Mac 4.10.3+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Policy Testing iOS 5.20.0+ Mac 6.7.0+ | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · Policy Testing iOS 5.20.0+ Mac 6.7.0+ | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ECN and DSCP | https://manual.nssurge.com/policies/wireguard.html | 代理协议配置 · ECN and DSCP | feature-protocols | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Fallback Group | https://manual.nssurge.com/policy-groups/fallback.html | 策略组 · Fallback Group | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Temporary Override | https://manual.nssurge.com/policy-groups/fallback.html | 策略临时覆盖 · Temporary Override | feature-policyoverride | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interval | https://manual.nssurge.com/policy-groups/fallback.html | 策略组 · interval | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| timeout | https://manual.nssurge.com/policy-groups/fallback.html | 策略组 · timeout | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| evaluate-before-use | https://manual.nssurge.com/policy-groups/fallback.html | 策略组 · evaluate-before-use | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Load Balance Group | https://manual.nssurge.com/policy-groups/load-balance.html | 策略组 · Load Balance Group | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Temporary Override | https://manual.nssurge.com/policy-groups/load-balance.html | 策略临时覆盖 · Temporary Override | feature-policyoverride | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| persistent | https://manual.nssurge.com/policy-groups/load-balance.html | 策略组 · persistent | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Policy Groups | https://manual.nssurge.com/policy-groups/overview.html | 策略组 · Policy Groups | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Group Types | https://manual.nssurge.com/policy-groups/overview.html | 策略组 · Group Types | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Nesting Groups | https://manual.nssurge.com/policy-groups/overview.html | 策略临时覆盖 · Nesting Groups | feature-policyoverride | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| How Testing Works | https://manual.nssurge.com/policy-groups/overview.html | 策略组 · How Testing Works | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Common Group Parameters | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · Common Group Parameters | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| no-alert | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · no-alert | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hidden | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · hidden | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| icon-url Mac 6.5.0+ | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · icon-url Mac 6.5.0+ | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| category iOS 5.23.0+ Mac 6.10.0+ | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · category iOS 5.23.0+ Mac 6.10.0+ | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| underlying-proxy iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · underlying-proxy iOS 5.22.0+ Mac 6.9.0+ | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Testing URL and Timeout | https://manual.nssurge.com/policy-groups/parameters.html | 高级策略组 · Testing URL and Timeout | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Temporary Override | https://manual.nssurge.com/policy-groups/parameters.html | 策略临时覆盖 · Temporary Override | feature-policyoverride | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Policy Including | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · Policy Including | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Include External Policies | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · Include External Policies | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| update-interval | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · update-interval | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| policy-regex-filter | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · policy-regex-filter | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| external-policy-modifier | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · external-policy-modifier | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| external-policy-name-prefix | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · external-policy-name-prefix | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Include Existing Policies iOS 4.12.0+ Mac 4.5.0+ | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · Include Existing Policies iOS 4.12.0+ Mac 4.5.0+ | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| include-all-proxies | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · include-all-proxies | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| include-other-group | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · include-other-group | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Ordering | https://manual.nssurge.com/policy-groups/policy-including.html | 高级策略组 · Ordering | feature-policyadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Manual Selection Group | https://manual.nssurge.com/policy-groups/select.html | 策略组 · Manual Selection Group | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Smart Group iOS 5.11.0+ Mac 5.7.0+ | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · Smart Group iOS 5.11.0+ Mac 5.7.0+ | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| How Selection Works | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · How Selection Works | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Per-site Memory | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · Per-site Memory | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Testing | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · Testing | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Temporary Override | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · Temporary Override | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| policy-priority | https://manual.nssurge.com/policy-groups/smart.html | 智能策略与站点记忆 · policy-priority | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Subnet Group | https://manual.nssurge.com/policy-groups/subnet.html | 策略组 · Subnet Group | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Conditions | https://manual.nssurge.com/policy-groups/subnet.html | 策略组 · Conditions | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| default | https://manual.nssurge.com/policy-groups/subnet.html | 策略组 · default | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| cellular | https://manual.nssurge.com/policy-groups/subnet.html | 策略组 · cellular | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Automatic Testing Group | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · Automatic Testing Group | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| How Testing Works | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · How Testing Works | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Temporary Override | https://manual.nssurge.com/policy-groups/url-test.html | 策略临时覆盖 · Temporary Override | feature-policyoverride | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interval | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · interval | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tolerance | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · tolerance | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| timeout | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · timeout | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| evaluate-before-use | https://manual.nssurge.com/policy-groups/url-test.html | 策略组 · evaluate-before-use | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Profile Format | https://manual.nssurge.com/profile/format.html | 配置文件 · Profile Format | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Comments | https://manual.nssurge.com/profile/format.html | 配置文件 · Comments | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Quoted Values iOS 5.21.0+ Mac 6.8.0+ | https://manual.nssurge.com/profile/format.html | 配置文件 · Quoted Values iOS 5.21.0+ Mac 6.8.0+ | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Detached Profile Section | https://manual.nssurge.com/profile/format.html | 配置文件 · Detached Profile Section | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Include Patterns | https://manual.nssurge.com/profile/format.html | 配置文件 · Include Patterns | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Dedicated Include | https://manual.nssurge.com/profile/format.html | 配置文件 · Dedicated Include | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Multiple Includes iOS 4.12.0+ Mac 4.5.0+ | https://manual.nssurge.com/profile/format.html | 配置文件 · Multiple Includes iOS 4.12.0+ Mac 4.5.0+ | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Mixed Content and Includes iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/profile/format.html | 配置文件 · Mixed Content and Includes iOS 5.22.0+ Mac 6.9.0+ | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Wildcard Named Sections iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/profile/format.html | 配置文件 · Wildcard Named Sections iOS 5.22.0+ Mac 6.9.0+ | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Linked Profiles Mac 6.0.0+ | https://manual.nssurge.com/profile/format.html | 配置文件 · Linked Profiles Mac 6.0.0+ | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Modules | https://manual.nssurge.com/profile/format.html | 配置文件 · Modules | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Line Requirement | https://manual.nssurge.com/profile/format.html | 配置文件 · Line Requirement | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| The [General] Section | https://manual.nssurge.com/profile/general.html | 设置与偏好 · The [General] Section | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Logging & Debugging | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Logging & Debugging | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| loglevel | https://manual.nssurge.com/profile/general.html | 设置与偏好 · loglevel | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| debug-cpu-usage | https://manual.nssurge.com/profile/general.html | 设置与偏好 · debug-cpu-usage | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| debug-memory-usage | https://manual.nssurge.com/profile/general.html | 设置与偏好 · debug-memory-usage | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS | https://manual.nssurge.com/profile/general.html | DNS 解析器 · DNS | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-server | https://manual.nssurge.com/profile/general.html | DNS 解析器 · dns-server | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-server | https://manual.nssurge.com/profile/general.html | 加密 DNS · encrypted-dns-server | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-follow-outbound-mode | https://manual.nssurge.com/profile/general.html | 加密 DNS · encrypted-dns-follow-outbound-mode | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| encrypted-dns-skip-cert-verification | https://manual.nssurge.com/profile/general.html | 加密 DNS · encrypted-dns-skip-cert-verification | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allow-dns-svcb | https://manual.nssurge.com/profile/general.html | Fake-IP 与 DNS 缓存 · allow-dns-svcb | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| use-local-host-item-for-proxy | https://manual.nssurge.com/profile/general.html | 系统代理 · use-local-host-item-for-proxy | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| hijack-dns | https://manual.nssurge.com/profile/general.html | Fake-IP 与 DNS 缓存 · hijack-dns | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| always-real-ip | https://manual.nssurge.com/profile/general.html | Fake-IP 与 DNS 缓存 · always-real-ip | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| GeoIP Database | https://manual.nssurge.com/profile/general.html | GeoIP / ASN 数据库 · GeoIP Database | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| geoip-maxmind-url | https://manual.nssurge.com/profile/general.html | GeoIP / ASN 数据库 · geoip-maxmind-url | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| disable-geoip-db-auto-update | https://manual.nssurge.com/profile/general.html | GeoIP / ASN 数据库 · disable-geoip-db-auto-update | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IPv6 & Virtual Network Interface | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · IPv6 & Virtual Network Interface | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ipv6 | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · ipv6 | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ipv6-vif | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · ipv6-vif | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tun-excluded-routes | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · tun-excluded-routes | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| tun-included-routes | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · tun-included-routes | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| icmp-forwarding iOS 5.14.3+ Mac 5.10.0+ | https://manual.nssurge.com/profile/general.html | 增强模式 / TUN · icmp-forwarding iOS 5.14.3+ Mac 5.10.0+ | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| System Proxy Bypass | https://manual.nssurge.com/profile/general.html | 系统代理 · System Proxy Bypass | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| skip-proxy | https://manual.nssurge.com/profile/general.html | 系统代理 · skip-proxy | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| exclude-simple-hostnames | https://manual.nssurge.com/profile/general.html | 系统代理 · exclude-simple-hostnames | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Proxy Services & Remote Access | https://manual.nssurge.com/profile/general.html | 系统代理 · Proxy Services & Remote Access | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| proxy-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ | https://manual.nssurge.com/profile/general.html | 系统代理 · proxy-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| gateway-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ | https://manual.nssurge.com/profile/general.html | 网关与设备 · gateway-restricted-to-lan iOS 5.13.1+ Mac 5.8.1+ | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| external-controller-access | https://manual.nssurge.com/profile/general.html | 远程控制与设备授权 · external-controller-access | feature-remote | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-api | https://manual.nssurge.com/profile/general.html | HTTP API / 命令行 · http-api | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-api-tls | https://manual.nssurge.com/profile/general.html | HTTP API / 命令行 · http-api-tls | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-api-web-dashboard | https://manual.nssurge.com/profile/general.html | HTTP API / 命令行 · http-api-web-dashboard | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Connectivity Testing | https://manual.nssurge.com/profile/general.html | 代理测速与基准测试 · Connectivity Testing | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| internet-test-url | https://manual.nssurge.com/profile/general.html | 代理测速与基准测试 · internet-test-url | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| proxy-test-url | https://manual.nssurge.com/profile/general.html | 代理测速与基准测试 · proxy-test-url | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| test-timeout | https://manual.nssurge.com/profile/general.html | 代理测速与基准测试 · test-timeout | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| proxy-test-udp | https://manual.nssurge.com/profile/general.html | 代理测速与基准测试 · proxy-test-udp | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Traffic Processing | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Traffic Processing | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| force-http-engine-hosts | https://manual.nssurge.com/profile/general.html | 抓包 · force-http-engine-hosts | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| always-raw-tcp-hosts iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/profile/general.html | 抓包 · always-raw-tcp-hosts iOS 5.8.0+ Mac 5.4.0+ | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| always-raw-tcp-keywords Mac 5.5.0+ | https://manual.nssurge.com/profile/general.html | 抓包 · always-raw-tcp-keywords Mac 5.5.0+ | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-policy-not-supported-behaviour | https://manual.nssurge.com/profile/general.html | UDP 与协议控制 · udp-policy-not-supported-behaviour | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| udp-priority | https://manual.nssurge.com/profile/general.html | UDP 与协议控制 · udp-priority | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| block-quic iOS 5.14.6+ Mac 5.10.3+ | https://manual.nssurge.com/profile/general.html | UDP 与协议控制 · block-quic iOS 5.14.6+ Mac 5.10.3+ | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Error Pages | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Error Pages | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| show-error-page Mac 5.8.0+ | https://manual.nssurge.com/profile/general.html | 抓包 · show-error-page Mac 5.8.0+ | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| show-error-page-for-reject | https://manual.nssurge.com/profile/general.html | 抓包 · show-error-page-for-reject | capture | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Surge iOS Only Parameters | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Surge iOS Only Parameters | settings | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Working Mode | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Working Mode | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| compatibility-mode | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · compatibility-mode | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| auto-suspend iOS 5.11.0+ | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · auto-suspend iOS 5.11.0+ | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Sharing Proxy Services over LAN | https://manual.nssurge.com/profile/general.html | 系统代理 · Sharing Proxy Services over LAN | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allow-wifi-access | https://manual.nssurge.com/profile/general.html | 系统代理 · allow-wifi-access | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| allow-hotspot-access | https://manual.nssurge.com/profile/general.html | 系统代理 · allow-hotspot-access | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wifi-access-http-port | https://manual.nssurge.com/profile/general.html | 系统代理 · wifi-access-http-port | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wifi-access-socks5-port | https://manual.nssurge.com/profile/general.html | 系统代理 · wifi-access-socks5-port | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wifi-access-http-auth | https://manual.nssurge.com/profile/general.html | 系统代理 · wifi-access-http-auth | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Network Behavior | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Network Behavior | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wifi-assist | https://manual.nssurge.com/profile/general.html | 设置与偏好 · wifi-assist | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| all-hybrid | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · all-hybrid | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| hide-vpn-icon | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · hide-vpn-icon | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| VPN Tunnel Scope | https://manual.nssurge.com/profile/general.html | 设置与偏好 · VPN Tunnel Scope | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| include-all-networks | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · include-all-networks | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| include-local-networks | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · include-local-networks | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| include-apns | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · include-apns | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| include-cellular-services | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · include-cellular-services | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| include-device-communication iOS 5.23.0+ | https://manual.nssurge.com/profile/general.html | 蜂窝与 Apple 网络扩展 · include-device-communication iOS 5.23.0+ | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Surge Mac Only Parameters | https://manual.nssurge.com/profile/general.html | 设置与偏好 · Surge Mac Only Parameters | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-listen | https://manual.nssurge.com/profile/general.html | 系统代理 · http-listen | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| socks5-listen | https://manual.nssurge.com/profile/general.html | 系统代理 · socks5-listen | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| set-system-socks-proxy | https://manual.nssurge.com/profile/general.html | 系统代理 · set-system-socks-proxy | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| read-etc-hosts | https://manual.nssurge.com/profile/general.html | DNS 解析器 · read-etc-hosts | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| subnet-exp-wifi-always-match | https://manual.nssurge.com/profile/general.html | 设置与偏好 · subnet-exp-wifi-always-match | settings | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Host List Parameter Type | https://manual.nssurge.com/profile/host-list.html | Hosts 与本地 DNS · Host List Parameter Type | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Keystore | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · Keystore | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| type | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · type | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| base64 | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · base64 | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| password | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · password | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Client Certificate for TLS Proxy | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · Client Certificate for TLS Proxy | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| MITM CA Certificate | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · MITM CA Certificate | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SSH Private Key | https://manual.nssurge.com/profile/keystore.html | 密钥库与证书引用 · SSH Private Key | feature-keystore | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Managed Profile | https://manual.nssurge.com/profile/managed-profile.html | 托管配置与外部资源 · Managed Profile | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| interval | https://manual.nssurge.com/profile/managed-profile.html | 托管配置与外部资源 · interval | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| strict | https://manual.nssurge.com/profile/managed-profile.html | 托管配置与外部资源 · strict | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REQUIREMENT Statement | https://manual.nssurge.com/profile/managed-profile.html | 托管配置与外部资源 · REQUIREMENT Statement | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| FORBIDDEN-AUTO-UPGRADE Statement | https://manual.nssurge.com/profile/managed-profile.html | 托管配置与外部资源 · FORBIDDEN-AUTO-UPGRADE Statement | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Module | https://manual.nssurge.com/profile/module.html | 配置模块 · Module | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Parameter Tables Mac 5.5.0+ | https://manual.nssurge.com/profile/module.html | 配置模块 · Parameter Tables Mac 5.5.0+ | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Requirements iOS 5.10.0+ Mac 5.6.0+ | https://manual.nssurge.com/profile/module.html | 配置模块 · Requirements iOS 5.10.0+ Mac 5.6.0+ | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Line Requirement iOS 5.11.0+ Mac 5.7.0+ | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · Line Requirement iOS 5.11.0+ Mac 5.7.0+ | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Start-of-Line and End-of-Line Forms | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · Start-of-Line and End-of-Line Forms | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| REQUIREMENT Expression | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · REQUIREMENT Expression | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Core Version | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · Core Version | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Simplified Notation iOS 5.14.3+ Mac 5.10.0+ | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · Simplified Notation iOS 5.14.3+ Mac 5.10.0+ | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Usage in Managed Profiles | https://manual.nssurge.com/profile/requirement.html | 模块条件与参数 · Usage in Managed Profiles | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Domain Rules | https://manual.nssurge.com/rules/domain.html | 分流规则 · Domain Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Matching Semantics | https://manual.nssurge.com/rules/domain.html | 分流规则 · Matching Semantics | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN-SUFFIX | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN-SUFFIX | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN-KEYWORD | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN-KEYWORD | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN-WILDCARD | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN-WILDCARD | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN-SET | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN-SET | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DOMAIN-SET File Format | https://manual.nssurge.com/rules/domain.html | 分流规则 · DOMAIN-SET File Format | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| extended-matching iOS 5.8.0+ Mac 5.4.0+ | https://manual.nssurge.com/rules/domain.html | 分流规则 · extended-matching iOS 5.8.0+ Mac 5.4.0+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pre-matching iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/rules/domain.html | 分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Final Rule | https://manual.nssurge.com/rules/final.html | 分流规则 · Final Rule | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns-failed | https://manual.nssurge.com/rules/final.html | 分流规则 · dns-failed | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Relationship to Outbound Mode | https://manual.nssurge.com/rules/final.html | 分流规则 · Relationship to Outbound Mode | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTP Rules | https://manual.nssurge.com/rules/http.html | 分流规则 · HTTP Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| When HTTP Rules Apply | https://manual.nssurge.com/rules/http.html | 分流规则 · When HTTP Rules Apply | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| USER-AGENT | https://manual.nssurge.com/rules/http.html | 分流规则 · USER-AGENT | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| URL-REGEX | https://manual.nssurge.com/rules/http.html | 分流规则 · URL-REGEX | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP Rules | https://manual.nssurge.com/rules/ip.html | 分流规则 · IP Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP Rules and DNS | https://manual.nssurge.com/rules/ip.html | 分流规则 · IP Rules and DNS | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP-CIDR | https://manual.nssurge.com/rules/ip.html | 分流规则 · IP-CIDR | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP-CIDR6 | https://manual.nssurge.com/rules/ip.html | 分流规则 · IP-CIDR6 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| GEOIP | https://manual.nssurge.com/rules/ip.html | GeoIP / ASN 数据库 · GEOIP | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IP-ASN | https://manual.nssurge.com/rules/ip.html | GeoIP / ASN 数据库 · IP-ASN | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Unknown Database Results iOS 5.102.0+ Mac 6.9.1+ | https://manual.nssurge.com/rules/ip.html | 分流规则 · Unknown Database Results iOS 5.102.0+ Mac 6.9.1+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| no-resolve | https://manual.nssurge.com/rules/ip.html | 分流规则 · no-resolve | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pre-matching iOS 5.14.0+ Mac 5.9.0+ | https://manual.nssurge.com/rules/ip.html | 分流规则 · pre-matching iOS 5.14.0+ Mac 5.9.0+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| GeoIP and ASN Databases | https://manual.nssurge.com/rules/ip.html | GeoIP / ASN 数据库 · GeoIP and ASN Databases | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| GeoIP country database | https://manual.nssurge.com/rules/ip.html | GeoIP / ASN 数据库 · GeoIP country database | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ASN database | https://manual.nssurge.com/rules/ip.html | GeoIP / ASN 数据库 · ASN database | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Logical Rules | https://manual.nssurge.com/rules/logical.html | 规则集与逻辑规则 · Logical Rules | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Nesting | https://manual.nssurge.com/rules/logical.html | 规则集与逻辑规则 · Nesting | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Flags on logical rules | https://manual.nssurge.com/rules/logical.html | 规则集与逻辑规则 · Flags on logical rules | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rules Overview | https://manual.nssurge.com/rules/overview.html | 分流规则 · Rules Overview | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Composition | https://manual.nssurge.com/rules/overview.html | 分流规则 · Composition | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Evaluation Order | https://manual.nssurge.com/rules/overview.html | 分流规则 · Evaluation Order | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rules and DNS | https://manual.nssurge.com/rules/overview.html | 分流规则 · Rules and DNS | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Pre-matching | https://manual.nssurge.com/rules/overview.html | 规则测试与命中解释 · Pre-matching | feature-ruleinspection | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rule Parameters | https://manual.nssurge.com/rules/overview.html | 分流规则 · Rule Parameters | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| notification-text and notification-interval | https://manual.nssurge.com/rules/overview.html | 分流规则 · notification-text and notification-interval | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rule Type Index | https://manual.nssurge.com/rules/overview.html | 分流规则 · Rule Type Index | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Process Rules | https://manual.nssurge.com/rules/process.html | 分流规则 · Process Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| PROCESS-NAME Mac Only | https://manual.nssurge.com/rules/process.html | 分流规则 · PROCESS-NAME Mac Only | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Protocol and Network Rules | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · Protocol and Network Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| PROTOCOL | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · PROTOCOL | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HOSTNAME-TYPE Mac 5.7.3+ | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · HOSTNAME-TYPE Mac 5.7.3+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| CELLULAR-RADIO iOS Only | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · CELLULAR-RADIO iOS Only | rules | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| CELLULAR-CARRIER iOS Only | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · CELLULAR-CARRIER iOS Only | rules | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| SUBNET | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · SUBNET | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Subnet Expressions | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · Subnet Expressions | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SSID:<value> | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · SSID:<value> | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| BSSID:<value> | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · BSSID:<value> | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| ROUTER:<ip> | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · ROUTER:<ip> | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| TYPE:WIFI / TYPE:WIRED / TYPE:CELLULAR | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · TYPE:WIFI / TYPE:WIRED / TYPE:CELLULAR | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| MCCMNC:<digits> | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · MCCMNC:<digits> | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Bare value (legacy) | https://manual.nssurge.com/rules/protocol-and-network.html | 分流规则 · Bare value (legacy) | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Rule Set | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Rule Set | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Internal Rule Sets | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Internal Rule Sets | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SYSTEM | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · SYSTEM | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| LAN | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · LAN | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Inline Rule Sets Mac 5.3.1+ | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Inline Rule Sets Mac 5.3.1+ | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| External Rule Sets | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · External Rule Sets | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Nested Rule Sets iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Nested Rule Sets iOS 5.22.0+ Mac 6.9.0+ | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Options on the RULE-SET Line | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Options on the RULE-SET Line | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| no-resolve | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · no-resolve | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| extended-matching | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · extended-matching | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| update-interval | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · update-interval | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pre-matching | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · pre-matching | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Performance | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · Performance | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| RULE-SET vs. DOMAIN-SET | https://manual.nssurge.com/rules/ruleset.html | 规则集与逻辑规则 · RULE-SET vs. DOMAIN-SET | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Script Rule | https://manual.nssurge.com/rules/script.html | 脚本触发与 API · Script Rule | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| requires-resolve | https://manual.nssurge.com/rules/script.html | 脚本触发与 API · requires-resolve | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Source and Port Rules | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · Source and Port Rules | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| When Source-Based Rules Make Sense | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · When Source-Based Rules Make Sense | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Port Expressions | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · Port Expressions | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DEST-PORT | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · DEST-PORT | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SRC-PORT iOS 5.8.4+ Mac 5.4.4+ | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · SRC-PORT iOS 5.8.4+ Mac 5.4.4+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| IN-PORT | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · IN-PORT | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| SRC-IP | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · SRC-IP | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DEVICE-NAME | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · DEVICE-NAME | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| MAC-ADDRESS Mac 6.1.0+ | https://manual.nssurge.com/rules/source-and-port.html | 分流规则 · MAC-ADDRESS Mac 6.1.0+ | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| JavaScript API | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · JavaScript API | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Globals | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · Globals | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $environment | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $environment | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $script | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $script | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $network | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $network | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $argument | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $argument | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $trigger | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $trigger | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $intent | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $intent | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $input | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $input | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $done | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $done | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $httpClient | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $httpClient | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $httpClient.get(options<String/Object>, callback<Function>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $httpClient.get(options<String/Object>, callback<Function>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $httpAPI | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $httpAPI | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $httpAPI(method<String>, path<String>, body<Object>, callback<Function>(result<Object>)) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $httpAPI(method<String>, path<String>, body<Object>, callback<Function>(result<Object>)) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $persistentStore | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $persistentStore | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $persistentStore.write(data<String>, [key<String>]) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $persistentStore.write(data<String>, [key<String>]) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $persistentStore.read([key<String>]) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $persistentStore.read([key<String>]) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $notification | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $notification | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $notification.post(title<String>, subtitle<String>, body<String>[, options<Object>]) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $notification.post(title<String>, subtitle<String>, body<String>[, options<Object>]) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $utils | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $utils | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $utils.geoip(ip<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $utils.geoip(ip<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $utils.ipasn(ip<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $utils.ipasn(ip<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $utils.ipaso(ip<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $utils.ipaso(ip<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $utils.ungzip(binary<Uint8Array>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $utils.ungzip(binary<Uint8Array>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setSelectGroupPolicy(groupName<String>, policyName<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setSelectGroupPolicy(groupName<String>, policyName<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.selectGroupDetails() | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.selectGroupDetails() | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.retestGroup(groupName<String>, callback<Function>(result<Object>)) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.retestGroup(groupName<String>, callback<Function>(result<Object>)) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setOutboundMode(mode<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setOutboundMode(mode<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setHTTPCaptureEnabled(enabled<Boolean>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setHTTPCaptureEnabled(enabled<Boolean>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setRewriteEnabled(enabled<Boolean>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setRewriteEnabled(enabled<Boolean>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setEnhancedModeEnabled(enabled<Boolean>) Mac Only | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setEnhancedModeEnabled(enabled<Boolean>) Mac Only | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.setCellularModeEnabled(enabled<Boolean>) Mac Only | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.setCellularModeEnabled(enabled<Boolean>) Mac Only | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| $surge.logbook(content<String>) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · $surge.logbook(content<String>) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Miscellaneous | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · Miscellaneous | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| console.log(message) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · console.log(message) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| setTimeout(function[, delay]) | https://manual.nssurge.com/scripting/api.html | 脚本触发与 API · setTimeout(function[, delay]) | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| cron Script | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · cron Script | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| cronexp | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · cronexp | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wake-system iOS Only | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · wake-system iOS Only | scripts | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Manual Triggering | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · Manual Triggering | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Constraints | https://manual.nssurge.com/scripting/cron.html | JavaScript 脚本 · Constraints | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| dns Script | https://manual.nssurge.com/scripting/dns.html | 脚本触发与 API · dns Script | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trigger | https://manual.nssurge.com/scripting/dns.html | JavaScript 脚本 · Trigger | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/dns.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/dns.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| event Script | https://manual.nssurge.com/scripting/event.html | 脚本触发与 API · event Script | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| event-name | https://manual.nssurge.com/scripting/event.html | 脚本触发与 API · event-name | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/event.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/event.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Constraints | https://manual.nssurge.com/scripting/event.html | JavaScript 脚本 · Constraints | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| generic Script | https://manual.nssurge.com/scripting/generic.html | JavaScript 脚本 · generic Script | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trigger | https://manual.nssurge.com/scripting/generic.html | JavaScript 脚本 · Trigger | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/generic.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/generic.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-request Script | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · http-request Script | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trigger | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · Trigger | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pattern | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · pattern | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| requires-body | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · requires-body | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-size | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · max-size | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| binary-body-mode | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · binary-body-mode | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| full-header-mode | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · full-header-mode | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/http-request.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| http-response Script | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · http-response Script | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trigger | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · Trigger | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pattern | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · pattern | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| requires-body | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · requires-body | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-size | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · max-size | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| binary-body-mode | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · binary-body-mode | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| full-header-mode | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · full-header-mode | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/http-response.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Scripting | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Scripting | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Declaration | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Declaration | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| type: Optional, default: generic | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · type: Optional, default: generic | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| script-path: Required | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · script-path: Required | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| script-update-interval: Optional, in seconds, default: 86400 | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · script-update-interval: Optional, in seconds, default: 86400 | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| timeout: Optional, in seconds, default: 5 | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · timeout: Optional, in seconds, default: 5 | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| argument: Optional | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · argument: Optional | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| engine: Optional, auto/jsc/webview, default: auto | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · engine: Optional, auto/jsc/webview, default: auto | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| debug: Optional, Boolean, default: false | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · debug: Optional, Boolean, default: false | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| pattern: Required for http-request and http-response, regex | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · pattern: Required for http-request and http-response, regex | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| requires-body: Optional, Boolean, default: false | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · requires-body: Optional, Boolean, default: false | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| max-size: Optional, in bytes, default: 1 MB (iOS) / 10 MB (Mac) | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · max-size: Optional, in bytes, default: 1 MB (iOS) / 10 MB (Mac) | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| binary-body-mode: Optional, Boolean, default: false | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · binary-body-mode: Optional, Boolean, default: false | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| full-header-mode: Optional, Boolean, default: false | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · full-header-mode: Optional, Boolean, default: false | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| cronexp: Required for cron | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · cronexp: Required for cron | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| event-name: Required for event | https://manual.nssurge.com/scripting/overview.html | 脚本触发与 API · event-name: Required for event | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| wake-system: Optional, Boolean, default: false iOS Only | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · wake-system: Optional, Boolean, default: false iOS Only | scripts | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口；Windows 无直接等价能力 | 是 | 否；共享归属不新建重复页面 |
| Script Engine iOS 5.9.0+ Mac 5.5.0+ | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Script Engine iOS 5.9.0+ Mac 5.5.0+ | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| JavaScriptCore (engine=jsc) | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · JavaScriptCore (engine=jsc) | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| WebView (engine=webview) | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · WebView (engine=webview) | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Usage Recommendations | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Usage Recommendations | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Engine Availability | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Engine Availability | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Performance Constraints | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Performance Constraints | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Debugging | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本 · Debugging | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| rule Script | https://manual.nssurge.com/scripting/rule.html | 脚本触发与 API · rule Script | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Trigger | https://manual.nssurge.com/scripting/rule.html | JavaScript 脚本 · Trigger | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Input | https://manual.nssurge.com/scripting/rule.html | JavaScript 脚本 · Input | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS Resolution | https://manual.nssurge.com/scripting/rule.html | 脚本触发与 API · DNS Resolution | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Result | https://manual.nssurge.com/scripting/rule.html | JavaScript 脚本 · Result | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Surge CLI | https://manual.nssurge.com/tools/cli.html | HTTP API / 命令行 · Surge CLI | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Editor Language Server Mac 6.10.0+ | https://manual.nssurge.com/tools/cli.html | HTTP API / 命令行 · Editor Language Server Mac 6.10.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Expanded Management and Diagnostics Mac 6.8.0+ | https://manual.nssurge.com/tools/cli.html | HTTP API / 命令行 · Expanded Management and Diagnostics Mac 6.8.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Routing and Network Diagnostics Mac 6.9.0+ | https://manual.nssurge.com/tools/cli.html | HTTP API / 命令行 · Routing and Network Diagnostics Mac 6.9.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Agent Skill Mac 6.5.0+ | https://manual.nssurge.com/tools/cli.html | HTTP API / 命令行 · Agent Skill Mac 6.5.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Surge Dashboard | https://manual.nssurge.com/tools/dashboard.html | Dashboard 仪表盘 · Surge Dashboard | dashboard | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Local and Remote Connections | https://manual.nssurge.com/tools/dashboard.html | Dashboard 仪表盘 · Local and Remote Connections | dashboard | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| external-controller-access | https://manual.nssurge.com/tools/dashboard.html | Dashboard 仪表盘 · external-controller-access | dashboard | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Web Dashboard | https://manual.nssurge.com/tools/dashboard.html | Dashboard 仪表盘 · Web Dashboard | dashboard | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTP API iOS 4.4.0+ Mac 4.0.0+ | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · HTTP API iOS 4.4.0+ Mac 4.0.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| HTTPS (TLS) | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · HTTPS (TLS) | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Basic Constraints | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Basic Constraints | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Toggle Capabilities | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Toggle Capabilities | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Outbound Mode | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Outbound Mode | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Proxy Policy | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Proxy Policy | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Requests | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Requests | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Profiles | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Profiles | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| External Resources iOS 5.23.0+ Mac 6.10.0+ | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · External Resources iOS 5.23.0+ Mac 6.10.0+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| DNS | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · DNS | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Modules | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Modules | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Scripting | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Scripting | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Device Management Mac Only 4.0.6+ | https://manual.nssurge.com/tools/http-api.html | HTTP API / 命令行 · Device Management Mac Only 4.0.6+ | api | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Prometheus Metrics iOS 5.22.0+ Mac 6.9.0+ | https://manual.nssurge.com/tools/http-api.html | Prometheus 指标 · Prometheus Metrics iOS 5.22.0+ Mac 6.9.0+ | feature-prometheus | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Logbook Mac 6.6.0+ | https://manual.nssurge.com/tools/logbook.html | Logbook 日志 · Logbook Mac 6.6.0+ | logs | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Remote Viewing | https://manual.nssurge.com/tools/logbook.html | Logbook 日志 · Remote Viewing | logs | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Information Panel iOS 4.9.3+ Mac 5.7.5+ | https://manual.nssurge.com/tools/panel.html | 自定义面板 · Information Panel iOS 4.9.3+ Mac 5.7.5+ | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Static Mode | https://manual.nssurge.com/tools/panel.html | 自定义面板 · Static Mode | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Dynamic Mode | https://manual.nssurge.com/tools/panel.html | 自定义面板 · Dynamic Mode | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| More Customization | https://manual.nssurge.com/tools/panel.html | 自定义面板 · More Customization | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Testing | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · Testing | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Connectivity and Latency Testing | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · Connectivity and Latency Testing | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| Throughput Test Parameters Mac 6.4.4+ | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · Throughput Test Parameters Mac 6.4.4+ | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| download-url | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · download-url | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| upload-url | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · upload-url | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| download-url-proxy | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · download-url-proxy | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| upload-url-proxy | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · upload-url-proxy | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| download-concurrency | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · download-concurrency | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| upload-concurrency | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · upload-concurrency | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| download-duration-limit | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · download-duration-limit | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| upload-size-limit | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · upload-size-limit | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| upload-duration-limit | https://manual.nssurge.com/tools/testing.html | 代理测速与基准测试 · upload-duration-limit | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| URL Scheme | https://manual.nssurge.com/tools/url-scheme.html | URL Scheme 与快捷指令 · URL Scheme | feature-urlscheme | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| x-callback-url | https://manual.nssurge.com/tools/url-scheme.html | URL Scheme 与快捷指令 · x-callback-url | feature-urlscheme | 更多 → 全部功能 | 待开发 | Windows 具备相关基础能力；需 Swirl 自研或 Mihomo 接入 | 是 | 否；共享归属不新建重复页面 |
| 系统代理开启 | https://manual.nssurge.com/profile/general.html | 系统代理开启 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 系统代理关闭 | https://manual.nssurge.com/profile/general.html | 系统代理关闭 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 读取真实 Windows 代理状态 | https://manual.nssurge.com/profile/general.html | 读取真实 Windows 代理状态 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按偏好自动接管 | https://manual.nssurge.com/profile/general.html | 按偏好自动接管 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| PAC 与绕过列表恢复 | https://manual.nssurge.com/profile/general.html | PAC 与绕过列表恢复 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| GUI 和引擎崩溃恢复 | https://manual.nssurge.com/profile/general.html | GUI 和引擎崩溃恢复 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 多实例竞争保护 | https://manual.nssurge.com/profile/general.html | 多实例竞争保护 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 外部代理修改保护 | https://manual.nssurge.com/profile/general.html | 外部代理修改保护 | feature-system | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| TUN 增强模式 | https://manual.nssurge.com/features/enhanced-mode.html | TUN 增强模式 | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| IPv4 / IPv6 接管 | https://manual.nssurge.com/features/enhanced-mode.html | IPv4 / IPv6 接管 | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 包含与排除路由 | https://manual.nssurge.com/features/enhanced-mode.html | 包含与排除路由 | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| ICMP 转发 | https://manual.nssurge.com/features/enhanced-mode.html | ICMP 转发 | feature-enhanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 局域网 HTTP / SOCKS5 代理 | https://manual.nssurge.com/profile/general.html | 局域网 HTTP / SOCKS5 代理 | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 局域网代理身份验证 | https://manual.nssurge.com/profile/general.html | 局域网代理身份验证 | feature-system | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网络接口绑定 | https://manual.nssurge.com/policies/parameters.html | 网络接口绑定 | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 接口故障回退 | https://manual.nssurge.com/policies/parameters.html | 接口故障回退 | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| IP 版本选择 | https://manual.nssurge.com/policies/parameters.html | IP 版本选择 | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 代理链 | https://manual.nssurge.com/policies/parameters.html | 代理链 | feature-routing | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按 Wi-Fi / 网关切换配置 | https://manual.nssurge.com/features/subnet-settings.html | 按 Wi-Fi / 网关切换配置 | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网络变化自动重新检测 | https://manual.nssurge.com/features/subnet-settings.html | 网络变化自动重新检测 | feature-networks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| UDP 转发 | https://manual.nssurge.com/policies/udp.html | UDP 转发 | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| QUIC 策略 | https://manual.nssurge.com/policies/udp.html | QUIC 策略 | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| UDP 性能优先级 | https://manual.nssurge.com/policies/udp.html | UDP 性能优先级 | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| UDP 测试 | https://manual.nssurge.com/policies/udp.html | UDP 测试 | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 不支持 UDP 时拒绝或直连 | https://manual.nssurge.com/policies/udp.html | 不支持 UDP 时拒绝或直连 | feature-udp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 24 种协议导入与凭据保护 | https://manual.nssurge.com/tools/testing.html | 24 种协议导入与凭据保护 | proxies | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 全部节点独立测速 | https://manual.nssurge.com/tools/testing.html | 全部节点独立测速 | proxies | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 单节点独立测试请求 | https://manual.nssurge.com/tools/testing.html | 单节点独立测试请求 | proxies | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 连接 / 断开 / 切换节点 | https://manual.nssurge.com/tools/testing.html | 连接 / 断开 / 切换节点 | proxies | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 独立超时与取消 | https://manual.nssurge.com/tools/testing.html | 独立超时与取消 | proxies | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 手动策略组 | https://manual.nssurge.com/policy-groups/overview.html | 手动策略组 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 延迟自动选择 | https://manual.nssurge.com/policy-groups/overview.html | 延迟自动选择 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 故障转移 | https://manual.nssurge.com/policy-groups/overview.html | 故障转移 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 负载均衡 | https://manual.nssurge.com/policy-groups/overview.html | 负载均衡 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 策略运行状态 | https://manual.nssurge.com/policy-groups/overview.html | 策略运行状态 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按网络选择 | https://manual.nssurge.com/policy-groups/overview.html | 按网络选择 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 嵌套组循环检测 | https://manual.nssurge.com/policy-groups/overview.html | 嵌套组循环检测 | policies | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 连接质量智能选路 | https://manual.nssurge.com/policy-groups/smart.html | 连接质量智能选路 | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按站点策略记忆 | https://manual.nssurge.com/policy-groups/smart.html | 按站点策略记忆 | feature-smart | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则 / 全局 / 直连真实模式 | https://manual.nssurge.com/rules/overview.html | 规则 / 全局 / 直连真实模式 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 局域网与本机直连 | https://manual.nssurge.com/rules/overview.html | 局域网与本机直连 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 中国域名与 IP 直连 | https://manual.nssurge.com/rules/overview.html | 中国域名与 IP 直连 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 国外目标代理 | https://manual.nssurge.com/rules/overview.html | 国外目标代理 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则顺序查看 | https://manual.nssurge.com/rules/overview.html | 规则顺序查看 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 连接匹配规则查看 | https://manual.nssurge.com/rules/overview.html | 连接匹配规则查看 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 缺少规则数据明确报错 | https://manual.nssurge.com/rules/overview.html | 缺少规则数据明确报错 | rules | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 精确域名规则 | https://manual.nssurge.com/rules/overview.html | 精确域名规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 域名后缀规则 | https://manual.nssurge.com/rules/overview.html | 域名后缀规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 域名关键词规则 | https://manual.nssurge.com/rules/overview.html | 域名关键词规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 通配域名规则 | https://manual.nssurge.com/rules/overview.html | 通配域名规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| IPv4 / IPv6 CIDR | https://manual.nssurge.com/rules/overview.html | IPv4 / IPv6 CIDR | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 进程规则 | https://manual.nssurge.com/rules/overview.html | 进程规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 目标 / 来源 / 监听端口规则 | https://manual.nssurge.com/rules/overview.html | 目标 / 来源 / 监听端口规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 来源 IP 规则 | https://manual.nssurge.com/rules/overview.html | 来源 IP 规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 设备名称和 MAC 规则 | https://manual.nssurge.com/rules/overview.html | 设备名称和 MAC 规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 协议规则 | https://manual.nssurge.com/rules/overview.html | 协议规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 主机类型规则 | https://manual.nssurge.com/rules/overview.html | 主机类型规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网络环境规则 | https://manual.nssurge.com/rules/overview.html | 网络环境规则 | rules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| GeoIP 规则 | https://manual.nssurge.com/rules/ip.html | GeoIP 规则 | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| ASN 规则 | https://manual.nssurge.com/rules/ip.html | ASN 规则 | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 数据库更新与校验 | https://manual.nssurge.com/rules/ip.html | 数据库更新与校验 | feature-geodb | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| AND / OR / NOT 逻辑规则 | https://manual.nssurge.com/rules/overview.html | AND / OR / NOT 逻辑规则 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 外部规则集 | https://manual.nssurge.com/rules/overview.html | 外部规则集 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 域名集合 | https://manual.nssurge.com/rules/overview.html | 域名集合 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 内联规则集 | https://manual.nssurge.com/rules/overview.html | 内联规则集 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 拒绝策略及预匹配 | https://manual.nssurge.com/rules/overview.html | 拒绝策略及预匹配 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 最终兜底规则 | https://manual.nssurge.com/rules/overview.html | 最终兜底规则 | feature-rulesets | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 临时规则 | https://manual.nssurge.com/rules/overview.html | 临时规则 | feature-ruleinspection | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则匹配测试 | https://manual.nssurge.com/rules/overview.html | 规则匹配测试 | feature-ruleinspection | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则命中解释 | https://manual.nssurge.com/rules/overview.html | 规则命中解释 | feature-ruleinspection | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则命中统计 | https://manual.nssurge.com/rules/overview.html | 规则命中统计 | feature-ruleinspection | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 常规 DNS | https://manual.nssurge.com/dns/overview.html | 常规 DNS | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 系统解析器 | https://manual.nssurge.com/dns/overview.html | 系统解析器 | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS over TCP | https://manual.nssurge.com/dns/overview.html | DNS over TCP | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 并发 DNS 查询 | https://manual.nssurge.com/dns/overview.html | 并发 DNS 查询 | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| A / AAAA 并发与回退 | https://manual.nssurge.com/dns/overview.html | A / AAAA 并发与回退 | dns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DoH | https://manual.nssurge.com/dns/encrypted-dns.html | DoH | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DoH3 | https://manual.nssurge.com/dns/encrypted-dns.html | DoH3 | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DoT | https://manual.nssurge.com/dns/encrypted-dns.html | DoT | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DoQ | https://manual.nssurge.com/dns/encrypted-dns.html | DoQ | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 加密 DNS 跟随出站策略 | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS 跟随出站策略 | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 加密 DNS 证书验证 | https://manual.nssurge.com/dns/encrypted-dns.html | 加密 DNS 证书验证 | feature-encrypteddns | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Hosts | https://manual.nssurge.com/dns/local-dns-mapping.html | Hosts | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 本地域名映射 | https://manual.nssurge.com/dns/local-dns-mapping.html | 本地域名映射 | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 域名别名 | https://manual.nssurge.com/dns/local-dns-mapping.html | 域名别名 | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 指定 DNS 服务器 | https://manual.nssurge.com/dns/local-dns-mapping.html | 指定 DNS 服务器 | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 系统解析与 mDNS | https://manual.nssurge.com/dns/local-dns-mapping.html | 系统解析与 mDNS | feature-hosts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 分流 | https://manual.nssurge.com/dns/local-dns-mapping.html | DNS 分流 | feature-dnspolicy | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 指定应答 | https://manual.nssurge.com/dns/local-dns-mapping.html | 指定应答 | feature-dnspolicy | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则集关联 DNS | https://manual.nssurge.com/dns/local-dns-mapping.html | 规则集关联 DNS | feature-dnspolicy | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Fake-IP | https://manual.nssurge.com/dns/advanced.html | Fake-IP | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 劫持 | https://manual.nssurge.com/dns/advanced.html | DNS 劫持 | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 真实 IP 例外 | https://manual.nssurge.com/dns/advanced.html | 真实 IP 例外 | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| SVCB 控制 | https://manual.nssurge.com/dns/advanced.html | SVCB 控制 | feature-fakeip | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 缓存查看 | https://manual.nssurge.com/dns/overview.html | DNS 缓存查看 | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 缓存清理 | https://manual.nssurge.com/dns/overview.html | DNS 缓存清理 | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 查询追踪 | https://manual.nssurge.com/dns/overview.html | DNS 查询追踪 | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 故障诊断 | https://manual.nssurge.com/dns/overview.html | DNS 故障诊断 | feature-dnstrace | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 真实明文 HTTP 抓包 | https://manual.nssurge.com/http/overview.html | 真实明文 HTTP 抓包 | capture | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 请求 / 响应头与正文检查 | https://manual.nssurge.com/http/overview.html | 请求 / 响应头与正文检查 | capture | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| HTTPS 解密 | https://manual.nssurge.com/http/mitm.html | HTTPS 解密 | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按域名启用 MITM | https://manual.nssurge.com/http/mitm.html | 按域名启用 MITM | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| HTTP/2 解密 | https://manual.nssurge.com/http/mitm.html | HTTP/2 解密 | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| QUIC 自动阻止 | https://manual.nssurge.com/http/mitm.html | QUIC 自动阻止 | tls | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| CA 证书导入 | https://manual.nssurge.com/http/mitm.html | CA 证书导入 | feature-certificates | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 证书生成与信任 | https://manual.nssurge.com/http/mitm.html | 证书生成与信任 | feature-certificates | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 客户端证书 | https://manual.nssurge.com/http/mitm.html | 客户端证书 | feature-certificates | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 证书指纹 | https://manual.nssurge.com/http/mitm.html | 证书指纹 | feature-certificates | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| URL 重写 | https://manual.nssurge.com/http/url-rewrite.html | URL 重写 | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 302 / 307 重定向 | https://manual.nssurge.com/http/url-rewrite.html | 302 / 307 重定向 | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 拒绝重写 | https://manual.nssurge.com/http/url-rewrite.html | 拒绝重写 | rewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 请求 / 响应 Header 重写 | https://manual.nssurge.com/http/body-rewrite.html | 请求 / 响应 Header 重写 | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Header 增删与正则 | https://manual.nssurge.com/http/body-rewrite.html | Header 增删与正则 | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 请求 / 响应 Body 重写 | https://manual.nssurge.com/http/body-rewrite.html | 请求 / 响应 Body 重写 | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| JQ 正文重写 | https://manual.nssurge.com/http/body-rewrite.html | JQ 正文重写 | feature-bodyrewrite | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Map Remote | https://manual.nssurge.com/http/map-local.html | Map Remote | map | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 本地资源映射 | https://manual.nssurge.com/http/map-local.html | 本地资源映射 | map | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| API Mock | https://manual.nssurge.com/http/map-local.html | API Mock | feature-mock | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 自定义状态码 | https://manual.nssurge.com/http/map-local.html | 自定义状态码 | feature-mock | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 自定义响应头与正文 | https://manual.nssurge.com/http/map-local.html | 自定义响应头与正文 | feature-mock | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| HTTP 请求断点 | https://manual.nssurge.com/http/overview.html | HTTP 请求断点 | breakpoint | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| HTTP 响应断点 | https://manual.nssurge.com/http/overview.html | HTTP 响应断点 | breakpoint | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 请求重放 | https://manual.nssurge.com/http/overview.html | 请求重放 | replay | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网络请求构造 | https://manual.nssurge.com/http/overview.html | 网络请求构造 | replay | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| HTTP 测试 | https://manual.nssurge.com/http/overview.html | HTTP 测试 | replay | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| WebSocket 会话检查 | https://manual.nssurge.com/http/overview.html | WebSocket 会话检查 | feature-websocket | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| JavaScript 脚本管理 | https://manual.nssurge.com/scripting/overview.html | JavaScript 脚本管理 | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 脚本运行日志 | https://manual.nssurge.com/scripting/overview.html | 脚本运行日志 | scripts | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 请求事件 | https://manual.nssurge.com/scripting/overview.html | 请求事件 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 响应事件 | https://manual.nssurge.com/scripting/overview.html | 响应事件 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 脚本 | https://manual.nssurge.com/scripting/overview.html | DNS 脚本 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则脚本 | https://manual.nssurge.com/scripting/overview.html | 规则脚本 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 系统事件触发 | https://manual.nssurge.com/scripting/overview.html | 系统事件触发 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 手动脚本 | https://manual.nssurge.com/scripting/overview.html | 手动脚本 | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 脚本持久化与通知 API | https://manual.nssurge.com/scripting/overview.html | 脚本持久化与通知 API | feature-scripthooks | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 定时任务 | https://manual.nssurge.com/scripting/overview.html | 定时任务 | automation | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 自动化面板 | https://manual.nssurge.com/scripting/overview.html | 自动化面板 | automation | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 自动化事件 | https://manual.nssurge.com/scripting/overview.html | 自动化事件 | automation | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 静态信息面板 | https://manual.nssurge.com/tools/panel.html | 静态信息面板 | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 动态脚本面板 | https://manual.nssurge.com/tools/panel.html | 动态脚本面板 | feature-panels | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网关模式 | https://manual.nssurge.com/features/gateway.html | 网关模式 | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 设备管理 | https://manual.nssurge.com/features/gateway.html | 设备管理 | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 设备独立分流 | https://manual.nssurge.com/features/gateway.html | 设备独立分流 | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 设备访问限制 | https://manual.nssurge.com/features/gateway.html | 设备访问限制 | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| UDP Fast Path | https://manual.nssurge.com/features/gateway.html | UDP Fast Path | gateway | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DHCP 服务 | https://manual.nssurge.com/features/dhcp.html | DHCP 服务 | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 租约管理 | https://manual.nssurge.com/features/dhcp.html | 租约管理 | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 冲突探测 | https://manual.nssurge.com/features/dhcp.html | 冲突探测 | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 单客户端租约 | https://manual.nssurge.com/features/dhcp.html | 单客户端租约 | feature-dhcp | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| TCP / UDP 端口转发 | https://manual.nssurge.com/features/port-forwarding.html | TCP / UDP 端口转发 | feature-forwarding | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 指定出站策略 | https://manual.nssurge.com/features/port-forwarding.html | 指定出站策略 | feature-forwarding | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 远程设备互联 | https://manual.nssurge.com/features/ponte.html | 远程设备互联 | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 家庭网络访问 | https://manual.nssurge.com/features/ponte.html | 家庭网络访问 | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 设备客户端与服务端角色 | https://manual.nssurge.com/features/ponte.html | 设备客户端与服务端角色 | feature-ponte | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Snell 服务端 | https://manual.nssurge.com/features/snell-server.html | Snell 服务端 | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Snell v6 | https://manual.nssurge.com/features/snell-server.html | Snell v6 | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 模块配置服务端 | https://manual.nssurge.com/features/snell-server.html | 模块配置服务端 | feature-snellserver | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| MTProto 服务端 | https://manual.nssurge.com/features/mtproto.html | MTProto 服务端 | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DC 配置与缓存 | https://manual.nssurge.com/features/mtproto.html | DC 配置与缓存 | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Telegram 分流 | https://manual.nssurge.com/features/mtproto.html | Telegram 分流 | feature-mtproto | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 远程控制 | https://manual.nssurge.com/tools/dashboard.html | 远程控制 | feature-remote | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 远程设备授权 | https://manual.nssurge.com/tools/dashboard.html | 远程设备授权 | feature-remote | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 远程日志查看 | https://manual.nssurge.com/tools/dashboard.html | 远程日志查看 | feature-remote | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 真实上传 / 下载速度 | https://manual.nssurge.com/tools/dashboard.html | 真实上传 / 下载速度 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 1 分钟 / 5 分钟 / 1 小时曲线 | https://manual.nssurge.com/tools/dashboard.html | 1 分钟 / 5 分钟 / 1 小时曲线 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 今日 / 本月流量 | https://manual.nssurge.com/tools/dashboard.html | 今日 / 本月流量 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 代理 / 直连分类 | https://manual.nssurge.com/tools/dashboard.html | 代理 / 直连分类 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 应用 / 域名 / 节点排行 | https://manual.nssurge.com/tools/dashboard.html | 应用 / 域名 / 节点排行 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 客户端来源 | https://manual.nssurge.com/tools/dashboard.html | 客户端来源 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 真实活跃连接 | https://manual.nssurge.com/tools/dashboard.html | 真实活跃连接 | activity | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 互联网 TCP 延迟 | https://manual.nssurge.com/tools/testing.html | 互联网 TCP 延迟 | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 路由器 ICMP 延迟 | https://manual.nssurge.com/tools/testing.html | 路由器 ICMP 延迟 | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| DNS 解析延迟 | https://manual.nssurge.com/tools/testing.html | DNS 解析延迟 | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 当前代理 HTTP 延迟 | https://manual.nssurge.com/tools/testing.html | 当前代理 HTTP 延迟 | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 网络环境摘要 | https://manual.nssurge.com/tools/testing.html | 网络环境摘要 | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 实际出口 IP | https://manual.nssurge.com/tools/testing.html | 实际出口 IP | toolbox | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 连接访问时间 | https://manual.nssurge.com/tools/dashboard.html | 连接访问时间 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 目标域名与协议 | https://manual.nssurge.com/tools/dashboard.html | 目标域名与协议 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 实际进程 | https://manual.nssurge.com/tools/dashboard.html | 实际进程 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 匹配规则 | https://manual.nssurge.com/tools/dashboard.html | 匹配规则 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 实际出站节点 | https://manual.nssurge.com/tools/dashboard.html | 实际出站节点 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 上传 / 下载字节 | https://manual.nssurge.com/tools/dashboard.html | 上传 / 下载字节 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 终止实际连接 | https://manual.nssurge.com/tools/dashboard.html | 终止实际连接 | connections | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 有界历史流量 | https://manual.nssurge.com/tools/dashboard.html | 有界历史流量 | traffic | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 防重复累计 | https://manual.nssurge.com/tools/dashboard.html | 防重复累计 | traffic | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 采集失败状态 | https://manual.nssurge.com/tools/dashboard.html | 采集失败状态 | traffic | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 重启后旧采样隔离 | https://manual.nssurge.com/tools/dashboard.html | 重启后旧采样隔离 | traffic | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 分级运行日志 | https://manual.nssurge.com/tools/logbook.html | 分级运行日志 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 事件时间与组件 | https://manual.nssurge.com/tools/logbook.html | 事件时间与组件 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 错误码搜索 | https://manual.nssurge.com/tools/logbook.html | 错误码搜索 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 错误详情 | https://manual.nssurge.com/tools/logbook.html | 错误详情 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 脱敏诊断 ZIP | https://manual.nssurge.com/tools/logbook.html | 脱敏诊断 ZIP | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 日志轮转 | https://manual.nssurge.com/tools/logbook.html | 日志轮转 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 崩溃线索 | https://manual.nssurge.com/tools/logbook.html | 崩溃线索 | logs | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 吞吐量基准测试 | https://manual.nssurge.com/tools/testing.html | 吞吐量基准测试 | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 上传 / 下载并发和时限 | https://manual.nssurge.com/tools/testing.html | 上传 / 下载并发和时限 | feature-benchmark | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 本地 HTTP API | https://manual.nssurge.com/tools/http-api.html | 本地 HTTP API | api | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 命令行工具 | https://manual.nssurge.com/tools/http-api.html | 命令行工具 | api | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 远程 CLI | https://manual.nssurge.com/tools/http-api.html | 远程 CLI | api | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| API 认证与 TLS | https://manual.nssurge.com/tools/http-api.html | API 认证与 TLS | api | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| Prometheus 指标导出 | https://manual.nssurge.com/tools/http-api.html | Prometheus 指标导出 | feature-prometheus | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 通知中心 | https://manual.nssurge.com/rules/overview.html | 通知中心 | feature-notifications | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 事件确认 | https://manual.nssurge.com/rules/overview.html | 事件确认 | feature-notifications | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则命中通知 | https://manual.nssurge.com/rules/overview.html | 规则命中通知 | feature-notifications | 更多 → 全部功能 | 部分实现 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 本地配置 | https://manual.nssurge.com/profile/format.html | 本地配置 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置编辑与错误提示 | https://manual.nssurge.com/profile/format.html | 配置编辑与错误提示 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置导入导出 | https://manual.nssurge.com/profile/format.html | 配置导入导出 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 分离和关联配置 | https://manual.nssurge.com/profile/format.html | 分离和关联配置 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 多个包含资源 | https://manual.nssurge.com/profile/format.html | 多个包含资源 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 通配命名配置段 | https://manual.nssurge.com/profile/format.html | 通配命名配置段 | profiles | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 托管配置 | https://manual.nssurge.com/profile/managed-profile.html | 托管配置 | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 严格更新模式 | https://manual.nssurge.com/profile/managed-profile.html | 严格更新模式 | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 托管配置条件 | https://manual.nssurge.com/profile/managed-profile.html | 托管配置条件 | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 规则资源自动更新 | https://manual.nssurge.com/profile/managed-profile.html | 规则资源自动更新 | feature-managed | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置模块 | https://manual.nssurge.com/profile/module.html | 配置模块 | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 模块参数 | https://manual.nssurge.com/profile/module.html | 模块参数 | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 模块优先级 | https://manual.nssurge.com/profile/module.html | 模块优先级 | modules | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 条件配置 | https://manual.nssurge.com/profile/requirement.html | 条件配置 | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 平台条件 | https://manual.nssurge.com/profile/requirement.html | 平台条件 | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 版本条件 | https://manual.nssurge.com/profile/requirement.html | 版本条件 | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 行条件表达式 | https://manual.nssurge.com/profile/requirement.html | 行条件表达式 | feature-moduleadvanced | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置同步 | https://manual.nssurge.com/profile/format.html | 配置同步 | feature-sync | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置备份 | https://manual.nssurge.com/profile/format.html | 配置备份 | feature-sync | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置恢复 | https://manual.nssurge.com/profile/format.html | 配置恢复 | feature-sync | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置验证 | https://manual.nssurge.com/profile/format.html | 配置验证 | feature-configvalidation | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 配置差异检查 | https://manual.nssurge.com/profile/format.html | 配置差异检查 | feature-configvalidation | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 快捷指令 | https://manual.nssurge.com/tools/url-scheme.html | 快捷指令 | feature-urlscheme | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 计费网络应用白名单 | https://manual.nssurge.com/getting-started/platform-differences.html | 计费网络应用白名单 | feature-metered | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| 按网络启用计费模式 | https://manual.nssurge.com/getting-started/platform-differences.html | 按网络启用计费模式 | feature-metered | 更多 → 全部功能 | 待开发 | Windows 具备相关网络或应用能力；Swirl 接入程度见细项 | 是 | 否；共享归属不新建重复页面 |
| iOS 蜂窝策略 | https://manual.nssurge.com/getting-started/platform-differences.html | iOS 蜂窝策略 | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
| Wi-Fi 与蜂窝混合链路 | https://manual.nssurge.com/getting-started/platform-differences.html | Wi-Fi 与蜂窝混合链路 | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
| Apple Network Extension | https://manual.nssurge.com/getting-started/platform-differences.html | Apple Network Extension | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
| tvOS | https://manual.nssurge.com/getting-started/platform-differences.html | tvOS | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
| VPN 状态图标 | https://manual.nssurge.com/getting-started/platform-differences.html | VPN 状态图标 | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
| 兼容接管模式 | https://manual.nssurge.com/getting-started/platform-differences.html | 兼容接管模式 | feature-mobileinterfaces | 更多 → 全部功能 | 平台受限 | Apple 平台专用接口，Windows 无同名系统能力 | 是 | 否；共享归属不新建重复页面 |
