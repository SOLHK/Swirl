# X1.4-A5 — 从真实 Xray/V2Ray JSON 导入到原生传输互通

此阶段补齐持久化的原生 transport 配置和导入映射后，通过 `tools/tests/test_imported_transports_xray.py` 运行完整链路：原始 Xray/V2Ray JSON → `swirl-inspect --xray-json --private-json --native-node 0 --listen 127.0.0.1:0` → 原样导出的 `native_config` → 普通 `Core.start` → Swirl 原生连接器 → 固定官方 Xray 服务端 → 独立 HTTP、HTTPS 或双向数据目标。

测试不传入外部 transport map，不在导出后注入 CA、改写凭据或改变节点配置。`swirl-inspect` 仍正确报告 `network_verified: false`；独立网络验收由后面的真实请求证明，不由导入成功推导。

## 官方 TLS 配置语义

源 JSON 使用 `tlsSettings.certificates` 中单个 `usage: "verify"` 条目，并以 `certificate` 字符串数组提供临时 CA 的 PEM 行。官方 [TLS 文档](https://xtls.github.io/en/config/transports/tls.html) 定义 `verify` 为验证对端的 CA，用于验证时不要求私钥；固定版本的 [`TLSCertConfig.Build`](https://github.com/XTLS/Xray-core/blob/v26.10.21/infra/conf/transport_security.go) 将此映射为 `AUTHORITY_VERIFY`，无证书/密钥文件时使用内嵌材料。默认根证书行为见 [`transport/internet/tls/config_other.go`](https://github.com/XTLS/Xray-core/blob/v26.10.21/transport/internet/tls/config_other.go)。

因此本测试的自签信任属于真实原始配置，不是导出后的测试替换。导入器映射到原生 `ca_der_base64`，在 Swirl 默认 WebPKI 信任根之外添加该 CA。Swirl 当前未读取操作系统额外安装的企业/用户 CA；这些 CA 需要显式提供，不能把默认根集合称为与所有平台的 Xray 系统证书池完全相同。要求 `disableSystemRoot: true`、未支持的证书用途或文件形式等情况须阻断原生导出，不能静默改变安全策略。本次负面测试实际覆盖 `disableSystemRoot: true`。

## 实际执行结果

Linux x86_64 执行 5 个测试方法，用时 13.539 秒，全部断言通过。固定服务端为官方 Xray `26.10.21 1b1647c`；旧 HTTP/2 传输使用官方 Xray `1.8.24 6baad79`，没有把已移除的旧传输归入当前服务端能力。

完整脱敏结果见 [official-results.json](evidence/x14-a5-imported-transports/official-results.json)，执行输出见 [official-tests.txt](evidence/x14-a5-imported-transports/official-tests.txt)。JSON 包含实际 runtime/inspector SHA-256、服务端版本以及 `post_export_modifications: false`、`external_transport_map: false`、`qt_product_acceptance: false`。

| 导入后原生组合 | 官方对端 | HTTP / HTTPS | 每向 4 MiB | 应用完成后正常关闭 |
|---|---|---|---|---|
| VLESS + gRPC + TLS | 26.10.21 | 均通过 | 通过 | 通过 |
| Trojan + gRPC + TLS | 26.10.21 | 均通过 | 通过 | 通过 |
| VLESS + HTTP/2 + TLS | 1.8.24 | 均通过 | 通过 | 通过 |
| VLESS + HTTPUpgrade + TLS | 26.10.21 | 均通过 | 通过 | 通过 |
| VLESS + XHTTP `stream-one` + TLS | 26.10.21 | 均通过 | 通过 | 通过 |

每个 4 MiB 测试逐块比较上传和回传内容，并核对最终 SHA-256 和独立目标收到的字节数。HTTP/HTTPS 共 10 次；HTTPS 对独立目标执行应用层证书验证和 `close_notify`。另通过 legacy V2Ray 单数 `outbound` JSON 入口导入 HTTP/2 节点，并运行四条同时存在的 HTTPS 会话。此处的 V2Ray 指兼容的旧/common JSON 格式，未声称 V2Ray v5 `transportSettings` 独立方言已实现。

`serviceName`、gRPC authority / user-agent、HTTP host/path/custom headers、TLS serverName / ALPN 由源 JSON 映射并交给原生连接器。测试检查导出字段，并通过官方服务端完成对应传输握手、代理认证和真实数据。

## 实际拒绝路径

12 种不支持的配置在原生导出阶段失败，无 `native_config`，没有使用降级后的节点尝试网络：

- XHTTP `auto`、`stream-up`、`packet-up` 三种模式。
- XHTTP `extra`、`downloadSettings`、`xmux`。
- TLS `fingerprint: chrome`、`allowInsecure: true`、`disableSystemRoot: true`。
- HTTPUpgrade `maxEarlyData`、`earlyDataHeaderName`、包含 `?ed=2048` 的 early-data 路径。

另外，在 gRPC、旧 HTTP/2、HTTPUpgrade、XHTTP 的 VLESS 节点中分别导入错误 service/path、错误 SNI 和错误 UUID，共 12 次实际连接尝试，独立目标的请求数均为零。SNI 错误由 TLS 校验拒绝；协议无显式肯定认证应答时，测试要求连接被关闭或 Core 返回失败，且独立目标没有收到数据，不把发送请求头当成认证通过。

## 性能记录和关闭边界

本次每向 4 MiB 的 debug loopback 端到端时间包括导入后的 Core 连接、代理握手、Python 逐块生成/校验和往返等待：

| 组合 | 本次总耗时（毫秒） |
|---|---:|
| VLESS gRPC TLS | 601.513 |
| Trojan gRPC TLS | 1641.829 |
| VLESS HTTP/2 TLS | 3680.214 |
| VLESS HTTPUpgrade TLS | 1790.827 |
| VLESS XHTTP stream-one TLS | 4502.218 |

这些数值用于复现及发现退化，没有标记为纯 TCP 延迟或公网吞吐。协议/传输之间的差异也包含测试逐块往返和不同服务端版本的影响，不用于宣称产品性能优劣。

本次测试让应用数据交换完成后正常关闭。它没有改变既有“先半关闭发送端、再等待对端回复”测试暴露的 Xray 上游关闭行为，也没有把该旧失败改为通过。Windows Qt 产品验收没有执行，Windows/macOS 原生结果应以相应 CI 的实际执行为准。

## 复现

```sh
cargo build --manifest-path core/Cargo.toml --locked \
  -p swirl-api --bin swirl-inspect -p swirl-core --example transport-runtime

SWIRL_TRANSPORT_RUNTIME=/absolute/path/transport-runtime \
SWIRL_TRANSPORT_CLIENT=/absolute/path/transport-client \
SWIRL_INSPECT_BINARY=/absolute/path/swirl-inspect \
SWIRL_XRAY_BINARY=/absolute/path/xray-26.10.21 \
SWIRL_XRAY_LEGACY_BINARY=/absolute/path/xray-1.8.24 \
SWIRL_IMPORTED_TRANSPORT_EVIDENCE=/absolute/path/official-results.json \
PYTHONPATH=tools/tests python3 -m unittest -v test_imported_transports_xray
```

服务端通过 `xray run -config <临时配置>` 启动，fixture 生成临时 CA、证书和合成身份，绑定 loopback，并记录服务端接受的目标。缺失二进制、版本不符、导入错误或真实流量失败均导致测试失败，不跳过或伪造通过。
