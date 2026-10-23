# X1.4-A7：Hysteria2 / TUIC 真实动态库 C ABI 互通

2026-10-22，在 Linux x86_64 上实际构建并动态加载本仓库的
`libswirl_api.so`，通过导出的 `swirl_core_abi_version` 和
`swirl_core_command` 驱动官方 Hysteria2 / TUIC 服务端互通。最终执行
**6 个测试方法，全部通过，0 失败、0 错误、0 跳过，23.192 秒**。

此处的控制调用确实跨越动态库 C ABI。Python `ctypes` 负责调用、生命周期
及独立应用目标；代理客户端与全部流量转发仍是 Swirl Rust Core。
官方 Hysteria / TUIC 可执行程序只作为独立服务端。
**本记录不代表 Qt / QML / NodeStore / DPAPI 产品验收，也没有连接公网节点。**

## 实际调用边界

新增 [native_ffi_host.py](../tools/tests/native_ffi_host.py) 使用 `ctypes.CDLL`
加载显式 `SWIRL_NATIVE_LIBRARY` 指定的库。Windows 同样使用 `cdecl`，与
Rust `extern "C"` 一致，不误用 `WinDLL` 的调用约定。

- 验证 ABI 版本为 **1**。
- 输入、输出声明为 `uint8_t*`；长度为 `ctypes.c_size_t`，返回值为
  `ctypes.c_ssize_t`，并核对两者与指针宽度相同。
- 调用者持有互不重叠且已初始化的输入、输出缓冲区。输入上限和输出
  容量均为 **1 MiB**，输出外附 32 字节 canary；每次调用校验返回长度和
  未写入区域，负返回值不会被误读为无符号长度。
- 每个宿主用真实导出函数验证：空指针、空输入、超长输入、输出容量不足
  均返回 `-1`；恰好 1 MiB 的合法 JSON 加空白仍到达命令解析；非法 UTF-8
  与含未知私密字段的命令返回固定错误，不回显输入。
- 配置只经 stdin 传入；异常输出只含固定诊断码，不打印输入 JSON、密码
  或异常原文。命令逐个串行调用；每个成功创建的句柄在退出前停止。

测试中的很小一层适配只将 `status` 映射为导出命令 `snapshot`，将
`select_node` 映射为 `select`，并为后续命令注入真实 `start` 返回的句柄。
配置直接交给库，返回值保留导出函数的实际 JSON，不制造额外状态或模拟协议。

本地最终六个独立宿主共执行 **143 次 `swirl_core_command`**，其中
**48 次**是上述缓冲区/解析边界探针，**95 次**是运行控制命令。
**17 个 Core 句柄全部经实际 C ABI 启动并停止**；各宿主退出前均为
`active_handles=0`。另有六次 ABI 版本函数调用，未计入命令调用数。

## 原有网络断言完整复用

[test_quic_ffi.py](../tools/tests/test_quic_ffi.py) 继承并运行
[test_quic_core.py](../tools/tests/test_quic_core.py) 的全部六个测试方法。
与 A6 HEAD 对比，六个 `test_*` 方法的 AST 完全一致，没有删除或修改网络断言。
测试没有绕过协议认证，全部应用数据经过真实 Rust Core 监听端口。

| 测试方法 | 实际验证 |
| --- | --- |
| `test_https_application_tls_through_native_core` | Hysteria2、TUIC native / quic UDP 模式对应节点的 HTTP CONNECT 入口、目标 TLS 证书验证、完整 HTTPS 内容及 `close_notify` |
| `test_live_tcp_sessions_node_switch_parallel_streams_and_runtime_restart` | 三种节点配置的真实 TCP、每节点四个并发 64 KiB 回传、旧会话跨节点切换继续收发、新会话、完成收发后关闭、Core 停止再启动 |
| `test_tuic_dns_configuration_change_does_not_reuse_an_old_resolved_endpoint` | 更新 DNS 映射后新连接不能复用旧端点；既有会话保留；恢复配置后新连接成功 |
| `test_tuic_heartbeat_keeps_idle_authenticated_stream_open` | 空闲超过参考服务端两秒期限后继续真实收发，验证 TUIC 心跳 |
| `test_udp_association_fragments_dns_and_control_close` | 三种节点的 123 / 3072 / 4000 字节 UDP 回传、真实 DNS 报文、远端域名解析、关闭 SOCKS5 控制通道后禁止继续转发、新 association 成功 |
| `test_wrong_credentials_never_forward_tcp_or_udp_and_existing_session_survives_selection` | 错误密码的 TCP / UDP 不能到达独立目标；旧已认证 UDP 会话保留；切回有效节点后恢复 TCP |

