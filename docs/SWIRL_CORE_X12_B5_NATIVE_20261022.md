# X1.2-B5：真实 Rust Core 原生适配

## 能力边界

本轮复用 X1.2-A 的严格 JSON 解析器、原始字节、重复键检查、资源限制与脱敏诊断。没有重新实现解析器，没有新增第三方代理运行时，没有修改 Qt UI 或原生协议连接器。

四种判断分开处理：

1. import_document 成功：源 JSON 结构可以读取；不代表所有字段语义已实现。
2. ValidationStatus::{Valid, Invalid, Unverified}：已核对的协议语义、错误或尚未核对的扩展。
3. NativeStatus::{Executable, Blocked}：当前 Rust Core 能否执行**选定节点的 TCP 代理路径**。
4. network_verified()：导入、保存、恢复和原生适配始终返回 false。测试证据不写成对任意节点的联网承诺。

原生导出不执行原配置的 DNS、routing、inbound、policy、负载均衡或 UDP 策略。完整源配置仍保存在 raw_json() 和归档中，A 的全局配置诊断仍可见。非空全局 transport 可能改变节点传输语义，因此会明确阻断所有相关节点。不能把单节点导出描述为全量 Xray/V2Ray 运行时替代。

## 实际接口与最终检查

ValidatedOutbound::native_outbound() 返回秘密信息视图，只允许在 validation == Valid 且**最终诊断**没有 error/unsupported 时访问。不能绕过映射后才加入的全局传输阻断。

ConvertedDocument::native_config(index, listen) 要求显式节点索引和 loopback 监听地址，构造一个只含该节点的标准 swirl_subscription::Config。不默认选第一个服务器或账号。创建时调用真实 Config::validate()；通过 Config::parse() 重新读取、Core 启动及 C ABI configure 时还会再次验证。

归档仍然只存 schema/source/raw_json；不保存或信任序列化的执行权限、候选对象或网络成功标记。恢复后重新执行 A、协议语义、安全传输和原生适配。伪造能力字段的归档被拒绝。

映射调用 core/crates/swirl-subscription/src/lib.rs 中已有的 Outbound 与验证器，不添加假的 VMess 枚举，不改协议，不把 REALITY 改为 TLS，不删除 Vision flow，不替换 Shadowsocks method，不把其他 transport 改成 TCP。原生 IR 中 SS/SOCKS5 的 UDP 明确为 false，VLESS/Trojan 连接器发 TCP command。

## 六协议原生范围

| 源协议 | 当前可生成的原生 TCP 路径 | 保留但不能执行的主要情况 |
|---|---|---|
| VLESS | 标准 UUID、encryption:none；TCP、普通 TLS、支持的 WS/WS+TLS；受限 REALITY；受限 REALITY+Vision | 自定义 ID、其他 encryption、非零用户策略、TLS+Vision、未知 flow、未实现传输或安全选项 |
| VMess | 无 | 所有节点仍保留 VMess；完整保留 id/alterId/security，不存在 VLESS 替换 |
| Trojan | 必需 TLS；支持的 WS+TLS；完整密码 | 无 TLS、REALITY、已移除 flow、非零策略、不可表示的 TLS/WS 参数 |
| Shadowsocks | aes-128-gcm、aes-256-gcm、chacha20-ietf-poly1305 | 2022、CFB、其他方法/别名、outer TLS/WS、插件、UoT、显式 ivCheck、OTA=true |
| SOCKS | SOCKS5 无认证或完整用户名密码，支持的 TLS；SOCKS4/4a USERID（不带 TLS） | 认证不完整、不可表示的长度/控制字符、4/4a 密码、其他认证选择器、WS/REALITY |
| HTTP | HTTP/1.1 CONNECT，无认证或 Basic；TLS 必须只协商 HTTP/1.1 | HTTP/2 ALPN、非 Basic 组合、额外代理请求头、WS/REALITY |

所有多服务器和多用户均按原顺序展开；一个服务器只配对自己的用户。NodeSource 保留 outbound/server/user 的原索引与路径。原文及归档不因挑选某个节点而裁掉其余账号。

## 细节与审查修正

