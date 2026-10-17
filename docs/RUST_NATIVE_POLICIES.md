# Rust 原生策略组与健康探测

更新：2026-10-17。本阶段在 `work/core-completion-20261017@0bf2666` 上接续已有候选代码，
将策略 IR、原生健康请求、运行时调度、路由和会话快照实际接入 crate 模块树。
本文的本地测试记录产生于本阶段提交之前；最终提交、推送和远端 CI 身份以
[接续入口](CONTINUE_DEVELOPMENT.md) 及[本轮阶段验收](RUST_POLICY_VALIDATION_20261017.md)为准，不预先记录远端通过。

## 可执行范围

Rust IR/API 已执行手动嵌套组、`url_test`、`fallback` 和按新会话轮询的 `load_balance`。
探测由 `swirl-protocol::health_probe` 经指定成员的原生出站建立连接，发送独立 HTTP/HTTPS 请求；
不运行 Mihomo 或其他完整外部代理内核。DNS、代理握手、TLS 和传输复用现有 Rust 模块。
TLS 仍使用 rustls/WebPKI 等成熟依赖，Swirl 不自行实现密码算法。

现有 Qt 组编辑器到 Rust 的转换仍只接受原来的有限手动组，不支持自动组或嵌套组输入。
本阶段的自动组入口是 typed IR 与本地控制 API，没有增加或重排 QML 控件。
现有 Qt 布局、动画及存储的组配置保持原有边界，不能将 Rust API 测试当作 Qt 自动组产品验收。
具体 Qt 路由子集见 [原生路由](RUST_NATIVE_ROUTING.md)。

## Schema 1 的增量字段

旧的 schema 1 手动选择配置继续有效。组字段如下，未知字段和错误类型均拒绝。

| 字段 | 手动组 | 自动组 |
|---|---|---|
| `id` | 1–64 字节 ASCII 字母、数字、`-`、`_`；与所有节点和组 ID 不冲突 | 相同 |
| `members` | 1–512 个不重复的已声明节点或组 ID | 1–64 个不重复的具体节点 ID；不能包含组或 REJECT 节点 |
| `selected` | 必须明确指向本组成员 | 省略或空字符串；非空返回 `AutomaticPolicySelection` |
| `strategy` | 省略或 `manual` | `url_test`、`fallback`、`load_balance`，使用下划线 |
| `probe` | 省略或 `null`，有探测对象则拒绝 | 必须显式提供已校验的探测对象 |

`Config.selected`、规则的 `outbound` 以及手动组的 `selected` 都可以引用合法组。
验证遍历整个成员图，包括尚未选中的成员；循环、缺失成员和超过 16 层组路径均拒绝。
最多 128 个组，其中自动组最多 32 个，所有自动组的成员总数最多 512。
这些限制与现有节点数、规则数、输入大小限制同时生效。

### 探测字段

| 字段 | 默认值 | 执行与限制 |
|---|---|---|
| `url` | 无，必须指定 | `http` 或 `https` URL，最多 2048 字节；ASCII 可打印字符；不接受 URL 用户名/密码、片段或反斜杠 |
| `interval_ms` | 300000 | 1000–3600000；每个成员完成一次探测后，至少等待此间隔再安排下一次 |
| `timeout_ms` | 5000 | 100–30000，且不大于 `interval_ms`；排队准入和本次网络执行共用该期限 |
| `expected_status` | 204 | 200–299 中的一个精确状态码；并非任意 2xx 都算成功 |
| `tolerance_ms` | 0 | 0–10000；仅 `url_test` 可为非零，其他策略非零则拒绝 |
| `tls` | HTTPS 自动使用 URL 主机名、`http/1.1` 和现有信任根 | 仅 HTTPS 可配置；`server_name` 必须与 URL 主机名大小写无关地相同，ALPN 只能为空或 `["http/1.1"]` |

`tls.ca_der_base64` 可提供现有 TLS 接口支持的额外 DER 信任锚，长度上限为 65536；
实际证书解析、信任链和主机名验证仍在 TLS 握手中执行。未知的跳过验证字段直接拒绝。
没有“探测专用关闭证书验证”设置。代理节点自身的 TLS 与 HTTPS 源站 TLS 分开验证。

例如，下列合成配置把全局选择交给手动外层组，默认再指向自动 fallback 组。
三个端口仅表示自建测试对端；需要真实启动相应对端才可能变为健康。