每个正常结束的 Core 会话均检查 `active=0`。本测试保留原 HY2 测试的有效
UDP 载荷范围和关闭顺序；它没有改变或掩盖官方 HY2 延迟响应半关闭、较大
UDP 回复和 TUIC 历史对端空 UDP 的已记录限制。对应边界仍见
[Hysteria2 互通记录](HYSTERIA2_NATIVE_INTEROP_20261022.md) 和
[TUIC 互通记录](TUIC_NATIVE_INTEROP_20261022.md)。

## 构建与来源证据

实际本地构建命令：

```sh
cargo build --manifest-path core/Cargo.toml -p swirl-api --lib --locked
```

该构建是 **unoptimized dev**，在 4.48 秒内完成；测试耗时包含 fixture、
失败路径等待及控制调用，不是协议阶段耗时或吞吐基准。

| 组件 | 固定身份 |
| --- | --- |
| 本次 `libswirl_api.so` SHA256 | `8e17ab565a89a6e42ceda652df934013db331eca5931965555ff7a861ea95c3a` |
| 工作树基线 Git HEAD | `42fd5782c1d30f32bb4cc2aef21857c52af50dc7`；当时 A7 修改尚未提交，具体修改列表及测试源码哈希已存入 receipt |
| Hysteria 官方发行版 | `app/v2.13.0`，commit `ca8fbd874fd6ca82413948de6dc5924405e103e1` |
| Hysteria Linux 二进制 SHA256 | `907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691` |
| TUIC 官方历史参考服务端 | `tuic-server-1.0.0`，TUIC v5；commit `a299ef02d9f4ab5a0edbf58b9998f41bf768b332` |
| TUIC Linux 二进制 SHA256 | `adb808944ca829857bf408d2ee438a156e8171543dbbed3e94964b66b4135393` |

服务端身份由既有严格版本和 SHA256 检查核验。以下文件均是原输出的未修改
归档，复制前后哈希相同，清单保存校验值：

- [最终 JSON 结果](evidence/x14-a7-ffi/final-results.json)与[测试输出](evidence/x14-a7-ffi/final-tests.log)：6/6 通过，23.192 秒；包含动态库、测试宿主、测试源码、API 源码和 Cargo.lock 哈希，ABI/缓冲区信息及每宿主控制调用、句柄统计。
- [首次结果](evidence/x14-a7-ffi/initial-results.json)与[输出](evidence/x14-a7-ffi/initial-tests.log)：同样 6/6 通过，23.175 秒。随后为其他既有 fixture 借用的 `close_runtime` 保留缺省属性兼容，再运行上述最终结果；没有覆盖首次记录。
- [动态库构建输出](evidence/x14-a7-ffi/library-build.log)。
- [默认宿主回归](evidence/x14-a7-ffi/default-host-regression.log)：未设置 `SWIRL_NATIVE_LIBRARY`，原 HTTP/SOCKS 官方 Xray 导入及 HTTPS 测试方法通过，验证借用的关闭 helper 仍适用于原 Rust 宿主；这是额外回归，不计为 FFI 的六个网络测试。
- [归档 SHA256 清单](evidence/x14-a7-ffi/archive-manifest.json)。

本地记录只能证明上述工作树与二进制。之后提交的 Windows、macOS、Linux
结果应以该提交实际 CI 运行另行验收，不能由此 Linux 结果推断另外两个平台已过。

## 三平台入口与复现

先从当前 checkout 构建库，不能只构建 `--bins`：

```sh
cargo build --manifest-path core/Cargo.toml --release -p swirl-api --lib --locked
python tools/Fetch-NativeProtocolPeers.py --output build/native-peers
```

设置下载工具核验过的 `HY2_SERVER`、`SWIRL_TUIC_SERVER`，并设置：

| 环境变量 | 值 |
| --- | --- |
| `SWIRL_NATIVE_LIBRARY` | Linux：`core/target/release/libswirl_api.so`；macOS：`core/target/release/libswirl_api.dylib`；Windows：`core/target/release/swirl_api.dll`，可用绝对路径 |
| `SWIRL_QUIC_FFI_EVIDENCE` | 此次运行独占且尚不存在的 JSON 路径，例如 `build/quic-ffi/results.json` |

```sh
python tools/tests/test_quic_ffi.py
```

FFI 入口要求显式动态库，缺少时失败，不能退回可执行宿主；缺少官方服务端
同样失败。遇到跳过、测试数不足或失败时入口返回非零。证据路径不得覆盖
`SWIRL_QUIC_CORE_EVIDENCE`，已有 FFI receipt 也不覆盖；下一次使用新路径。
只在 FFI 步骤设置 `SWIRL_NATIVE_LIBRARY`，普通 Core 步骤继续沿用
`SWIRL_TRANSPORT_RUNTIME`，两类证据各自保存。
