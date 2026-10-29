# UI V2 阶段 1：Rust 路由、策略与节点探测审计

审计基线：`4c8c9e076976e5cfb62f103daecdf2afc121eeb3`（Swirl 0.2.3），2026-10-24。只读核对源码，未运行编译或网络测试，未改变系统代理/TUN/DNS，未读取私人订阅内容。以下“已有”仅指代码实现存在，不代表本次或真实用户网络验收通过。

## 首要结论

1. **中国规则与自定义策略目前不能同时启用。** `EngineController::updateRoutingFlags()` 仅在 `customRules.isEmpty()` 时启用 `smartRouting`；添加任何自定义规则都会关闭中国 MRS 分流，改为启用本地私网规则（`src/Swirl.Quick/engine/EngineController.cpp:321-323`）。这是“国内直连 + 专属海外策略 + 默认策略”必须先修的实际断点。
2. **默认出口仍是具体节点。** Rust IR 的 `selected` 可以指向组，但 Qt 配置构造器先在节点库查找 `selectedNodeId`，找不到即“未选择节点”（`src/Swirl.Quick/engine/RustCoreEngine.cpp:230-236`）。还没有不可删除的产品级“默认策略”实体。
3. **自动完整配置导入可覆盖现有网络策略。** 已兼容的完整配置会设置 `m_nativeDocumentRouting=true`、关闭 smart/private routing，并写入源 DNS/rules/groups（`src/Swirl.Quick/engine/EngineController.cpp:769-783`）。新需求要求先确认，现有自动路径不能直接保留为新行为。
4. **TUN、进程匹配尚未提供。** Rust 配置构造器明确拒绝 TUN/网关（`src/Swirl.Quick/engine/RustCoreEngine.cpp:225`）；连接记录进程固定为“未知进程”（同文件 `411`）。不能把应用策略选择器做成可用假功能。

## 已有且应复用的实现

| 能力 | 源码证据 | 边界 |
|---|---|---|
| 真正 Rust 路由与实际出站 | `core/crates/swirl-core/src/lib.rs:573-608`；`core/crates/swirl-routing/src/lib.rs:147-246` | 请求先进入 Rust 路由，再由所选 Node 实际拨号，并记录规则。不是 UI 模拟。 |
| 国内域名/IP 库 | `core/crates/swirl-routing/src/mrs.rs:66-92` | 加载 `cn-domain.mrs`、`cn-ip.mrs`，校验固定 SHA-256，缺失/损坏失败关闭；应复用，不重新发明域名后缀判断。 |
| IPv4/IPv6 规则 | `core/crates/swirl-routing/src/mrs.rs:345-346,947`；`core/crates/swirl-subscription/src/lib.rs:166-177` | IP 数据与规则支持 IPv6；不等于 Windows TUN/真实 IPv6 路径已验收。 |
| DNS 与规则使用相同目标 IP | `core/crates/swirl-core/src/lib.rs:760-810` | 规则匹配 DNS 第一答案并按该 IP 拨号；直连备用地址只能使用相同节点及相同规则，不会把代理故障改成 DIRECT。 |
| 保守的未知域名兜底 | `core/crates/swirl-routing/src/lib.rs:66-75,163,216-246` | 未匹配走 `config.selected`；仅为 CN-IP 分类时不会隐式调用系统 DNS，只有显式 DNS 上游才请求解析。未配置上游且未命中 CN 域名的国内站点可能走默认代理，需如实说明。 |
| 四类策略核心 | `core/crates/swirl-subscription/src/policy.rs:7-28`；`core/crates/swirl-core/src/policy.rs:114-145` | 手动、测速、故障转移、负载均衡已经实现。自动组选健康节点；没有健康成员就报错，不隐式直连。 |
| 有界健康检测 | `core/crates/swirl-subscription/src/policy.rs:49-123,131-169`；`core/crates/swirl-core/src/policy.rs:165-189` | URL、间隔、超时、状态码、TLS 参数经过验证，并发预算为 4；不应重写基础探测层。 |
| 组循环/深度检测 | `core/crates/swirl-subscription/src/policy.rs:131-203`；`src/Swirl.Quick/engine/RustCoreEngine.cpp:118-127` | 全成员图检查，含未选择分支；最大 16 层。 |
| 运行态原子配置 | `core/crates/swirl-core/src/lib.rs:287-327` | 先完成所有可失败验证，再替换不可变 Plan；已建立会话保留自身快照，自动切换仅影响新会话。 |
| 模式切换/失败恢复 | `src/Swirl.Quick/engine/RustCoreEngine.cpp:463-468`；`src/Swirl.Quick/engine/EngineController.cpp:180-185,543-559`；`EngineController.h:132` | 原生 configure 成功才更新 engine status；Controller 保存偏好失败时回到实际模式，运行时 getter 读取 engine status。活动页还需接这个已有接口并明确 pending 状态。 |
| 稳定节点 ID | `src/Swirl.Quick/engine/NodeStore.cpp:596-667`；`ProxyNode.cpp:52,71` | UUID 用于节点引用；更新按语义身份/来源定位保留 ID，对不唯一来源拒绝更新。组仍按名称引用，需增设稳定组 ID。 |
| 真实协议节点测量 | `src/Swirl.Quick/engine/NodeTestService.cpp:12-20,30-88`；`core/crates/swirl-protocol/src/probe.rs:162-257` | 隔离 Rust worker，最多 3 个；执行完整 native outbound、目标 TLS、HEAD、响应头及 2xx 校验。不是 TCP 端口测试。 |

