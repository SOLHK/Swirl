# X1.4-A6：既有 REALITY / Vision 原生路径复测

2026-10-22，在 Linux x86_64 上使用当前工作树重新构建的 Rust 客户端，对固定官方 **Xray v26.10.21**（`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`）执行既有连接器和 Core 运行路径的回归。共 **46 次测试执行通过，0 失败，0 错误，0 跳过**。本轮没有改写 REALITY 或 Vision 协议实现。

Swirl Rust 是唯一代理客户端。完整官方 Xray 只负责独立服务端，Python/OpenSSL 提供目标 HTTP(S)、TCP 和 TLS 1.3 服务。下面的结果属于独立官方服务端回环互通，未执行 Windows Qt 产品验收或公网节点连接。

## 实际结果

| 测试入口 / 参数 | 执行数 | 时间 | 经过的真实路径 |
| --- | ---: | ---: | --- |
| `test_transport_reality_xray.py -v` | 10/10 | 5.520 s | 原生连接器：raw REALITY、Chrome133 raw Vision、gRPC `tun` / `tun_multi`、XHTTP `stream-one` |
| `test_reality_native_release.py` | 8/8 | 4.187 s | URI / JSON / YAML / Base64 导入 → Core JSON 命令宿主（`Controller.dispatch`）→ HTTP CONNECT / SOCKS5 → Rustls REALITY → VLESS → 独立目标 |
| `test_reality_native_release.py --fingerprint chrome_133` | 8/8 | 4.496 s | 同上，固定 Chrome133 配置，额外包含 Xray / sing-box 格式导入 |
| `test_reality_native_release.py --vision` | 10/10 | 7.618 s | Rustls REALITY + `xtls-rprx-vision`，含 TLS 1.3 Direct 与 TLS 1.2 保持封装 |
| `test_reality_native_release.py --vision --fingerprint chrome_133` | 10/10 | 7.638 s | 固定 Chrome133 REALITY + `xtls-rprx-vision`，同样验证两种内层 TLS 路径 |

连接器套件包含 HTTP 和验证证书的 HTTPS、4 MiB 双向传输、并发流、客户端取消、ALPN、错误公钥 / short ID / SNI / UUID、目标 HTTPS 证书错误，以及不适用传输 / Vision 组合的明确拒绝。Core 套件还验证节点切换保留已有会话、后续会话使用新节点、路由拒绝、握手超时不尝试备用节点或 Direct、运行期取消释放 socket、目标半关闭和全部会话结束。

### Vision Direct 的单独证据

两个 Vision Core 套件都执行了 `test_tls13_server_first_direct_large_transfer_and_inner_authenticated_close`：

- 内层 TLS 1.3 由独立 Python/OpenSSL 目标完成握手并先发送 34 字节探针，客户端收到后才发送应用数据。
- 每方向真实收发 **524,288 字节**，两端 SHA256 一致；客户端使用碎片化写入，目标会暂停读取后恢复。
- 官方日志统计上传 Direct 命令 **1 次**、下载 Direct 命令 **1 次**；REALITY 认证、客户端 Finished 和 VLESS 接受各 **1 次**。
- 独立目标确认收到并发送 TLS `close_notify`，连接关闭、线程释放；Core `active=0`、`failed=0`。官方服务端正常回收，没有强制 kill，监听端口关闭。

对应目标、官方观察和 Core 状态保存在 [Rustls Vision](evidence/x14-a6-reality-vision/vision-rustls/) 与 [Chrome133 Vision](evidence/x14-a6-reality-vision/vision-chrome/) 的同名测试子目录。TLS 1.2 测试则确认 Vision padding / unpadding 发生，但上传和下载 Direct 命令均为零。

## 可复核证据

- [重新构建客户端日志](evidence/x14-a6-reality-vision/client-build.txt)。本地构建为 unoptimized dev，未把它当作发布性能基准。
- [连接器套件汇总](evidence/x14-a6-reality-vision/transport/test-summary.json)与[完整输出](evidence/x14-a6-reality-vision/transport-tests.txt)。
- [Rustls Core 汇总](evidence/x14-a6-reality-vision/core-rustls/test-summary.json)、[Chrome133 Core 汇总](evidence/x14-a6-reality-vision/core-chrome/test-summary.json)。
- [Rustls Vision 汇总](evidence/x14-a6-reality-vision/vision-rustls/test-summary.json)、[Chrome133 Vision 汇总](evidence/x14-a6-reality-vision/vision-chrome/test-summary.json)。
- 每个 Core 套件的 `source-identity.json` 保存实际客户端哈希、官方服务器哈希、固定压缩包哈希、测试源文件哈希、Cargo.lock 哈希、Git HEAD 和未提交修改列表。此次测试针对记录中的工作树，不能据此替代之后提交的 CI。
- [归档清单](evidence/x14-a6-reality-vision/archive-manifest.json)保存原文件与归档文件 SHA256。官方 transport debug log 中包含临时 AuthKey / short ID 的 **56 行**在归档副本中明确替换为脱敏标记；认证结果、数据、关闭、目标统计和测试状态没有修改。未归档配置、私钥或真实订阅凭据。

