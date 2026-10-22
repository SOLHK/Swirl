# Rust DNS over TLS（DoT）阶段

> **历史阶段范围：** 本文保留从 `test@fbebb28` 接续的 DoT 实现及当时验收范围，不是当前全部 DNS 能力表。
> 后续开发分支已实现严格 HTTP/1.1 DoH 与现有 Qt `https://` 字段映射，见
> [当前加密 DNS 概述](../core/README.md#encrypted-dns-dot-and-http11-doh) 和
> [此前 DoH/公网验收](RUST_WS_VALIDATION_20261017.md)。最新回归和精确提交/CI 结果见
> [策略阶段验收](RUST_POLICY_VALIDATION_20261017.md)。以下历史测试不会倒写为新版已测结果。

本阶段从 `test` 的 `fbebb28` 接续。Rust DNS 原有 UDP/TCP、A/AAAA/CNAME、TTL 缓存没有重写；新增严格验证证书的 DoT 传输，并接入既有 Qt DNS 配置。当时仅完成本 DoT 阶段，未将其扩大为 DoH、DNS 分流或全部加密 DNS 验收。

## 实际代码与边界

- `core/crates/swirl-subscription/src/dns_tls.rs`：显式 IP 端点、TLS 认证名、参数和数量限制；原有 schema 1 配置继续可读。
- `core/crates/swirl-dns/src/dot.rs`：Rust TCP/TLS 执行与两字节长度 DNS 帧。复用 `wire.rs` 的请求 ID、问题、记录、压缩指针、CNAME、TTL 与大小校验。
- `swirl-transport::secure`：复用现有 rustls/WebPKI 主机名和证书链校验。不接受关闭校验参数，不修改系统信任。
- `RustDnsConfiguration.h` / `RustCoreEngine.cpp`：只转换现有配置；不在 Qt 中执行 DNS，不改 QML/页面/布局/动效。
- `tools/tests/test_dns_tls.py`：独立 Python TLS DNS 对端，临时证书与回环目标，无完整外部代理内核。

每次未命中缓存的查询在同一条已认证 TLS 连接中依次处理 A、AAAA 和必要的 CNAME 跟随。每种记录最多跟随 8 次，返回最多 16 个地址；无跨查询连接池或流水线承诺。DNS 帧沿用 16 KiB 上限，不宣称完整 65535 字节/EDNS 支持。

最多 4 个 DoT 端点。每端点连接、TLS、查询及关闭共用 1.4 秒期限，整个解析执行受现有 3 秒期限限制；等待共享 8 个解析许可还可能耗时最多 3 秒。错误不会产生无限后台任务。关闭通知最多等待 100 ms。

同配置下正向 TTL 缓存复用；不同配置代次隔离缓存。配置更新失败保留旧配置；既有 TCP/UDP 会话保留原代次与出口。显式本地映射优先，启用 `use_system_hosts` 时本机 hosts 也优先，这不是网络 DNS 回退。

DoT 超时、证书错误或无效响应不会回退为系统 DNS、明文 UDP/TCP 或另一个代理内核。可以按序尝试其他显式 DoT 端点；NXDOMAIN 直接结束，不去其他端点找不同答案。禁止同时激活明文 `servers` 和 `tls_servers`。

**本阶段 DoT 与此前自定义 DNS 一样，直接连接用户配置的 DNS 端点。** 尚未实现按代理策略发送 DoT、系统/自定义混合解析、域名 DNS bootstrap 或 DNS 分流。不能用此阶段证明所有 DNS 请求都走代理或不存在全部 DNS 泄漏。

## 现有界面用法（待用户 Windows 验收）

构建必须使用 `SWIRL_USE_RUST_CORE=ON`。旧默认兼容构建的能力不属于此阶段。

复用当前 DNS 页的字段：

1. 选择原有“使用系统 DNS 服务器”模式，传统服务器地址留空。
2. 加密 DNS URL 填写 `tls://IP[:端口]`，或 `tls://域名[:端口]`。缺省端口 853，IPv6 使用方括号。
3. 使用域名时，必须在原有“本地 DNS 映射”中配置该域名到正确 IP 的精确映射；TLS 仍验证 URL 中的域名，不把 IP 当作域名证书校验替代。
4. IP URL 则需要证书包含对应 IP 的合法 SAN；不能为了连接成功关闭验证。
5. 按既有操作保存，并在新建的 Rust 会话中验证。

这里的模式 0 只沿用既有设置容器；一旦 DoT 激活，普通目标的网络解析由 Rust DoT 执行，不调用系统 DNS。`useHosts` 开关仅决定是否读本机 hosts；显式本地映射始终保留。

该 DoT 配置路径接受单个严格 `tls://` URL。用户信息、查询参数、fragment、自定义路径、scope ID、无效或组播 IP 均拒绝。传统服务器与 DoT 同填、自定义模式/混合模式、缺少域名 bootstrap 映射时明确报错，不忽略字段。后续 `https://` DoH 使用单独的 HTTP POST 路径，不能把 DoT 的无自定义路径限制直接套到 DoH。

Qt 入口使用公开根证书；测试控制 IR 可显式提供额外 DER/base64 CA，不读取私钥或任意文件路径。现有页面文案含历史兼容内核能力；页面文字不能代替具体执行证据。`https://` 已在后续 DoH 阶段实现，详见顶部链接；显式 `tcp://` DNS 服务器 URL 仍未实现，UDP 截断后的 TCP 重试是另一条已有路径。

## 控制 IR 示例

下列仅为结构示例，TEST-NET 地址不可当作公共服务使用：

```json
{
  "dns": {
    "hosts": [],
    "servers": [],
    "tls_servers": [{
      "address": "192.0.2.53:853",
      "tls": {"server_name": "dns.example", "alpn": ["dot"]}
    }],
    "use_system_hosts": false,
    "force_proxy_hosts": false
  }
}
```

`tls_servers` 未配置时保留旧行为。端点必须是明确 SocketAddr；认证名与连接地址独立。ALPN 可以为空或仅 `dot`，不接受 HTTP ALPN 混入 DoT。

## 测试与验收

先在 `core` 执行：

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked -p swirl-api
```

在仓库根目录设置 `SWIRL_RUST_HARNESS` 为同次构建的 `swirl-api`，然后执行：

```text
python tools/tests/test_rust_core.py
python tools/tests/test_shadowsocks.py
python tools/tests/test_dns_tls.py
```

新增 3 项 IR 参数测试和 11 项独立 DoT 测试，覆盖分片帧、TLS 验证、TTL/CNAME、零 TTL、错误 ID/问题/帧/TC、超时、纯 TLS 故障切换、NXDOMAIN、原子更新、代次缓存、旧流存活及 IPv6。IPv6 不可用时单独报告跳过。Qt 新增两项参数映射/拒绝测试，仍保留原来的 Rust Qt 回归。

CI 的 Linux、macOS、Windows jobs 已接入新的 DoT 测试。测试通过数量及结果必须对应实际提交和 Actions，不以本文件代替运行证据。该轮没有访问用户私有节点、公开 DoT 服务或修改用户电脑；个人 Windows 运行、真实公共/私有 DNS、弱网和远程控制仍待用户验收。

## 下一阶段

该历史阶段的后续清单包括 DoH、显式 bootstrap 策略与多地址重试、负缓存、DNS 分流及自动策略组。
其中 DoH 和 Rust IR/API 自动策略组现已在后续阶段接入，见 [原生策略组](RUST_NATIVE_POLICIES.md)；
不应重复实现或继续把它们视为未编译候选。域名 bootstrap、策略感知的多地址重试、负缓存、DNS 分流、
更多协议传输、Qt 自动组映射和 TUN 仍待推进。不得把本阶段合成 TLS 测试扩大成全协议/完整内核验收。

规范依据：
- RFC 7858：<https://www.rfc-editor.org/rfc/rfc7858>
- RFC 8310：<https://www.rfc-editor.org/rfc/rfc8310>
- 既有 DNS 报文层沿用 RFC 1035 / TCP framing 校验。