```json
{
  "schema": 1,
  "listen": "127.0.0.1:0",
  "selected": "outer",
  "nodes": [
    {
      "id": "a",
      "outbound": {
        "type": "http_connect",
        "host": "127.0.0.1",
        "port": 18111,
        "auth": null
      }
    },
    {
      "id": "b",
      "outbound": {
        "type": "http_connect",
        "host": "127.0.0.1",
        "port": 18112,
        "auth": null
      }
    }
  ],
  "selectors": [
    {
      "id": "auto",
      "members": ["a", "b"],
      "strategy": "fallback",
      "probe": {
        "url": "http://127.0.0.1:18080/health",
        "interval_ms": 300000,
        "timeout_ms": 5000,
        "expected_status": 204
      }
    },
    {
      "id": "outer",
      "members": ["auto", "a"],
      "selected": "auto"
    }
  ]
}
```

## 选择规则与失败行为

| 策略 | 新会话如何选择 |
|---|---|
| `manual` | 沿明确的 `selected` 解析到节点，或进入另一个已验证组；本组不发健康请求 |
| `fallback` | 从声明的成员顺序选择第一个当前健康且未过期的成员；不会因为后面的成员更快而改变优先级 |
| `url_test` | 选择测得延迟最低的健康成员；若此前首选仍健康，且延迟不超过最快值加 `tolerance_ms`，则保留此前首选 |
| `load_balance` | 在会话所捕获的健康成员集合中按声明顺序轮询；仅实际使用这个组的新 TCP 会话或 UDP 关联消费一次轮次 |

初始化时没有节点被假定为健康。一个自动组只有收到成功探测后才有可用成员；
若某个新会话捕获的健康集合为空，返回 `NoHealthyPolicyMember`。
TCP 请求得到失败响应，UDP 数据报按现有丢弃计数处理，不等候探测完成后重放原请求。
不要求所有成员都完成首轮探测后才使用已成功的成员。

一次成功探测的健康有效期为：

```text
2 × interval_ms + timeout_ms
```

时间从该成员完成探测、写入健康记录时开始计算。超过有效期后，新捕获的会话视其为不健康。
明确失败的探测立即将该成员标为不健康，不继续借用此前成功状态。
健康过期由读取策略视图和报告时的时钟判断；不依赖额外无限增长的定时器集合。

自动选择在应用连接发起之前完成。选中的成员连接失败、消费了部分请求后断开、TLS 失败或不支持该 UDP
路径时，不改走其他成员、不隐式直连，也不重放应用字节。后续成功或失败的健康探测只影响新的会话。
`fallback` 是根据独立健康状态选择新会话出口，不是对已经发送的应用请求进行自动重试。

## 配置、会话与任务生命周期

核心当前 `Plan` 持有配置、DNS resolver 和 `PolicyRuntime`。接受 TCP 连接时创建独立 `SessionPlan`，
包含当时配置、resolver 和 `PolicyView`。健康成员集合在此时固定；轮询组仅在该会话首次实际使用时
取得并记住成员。即使应用稍后才完成握手，仍使用接受连接时的视图。

这里的冻结时刻是监听器 `accept`，不是第一次路由或第一次数据报到达时。
因此，初始化时已经被接受、当时没有健康成员的预连接，即使稍后首轮探测成功，仍会按自己的空视图失败。
反过来，一个已接受的连接当时捕获了健康成员，若直到较晚才开始路由，仍可使用该成员；
当前实时报告可能已把同一成员标为过期。健康过期门禁约束新捕获的视图，不会重新检查或改写已有视图。

对于 SOCKS5 UDP，控制连接拥有整个关联，同一关联的并行数据报准备任务共享同一个 `PolicyView`。
每个被使用的自动组只选择并固定一次成员，后续健康变化或配置更换不会把该关联改到新出口。
已有 UDP 目标地址、回复来源校验和会话回收边界继续生效。

控制接口的增量行为如下：

- `select` 可以选择一个已声明的具体节点或组；`select_group` 只允许手动组，成员可以是合法嵌套组。
- `select` 和 `select_group` 在现有配置写锁内验证和原子替换。它们共用原来的 resolver、健康运行时、
  已有探测任务和轮询游标，不重新开始全部探测，不清空健康记录。
- 完整 `configure` 先验证全部配置、监听约束和 DNS 配置；失败保留原代次、健康与任务。
  全部验证成功后创建新代健康运行时并取消旧代探测。新代健康和轮询游标从空状态开始。
