# sing-box 传输导入语义与拒绝执行边界（2026-10-19）

## 范围与真实缺口

本阶段接续 `4d73f6574bf9884dc4e173b58708ae543b2303bd` 的 REALITY/uTLS/Vision 导入保护，修复 Qt sing-box 导入中的另一条静默参数丢失路径。此前 `transport` 的错误 JSON 类型、缺失或错误的 `type` 可被 `toObject()` / `toString()` 转成空值，继而成为普通 TCP；WebSocket 的错误 `path` 类型可变成默认路径；共享字段白名单还会无声丢弃 WebSocket 上的 `service_name`。

修改仅涉及以下产品与测试文件；没有增加协议依赖、修改字体或 UI，也没有接通 REALITY/Vision：

- `src/Swirl.Quick/engine/SubscriptionNormalizer.cpp`：检查实际传输分支、参数类型和 uint32 范围，保留原始配置并标记未映射字段。
- `src/Swirl.Quick/tests/ImportTests.cpp`：加入传输反例、普通 WS 与可空字段正例，并扩充既有持久化拒绝输入。
- `src/Swirl.Quick/tests/RustCoreTests.cpp`：核对 TCP/TLS/WS/WSS 配置映射；未映射传输字段必须在启动前以 `InvalidOptions` 拒绝。
- `src/Swirl.Quick/CMakeLists.txt`：将新增导入测试加入既有 `swirl-import-boundaries` 菜单，供原生与兼容模式 CTest 使用。

## 协议语义与兼容边界

依据 sing-box 官方传输文档和固定版本源码审查，而不是将 Qt 默认转换当成协议定义：

| 输入 | 本阶段处理 |
| --- | --- |
| 未提供 `transport`，或 `transport: null` | 保持普通 TCP 的“未指定额外传输”语义。原始 null 保留。 |
| 非空传输为布尔、数字、字符串、数组 | 拒绝整次导入，不产生可执行的部分节点。 |
| 传输对象缺少 `type`，或 `type` 为 null、错误类型、未知值、`tcp`、`h2` | 明确拒绝。sing-box 的传输联合类型为 `http/ws/quic/grpc/httpupgrade`，没有 `tcp` 分支。 |
| 已映射的可选 WS 路径、请求头、早期数据字段或 gRPC 服务名为 null | 按上游新建配置的零值/缺省语义归一化，并保留原始 JSON。null 路径得到 `/`，null 请求头及早期数据字段视为未设置。 |
| 请求头值为 null | 上游 `Listable` 无条目，不发送该头。字符串数组中的 null 则成为空字符串条目；数组本身仍保留。 |
| 非 null 的错误字符串/请求头类型，或早期数据上限为负数、分数、超过 uint32 | 明确拒绝；不使用 Qt 默认值继续执行。 |
| 正常 WS 路径、大小写不同的 Host、字符串数组、显式早期数据参数 | 按现有映射保留；未知或当前 Rust 无法执行的选项仍拒绝启动。 |
| WS 上的 `service_name`、gRPC 上的 WS 参数、未知扩展 | 保留原始字段并产生转换问题，阻止静默忽略后的执行。 |

复审修正了一个初始假设：**可选字段的 null 不能笼统当作错误类型**。上游 `Transport` 是可空指针，Go 解码器及 `Listable` 有明确的 null 语义。最终测试把这些情况列为正例；缺失/null/未知的必需 `type` 仍是反例。该修正没有改动前一阶段的 TLS/REALITY 安全代码。

HTTP、QUIC、gRPC、HTTPUpgrade 本阶段没有新增可执行实现。普通 WS 之外的头部与早期数据即使可以保留，也不代表 Rust 已能执行。没有把解析成功描述为真实连接成功。

## 精确本地证据

测试环境为 Ubuntu 24.04、GCC 13.3.0、官方 Qt 6.10.3 的 Core/Network/Test 组件。Qt SDK 自身的构建标识为 GCC 11.4.1。隔离 harness 从仓库测试文件逐字提取下列五个测试函数，编译实际 `NodeImporter`、`SubscriptionNormalizer`、`ProxyNode`、`SwirlProtocolRegistry` 和 `RustCoreEngine`，没有改写被测生产逻辑：

