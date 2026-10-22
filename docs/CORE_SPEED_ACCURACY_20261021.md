# Swirl Core 节点测速口径与 Windows 实测（2026-10-21）

## 原因定位

`RustCoreEngine::probeNode` 从发出 Qt `QNetworkAccessManager::get()` 到 `QNetworkReply::finished` 计时，默认 URL 为 `https://www.gstatic.com/generate_204`，仅把无网络错误且 HTTP 2xx 的完整请求记为成功。它手动禁止跳转、要求正常 TLS 验证，并为请求设置 `Connection: close`。因此节点页原来的“延迟”数字是**一次完整 HTTP 请求耗时**，包含本机代理连接、Rust 出站、目标连接、HTTPS TLS 和响应，不是节点 TCP RTT。8 秒请求超时和 9 秒额外终止计时器均未修改。

批量测速由 `NodeTestService` 为每个节点建立隔离的 `RustCoreEngine`，最多同时运行 3 个；隔离内核启动完成后才调用上述 HTTP 计时函数。每次只测一个请求，不能获得连接复用收益。计时函数完成后才刷新 Rust 状态；当前证据没有显示 Qt→Rust FFI 本身形成 300 ms 固定等待。Rust 上游 TCP/Shadowsocks 握手、节点服务器 DNS 与加密开销目前未单独打点，不能从完整 HTTP 数字中分离。

Clash Stra 展示约 60 ms 的节点名为“实验性 IEPL 专线 1”，Swirl 约 365 ms 的节点名为“标准 IEPL 专线 1”。名称不同；本机经 `ifconfig.me/ip` 对两个代理入口做证书校验的公网出口检查，所得地址也不同（只比较本机摘要，未保存原始地址）。无法确认二者使用同一服务器、相同凭据、相同出口或相同规则。Clash UI 测速 URL、地址族和计时定义也没有取得可核对的记录，**不能把 60 与 365 解释为同节点的 Rust 性能差**。

## 固定目标的分段实验

`tools/Measure-ProxyHttpStages.py` 固定同一个 `www.gstatic.com` IPv4 地址和 `/generate_204`，通过本机 HTTP 代理 CONNECT 该 IP，用原域名做 TLS SNI 与证书验证。它分别记录本机 TCP 连接、CONNECT 收到 200、已验证 TLS、HTTP 首字节和 204 响应头完成；每个入口做 10 条新连接和同一 TLS 连接内的 10 次后续请求，报告中位数及最近秩 P95。请求带 `Cache-Control: no-cache`，不读节点配置、不输出请求正文。目标 DNS 查找发生在实验前，故下表不含目标域名解析；节点服务器 DNS 是否发生及耗时未知。

| 入口及状态 | 首条冷请求 | 10 条冷连接中位 / P95 | 10 次复用请求中位 / P95 | 冷请求内 CONNECT / TLS / HTTP 中位 |
|---|---:|---:|---:|---:|
| Swirl PID 37700，`127.0.0.1:7898`，10/10 | 947.7 ms | 960.2 / 988.5 ms | 305.4 / 307.7 ms | 45.6 / 583.0 / 306.9 ms |
| Clash PID 35488，`127.0.0.1:7897`，10/10 | 56.8 ms | 62.8 / 82.3 ms | 15.5 / 16.1 ms | 0.2 / 42.9 / 16.2 ms |

同一测试的本机 TCP 连接中位数分别为 15.5 和 0.2 ms；它是到本机监听端口的时间，**不是到代理节点的 TCP 建连时间**，Windows 进程调度和监听状态也可影响它。Clash 在约 0.2 ms 就返回 CONNECT 200，可能先确认本地隧道、后执行远端连接；两个入口的 CONNECT 耗时不能直接当作同一种上游握手。完整冷请求和复用请求差距证实连接建立及 TLS 成本不能与复用请求混为一个“延迟”。公网出口不同，表中绝对差距不能归因于 Shadowsocks 加密或 Rust 实现。

首次运行原版测量脚本时，Swirl 冷连接第 6/10 条发生 `SSLEOFError`，其余 9 条及 10 次复用请求完成；随后同目标 10/10 成功。原失败保存在 `docs/evidence/core-speed-20261021/swirl-7898.json`。原脚本的本机 TCP 数字还包含 Python `getaddrinfo` 与逐次建立 TLS context 的开销，因此只把修正后的 `swirl-corrected-7898.json` 与 `clash-corrected-7897.json` 用作上表。失败不能由一次重试通过抹除，其原因尚未定位。

## 本轮精度修复

- 节点页在 Rust 构建中明确标为“HTTP ms”，并解释完整请求与 TCP 往返延迟的区别；测试详情写“完整请求”。
- Rust 测速结果标记 `metricType=http_total`，供界面和后续诊断辨认。
- 重测开始时删除该节点旧结果；Rust 活跃节点重测或切换节点时立即清空旧耗时、HTTP 状态和健康状态，避免把上一节点的数字显示在新节点上。
- 不调整计时起点、TLS 验证、HTTP 成功判定或失败样本，也不减去固定毫秒数。

计时字段和 HTTP/TLS 检查参考 [curl 官方 write-out 文档](https://curl.se/docs/manpage.html#-w) 与 [Python `ssl` 验证接口](https://docs.python.org/3/library/ssl.html#ssl.create_default_context)；测量工具仅使用 Python 标准库，独立实现。

## 源码验证与剩余问题

Windows Release 的 `Swirl.exe`、`SwirlRustCoreTests.exe` 和更新后的 QML 缓存均编译成功；最终 `ctest -R ^swirl-rust-qt-integration$` 为 1/1 通过。XML 中 9 条需要另外对端的既有可选用例仍为跳过，未计作通过。新增 Qt 回归实际验证：原成功结果在同步失败的重测中不能留存；正在重测与切换节点时，旧 HTTP 耗时和 HTTP 状态立即清零。首次测试版本把“结果为空”写成过严断言，在同步返回失败时失败；改为验证“不保留旧成功”后完整测试通过。Rust `cargo fmt --all -- --check`、全工作区 clippy `-D warnings`、`cargo test --workspace --locked` 均退出 0；测量脚本语法编译和固定目标报告一致性检查通过。

仍未验证两款软件使用相同节点与出口；初次 `SSLEOFError` 原因也未定位。尚无 Rust 内部的节点服务器 DNS、Shadowsocks 分段计时，因此不声称已消除协议性能差。当前仍运行的是上一提交安装版，源代码中的新指标文案要在新构建安装后才会显示。