- 旧 TCP/UDP 会话不持有探测运行时，只保留配置、resolver 和策略视图。因此旧会话可以继续传输，
  而被替换的探测 worker 不会因旧会话仍存活而继续周期运行。
- `stop` 取消策略 worker 和监听/会话任务，然后结束运行时；停止后的核心不接受重新配置或选择。
  API `stop` 还会移除该 handle，后续 handle 命令按既有语义返回 `UnknownHandle`。

`select_group` 请求示例：

```json
{"op":"select_group","handle":1,"id":"outer","member":"a"}
```

对 `auto` 组发送同类请求会返回 `AutomaticPolicySelection`，不会偷偷把自动策略改为手动策略。

## 健康请求、调度与资源边界

每个明确配置的自动组都会安排独立成员探测，包括当前未被路由选中的组。
健康请求直接使用该具体成员的原生出站，避免把探测再递归交给组路由。没有为未配置 probe 的手动组
或普通节点隐式生成探测 URL。

探测请求使用 HTTP/1.1 GET、`Connection: close`、`User-Agent: Swirl-Core-Health/1`。
成功需要收到完整、语法有效且状态码精确符合配置的最终响应头；TCP 建连或 TLS 握手成功本身不够。
响应头总量最多 8192 字节，每段最多 64 个字段，最多接受 8 个非 101 的临时 1xx 响应。
临时响应不会重置总字节或总时间预算，101、重定向、错误状态、截断和无效响应都不能证明健康。
重定向目标不会被跟随，不注入 Cookie 或源站 Authorization。

`latency_ms` 从原生探测执行开始计时，到已验证的最终响应头到达为止，包括必要 DNS、代理握手、
源站 TLS 和请求/响应时间；不把等待探测并发许可的时间加入该网络延迟。
请求的写方向关闭仍须在同一总期限内完成，否则本次探测按关闭失败处理。
不进行无界响应体下载，也不等待服务端永久保持的连接结束。

调度执行限制为每核心最多 4 个并行探测，所有配置代次共享同一个 semaphore。
旧代取消与新代启动短暂重叠时，仍共用这 4 个网络执行许可。
每次探测的许可准入、DNS、出站握手、TLS、请求、响应及关闭共用一个 `timeout_ms` 截止时间；
排队等待结束后不会重新获得一整段超时预算。

调度表最多 512 个成员任务，最多 4 个已安排的异步任务。相同初始期限的成员按组交错安排，
随后优先处理尚未运行且最早到期的成员，避免第一个大组整批排空后才看其他组。
同一成员不会并发探测；一次完成后再计算下一次间隔，错过的周期不会堆积成补跑队列。
当节点很多或网络很慢时，实际检查时间可能晚于目标期限；健康会按上述规则过期，
不能据此承诺所有节点都精确按 interval 运行。

## Snapshot 与统计含义

`snapshot.status.policies` 按组 ID 提供报告。以下为结构示例，不是实际测量值：

```json
{
  "auto": {
    "strategy": "fallback",
    "selected": "a",
    "checks": 2,
    "members": [
      {"node":"a","healthy":true,"latency_ms":25,"checked_age_ms":80,"error":""},
      {"node":"b","healthy":false,"latency_ms":null,"checked_age_ms":50,"error":"PolicyProbeTimeout"}
    ]
  }
}
```

- `checks` 是该组本代已完成的成员探测总数，不是应用请求数。
- 手动组的 `selected` 是其直接选择的成员 ID，可能是下一层组；`checks=0`、`members=[]`。
- `url_test` / `fallback` 的 `selected` 是当前健康状态下的新会话首选，无可用成员时为 `null`。
- `load_balance` 的 `selected` 是当前游标下的下一候选预览；读取 snapshot 不消费轮次，
  它不是“最后一次流量使用的成员”。具体会话的 `connections[].node` 仍是实际固定的节点。
- `checked_age_ms` 为最近完成检查距今的时间；未检查为 `null`。过期的成功记录可以保留旧延迟，
  但 `healthy=false` 且 `error=PolicyHealthExpired`，不能仅凭延迟非空判断可用。
- 原有 `selectors` 映射继续存在，手动组显示原选择，自动组显示报告中的选择；无健康成员时为空字符串。

成员未检查时错误为 `PolicyNotChecked`，其余错误使用固定脱敏代码。
探测自身不增加应用会话的 `accepted`、`failed`、流量或连接记录；应用走自动组之后的计数仍由原有会话层记录。
健康报告不包含 probe URL、密码、认证头、证书内容或私有订阅。

