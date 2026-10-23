# Swirl Core X1.2-A：固定上游 JSON 结构与许可证核对

日期：2026-10-22（Asia/Singapore）。本记录针对严格输入解析与结构识别；不证明协议转换、配置执行或真实联网。

## 已读取的固定版本

| 上游 | 版本 / commit | 仓库许可证 |
| --- | --- | --- |
| XTLS/Xray-core | v26.10.21 / `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` | [MPL-2.0](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/LICENSE) |
| v2fly/v2ray-core | v5.55.0 / `de610153d59ee0bc9222a17680061d732fa14e7b` | [MIT](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/LICENSE) |

版本来自实际读取的 [Xray commit](https://github.com/XTLS/Xray-core/commit/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74) 和 [V2Ray commit](https://github.com/v2fly/v2ray-core/commit/de610153d59ee0bc9222a17680061d732fa14e7b)。以下链接均固定到该提交，不依赖浮动分支。

## 根结构与入站 / 出站边界

依据 [Xray `infra/conf/xray.go`](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/xray.go) 与 [V2Ray `infra/conf/v4/v2ray.go`](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/v2ray.go)：

- 经典完整配置的 `inbounds`、`outbounds` 是对象数组；`log`、`dns`、`routing`、`policy`、`transport`、`stats` 是对象配置。
- Inbound 与 outbound 都可能包含 `protocol`、`settings`、`streamSettings`、`tag`；仅凭协议名不能断言其为客户端节点。Inbound 的 `listen`、`port`、`sniffing` 等不能解释成 outbound 服务器地址。
- V2Ray v4 仍有历史 `inbound`、`outbound` 对象及 `inboundDetour`、`outboundDetour` 数组。其构建顺序明确为 `outbound` → `outboundDetour[]` → `outbounds[]`；入站同样先单对象、再历史数组、最后当前数组。结构提取应保留此顺序和原始路径，不在 A 阶段应用全局 transport。
- Xray 当前仍识别根 `transport` 字段，但构建阶段拒绝非空全局 transport。A 阶段保留字段不代表支持执行。
- Xray 与 V2Ray 经典格式重叠很大。输入来源应由调用方标记，不能仅因出现 `vmess` / `vless` 或 `outbounds` 就伪造确定的生产者身份。

Swirl 单 outbound 入口和裸 JSON 节点数组属于导入接口约定；裸数组应标记为 Swirl 扩展，不能描述为上游标准完整配置。

## 全局与入站的安全类型边界

补充读取：Xray [log.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/log.go)、[dns.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/dns.go)、[router.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/router.go)、[policy.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/policy.go)；V2Ray [synthetic/log/log.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/synthetic/log/log.go)、[synthetic/dns/dns.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/synthetic/dns/dns.go)、[synthetic/router/router.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/synthetic/router/router.go)、[v4/policy.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/policy.go)、[cfgcommon/sniffer/sniffer.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/cfgcommon/sniffer/sniffer.go)。

- `log.access`、`error`、`loglevel` 是字符串；`dnsLog` 是 Xray 的布尔字段，固定 V2Ray v4 没有该字段。
- `dns.hosts` 是对象，其任意域名键的值为地址字符串或字符串数组。`dns.servers` 为数组，成员可以是字符串或对象，不能强制全部为对象。服务器对象的 `port` 为 uint16，`skipFallback` 为布尔值。其 `domains` 在 Xray 是 StringList，在 V2Ray 是字符串数组，跨格式结构识别需保留差异。
- `routing.rules`、`balancers` 为对象数组，`domainStrategy` 为字符串。V2Ray 另有历史 `routing.settings` 对象，包含 `rules` 和 `domainStrategy`。
- `policy.levels` 是对象，上游键按 uint32 解析、值为 policy 对象；`system` 为对象。用户策略的握手/空闲时间等字段为 uint32，`bufferSize` 为 int32；流量统计开关为布尔值。任意键不得原样回显到诊断。
- 两上游 `stats` 都是空结构对象；未知字段仍可原样保留并报告未验证，不等于必须删除它们。
- Inbound `protocol`、`tag` 为字符串，`settings`、`streamSettings`、`sniffing` 为对象；缺省 `settings` 会在上游构建时使用空对象。`sniffing.enabled`、`metadataOnly` 为布尔值，`destOverride` 为 StringList。Xray 还有 `routeOnly` 布尔值及 `domainsExcluded`、`ipsExcluded` StringList；V2Ray 有 `allocate` 对象，其 `strategy` 为字符串，`concurrency`、`refresh` 为 uint32。

## 协议结构与端口类型

已读取的协议源码：

| 上游 | 固定源码 |
| --- | --- |
| Xray | [VMess](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/vmess.go)、[VLESS](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/vless.go)、[Trojan](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/trojan.go)、[HTTP](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/http.go)、[SOCKS](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/socks.go)、[Shadowsocks](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/shadowsocks.go) |
| V2Ray v4 | [VMess](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/vmess.go)、[VLESS](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/vless.go)、[Trojan](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/trojan.go)、[HTTP](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/http.go)、[SOCKS](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/socks.go)、[Shadowsocks](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/shadowsocks.go) |

- 经典 VMess/VLESS 的 `settings.vnext` 及各服务器的 `users` 是对象数组；Trojan/HTTP/SOCKS/Shadowsocks 的 `settings.servers` 是对象数组。
- 上述两上游 outbound 服务器的 `port` 均为 `uint16`。出现时应为 0–65535 的 JSON 整数，不接受数字字符串、浮点数或负值。端口 0 的实际可用性属于语义验证，不由整数类型本身决定。
- 固定 Xray 版本还支持 VMess、VLESS、Trojan、HTTP、SOCKS、Shadowsocks 的简化设置，把 `address`、`port` 和账号字段直接放在 `settings`。其 `port` 同样为 `uint16`；解析层不能强制所有此类配置必须有 `vnext` 或 `servers`。
- Inbound 端口使用不同的 PortList/PortRange 类型，可出现字符串形式。不可用 outbound 端口规则遍历所有名为 `port` 的未知字段。
- A 阶段检查已知字段的结构与类型，不把 UUID 合法性、凭据组合、用户数量或可执行协议约束混同为完整协议转换。

## 传输与 TLS 的类型差异

依据 [Xray transport_internet.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_internet.go)、[transport_method.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_method.go)、[transport_security.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_security.go)、[V2Ray transport_internet.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/transport_internet.go)、[gun.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/gun.go) 和 [tlscfg/tls.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/cfgcommon/tlscfg/tls.go)：

| 路径 | 已核实类型 |
| --- | --- |
| 经典 `streamSettings.network` / `.security` | 字符串 |
| 各 `*Settings`、`sockopt`、`tlsSettings`、`realitySettings` 配置容器 | 按其所属方言为对象；未知容器须保留并报告未验证 |
| Xray `wsSettings.host` / `httpupgradeSettings.host` | 字符串 |
| 两上游 `wsSettings.headers` | 对象，值为字符串 |
| V2Ray `httpSettings.host` | 字符串或字符串数组 |
| V2Ray `httpSettings.headers` | 对象，值为字符串或字符串数组 |
| 两上游 `tlsSettings.alpn` | 字符串或字符串数组 |
| `tlsSettings.certificates` | 对象数组；各证书的 `certificate`、`key` 为字符串数组，`certificateFile`、`keyFile`、`usage` 为字符串 |
| gRPC `serviceName` | 字符串 |
| gRPC `idle_timeout`、`health_check_timeout`、`initial_windows_size` | `int32`；负值在结构上合法，不能按无符号数一律拒绝 |
| gRPC `permit_without_stream` | 布尔值 |
| Xray gRPC 额外字段 | `authority`、`user_agent` 为字符串，`multiMode` 为布尔值 |
| V2Ray v4 gRPC / gun 额外字段 | `parseXForwardedFor` 为布尔值 |

`StringList` 在 [Xray common.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/common.go) 和 [V2Ray cfgcommon/common.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/cfgcommon/common.go) 中均接受字符串或字符串数组，上游对字符串按逗号切分。A 阶段保留原形式，不提前切分或丢弃。

## V2Ray v5 格式

已读取 [v5cfg/skeleton.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v5cfg/skeleton.go)、[root.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v5cfg/root.go)、[inbound.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v5cfg/inbound.go)、[outbound.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v5cfg/outbound.go) 和 [stream.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v5cfg/stream.go)。

V5 根配置使用 `router`、`services`、`extension`，不是把经典 `routing` 原名照搬。`services` 是对象，`extension` 是数组。其 `streamSettings.transport`、`security` 是字符串，`transportSettings`、`securitySettings`、`socketSettings` 是配置对象。字段应保留、识别或明确报告未支持；不应把该 stream 内 `transport` 按根全局 transport 的对象规则拒绝。读取这些结构不表示 X1.2-A 已完成 V5 协议字段转换。

## 严格 JSON 与 JSONC

已读取 [Xray serial/loader.go](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/serial/loader.go)、[V2Ray serial/loader.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/serial/loader.go)、[V2Ray json/reader.go](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/json/reader.go)。

两者的经典本地文件读取路径支持注释过滤；固定 Xray 版本还具有不做注释过滤的远程严格 JSON 路径。本阶段按用户要求采用严格 JSON：注释、尾逗号、单引号、无效 UTF-8、尾随第二个根值均不应静默修复。JSONC 不在本阶段支持声明内。

重复键拒绝、输入/深度/值数量限制以及诊断脱敏是 Swirl 的独立安全契约，不能引用上游默认 JSON 解码器来冒充已经实现。未知字段可以保留；字段保留、结构验证、协议转换、原生执行和联网验收必须分别报告。

## 实现与许可证边界

本次研究核对官方公开接口、字段类型与可观察行为。Swirl X1.2-A 应在现有 Rust `swirl-subscription` 中独立实现，不复制上述 Go 源码，不加入、调用、嵌入或回退至 Xray、V2Ray、Mihomo 或其他完整代理运行时。此文档记录参考来源与许可证，不声称上游代码已被引入，不声称完成 X1.2-B 或联网验收；实际源码和测试结果由本阶段交付记录提供。