- SOCKS 版本 4A 按官方大小写语义映射为 SOCKS4a，源值仍为 4A。显式空账号 {} 对 SOCKS4 生成空 USERID，不伪造 SOCKS5 密码认证。
- [固定 Xray UUID 语义](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/common/uuid/uuid.go) 的 custom ID 是 UTF-8 1..=30 字节。本轮最小修正 <30 为 <=30，30 字节标记 CustomIdMappingUnsupported，保留且不可执行；没有生成 UUID。当前原生 UUID 范围仍是标准 36 字符形式。可识别的紧凑 32 位十六进制及分组边界可选分隔形式以 NonCanonicalUuidMappingUnsupported 保留并阻断；不模仿上游忽略尾随垃圾的宽松行为。
- 显式 ivCheck:false 不能当作原生已经应用。固定 [V2Ray 配置](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/proxy/shadowsocks/config.go) 允许关闭该重放检查；Swirl 的 AEAD TCP 连接器固定启用 600 秒重放窗口，IR 没有关闭开关。因此显式 ivCheck 的两种布尔值都保留并阻断。缺省使用原生固定安全策略，不削弱 Core 防护。ota:false 保留为已核对的无作用值。
- 普通 TLS 使用原生 rustls 与 bundled roots。没有声明它与某个上游缺省 ClientHello、操作系统根集合完全相同。显式 fingerprint、额外证书、关闭验证、禁用根信任等不可表示请求仍保留并阻断。
- REALITY 的源指纹只支持本轮固定 Xray/uTLS 下匹配原生实现的 chrome、hellochrome_133；原生内部 rustls/chrome_133 名字不能绕过官方源语义。缺省 spiderX 的上游失败爬虫不在原生实现范围内，RealityNativeAuthenticationOnly 明确披露；显式 spiderX、show、其他扩展不能被删除以获得执行资格。
- HTTP CONNECT 连接器发 HTTP/1.1；因此默认带 h2 的 ALPN 也会阻断，只有兼容的显式 ALPN 才导出。WS 同样必须满足 HTTP/1.1 与 Host/Path 的映射条件；未知头、early data 等不会被丢弃。

## 本阶段真实本地验证

以下为当前隔离 Linux 工作树的真实执行结果，所有测试使用合成数据：

- cargo check --workspace --locked：通过。
- cargo fmt --all -- --check：通过。
- cargo clippy --workspace --all-targets --locked -- -D warnings：通过。
- cargo test -p swirl-subscription --locked：222 项通过；其中 xray_native.rs 21 项。
- cargo test -p swirl-core --test xray_import --locked：6 项通过。
- cargo test -p swirl-api --test xray_boundary --locked：4 项通过。

Core 链路测试从原始 JSON、归档恢复、原生 Config、严格重读到实际 Core，经独立协议 peer 到独立 origin。HTTP、SOCKS5、VLESS、SOCKS4、SOCKS4a 正例验证指定账号/UUID、32,785 字节上传、16,422 字节下载、写 EOF 后响应及完整尾部。origin 看到的源端口必须等于 peer 的出站端口，验证没有 DIRECT 绕过；未选择服务器不得收到连接。VMess/gRPC 负例不得产生配置或连接。

C ABI 测试直接调用 swirl_core_command，验证调用者缓冲区边界、start/configure/snapshot/stop、失败更新原子性和监听端口释放。原始 Xray、归档、伪造 VMess IR、未知字段和 TLS+REALITY 冲突不能越过边界。该测试是 Qt 所用 ABI 契约验证，不冒充本地 Qt UI 运行。

上述新增链路没有验证 TLS/REALITY、公网或私人供应商节点。原有独立 TLS/WS/AEAD/REALITY/Vision 互通以及 Windows Qt/应用集成，由完整 Rust Core 工作流另行验证并在 B6 记录精确提交结果。

## 可直接调用的 CLI

既有 swirl-inspect 无参数和单独 --private-json 的输出保持兼容。新增显式模式只读 stdin，不打开文件路径、URL、DNS 或网络连接：

```bash
swirl-inspect --xray-json < configuration.json
swirl-inspect --xray-json --private-json < configuration.json
swirl-inspect --xray-json --private-json --native-node 1 --listen 127.0.0.1:0 < configuration.json
```

默认只返回脱敏报告，分别显示 syntax、validation、native_status、network_verified；native_execution_scope 明确为 explicit_single_node_tcp，全局配置执行标记为 false。导入成功的 ok 不代表节点可执行，调用者必须检查逐节点 native_status。

显式 --private-json 输出 report、原始 raw_json、archive 及与展开节点顺序一致的 native_candidates；不可执行项为 null。只有同时明确提供 --native-node 和 --listen 才附带 native_config，不隐式选第一个账号。此输出含原文凭据，只供受控本地配置/缓存管线，不是日志格式。

未知/重复参数、不完整 native 参数、非 loopback listen 或未开启私密导出时请求完整配置：退出码 2；结构输入失败或选定节点不可执行：退出码 1，并仅返回脱敏诊断；可读取且无需导出的普通报告：退出码 0，即使报告中节点不可执行。导出失败不会返回部分配置或私密负载。

新增 xray_cli.rs 的 8 项实际进程测试全部通过，覆盖上述边界、18 种非法参数组合、第二账号选择、旧两个入口输出字节兼容、BOM/归档、输入预算、敏感未知字段和 VMess 拒绝。

## B5 最终冻结验证

在包含 CLI 和 UUID 边界修正的完整本地源上，按顺序运行以下全部命令并全部通过：

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

完整 workspace：35 个 suite，519 项通过，0 失败、0 忽略（含 1 项 compile-fail doctest）。其中 subscription 为 223 项，native 回归为 22 项，Core 新链路 6 项、C ABI 4 项、CLI 8 项。测试使用 locked 公共依赖缓存；不依赖私人订阅或令牌。阶段发布后仍须核对 GitHub 对精确提交执行的 Windows/Linux/macOS 结果，不能用此本地结果替代三平台验收。