## 源码与本地测试证据

| 源码 | 本阶段实际职责 |
|---|---|
| `core/crates/swirl-subscription/src/policy.rs`、`lib.rs` | 探测和策略字段、成员图验证、预算和兼容 schema 1 |
| `core/crates/swirl-protocol/src/probe.rs` | 原生 HTTP/HTTPS 探测与完整最终响应头校验 |
| `core/crates/swirl-transport/src/lib.rs` | 严格 TLS 封装，允许在已有原生代理流上再建立源站 TLS |
| `core/crates/swirl-routing/src/lib.rs` | 有界嵌套组解析和会话自动选择回调；保持原有规则顺序及 DNS 地址钉住 |
| `core/crates/swirl-core/src/policy.rs`、`lib.rs` | 调度、健康/轮询、原子更新、会话视图、统计和取消 |
| `core/crates/swirl-core/tests/network.rs` | 实际回环 TCP/UDP 生命周期与自动组替换回归 |
| `tools/tests/test_policy_groups.py` | 独立 Python HTTP、HTTPS、认证 HTTP CONNECT、双层 TLS 和可区分 SS UDP 对端 |

已在本地 Linux 工作区执行并通过：

- `cargo check --workspace --locked --offline`。
- `cargo clippy --workspace --all-targets --locked --offline -- -D warnings`。
- 本阶段策略实现涉及的六个 Rust 源码/测试文件的格式检查、精确 diff 空白检查。
- `cargo test --locked --offline -p swirl-subscription -p swirl-routing`：该次工作区快照为
  subscription 31 项、routing 4 项全部通过；其中包含本阶段已接入的候选测试及并行 SOCKS4 转换改动。
- `cargo test --locked --offline -p swirl-core`：5 项策略单测与 11 项真实 TCP/UDP 网络测试通过，
  网络套件用时 2.35 秒。新增测试验证手动选择保留健康、无效配置回滚、完整配置取消旧探测、
  老 TCP 继续传输、stop 后超过一次周期无新探测，以及组替换前建立的 UDP 关联继续使用旧 DIRECT 配置，
  新关联执行 REJECT。该 Rust UDP 测试中的两个成员都为 DIRECT，不能单独证明不同 SS UDP 对端之间的
  成员固定；可区分的独立 UDP 对端验证应另列实际执行证据。
- 最终完整 workspace：fmt/check/clippy、83 项 Rust 测试及 release 构建全部通过。
- 独立 Python 策略套件最终 13/13 通过，5.214 秒；包括源站 TLS 嵌套于认证 TLS 代理的双层连接。
- 新增两个可区分 SS UDP 出口的独立测试，分别使用 AES-128-GCM、ChaCha20-Poly1305。
  健康切换后旧关联保留 A、新关联走 B；完整配置删除节点/组后旧 A/B 关联仍固定原出口，
  新关联丢弃。A 四次、B 两次共六次实际 UDP 往返，为上述 DIRECT 测试补足不同出口证据。

首次受限容器的回环 socket 权限不足；以上网络测试在本会话已授权、自动审核通过的临时本地 TCP/UDP
测试权限下完成，不修改系统代理、DNS、路由或防火墙。无私有订阅、真实供应商节点或十分钟更新窗口参与。
本阶段的源码/App 提交及具体远端运行记录见[本轮阶段验收](RUST_POLICY_VALIDATION_20261017.md)，
已有旧提交的 Actions 成功不能证明本阶段通过。

## 尚未完成

自动组并不增加某一协议自身的 UDP 能力。目前 UDP 仍仅限已实现的 DIRECT 和 SS AEAD 路径；
选择到不支持 UDP 的健康 TCP 节点时仍丢弃并计数，不改选 DIRECT。HTTP/HTTPS 健康成功也不能证明 UDP 可用。

Qt 自动组/嵌套组映射、通用订阅配置的策略组完整执行、DNS 分流与域名 bootstrap、智能 MRS/进程规则、
更多协议及传输、TUN/平台接管、私有节点验收和长期性能测试仍需独立推进。
默认兼容构建依然保留现有外部内核，Rust 专用模式仍由 `SWIRL_USE_RUST_CORE=ON` 显式选择。
本阶段完成的是一个原生策略能力阶段，不能称为全自研迁移完成版。