探测指标必须保持准确：`NodeTestService.cpp:102` 的指标为 `http_headers`，结果还包含 `outboundConnectMs` 和 `originTlsMs`（`68`）。当前列表的“延迟”不能称为 RTT，HEAD 成功也不证明所有 App、UDP、大流量或 TLS orderly-close 场景通过。

## 对照 V2 的缺口

### 优先级、专属服务与默认策略

- 当前 Qt 将用户规则先加入，再追加私网规则（`RustCoreEngine.cpp:129-184`），所以本地优先级不是最高。
- Rust 的 smart CN 检查在遇到 MATCH 前、或所有显式规则未命中后才执行（`core/crates/swirl-routing/src/lib.rs:165-220`）。单靠恢复 smartRouting 开关仍不能实现“本地/显式国内直连 → 海外专属 → 中国库 → 其他自定义 → 默认”的分层。
- 核心 `Rule` 只有 matcher/outbound（`core/crates/swirl-subscription/src/lib.rs:183-186`），没有稳定规则 ID、显示名称、启用状态、规则层级或显式优先级。数组顺序是当前优先级。
- 未发现 OpenAI/Claude/Google/YouTube 等专属服务目录及重叠管理。通用 DOMAIN / DOMAIN-SUFFIX 可以执行服务规则，但还缺产品级命名策略、多个匹配项、启停和优先级编辑。
- 重复规则检查仅阻止匹配 JSON 完全相同但出口不同（`RustCoreEngine.cpp:168-172`）；尚不覆盖父子域名、CIDR 包含或跨服务集合冲突。
- 最终 MATCH 可删除，默认节点可以不存在；不能把现有 SWIRL 文本出口当作已完成不可删除的“默认策略”。

### 策略组

- 手动组允许嵌套；**自动组只允许具体节点**（`core/crates/swirl-subscription/src/policy.rs:161-166`；`RustCoreEngine.cpp:102-105`）。需求中的一般嵌套策略组尚未全面实现。
- 负载均衡必须显式 `strategy=round-robin`，不会把外部默认哈希语义偷偷转换（`RustCoreEngine.cpp:71-74`）。Core 为每条会话固定一次选择（`core/crates/swirl-core/src/policy.rs:68-94`），但同一服务的多条新连接可能轮换 IP，缺少按服务/目标的粘性保持。
- 现有 `savePolicyGroup(name,type,members)` 只传名称、类型、成员，新建时写固定检测地址/间隔（`EngineController.cpp:862-875`）；编辑保留隐藏高级字段，但用户不能自由编辑完整探测参数。新建 load-balance 没有写必需的 round-robin strategy，不能视为四类组完整可用的 UI。
- 自动切换条件已有测速容差，未见失败阈值/连续成功次数/冷却时间等显式产品契约；需在设计时确定最小支持范围。

### 模式与可观测性

- global 模式直接跳过 `routingConfiguration`（`RustCoreEngine.cpp:27-28`），所以必要本地规则也不执行；与新需求“全局代理保留必要本地例外”不同。
- direct 模式构造 explicit-direct 节点（`RustCoreEngine.cpp:231`）；该语义确实直连。
- 记录含实际 leaf node 与 matched_rule（`core/crates/swirl-core/src/lib.rs:107-124,595-608`）；Qt `policy=node`、`nodeChain={node}`（`RustCoreEngine.cpp:407-411`），缺少完整组解析链/业务策略 ID。需要保存规则 → 服务策略 → 组 → 实际节点的真实解析链。
- 系统代理请求只带目标/来源地址，Rust matcher 无进程字段（`swirl-subscription/src/lib.rs:156-178`）；Qt 规则类型列表虽含 PROCESS-NAME（`EngineController.cpp:829`），下游 mapper 拒绝它。前端应明确标为不支持，或者在独立 Windows adapter 补足可信进程关联后才启用。

## 阶段 2 应固定的契约

1. 独立持久化 `DefaultPolicy`、服务策略及稳定 `groupId/ruleId`；迁移旧 UUID 节点引用，保留当前已有用户规则次序，不自动丢弃。
2. Rust 编译明确的五层规则计划；中国库与服务规则共存；global 保留明确列出的本地例外，direct 全部走直连。
3. 自动订阅更新只更新来源节点；完整网络配置采用可审阅的显式导入事务，确认前不覆盖现有配置。
4. Qt 先提交候选配置，Rust 验证/应用并返回 generation；成功后显示实际状态，失败保留旧计划和明确错误。配置态、pending、运行态分别表示。
5. 保留完整协议 HEAD 测量及错误分阶段信息；新增测试针对新分层规则、策略出口、组循环/粘性、配置失败回滚、来源删除引用失效处理。
6. 不把 TUN 和进程规则列为当前可用能力。需要另设可测量的 Windows 平台实现/验收阶段，系统代理不能等同全部系统流量。

## 本次验证边界

只读静态审计，没有运行测试，也没有复用旧测试作为新提交通过证明。现有测试源码包括 `core/crates/swirl-core/tests/china_rules.rs`（规则资产失败关闭）、`core/crates/swirl-core/src/route_tests.rs`（DNS 同地址分流及禁止隐式直连回退）、`core/crates/swirl-core/src/probe_tests.rs`（切换/停机使探测失效）、`src/Swirl.Quick/tests/RustCoreTests.cpp`（模式、组、路由回归）。下一阶段应按改动选取和增补相关测试。
