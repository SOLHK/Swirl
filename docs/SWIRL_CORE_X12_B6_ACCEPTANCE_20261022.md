# X1.2-B6：27 项验收与真实证据映射

日期：2026-10-22。目标研发分支：`work/xray-v2ray-json-import-20261021`。

**此文件是可继续更新的验收映射，不是 B6 三平台最终通过声明。** B5 已发布提交为 [`a0ff384d01698047b28b468046dac319314994b8`](https://github.com/SOLHK/Swirl/commit/a0ff384d01698047b28b468046dac319314994b8)。本文件复核了其测试源码及完整工作区日志；B6 新增四项混合有效/无效节点回归已经集成并通过，最终完整本地门禁也已执行通过。B6 以本文件所属提交的 Checks/Actions 为准；截至发布前，各平台 job 尚待逐一确认。具体运行结果与源 SHA 在验收报告中对应记录，不得把旧 CI 的成功改写为本轮成功。

## 1. 已完成的本地门禁与发布后 CI 核对

下列 B5 已通过结果由主集成工作树负责人在本轮实际运行后确认；本文件作者复核了测试源码、断言及完整工作区日志。`b5-final-workspace-test.log` 共 35 个结果段，519 项通过（普通测试 518、doc-test 1）、0 失败、0 忽略，SHA-256 为 `6ce647f8e430ca2cf4e973c642d5e8ee988113113f54ed0b5b0fd24ab361c033`。测试子集是完整总数的组成部分，不得重复相加；此前未含 CLI 和 UUID 补充用例的 510 项日志仅为较早检查点。

B6 最终本地运行时间为 2026-10-22 06:03 UTC，四条规定命令全部退出 0，完整 workspace 共 36 个结果段、523 项通过（522 普通测试与 1 doc-test）、0 失败、0 忽略。完整测试日志 SHA-256 为 `169e02e02f6adb3cb5855117f6c8a1687324fd7fe32a7c128c6b2a358f0c13fe`。可机读的 [本地验证记录](evidence/CORE_X12_B6_LOCAL_20261022.json) 包含实际命令、时间、退出码、工具版本和逐文件 SHA-256；最终 GitHub 提交在发布时核对同一树内容。以下各子集均包含在 523 项内，不重复相加。

| 门槛 | 当前真实状态 | 限定范围 |
| --- | --- | --- |
| `cargo fmt --all -- --check` | B6 最终本地已通过 | 命令、退出码和源文件摘要见本地证据 JSON；三平台 CI 另行核对 |
| `cargo check --workspace --locked` | B6 最终本地已通过 | 命令、退出码和源文件摘要见本地证据 JSON；三平台 CI 另行核对 |
| `cargo clippy --workspace --all-targets --locked -- -D warnings` | B6 最终本地已通过 | 命令、退出码和源文件摘要见本地证据 JSON；三平台 CI 另行核对 |
| swirl-subscription 全包 | 227 项已通过，主工作树确认 | 包含 `xray_native` 22 项；不表示发生联网 |
| `swirl-subscription/tests/xray_native.rs` | 22/22 已通过 | 解析、语义、存档重载、原生 IR 与阻断门槛 |
| `swirl-core/tests/xray_import.rs` | 6/6 已通过 | 5 项真实回环正向链路，1 项不得启动/不得连接负向用例 |
| `swirl-api/tests/xray_boundary.rs` | 4/4 已通过 | 实际 C ABI 生命周期与拒绝路径；未发送上游应用流量 |
| `swirl-inspect --xray-json` 显式入口与进程级测试 | 8/8 已通过，包含于 B6 完整 523 项 | `swirl-api/tests/xray_cli.rs`：真实子进程、公私输出、显式索引、拒绝路径；不是网络测试 |
| `cargo test --workspace --locked` | B6 本地已通过：36 suites / 523 passed / 0 failed / 0 ignored | 普通测试 522、doc-test 1；精确源摘要与日志摘要已记录 |
| B6 `xray_native_selection.rs` 四项新增回归 | 4/4 已通过 | 已独立执行并包含于最终 workspace 523 项 |
| Windows B6 本提交 Rust / 完整 Core 工作流 | 截至发布前尚待逐 job 确认 | 以本提交 Checks/Actions 为准，逐必需步骤和制品核对 |
| Linux B6 本提交 Rust / 完整 Core 工作流 | 截至发布前尚待逐 job 确认 | 以本提交 Checks/Actions 为准，逐必需步骤和制品核对 |
| macOS B6 本提交 Rust / 完整 Core 工作流 | 截至发布前尚待逐 job 确认 | 以本提交 Checks/Actions 为准；特别核对原先 Subscription to native proxy and target 与证据上传故障 |
| Qt 实际进程 / NodeStore / DPAPI / UI 产品路径最终 SHA | 截至发布前尚待 CI 确认 | C ABI 测试不能代替真实 Qt 进程测试；本地未声称拥有 Qt SDK |
| 本轮新 JSON 导入链正向 TLS、REALITY、Vision、WS、Trojan、SS 联网 | 新增回环菜单未覆盖 | 这是本次网络证据的范围限制；正向 IR 映射与既有原生互操作测试不代表这些新链路已经联网 |

最终汇总时必须保留失败、忽略及条件跳过的真实数目；环境跳过不能计为通过。完整工作流失败不能因为 Rust 子步骤成功就标为整体成功。

### 已核对的 B5 文件身份

以下摘要用于确认本记录映射过的源码，不是编译产物身份或独立的测试结果。最终提交有变化时应更新摘要或记录差异。

| 文件 | SHA-256 |
| --- | --- |
| `core/crates/swirl-subscription/tests/xray_native.rs` | `6418c0e948b503de89fd1fd40e5ef5c4a6cbf362694e7aff05f902c0028cff76` |
| `core/crates/swirl-core/tests/xray_import.rs` | `3f428c38bc75ce792e4eb9b862b35114e538f0cb96d6f84f149c82322b45d12f` |
| `core/crates/swirl-api/tests/xray_boundary.rs` | `1ceebc74481f7c5e6bc9bfc65c8339ed98a7dbdf1508bd5e49e39cf219bd3db6` |
| `core/crates/swirl-subscription/src/xray/convert/native.rs` | `b0b13e2a0a86c605e1860add9b4e41a3a214c464c3c30573ff20d96e564e3470` |
| `core/crates/swirl-api/tests/xray_cli.rs` | `1afdcda8d9ce665e2ab1b66f8141fa62593cb45c326899091f3cd34a4e31f29a` |

## 2. 证据分层与测试文件索引

- **结构**：X1.2-A 严格解析、字段类型、重复键、限制、原始字节。没有网络含义。
- **语义**：协议字段、互斥条件、来源索引、参数保留、`Valid/Invalid/Unverified` 与诊断。
- **原生 IR**：产生当前真实 `Outbound/Config`，通过真实 `Config::validate()`；仍不是握手或联网成功。
- **C ABI**：调用实际 `swirl_core_command`，检查 start/configure/snapshot/stop、非法更新原子拒绝与脱敏。当前新增四例明确断言没有上游连接。
- **CLI 进程**：实际运行 `swirl-inspect --xray-json`，核对退出码、stdout/stderr、公私输出边界、显式节点导出与解析错误；不等于启动 Core 或握手成功。
- **回环联网**：新 JSON → 存档 → 重载 → 选定原生配置 → Core → 独立协议 peer → 独立 target，实际 socket/认证/数据/半关闭证据。仅覆盖该测试实际构建的协议组合。
- **既有外部互操作**：独立 Python peer、官方 Xray 可执行文件、既有 Qt 路径或公网脚本。外部实现不等于公网；旧入口和旧 SHA 不能代替本轮新增导入链验收。

下表的 `别名::测试名` 精确指向此索引，避免在每一行重复很长的路径。

| 别名 | 实际文件 | 已确认范围 |
| --- | --- | --- |
| `J` | [xray_structure.rs](../core/crates/swirl-subscription/tests/xray_structure.rs) | 结构；包含于已确认的 227 项 |
| `H` | [xray_adversarial.rs](../core/crates/swirl-subscription/tests/xray_adversarial.rs) | 结构/恶意输入；包含于 227 项 |
| `B` | [xray_conversion.rs](../core/crates/swirl-subscription/tests/xray_conversion.rs) | B1 语义/往返；包含于 227 项 |
| `P` | [xray_conversion_password.rs](../core/crates/swirl-subscription/tests/xray_conversion_password.rs) | B2 Trojan/SS；包含于 227 项 |
| `A` | [xray_conversion_auth.rs](../core/crates/swirl-subscription/tests/xray_conversion_auth.rs) | B3 SOCKS/HTTP；包含于 227 项 |
| `S` | [xray_conversion_security.rs](../core/crates/swirl-subscription/tests/xray_conversion_security.rs) | B4 安全/传输；包含于 227 项 |
| `N` | [xray_native.rs](../core/crates/swirl-subscription/tests/xray_native.rs) | B5 22 项；包含于 227 项 |
| `L` | [xray_import.rs](../core/crates/swirl-core/tests/xray_import.rs) | 新导入链回环测试 6 项 |
| `F` | [xray_boundary.rs](../core/crates/swirl-api/tests/xray_boundary.rs) | 实际 C ABI 测试 4 项 |
| `C` | [xray_cli.rs](../core/crates/swirl-api/tests/xray_cli.rs) | 真实 CLI 子进程测试 8 项 |
| `M` | [xray_native_selection.rs](../core/crates/swirl-subscription/tests/xray_native_selection.rs) | B6 新增 4/4 已通过，包含于 227 项 subscription 回归 |

## 3. 用户要求的全部 27 项映射

本表“已过”均指第 1 节已收到的本地工作树结果；最终 B6 SHA 及三平台通过情况仍以待补充的 CI 表为准。保留且阻断是对不支持配置的正确验收结果，不是正向执行成功。

| # | 用户验收项 | 实际测试名 | 证据与当前结论 |
| --- | --- | --- | --- |
| 1 | VLESS TCP | `N::vless_tcp_keeps_uuid_protocol_and_explicit_encryption_requirement`；`L::xray_vless_selected_uuid_survives_archive_and_halfclose_to_origin` | 语义、原生 IR、**新链回环正向已过**；独立 peer 核对所选 UUID、VLESS TCP command、目标及双向字节；未推定公网可达 |
| 2 | VLESS TLS | `N::vless_tls_keeps_sni_and_alpn_without_a_plaintext_candidate`；`S::tls_sni_and_string_or_array_alpn_are_lossless` | 语义、原生 IR 已过；SNI/ALPN 保留，未产生明文候选；新增回环菜单未覆盖正向 TLS 握手 |
| 3 | VLESS REALITY | `N::vless_reality_and_vision_never_become_tls_or_lose_flow`；`S::reality_password_alias_maps_only_when_unambiguous`；`S::native_only_fingerprint_names_cannot_bypass_the_source_schema` | 语义、原生 IR 已过；公钥/shortId/指纹与真实 REALITY 层保留；原生专有源名称拒绝；新增回环菜单未覆盖正向 REALITY 联网 |
| 4 | VLESS Vision | `N::vless_reality_and_vision_never_become_tls_or_lose_flow`；`S::reality_and_vision_keep_the_real_security_and_flow`；`S::vision_unsupported_combinations_keep_exact_flow_and_source` | 原生 IR 已过，仅 TCP+REALITY+`xtls-rprx-vision` 可执行；普通 TLS Vision、WS Vision、UDP443 variant 阻断；新增回环菜单未覆盖 Vision 联网 |
| 5 | VLESS WebSocket TLS | `N::vless_and_trojan_websocket_tls_keep_both_layers_host_and_path`；`S::websocket_tls_host_path_and_defaults_are_not_erased` | 原生 IR 已过；同时保留 WS、TLS、Host、path；新增回环菜单未覆盖 WSS 认证和数据交换 |
| 6 | VMess TCP | `N::vmess_tcp_and_ws_tls_keep_protocol_alter_id_and_cipher_but_cannot_execute`；`B::vmess_legacy_alter_id_cipher_and_protocol_never_change`；`L::vmess_and_unsupported_transport_never_produce_a_runtime_or_socket` | 语义保留与原生阻断已过；回环负向证实没有 runtime/socket；VMess 始终是 VMess，没有原生 connector |
| 7 | VMess WebSocket TLS | `N::vmess_tcp_and_ws_tls_keep_protocol_alter_id_and_cipher_but_cannot_execute`；`B::websocket_tls_host_path_headers_and_early_data_are_not_lost` | TCP/WS TLS、alterId=0/64/65535、五种已知 cipher 的保留与阻断已过；不以改成 VLESS 获取执行资格 |
| 8 | Trojan TLS | `N::trojan_requires_real_tls_and_preserves_the_exact_password`；`P::trojan_and_ss_password_algorithm_level_email_and_transport_roundtrip` | 语义、原生 IR 已过；完整空白/Unicode/特殊符号密码保留，缺 TLS 与 REALITY 组合拒绝；新增回环菜单未覆盖此正向 TLS 联网 |
| 9 | Trojan WebSocket TLS | `N::vless_and_trojan_websocket_tls_keep_both_layers_host_and_path`；`P::trojan_tls_ws_and_mux_are_retained_independently_of_password_projection` | 语义、原生 IR 已过；不删除 mux 或额外 headers 来执行；新增回环菜单未覆盖此 WSS 联网 |
| 10 | Shadowsocks AEAD | `N::shadowsocks_exact_aead_cipher_password_and_tcp_scope_are_preserved`；`P::ss_aead_and_unsupported_ciphers_are_retained_not_replaced` | 三种 AEAD 的原生 IR 已过；cipher/password 原样、`udp:false`、无擅加 obfs；新增回环菜单未覆盖 SS 数据交换，既有 SS peer 证据独立列出 |
| 11 | SOCKS 用户名密码 | `N::socks_and_http_authentication_is_exact_and_not_changed_to_no_auth`；`A::socks5_credentials_require_each_wire_length_in_one_to_255_bytes`；`L::xray_socks5_selected_server_and_account_halfclose_to_origin` | 语义、原生 IR、**新链回环正向已过**；peer 只接受方法 2，独立核对用户名密码，未回退 no-auth |
| 12 | HTTP 用户名密码 | `N::socks_and_http_authentication_is_exact_and_not_changed_to_no_auth`；`L::xray_http_selected_account_survives_archive_and_halfclose_to_origin`；`A::unsupported_authentication_schemes_and_basic_injection_are_never_dropped` | 语义、原生 IR、**新链回环正向已过**；独立核对 HTTP/1.1 CONNECT、Basic bytes、Host 与目标；TLS 代理仍需其独立证据 |
| 13 | 多服务器展开 | `N::all_servers_and_accounts_remain_selectable_by_original_index`；`P::multiple_password_servers_and_flat_form_preserve_source_identity`；`L::xray_socks5_selected_server_and_account_halfclose_to_origin` | 原始 server_index 保留且每节点可显式选择；新链实际选择第二服务器，未使用服务器无连接；不宣称复制 V2Ray 自动调度 |
| 14 | 多用户展开 | `B::multiple_servers_expand_only_their_own_users_in_original_order`；`A::every_server_and_account_has_its_original_path_and_no_cross_product`；`N::all_servers_and_accounts_remain_selectable_by_original_index`；`L::xray_vless_selected_uuid_survives_archive_and_halfclose_to_origin` | 语义、原生 IR、所选账号回环已过；服务器只展开自己的用户，稳定顺序与原索引，未跨服务器做笛卡尔积或默认取首个 |
| 15 | 非法 UUID | `N::every_invalid_port_uuid_and_wrong_type_remains_unexecutable`；`N::short_custom_id_uses_the_fixed_upstream_utf8_byte_boundary`；`N::compact_and_partially_separated_uuid_syntax_is_retained_without_native_normalization`；`B::invalid_uuid_empty_host_zero_port_and_missing_auth_are_diagnosed` | 已过；仅 canonical UUID 可执行。1..=30 UTF-8 字节 custom ID 为 Unverified/unsupported；被识别的 32..=36 字节 compact/部分分隔 UUID 为 Unverified + `NonCanonicalUuidMappingUnsupported`，原文不规范化。错误 hex、重复 hyphen、尾随垃圾与 31 字节普通 ID 为 Invalid；不自动生成 UUID |
| 16 | 非法端口 | `N::every_invalid_port_uuid_and_wrong_type_remains_unexecutable`；`J::outbound_port_types_follow_uint16_and_preserve_flat_settings` | 0、65536、负数、字符串、null 的结构/语义拒绝与无可执行配置已过；没有截断、取模或默认 443 |
| 17 | 不支持的加密算法 | `N::unsupported_shadowsocks_methods_layers_and_replay_options_have_no_fallback`；`P::official_ss_cipher_aliases_and_xchacha_are_not_rewritten_to_a_native_method`；`B::vmess_known_and_unknown_ciphers_are_preserved_without_fallback` | 已过；SS 2022/旧算法/别名/unknown 与 VMess cipher 保留，明确阻断；不改成某个支持的 AEAD 或 AUTO |
| 18 | 不支持的传输 | `N::unsupported_transports_tls_reality_conflict_and_vision_conflicts_stay_blocked`；`S::unsupported_transports_are_identified_and_never_fall_back_to_tcp`；`L::vmess_and_unsupported_transport_never_produce_a_runtime_or_socket` | 已过；gRPC、H2/HTTP、HTTPUpgrade、XHTTP、unknown 不变 TCP；gRPC 负向回环证实无导出、无socket |
| 19 | TLS/REALITY 冲突 | `S::tls_reality_and_network_alias_conflicts_are_invalid`；`N::unsupported_transports_tls_reality_conflict_and_vision_conflicts_stay_blocked`；`F::c_abi_revalidates_security_and_failed_configure_keeps_running_generation` | 语义、原生 IR、C ABI 已过；同时存在两层不择一丢弃；伪造 IR 仍被真实验证器拒绝，运行代次不变 |
| 20 | Vision 参数冲突 | `S::vision_unsupported_combinations_keep_exact_flow_and_source`；`N::unsupported_transports_tls_reality_conflict_and_vision_conflicts_stay_blocked`；`N::listen_address_and_mutated_native_config_are_revalidated_at_the_real_ir_boundary` | 已过；不支持 flow/transport/security 组合及绕过导入后修改的 IR 被拒绝，原 flow 不删除 |
| 21 | 参数往返 | `B::vless_flat_roundtrip_preserves_required_fields_and_missing_optional_fields`；`P::trojan_and_ss_password_algorithm_level_email_and_transport_roundtrip`；`A::current_xray_flat_authentication_is_preserved_without_trimming`；`S::tls_sni_and_string_or_array_alpn_are_lossless` | 六协议相关测试使用真实 save/restore；字段值、缺省/显式空值、来源索引、投影与最终诊断重复核对；N 中每例再次按原始配置校验 |
| 22 | 原始 JSON 恢复 | `B::raw_byte_roundtrip_keeps_bom_numbers_key_order_and_unknowns`；`J::original_bytes_keep_numeric_lexemes_order_whitespace_and_bom`；`L::xray_http_selected_account_survives_archive_and_halfclose_to_origin` | 字节级恢复已过；BOM/空白/顺序/数字词法/未知字段保持；新链回环先存档重载，再构造配置 |
| 23 | 未知关键字段 | `N::unknown_fields_mux_and_policy_levels_cannot_authorize_native_execution`；`S::inactive_nonempty_settings_and_unknown_stream_fields_block_execution`；`A::unknown_account_fields_block_validation_and_preserve_all_credentials`；`F::c_abi_refuses_xray_archives_unknown_fields_and_forged_vmess_ir` | 已过；未知源字段保留并阻断，未知 native/command字段不接受；不因字段名或值为空就默认获得执行权 |
| 24 | 字段类型错误 | `J::nested_structural_errors_have_exact_outbound_and_user_paths`；`S::malformed_security_types_still_use_the_existing_strict_parser`；`A::malformed_known_account_fields_are_rejected_by_existing_strict_parser`；`N::every_invalid_port_uuid_and_wrong_type_remains_unexecutable` | 已过；复用 A 严格解析，无字符串→数字/布尔默认修复；新增 method/mux/协议附加字段由语义层明确拒绝错误类型 |
| 25 | 敏感信息脱敏 | `B::all_public_debug_views_redact_credentials_and_unknown_names`；`J::diagnostics_never_echo_credentials_header_values_or_private_urls`；`N::archive_and_diagnostics_cannot_forge_or_leak_execution_authority`；`F::c_abi_refuses_xray_archives_unknown_fields_and_forged_vmess_ir` | 已过；密码、header值、未知字段名、私有URL与目标不进入公开Debug/诊断；存档/native配置本身仍是明确的私密数据接口 |
| 26 | 重新加载后再次校验执行能力 | `N::archive_and_diagnostics_cannot_forge_or_leak_execution_authority`；`N::late_global_transport_diagnostics_revoke_cached_native_candidates`；`B::archive_reload_rechecks_duplicate_keys_inside_the_raw_document`；`F::reloaded_vmess_and_conflicting_source_security_have_no_abi_export` | 已过；拒绝伪造 native_status，改写raw为VMess后重新阻断；重跑A/B；后置global transport诊断撤销缓存候选 |
| 27 | Qt 与 Rust Core 配置边界 | `F::restored_native_config_crosses_actual_c_abi_start_configure_snapshot_stop`；`F::c_abi_refuses_xray_archives_unknown_fields_and_forged_vmess_ir`；`F::c_abi_revalidates_security_and_failed_configure_keeps_running_generation`；`N::listen_address_and_mutated_native_config_are_revalidated_at_the_real_ir_boundary` | **Rust/C ABI 边界已过**：源文档/存档不能冒充标准IR，非法重配保持原运行代次，stop释放监听；真实 Qt 进程结果在发布后核对；新增 CLI 不等于已接入 Qt UI，不能由这四项替代 |

### B6 新增：混合有效与无效节点的选择隔离

以下四项针对有效 sibling 与无效 sibling 共存的具体边界，不把整个文档的可导入性当作每个节点的执行许可。四项在 B6 独立执行全部通过，并计入 B6 的 523 项完整回归；不计入此前 B5 的 519 项。

| 实际测试名 | 具体不变量 | 状态 |
| --- | --- | --- |
| `M::invalid_uuid_account_stays_blocked_without_contaminating_valid_siblings` | VLESS 同一服务器的中间账号为非法 UUID，前后有效账号仍可显式选择；中间账号不能导出，后面的 UUID 不被首账号替换 | 已通过 |
| `M::unsupported_cipher_server_keeps_its_slot_and_does_not_replace_valid_siblings` | SS 中间服务器的 2022 算法保持原值并阻断；两侧原生 AEAD 仍按自身 endpoint/password/cipher 导出，source server_index 不变 | 已通过 |
| `M::invalid_http_basic_username_cannot_be_exported_or_disable_sibling_authentication` | HTTP 首账号用户名含冒号时明确拒绝；显式选择下一有效账号保留完整 Basic 凭据，不退为首账号或 no-auth | 已通过 |
| `M::invalid_server_does_not_shift_cross_outbound_indices_or_authorize_fallback_selection` | 第二 outbound 的零端口服务器不污染前一 outbound 或后续服务器的用户；选择后续用户保留三层原索引；非法索引与被阻断节点均不回退首节点 | 已通过 |

四项都经真实原始 JSON → 存档 → restore，再核对原始 BOM/空白/全部字段、诊断、认证、来源路径、最终 `native_status` 与候选配置；有效候选再次经过真实 `Config::parse/validate`。这是结构、语义与原生 IR 证据，**不是新联网用例**。它们补充第 12–17、21–22、26 项的混合输入边界，不能替代第 1 节须按最终提交核对的三平台 CI。

## 4. 新增链路到底验证了什么

`L` 的五个正向用例覆盖 VLESS TCP、HTTP Basic CONNECT、SOCKS5 用户名密码、SOCKS4 空 USERID、SOCKS4a 大写版本别名与远端域名。它们用独立 peer 解析握手、核对所选服务器/账号/UUID和目标，传输分段二进制数据，在真实上传半关闭之后接收延迟尾部，核对 Core 统计与实际源端口对应关系，并断言未选端点没有连接。第六例确认 VMess 与 gRPC 无法生成运行配置，也没有对监听 peer 建连。

这些是实际回环联网证据，但不包含 TLS、REALITY、Vision、WebSocket、Trojan、SS 的新 JSON 链正向握手，不包含真实供应商节点。即使回环用例已经实际通信，`network_verified()` 仍不因导入或测试代码自动变成 true；节点执行资格与独立观测证据保持分开。

`F` 的四例真实调用 C ABI，并真实启动/重配/停止本地 Core 监听。它们验证无效输入、额外字段、伪造 VMess、TLS+REALITY 冲突、配置失败时状态不变以及脱敏；测试中没有应用代理请求，明确断言没有上游连接，因此不能把这四例算作 SOCKS/HTTP 联网成功。

`C` 的八项真实子进程测试为 `no_flag_and_legacy_private_pipeline_keep_their_existing_output`、`xray_public_mode_reports_distinct_states_and_safe_source_indices`、`explicit_private_mode_preserves_bom_raw_archive_and_all_native_candidates`、`explicit_native_export_selects_second_account_without_implicit_first_selection`、`malformed_or_unknown_flags_never_enable_private_output`、`strict_parser_errors_are_not_downgraded_or_echoed`、`input_limit_uses_strict_xray_budget`、`vmess_is_preserved_but_native_export_is_rejected_without_private_payload`。默认输出只有脱敏报告；必须显式选择私有输出和节点索引才导出执行配置。测试核对原始字节与存档、公私边界、未知参数失败、VMess 原样保存及执行拒绝，不启动 Core 或证明网络可达。

已有 Qt 单测 `src/Swirl.Quick/tests/RustCoreTests.cpp::importedParametersSurviveStoreDestructionAndNativeRoundTrip`、`browserRealityParametersSurviveImportStoreAndConfiguration`、`extractedUnsupportedFieldsNeverDisappearBeforeNativeValidation` 与 `src/Swirl.Quick/tests/ImportTests.cpp::sourceGlobalsArePreservedAndCannotBecomeNodeOnlyImports` 是现有 UI/持久化约束的入口。它们是否在最终 SHA 实际通过以及是否涉及新增入口，需单独核对；存在这些名字不等于本轮完成了新的 Qt 导入集成。

## 5. 既有运行时和独立实现互操作：单独记账

以下测试/工作流在仓库已经存在。这里只确认它们的代码与证据类型，不预填它们在最终 B6 SHA 的运行结果。

| 已存在的测试入口 | 能提供的证据 | 本轮状态与限制 |
| --- | --- | --- |
| `tools/tests/test_rust_core.py::test_vless_tcp_tls_addresses_and_invalid_responses`；`test_tls_http_socks_and_trojan_with_validated_certificate`；`test_untrusted_or_wrong_name_tls_fails_closed` | 原生VLESS/TLS、HTTP/SOCKS/Trojan TLS、证书拒绝与独立peer | 最终 SHA **pending**；不是 `xray::convert` 新入口正向链路证明 |
| `tools/tests/test_websocket_transport.py::test_vless_ws_wss_trojan_wss_forward_actual_origin_and_mask_frames`；`test_wss_verifies_name_and_trust_before_http_upgrade` | 实际WS/WSS独立peer、mask、目标、TLS验证顺序 | 最终 SHA **pending**；此脚本直接构造原生配置 |
| `tools/tests/test_shadowsocks.py::test_three_ciphers_plain_and_http_obfs_large_transfer_halfclose`；`test_response_salt_replay_rejected_across_connections` | 三AEAD、分段数据、半关闭、抗重放 | 最终 SHA **pending**；不证明本新JSON入口的SS正向链路；旧原生obfs/UDP能力不扩大本轮导出范围 |
| `tools/tests/test_reality_xray.py::test_chrome_hybrid_authentication_finished_bidirectional_data_and_close`；`test_chrome_independent_x25519_authentication_finished_bidirectional_data_and_close` | 与固定官方Xray的真实REALITY认证/Finished/双向数据 | 最终 SHA **pending**；官方peer可执行文件只作测试，不能成为产品后备内核 |
| `tools/tests/test_reality_runtime.py::RealityRuntimeInterop::test_import_uri_yaml_json_base64_to_http_and_verified_https` | 既有导入/原生Runtime→官方Xray→HTTP/HTTPS；Chrome菜单包含旧Xray格式入口 | 最终 SHA **pending**；旧 `swirl-inspect` 默认导入器不是新增 `--xray-json` 的链路证明 |
| `tools/tests/test_reality_runtime.py::VisionRuntimeInterop::test_tls13_server_first_direct_large_transfer_and_inner_authenticated_close`；`test_tls12_remains_in_authenticated_vision_outer_stream` | REALITY+Vision实际Direct/非Direct行为和内层TLS关闭 | 最终 SHA **pending**；与本轮新JSON导出入口分别记账 |
| `tools/tests/test_reality_runtime.py::RealityQtInterop::test_actual_qt_import_dpapi_select_route_and_recreate` | 实际Qt、DPAPI、选择、路由、销毁重建 | Windows最终 SHA **pending**；不能用Linux跳过Qt菜单替代 |
| `tools/tests/test_product_subscription_chain.py::test_imported_six_protocols_reach_independent_http_and_verified_https` | 既有订阅产品链路到独立HTTP/HTTPS源站 | 最终 SHA **pending**；该“six”具体是 http/socks4/socks4a/socks5/ss/vless，**不是本轮 VLESS/VMess/Trojan/SS/SOCKS/HTTP 六种JSON协议**，没有VMess支持含义 |
| `tools/Verify-PublicRealityRuntime.py`；`tools/Verify-PublicQtReality.py` | 独立公网目标的运行时证据 | 最终 SHA **pending**；历史记录与本轮新入口分开，供应商私有节点仍未验证 |

旧 `docs/evidence/CORE_REALITY_CHROME133_CI_20261020.json` 记录的源码 SHA 为 `a3b89050e141557444519c8c17f2a263e6a013fc`，它可以说明既有实现有历史证据，但本记录不把旧日志重新标成 B5/B6 测试。原 B1 完整工作流问题及修复依据见 [CI 修复记录](SWIRL_CORE_X12_B_CI_FIX_20261022.md)。

## 6. 原生执行与保留范围

- 六种协议的原始 JSON 字节、所有字段、未知项、server/user原路径索引和完整账号数据均保存在原始文档与存档中。原生投影不是唯一存储副本。
- `native_config(index, listen)` 只导出调用者显式选择的一个节点，监听必须为回环地址。标准 IR 在导出和 Core/C ABI 配置边界再次验证；不自动取第一个服务器/账号，不自动执行源 routing/DNS/inbounds/policy，不重现 V2Ray 自动轮询。
- 当前执行资格是 **TCP 代理路径**。VLESS/Trojan发送TCP command；SS/SOCKS5导出 `udp:false`。源协议支持UDP不等于本轮导出声明UDP可用。
- VLESS 支持当前原生 TCP、TLS、受限WS、受限WS+TLS，以及明确 `chrome`/`hellochrome_133` 的 TCP REALITY。Vision仅支持 TCP+REALITY+`xtls-rprx-vision`。canonical UUID以外的ID保留并阻断；上游可识别但当前未映射的 custom/compact/部分分隔 ID 标为 Unverified，错误格式标为 Invalid，绝不静默规范化。
- VMess没有原生connector，始终保持VMess并阻断。alterId原值保留；非零值不改为0；auto/AES/ChaCha/none/zero不互相替换。VMess入站/目标连接成功从未由这些测试声称。
- Trojan需要真实TLS，允许当前受限WS+TLS；不凭端口443补TLS，也不把REALITY改成TLS。
- SS只执行原样的 `aes-128-gcm`、`aes-256-gcm`、`chacha20-ietf-poly1305`。其他算法和别名保留并拒绝替换；显式 `ivCheck:false/true` 都阻断，因为原生固定抗重放没有等价可配置开关；缺省使用原生策略并明确其范围。
- SOCKS5有无认证保持不同；SOCKS4/4a的USERID不是密码。HTTP为HTTP/1.1 CONNECT；空/超长或原生无法表达的认证组合保留并阻断，不退成no-auth。
- TLS保留serverName、ALPN原表示、fingerprint、allowInsecure、certificates、disableSystemRoot以及额外字段。原生TLS使用rustls与bundled roots；显式不能表达的指纹、证书、验证模式等不能被忽略以获得执行资格。WS默认ALPN为HTTP/1.1；一般TLS缺省为h2/http1.1；HTTP CONNECT不支持h2，需明确可表示的HTTP/1.1配置。
- REALITY保留公钥/password别名、shortId、SNI、指纹、spiderX、show及全部额外字段。别名冲突拒绝。显式spiderX（包括空和`/`）阻断；缺省的上游失败爬虫与原生认证失败即关闭差异，以 `RealityNativeAuthenticationOnly` 信息诊断说明。不是普通TLS降级。
- WS原始host/path/headers/maxEarlyData/earlyDataHeaderName/heartbeat等完整保留。原生只承载单一Host/path；其他请求头、早期数据、心跳、含糊的默认Host、冲突Host等明确阻断，绝不回退TCP。
- gRPC、H2/HTTP、HTTPUpgrade、XHTTP及其他未实现传输保持原标识与全部设置，原生不可执行。enabled mux、不可表示XUDP、未知critical字段及非空全局transport defaults同样阻断。
- 诊断数量/大小/深度/扩展节点限制继续生效。达到边界明确失败，不裁掉账号、字段或诊断来制造成功。

## 7. 固定上游与许可证

B4已恢复并核对的完整研究依据见 [上游字段与语义记录](SWIRL_CORE_X12_B_UPSTREAM_20261022.md)。以下版本是语义研究锁定值；既有运行时互操作peer的不同锁定值另列，不能混为同一版本。

| 来源 | 固定提交 | 已读许可证与作用 |
| --- | --- | --- |
| [Xray-core](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74) | `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`，v26.10.21 | MPL-2.0；核对JSON字段/别名/默认行为，不复制代理实现 |
| [V2Ray-core](https://github.com/v2fly/v2ray-core/tree/de610153d59ee0bc9222a17680061d732fa14e7b) | `de610153d59ee0bc9222a17680061d732fa14e7b`，v5.55.0 | MIT；核对v4 JSON兼容路径、多服务器/用户、认证与IV设置 |
| [sing-box](https://github.com/SagerNet/sing-box/tree/dfb80349bf5779ec0a3f834c9ec2794345bff8f0) | `dfb80349bf5779ec0a3f834c9ec2794345bff8f0` | GPL-3.0-or-later，LICENSE另含名称/关联限制；只作语义比较，不引入运行时或复制实现 |
| [uTLS](https://github.com/refraction-networking/utls/tree/aa6edf4b11af82e110eea845bb2983d30138d651) | `aa6edf4b11af82e110eea845bb2983d30138d651` | BSD-3-Clause（Go Authors）；已核对 `HelloChrome_Auto = HelloChrome_133`，仅参考profile身份 |
| 既有官方Xray测试peer | `92ccc939aaf4f8965f369cf0b142e005aeaa11d5`，v26.10.17 | MPL-2.0；锁定于 `tools/tests/xray_peer/lock.json`，完整可执行文件仅作独立测试peer |
| 既有peer的REALITY模块 | `83f621788ca88b83179810b12baa7ae518aacb83` | 既有锁与构建证据保留其许可；不是本轮新增产品依赖 |

官方文档入口为 https://xtls.github.io/ 与 https://www.v2fly.org/ 。字段与默认值以记录的固定源码为准；文档持续更新不改变本轮锁定证据。实现属于Swirl现有Rust crates，未引入Mihomo、旧C++代理内核或第三方完整运行时。

## 8. 发布时状态与结果定位

| 必填项 | 当前值 |
| --- | --- |
| B5 最终完整 SHA / GitHub 提交链接 | [`a0ff384d01698047b28b468046dac319314994b8`](https://github.com/SOLHK/Swirl/commit/a0ff384d01698047b28b468046dac319314994b8) |
| B6 提交身份 | 本文件所属提交；查看其 Checks/Actions，验收报告另记录完整源 SHA 与运行 URL |
| 最终完整 workspace test 普通测试/文档测试/忽略/失败数 | B6 本地已过：522 / 1 / 0 / 0，共 36 suites，总计 523 项 |
| Linux CI 结果 | 截至发布前尚待逐 job 确认；以 B6 本提交 Checks/Actions 为准 |
| Windows CI 结果 | 截至发布前尚待逐 job 确认；以 B6 本提交 Checks/Actions 为准 |
| macOS CI 结果 | 截至发布前尚待逐 job 确认；以 B6 本提交 Checks/Actions 为准 |
| 完整Core必需步骤与证据上传结果 | 截至发布前尚待逐步骤确认；不能从 Rust 子步骤成功推定整体通过 |
| Qt / 实际产品入口 | Rust C ABI 与 CLI 已通过；真实 Qt 进程的本提交 CI 结果截至发布前尚待核对 |
| `--xray-json` CLI实现提交、进程测试名及结果 | B5 `a0ff384d01698047b28b468046dac319314994b8`；`C` 中 8 项在 B5 与 B6 都已通过；B6 完整 523 项已包含它们 |
| CI 日志与证据制品 | 在实际运行产生后核对源 SHA、制品摘要及关键 JSON/XML 计数；截至发布前尚未确认 |
| 本次新增回环菜单的覆盖限制 | 未覆盖 TLS / REALITY / Vision / WS / Trojan / SS 新 JSON 链正向握手；本轮据此严格区分可执行性与已联网证据，不宣称全协议新入口联网 |

更新规则：状态必须对应实际执行日志、返回码、源 SHA 和制品；保留旧失败原因；不要删除测试、忽略错误、把条件skip当success或拿格式检查代替完整验收。若新增测试或最后的CLI入口改变源码，需要重新对应最终SHA，不可沿用早期工作树的身份。