原始 `source-identity.json` 的 `production Rust control ABI with portable JSON test host` 与归档清单的 `production Core ABI` 是历史测试宿主标签，措辞不够精确。本报告将其明确为 **Rust Core JSON 命令宿主**：`core/crates/swirl-api/src/main.rs` 直接创建 `Controller` 并调用 `dispatch`，此次网络测试没有调用导出的 `swirl_core_command`，也没有加载 Windows DLL。原始证据及其哈希保持不变；测试入口已修正后续生成的 scope。另有 `swirl-api/tests/xray_boundary.rs` 直接调用导出 C ABI 的配置与生命周期测试，但它没有上游应用流量，不能据此将本节网络结果标为经导出 C ABI 或 Qt 产品运行。

## 固定版本验证与测试入口

原有 `test_reality_runtime.py` 绑定 `tools/tests/xray_peer/lock.json` 中的 v26.10.17 源码编译对端，以及可复现构建证明。该验证规则保持不变，不能把新的官方二进制放进去伪造旧 manifest。

新增 `tools/tests/test_reality_native_release.py` 直接复用原有 `RealityRuntimeInterop` / `VisionRuntimeInterop` 的测试方法与断言，只为独立官方发行版提供另一种明确的来源验证。它使用 `tools/tests/transport-peer-lock.json` 的当前 v26.10.21 固定版本，验证二进制版本以及以下两种来源之一：

1. `SWIRL_XRAY_RELEASE_ARCHIVE`：完整 ZIP SHA256 必须与锁文件一致，ZIP 内的 `xray` / `xray.exe` 字节 SHA256 必须与待运行二进制一致。本地此次运行使用此路径。
2. `SWIRL_XRAY_RELEASE_MANIFEST`：使用 `tools/Fetch-TransportPeers.py` 的实际输出 `manifest.json`，校验平台、版本、提交、压缩包 SHA256 和二进制 SHA256。它用于现有 CI 下载步骤；此次本地四套 Core 网络测试使用的是上面的 ZIP 路径。

两种来源必须提供且只能提供一种。缺少依赖、版本不符、校验不符或跳过测试均使套件失败。

## CI 与本地复现

先构建实际客户端并下载固定官方测试服务端：

```sh
cargo build --manifest-path core/Cargo.toml --release --workspace --bins --examples --locked
python tools/Fetch-TransportPeers.py --output out/peers/xray
```

新入口使用以下环境键。Windows 为可执行文件加 `.exe` 后缀；不要把其他代理程序填入客户端路径。

| 环境键 | 角色 / 示例 |
| --- | --- |
| `SWIRL_XRAY_BINARY` | `out/peers/xray/current/xray`，官方服务端 |
| `SWIRL_XRAY_RELEASE_MANIFEST` | `out/peers/xray/manifest.json`，真实下载工具输出 |
| `SWIRL_XRAY_RELEASE_ARCHIVE` | 与 manifest 二选一，用于直接复核完整官方 ZIP |
| `SWIRL_RUST_HARNESS` | `core/target/release/swirl-api`，直接调用 `Controller.dispatch` 的 Rust Core JSON 命令宿主；不经过导出 C ABI |
| `SWIRL_RUST_INSPECTOR` | `core/target/release/swirl-inspect`，实际导入和归一化入口 |
| `SWIRL_REALITY_RUNTIME_EVIDENCE` | 每次运行使用不同证据目录，保留全部结果 |

分别执行四个参数组合，不能让后一次证据覆盖前一次：

```sh
python tools/tests/test_reality_native_release.py
python tools/tests/test_reality_native_release.py --fingerprint chrome_133
python tools/tests/test_reality_native_release.py --vision
python tools/tests/test_reality_native_release.py --vision --fingerprint chrome_133
```

连接器套件使用 `SWIRL_TRANSPORT_CLIENT=core/target/release/examples/transport-client`、同一 `SWIRL_XRAY_BINARY`，并设置独立 `SWIRL_TRANSPORT_EVIDENCE`，运行 `python tools/tests/test_transport_reality_xray.py -v`。既有 `.github/workflows/rust-transport.yml` 已定义该连接器步骤；新增 release Core 入口的跨平台工作流接入及 GitHub 运行结果由根阶段验收单独记录，本记录不宣称这些 CI 已运行。

## 未扩大宣称的范围

本轮完整 Vision Direct 证据限定 **VLESS + raw TCP + REALITY + `xtls-rprx-vision`**。普通 TLS 的通用 Vision 组件不能获取底层原始 socket 的所有权，仍明确拒绝 Direct；Core 对没有 REALITY 的非空 flow 明确拒绝。gRPC / XHTTP 不能与 Vision 任意组合，相关负面测试通过。

`rustls` 与固定 `chrome_133` 配置的真实认证和数据已验证。本轮没有重新执行独立 uTLS ClientHello 字节级对照、旧 v26.10.17 TLS 组件对端套件、Windows Qt / DPAPI、外部公网节点、移动平台或峰值内存基准。测试的耗时包含 fixture 和失败路径等待，不能称为纯 TCP 延迟或网络吞吐基准。
