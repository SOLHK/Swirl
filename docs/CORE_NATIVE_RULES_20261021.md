# Windows 原生 Rust 规则分流：手工规则阶段（2026-10-21）

## 实际范围

普通 Windows 会话此前即使已保存自定义规则，仍按 `smartRouting` 进入尚未迁移的 MRS 智能规则库预检，无法启动 Rust 规则模式。本阶段在用户明确保存规则后启用 Rust 原生规则路径；没有手工规则时继续拒绝声称已实现智能国内外分流，也不会静默切到全局代理、DIRECT 或 Mihomo。

原生手工规则按现有先后次序匹配。其后加入仅对**目标地址本身**生效的 RFC1918、环回、链路本地、共享地址及 IPv6 ULA/环回/链路本地 DIRECT 规则，并将 `localhost`、`.local` 直连。内建 CIDR 均 `no-resolve`，避免为分类私有地址而查询任意域名；用户显式配置的域名、IP-CIDR、IP-CIDR6、REJECT、节点/组规则优先。若配置终结 `MATCH`，它排在内建私有规则之后；未命中时仍使用已选择的代理节点。用户编辑中的 `MATCH` 必须是最后一条，完全相同的匹配条件若指向不同出站则拒绝保存并指出两条序号。其他重叠规则遵循首条命中，连接诊断显示实际匹配者。

网络规则随现有加密 NodeStore 事务保存，重建 `EngineController` 后自动恢复原生手工模式。连接运行时编辑 DNS、规则或组会明确拒绝，旧会话不会被静默终止。运行中切换到不受支持的规则模式先预检；异步 Rust 配置失败时还会将界面与持久化模式恢复为实际运行模式并显示错误。

Rust 每个 TCP 连接的快照现在包含目标、序号与匹配条件、DIRECT/PROXY/REJECT 出站、实际叶节点、active/closed/failed 状态、上传/下载字节数。Qt 连接详情展示这些字段，不采集 HTTP 正文或 TLS 明文。尚未完成路由的连接显示 `ROUTE_ERROR`；UDP 关联显示 `PER_DATAGRAM`，不冒称整个 UDP 关联都走 DIRECT。

## 真实执行的隔离路径

Windows Qt 测试通过真实导入、选择、`ThreadedEngine`、Rust DLL、HTTP 代理入口和两个独立本地 HTTP 目标执行：

1. 私有 IPv4 目标经明确 `DST-PORT` 规则命中 DIRECT，独立目标回复 `private-direct`，SOCKS 对端计数不增加。
2. 明确的海外合成域名命中 `DOMAIN` → SWIRL，及未命中的另一合成域名命中 `DEFAULT`，两者均经独立 SOCKS5 出站对端到第二 HTTP 目标，回复 `exit-A`。此处 SOCKS5 是无私人凭据的本地测试对端；策略 Rust 链路与真实 Shadowsocks 服务商验收分开报告。
3. 广告合成域名命中 `DOMAIN-SUFFIX` → REJECT，两个目标和 SOCKS 对端计数不增加。
4. 目标写成环回 IP 时命中内建 DIRECT。每条记录的命中规则、最终出站、节点和字节数均由 Rust 快照交叉检查。
5. 保存后销毁并重建控制器，DIRECT/PROXY 路径再执行成功。连接运行时的规则编辑被拒绝；未配置规则时从全局尝试切换原生规则模式也被拒绝，实际运行模式与 QSettings 保持一致。

这是两个独立 loopback 目标和出站对端的**本机真实套接字**测试，不是公网国内站、海外站或用户私人 Shadowsocks 节点验收。独立策略套件还通过 Shadowsocks/UDP、HTTP/HTTPS、DNS 及 IPv4/IPv6 回归；各项命令、数量和跳过状态以本轮测试结果为准。

## 仍需开发和物理验收

- 随包 `cn-domain.mrs`、`cn-ip.mrs` 有来源提交与 SHA-256 清单，当前只由兼容实现读取；Rust 尚无经过验证的 MRS 解析、版本和更新事务。因此本阶段**没有全国域名/IP 自动分类**，不按 `.cn` 等后缀猜测。未列出的国内站点会按安全默认走所选代理，仍可能消耗套餐流量。
- 以域名请求但最终解析到私有 IP 的地址不会自动采用内建 `no-resolve` CIDR；需要显式域名规则，或后续设计可验证的 DNS/路由联合判定。现有普通 IP-CIDR 解析规则采用第一条解析地址并拨同一地址，不能把其他地址族的候选错误套用到该连接。
- 当前 Windows 已安装且正在运行的仍是前一版程序；本阶段尚未安装到用户进程。真实国内公网 DIRECT、海外私人 Shadowsocks PROXY、关闭 Swirl 后的系统代理恢复、Mihomo 完全独立性和 TUN 覆盖均需分项验收，不由本机 loopback 或 CI 代替。

规则数据边界参考 [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat) 与 [Mihomo rule-provider 格式说明](https://github.com/MetaCubeX/Meta-Docs/blob/main/docs/config/rule-providers/index.en.md)；本阶段未把 MRS 当作 Rust 已支持格式，也未复制外部代理内核代码。

## 本地验证

- Rust `cargo fmt --all -- --check`、`cargo check --workspace --locked`、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`cargo test --workspace --locked` 与 `cargo build --release --locked -p swirl-api` 均退出 0。
- Windows Release 构建的 `Swirl.exe`、`SwirlRustCoreTests.exe` 成功；另以 `SWIRL_USE_RUST_CORE=ON`、`SWIRL_BUILD_UI_TESTS=OFF` 完成正常产品 `Swirl.exe` 构建。`ctest -R ^swirl-rust-qt-integration$` 最终 1/1 通过。XML 中新增手工规则产品案例和“私有规则优先于终结 MATCH”案例均为 PASS，9 个需其他对端的既有可选案例为 SKIP，不算通过。
- 独立 Windows 回环测试：`test_policy_groups.py` 21/21、`test_connection_stages.py` 19/19、`test_dns_negative.py` 43/43 通过；`test_shadowsocks.py` 9 项中 1 项明确跳过，`test_rust_core.py` 24 项中 1 项明确跳过，其余通过。包含 TCP、DNS、IPv4/IPv6、HTTP/HTTPS 与合成 Shadowsocks 出站，均不替代真实服务商或物理系统代理验收。

追加复核将手工规则开关严格限定在 `SWIRL_USE_RUST_CORE` 构建；兼容构建继续沿用原 `smartRouting` 条件。Windows 兼容 `SwirlNativeTests.exe` 编译通过，定向 `explicitCompatibilityPreferenceKeepsNetworkOptions` 通过。完整 `swirl-native-engine` 运行结果为 **13 PASS、3 FAIL、1 SKIP**：两个 FAIL 明确缺少本构建目录的 `core/mihomo.exe`，另一个独立 Trojan 对端未能启动，原因尚未确认。该完整兼容套件不能记为通过；这不改变上述 Rust 模式本地结果。
