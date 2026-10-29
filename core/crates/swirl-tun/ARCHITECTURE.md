# Windows 原生 TUN 架构审计（阶段 A）

基线：`main` @ `4ad8a23b7fd59f0f8c09f1e3547548b16baaf4e9`（2026-10-30，Swirl 0.2.25 Rust-only）。`origin/test` 为 `9d35542`，是 `main` 的直接父提交；`main` 比 `test` 多 1 个已合并提交，包含同一套 Rust Core。活动页 UI 分支没有更新的 Rust 运行时，因此不作为基线。本分支 `work/native-tun-windows-20261030` 只增加 TUN 后端，不改 QML、主题、字体、图标或活动页。

## 已有，必须复用

- **V2 运行时**（`swirl-core` `v2::Core`）：配置事务、会话登记、撤销、准入和统计。SOCKS/HTTP 入站在 `session()` 里调用私有 `route()`。
- **策略与规则**（`swirl-routing::v2::select` + MRS `ChinaRules`）：全局 / 规则 / 直连、显式直连、服务策略、中国域名/IP、自定义规则、默认策略、明确 REJECT。本地地址在全局模式之前直连，这是现有语义。
- **DNS 解析器**（`swirl-dns::Resolver`）：系统、自定义、DoT、DoH、缓存、失败 TTL、查询族。`Resolver::resolve` 不分配 Fake-IP。
- **协议出站**（`swirl_protocol::connect` / `connect_with_transport` 和各 UDP association）：DIRECT 失败不会改走其他出口；REJECT 返回 `Rejected`。
- **传输中继**（`swirl-transport` 的 `BoxStream` 与计数器）。
- **C ABI**（`swirl-api`）：现有 `swirl_core_command` 保持不变。产品能力位 `optional.tun` 仍为 `false`，因为 Qt `RustCoreEngine` 还没有接上这一路；新的 `swirl_tun_command` 是后续集成接口。

## 部分实现

- **域名只存在于代理入站的目标主机名**。TUN 的 IP 包没有域名，现有 `route()` 无法单独完成域名关联。
- **UDP** 只从 SOCKS UDP 关联进入，报文格式带 SOCKS 头。TUN 需要同一套出站，但不能再套一层本地 SOCKS。
- **Qt 侧**已有增强模式开关、`GatewayRouting` / `GatewayService` 和“Rust Core 暂不支持 TUN”的拒绝。那些文件属于 UI/系统代理桥，本分支不修改，避免覆盖活动页开发。
- **平台 crate** 只解析 hosts 路径，没有网卡、路由或驱动。

## 新增

- `swirl-dns` 的关联表和 DNS 报文存根：Fake-IP、真实 IP 映射、TTL、冲突失败关闭。解析器本体不改。
- `swirl-tun`：smoltcp 0.12（0BSD）负责 TCP 状态机；本 crate 只做 L3 分类、UDP/DNS 会话、分流缓存、回环防护和恢复事务。
- `swirl-wintun`：仅 Windows 的 Wintun 0.14 API 装载。不编译、不链接 GPL 驱动源码，也不把 `wintun.dll` 放进仓库。未授权时不创建网卡。
- `v2::TunIngress`：在 Core 运行时上直接 `route()` + `connect()`，TCP/UDP 都不经过本机 SOCKS。
- 恢复、链路和权限模块只产生可检查的状态和命令文本。它们不会在开发机上改路由、DNS 或安装驱动。

## 明确不采用

- 不引入 Mihomo、sing-box、Xray 或其他代理内核。
- 不从零实现 TCP 拥塞、重传和握手。这些由 smoltcp 完成。
- 不把整个 Qt GUI 提升为管理员。需要改系统网络的操作留给以后的、可单独授权的辅助进程；当前代码在未授权时失败关闭。

## 依赖

| 组件 | 版本 | 许可证 | 用法 |
| --- | --- | --- | --- |
| smoltcp | 0.12.0（MSRV 1.80） | 0BSD | 用户态 IPv4/IPv6 TCP |
| Wintun 预编译 DLL | 0.14.1，不入库 | WireGuard Prebuilt Binaries License；源码 GPL-2.0 不链接 | 运行时按 `wintun.h` API 装载 |

smoltcp 的 `any_ip` 加上按目的地址监听，用来把任意目的地的 TCP 会话交给已有出站。IPv6 同时登记目的地址，因为仅靠默认路由不够可靠。