1. `uriRealityRequiresAnExplicitSecurityLayerAndCredential`
2. `singBoxTlsTypesAndFingerprintIntentArePreserved`
3. `singBoxTransportShapesAndFieldsCannotDowngrade`
4. `importedRealityVisionAndDefaultUtlsCannotStartAsOrdinaryTls`
5. `singBoxTransportMapsExactlyAndRejectsUnmappedFieldsBeforeStart`

以保留的 stage1 四文件快照为基线，只切换 normalizer 编译输入，执行同一份最终回归函数：

| 编译输入 | 实质测试结果 | Qt XML 总数（含初始化/清理） | 耗时 |
| --- | --- | --- | --- |
| stage1 normalizer | 3 通过、2 失败、0 跳过 | 5 通过、2 失败 | 42.5129 ms |
| 本阶段最终 normalizer | 5 通过、0 失败、0 跳过 | 7 通过、0 失败 | 57.5337 ms |

基线的两个失败分别实证：`transport: false` 被导入为默认 TCP，以及 WS `service_name` 被丢弃后仍可生成原生执行配置。修复后，原始/Base64 输入、合法 null、准确的地址/端口/UUID/SNI/ALPN/WS 路径/Host 映射、原始字段保留与拒绝前不改写输出均通过。拒绝启动测试使用独立回环监听器，观察到 0 次连接；同时断言错误是 `InvalidOptions`，因此不把缺少 Rust 动态库误当作安全拒绝成功。`git diff --check` 通过。

本地 XML 位于会话隔离目录 `qt-gap-harness`，不是已上传的 Actions 产物。以下 SHA-256 固定被测源码和本地结果：

```text
stage1 SubscriptionNormalizer.cpp
9836023dfb1873cac4848b27aa524f3ba4babb7a72d7a88e1f68655f42eb7523
fixed SubscriptionNormalizer.cpp
fe24e6548dc4ee8d0fba1b8b44e5d07e28fd1b3bb13af44514ce05344e921d46
fixed ImportTests.cpp
f86be6c9bdb08b63c805a02130c0e3621bedf8e30c1611829e6a949f294a58ea
fixed RustCoreTests.cpp
c055b374b0b590c1c90be87ad52c4de3f251722b218165eaa046a02bd0fc109c
fixed CMakeLists.txt
76a5639a225607ad519d11c4376a40058ce54d4f2dbdf3a58384ce839fe6b0d9
transport-baseline.xml
3d13538a3c92cf015afdb083c54f75d1959c88d61caa8c77d057bedda3b611ab
transport-fixed.xml
a2c1b84e4cd9a5fafac01558d5885d6d16c6550288859b1beb4ebde702c42dbb
```

本阶段增加的持久化坏输入已纳入现有测试函数，尚未在上述最小 harness 中运行。完整 Windows 原生/兼容 Qt CTest、Rust 三平台、独立转发对端和完整应用编译须以包含本阶段的精确提交及 Actions 记录另行核验；不能借用 stage1 或历史提交的结果。当前本地证据不包含新协议联网、公网节点、私有提供商整份订阅、Windows 物理显示设备验收。

## 上游依据、许可证与固定验收

- [sing-box 官方 V2Ray Transport 文档](https://sing-box.sagernet.org/configuration/shared/v2ray-transport/)：传输类型、WS 参数与省略 TCP 传输。
- [固定版本传输定义](https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/option/v2ray_transport.go)及 [VLESS 可选传输指针](https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/option/vless.go)：联合类型、可选字段和 uint32。
- [固定版本 WS 客户端](https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/transport/v2raywebsocket/client.go)：缺省路径、请求头和早期数据语义。
- [该版本依赖的 sing 解码器](https://github.com/SagerNet/sing/blob/6f21f2425a95/common/json/internal/contextjson/decode.go)、[Listable](https://github.com/SagerNet/sing/blob/6f21f2425a95/common/json/badoption/listable.go)和 [HTTPHeader](https://github.com/SagerNet/sing/blob/6f21f2425a95/common/json/badoption/http.go)：null 指针、零值与头部条目语义。
- 已核对 [sing-box 许可证](https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/LICENSE)和 [sing 许可证](https://github.com/SagerNet/sing/blob/6f21f2425a95/LICENSE)，均为 GPL-3.0-or-later；这里只参考行为，没有复制实现或引入其依赖。

固定验收仍为 **79 项、6 项已验收、权重 10.83%**。本次修复不删除、拆分或缩小验收项，不改变 REALITY/Vision 的可执行验收状态；没有更新验收 JSON 来提高比例。
