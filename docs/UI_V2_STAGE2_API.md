# 阶段 2：Qt / Rust 配置事务、持久化与迁移契约草案

基线 `856f11e12a20f992620597fbbddb6eab7d32929d`。本文是用户已确认架构的待实施契约；未修改产品源码，未证明路由或安装包通过。正文 camelCase 是 Qt 名义属性；磁盘/控制协议统一 snake_case，与主架构和示例一致。

## 1. 已核实的实现与最小变更

- 当前产品是 **Qt 进程内 Rust DLL**，`ThreadedEngine.h:11-31,68` 经工作线程排队，不是独立核心进程。跨进程传输仅是将来适配器边界，本阶段不新增服务进程、RPC 框架或数据库。
- `NodeStore.cpp:141-255,267-344,677-724` 已提供 DPAPI、32 MiB 上限、QSaveFile 原子替换、不可变 ImportPlan、版本检查和异步写租约；继续由 NodeStore 独占配置磁盘写入。
- 当前权威分裂：模式写 `QSettings`（`EngineController.cpp:221-223,543-559`），出口选择写 `.selected`（`NodeStore.cpp:400-414`），网络配置在加密快照。V2 把影响流量的模式/默认出口/手动组选择全部纳入同一配置快照；QSettings 仅保留显示、主题等界面偏好。
- `swirl-api/src/lib.rs:28-32,90-96` 的 configure 仅回 `{ok:true}`；Core snapshot 有 generation 但无配置 revision/digest/mode。Qt 成功后自行赋值 mode（`RustCoreEngine.cpp:462-468`），不能作为 V2 的完整应用回执。
- 复用 `Core` 的 `Arc<Plan>`、短期 `RwLock` 和已有会话快照（`swirl-core/src/lib.rs:142-167,287-326`）；拆出纯 prepare。`PolicyRuntime::reconfigured` 会启动探测任务（`policy.rs:192-225`），所以不能直接拿它充当无副作用 prepare。

## 2. 权威与状态字段

NodeStore 是**唯一持久配置权威**；Rust 是**当前运行计划权威**；EngineController 只协调事务，QML 只读取状态和提交意图。Rust 不写 NodeStore 文件；Qt 不以本地选择值冒充实际出口。

| 字段 | 来源与含义 |
|---|---|
| `storeId` | 首次 V2 迁移生成的 UUID；防止其他配置库相同 revision 混淆。 |
| `savedRevision` | 已完成最终 QSaveFile 提交的配置版本；已提交版本不回写旧值。未提交候选的回滚回到 base savedRevision，运行 generation 仍递增。 |
| `requestedRevision` | 当前受理候选的版本；候选取消/失败可以留下空号。内存单调分配，durable intent 保存 `lastIssuedRevision` 高水位，禁止复用已落盘版本。 |
| `appliedRevision` | Rust 当前计划声明的配置版本；停止时为 null，不能拿历史最后应用版本代替。 |
| `engineEpoch` / `generation` | 每个新 handle 生命周期的 epoch；该运行实例每次计划交换递增 generation，包括恢复旧内容。所有回复与采样都携带两者。 |
| `requestId` / `planDigest` | 不可重复的操作 UUID；Rust 对严格解析后的规范计划字节计算 SHA-256，Qt 原样保存回执，不自行实现另一套 canonicalization。 |
| `transactionState` | `idle/preparing/persisting_intent/activating/committing/reconciling/failed`；另有 `engineState`。保存态、请求态、应用态不得混成一个 bool。 |

epoch、revision、generation 在 JSON/QML 边界全部使用有界十进制字符串，在 C++/Rust 内部用 checked u64；不得经 JavaScript Number 转换。错误响应包含固定 `code`、`phase`、安全字段路径与上述身份，不回传凭据或原始配置。摘要只留本机，不放公共日志/诊断导出。

## 3. 单文件 intent 与运行提交

扩展现有加密快照为 V2 envelope：`schema:2`、`storeId`、`lastIssuedRevision`、`committed`、可选的**一个** `pending`。pending 含 requestId、baseRevision、candidateRevision、候选值、Rust 回执和操作种类；committed 在最终提交前仍是旧值。源文档继续按摘要去重共享；全 envelope 仍受 32 MiB 上限约束，超限拒绝，不默默提高上限。外层标记使用 `SWIRLNODE2`，旧程序必须拒绝读取而非忽略新字段后覆盖。

一次在线修改的唯一提交顺序：

1. Controller 在 UI 线程捕获 immutable candidate + baseRevision，设置 requested/busy；排至既有工作线程。Rust 严格解析、检查能力、引用、循环、上界及规则资产，返回 prepared token/digest；不拨号、不启动健康检查、不改 listener/系统设置。
2. NodeStore 核对基线并异步 QSaveFile 写 `committed=旧 + pending=候选`。未成功不得触碰运行计划。写入期间维持旧计划和现有连接；所有配置写者共享同一写租约。
3. 关闭短期 **new-request admission gate**，再以 `(engineEpoch, expectedGeneration, baseAppliedRevision, requestId, preparedToken)` CAS 激活候选。gate 关闭与取得新请求 SessionPlan 用同一短期同步边界；不得持有 Plan 锁等待磁盘或 Qt 回调。
4. NodeStore 最终 QSaveFile 把 candidate 提升为 committed 并清 pending。成功后 Rust `finish` 核对完整回执并释放 gate/启动候选健康检查；Controller 收到 Rust snapshot 的实际 revision/digest/mode 后才显示“已生效”。
5. 最终写明确失败：gate 仍关闭；Rust 恢复旧内容为新的 generation，NodeStore 清除 pending（保留 lastIssued 高水位），核对旧内容 receipt 后释放 gate。无法确认恢复时持续拒绝新流量，显示需恢复；不擅自切 DIRECT、不自动释放系统代理来掩盖失败。

gate 覆盖新逻辑流的路由/解析/拨号，包括 HTTP 复用连接上的新请求、UDP 新目的地、候选探测和新池连接，不能只暂停 accept。普通修改下已取得旧 SessionPlan 的连接保留旧快照；回执说明“新请求已应用”，不声称既有隧道换了出口。

gate 初始预算 2 秒、等待新流最多 64 个，二者是待实施测试的明确上界。超量立即拒绝；超过预算终止等待中的新流并转 reconciling。**若最终磁盘写仍在执行，不得因超时盲回滚**：写可能随后成功。保持 admission 关闭，等待写结果/核对磁盘 committed receipt 后决定 finish 或 rollback；UI 显示“结果待确认”，不提前报普通失败。没有无限队列或持锁等待。

离线编辑只需 Rust 纯验证 + 一次最终快照提交，appliedRevision=null，显示“已保存，下次连接应用”。首次启动必须从当前 committed 编译并返回相同 revision/digest 的 start receipt。listener、TUN、接管范围变更不混入热配置事务：返回 `RequiresRestart`/`UnsupportedCapability`，沿独立生命周期处理。

## 4. 失败、崩溃、关停与重复请求

- 当前 DLL 与 Qt 同进程：进程崩溃不会留下独立运行的新计划。重启先加 NodeStore 路径级 `QLockFile` 单写锁，核验 committed，再处理 pending，完成前禁止自动连接；不猜旧内存中的 appliedRevision。
- 普通 pending 且 committed 仍为 base：候选未提交，清 pending 后保留旧配置；若最终 committed 已记录 requestId/candidateRevision/digest，则识别为成功，禁止因 UI ACK 丢失回滚。
- 撤销来源/删除节点的 pending 不能自动恢复旧凭据并自连：离线重新验证并完成该撤销，失败则保持断开、显示待恢复；用户明确取消删除才可清除此意图。receipt 不包含可复用导入授权。
- 同一 requestId 的重试只查询/返回当前阶段，不再次 activate；内容或 digest 不一致返回 `RequestIdentityMismatch`。新 epoch 下旧 handle/preparedToken/回执一律无效。最多一个 prepared plan、一个 pending、一个最近终态 receipt；不构造无界历史缓存。
- 正常关闭：取消尚未写 intent 的候选；已有事务先判定最终磁盘结果并关闭/回收 gate、探测和句柄。不得强杀工作线程或把忽略 Qt 旧回调当成撤销已发生的磁盘写。强制退出由上述启动恢复路径处理。
- 将来若核心独立进程存活，连接重建必须先读取其 `(epoch,revision,digest,requestId,state)` 与磁盘比对；未协调前继续拒绝新流。此语义不要求本阶段增加 IPC。

## 5. 模式快切与忙碌

模式菜单保持实际 appliedMode，另显示 requestedMode/进度；点击并不立即改已选对勾。Controller 立即置 routingBusy，不能等工作线程第一次采样。保存/切换失败恢复实际状态和原因。

首版采用 **单一在途 mutation，无 latest-wins 队列**：模式 pending 时禁重复提交，但列表浏览、键盘焦点和动画继续响应。API 对不同 requestId 的并发 mutation 返回 Busy；相同 requestId 的查询/重试返回既有阶段或 receipt。每次回调按 requestId/epoch 匹配，不以到达顺序覆盖新请求。结构编辑/导入/删除同样使用该写租约，旧基线返回 RevisionConflict；不隐式 rebase 用户网络编辑。用户在完成后再次选择才生成新事务，避免连点触发多个临时实际出口。停止动作优先并按第 4 节收敛在途事务；动画的快速反向与配置提交状态独立。

## 6. 订阅与一次性完整配置确认

- 所有自动/定时刷新固定为 nodes-only：自动识别格式，复用严格节点安全验证、prepareImport 稳定 UUID、加密原文和事务保存。foreign DNS/rules/groups 只生成可查看候选，不写现有策略；旧 `importScope=full-profile` 迁移为安全刷新语义，无永久授权位。
- 下载发起捕获 sourceId、source-definition revision 和目录 baseRevision；响应回来发现来源已删除/URL或选项变化即丢弃。其他配置变动则在新基线重新构造 nodes-only 合并计划并重新验证，不提交旧 ImportPlan；lastSuccess 只在完整成功提交后更新。
- 完整配置先生成本机不可变 preview，列 DNS/规则/组差异及影响。Controller 签发只驻内存的 ReviewTicket，绑定 **sourceId + 源定义版本 + exact source bytes SHA-256 + candidate planDigest + savedRevision + schema/capability版本 + UI会话nonce**，有效期 10 分钟、最多一个。
- 用户点击“本次应用”才把 ticket 消耗为一次 requestId。Rust/Controller 复核以上绑定；任一变化必须重新预览/确认。来源删除、重新下载、应用重启、编辑候选或换基线都使 ticket 失效。定时刷新 API 不接受 ticket，原始文档里的 approved/importScope 字段不能制造授权。
- ticket 消耗后的网络/磁盘不确定结果按原 requestId 查询；明确失败后的新应用必须由用户再次点击确认。审计 receipt 可保存，但不是授权 token，自动刷新不得重放。

## 7. 删除与稳定 ID 迁移

- `nodeId/sourceId` 延续 UUID；新增稳定 `policyId/groupId/ruleId`，显示名只是文本。默认实体使用保留固定 ID `policy:default`，不能删除；允许 `target=unconfigured` 草稿。首次启动rule/global要求默认图结构合法、能力受支持且不是unconfigured/missing；自动组健康未知仍可启动其独立检测，但业务流量阻断至健康候选出现，避免冷启动死锁。
- v1 的 selected sidecar 仅按原 snapshot digest 规则读取一次，QSettings mode 仅迁移一次；生成 V2 committed 后不再读取旧 sidecar/mode。旧 `.network.json` 仅作首次迁移输入，原文件保留为不可再自动回放的备份。
- v1 组/规则名在迁移时构建单一名字表，解析成功后持久化 UUID；不得用列表顺序重新生成组 ID。名字重复、节点组同名、保留名冲突、未解析目标均阻止该策略迁移/完整配置应用，原数据不覆盖；nodes-only 节点提取仍可独立成功。禁止取第一个同名项或自动重命名后猜引用。
- 现有来源语义身份/providerAlias/原文位置算法保留；稳定 ID 决策不能只靠节点显示名。ambiguity 保留并报告，不随意合并/换 UUID。旧 `nativeDocumentRouting` 配置需明确迁移预览，不能把原始全文重新执行。
- 删除确认展示关联节点和策略影响；**不因引用存在而禁止删除来源**。删除凭据后，配置保留无凭据 tombstone `{kind,id,safeLabel,reason}`。新建未知引用仍被拒绝；仅受控删除/迁移可生成缺失状态。
- 缺失出口命中时 Rust 返回 `MissingTarget`；空组 `PolicyUnavailable`；手动组选中项缺失不自动换第一项/DIRECT。自动组只按用户既定策略使用剩余有效候选。运行中删除默认出口来源允许进入 default-unavailable：未分类海外阻断，本地/国内及无关已配置策略继续按规则运行，不要求全局停止。
- 成功撤销必须取消相关 source/node 的既有会话、探测、拨号与连接池；普通模式/策略切换继续保留旧会话快照。此差异需 Rust revoke barrier + 会话取消令牌，不能只更新列表或借“会话稳定”保留已删除凭据。准备期只计算撤销集合；提交完成后先执行撤销屏障再 release admission/成功 ACK；崩溃恢复不得重用旧集合中的凭据。撤销屏障失败时不能报告成功或恢复已删除节点；进入 RecoveryRequired，必要时停止该核心流量，但保留接管所有权，不沿当前普通 Failed 回调自动释放系统代理。

## 8. ABI、能力与边界

保留现有 buffer/ownership C ABI v1 和 exact build_id/source_sha 校验；新增控制协议 schema 2，明确命名 `prepare_configuration_v2 / activate_configuration_v2 / finish_configuration_v2 / rollback_configuration_v2 / configuration_status_v2`，不使用 JSON-RPC。start_v2 同样返回配置 receipt。旧 start/configure/select/select_group 不得绕过 V2 handle 的 revision/CAS。

所有 V2 消息公共字段：`control_schema:2, op, request_id`；在线操作另带十进制字符串 `handle, engine_epoch`。`prepare` 输入 `store_id, base_saved_revision, candidate_revision, expected_generation, base_applied_revision, candidate`；candidate 是 RuntimeConfigV2（既有 listener/limits/严格 Node-Outbound/DNS/transport 参数 + PolicyDocumentV2 + 受信 node_sources 映射），只包含运行闭包，不含惰性订阅原文。`prepare` 输出 `prepared_token, plan_digest, candidate_revision, expires_in_ms` 与安全验证摘要。

`activate` 输入上述 identity、token/digest和由Controller在加密intent成功后读取的候选版本；原子关闭admission并CAS换计划。`finish` 输入token和 `{store_id,request_id,saved_revision,plan_digest}` durable receipt；只接受匹配的候选，执行撤销屏障后放行。`rollback` 输入token、expected_generation及旧committed identity，只能回到该prepared plan记录的旧内容，不能提交任意payload。`configuration_status_v2` 输入request_id/handle/epoch，输出 `transaction_state, applied_revision, generation, applied_mode, plan_digest, last_receipt, error?`；`last_receipt`有界，不含授权ticket。每次成功响应都带 `ok:true,request_id,engine_epoch,generation`；失败带同一身份及 `ok:false,code,phase,field?`，不可只返回布尔值。

prepared token 最多一个、未激活有效期60秒，绑定store/epoch/基线/候选digest；未使用超时释放。activate开始后不靠token过期盲回滚，必须按最终持久化结果收敛。预览仅做纯validate生成digest，不占用长期prepared plan；用户确认后的prepare再次核对相同候选摘要。离线validate不启动handle，start_v2接受有效committed配置并返回新epoch和实际receipt。`stop`/probe/status继续可用但受handle类型隔离，旧mutation不能影响V2计划。

build-info 在既有 4096-byte 安全读取内新增受支持 control_schema/config_schema、required/optional capability、limits。缺少 `config_transactions_v1`/`stable_policy_ids_v1`/`routing_tiers_v1` 或版本不兼容，V2 配置应用失败并显示可修复错误；不得降级为旧语义。TUN/process matching 继续报告 unavailable，不能因有 ABI 字段就展示可用。

| 边界 | 固定契约 |
|---|---|
| JSON | Rust enum/struct 严格类型 + deny_unknown_fields；未知安全/路由字段拒绝应用，原文可加密惰性保留；请求/响应不允许重复键造成多解释。 |
| 大小 | 控制请求 ≤1 MiB，响应 ≤1 MiB，build-info ≤4096 bytes；拒绝超限且保持旧计划。不得把整个 32 MiB 私有源档案塞进控制命令。 |
| 目录/运行闭包 | 目录 ≤2000 节点/32 来源；当前运行闭包 ≤512 节点、128 组、4096 编译规则。Qt 当前 1000 自定义规则先保留为产品上限；不能截断到上限冒充成功。 |
| 组/探测 | 复用已有深度16、自动组32、自动候选每组64、总候选512、探测并发4及 URL/超时校验；扩大嵌套支持需对最终展开闭包再检查同等预算。 |
| 无效数值 | u64 溢出、负数、小数、非规范十进制、错误字段类型、未知版本全部拒绝；候选/token 数量有界，过期释放内存。 |

## 9. 必须覆盖的故障矩阵

| 注入点/场景 | 必须观察的结果 |
|---|---|
| prepare 失败/未知字段/超限/循环 | 磁盘与 runtime 不变，没有新探测/拨号；错误绑定正确请求。 |
| intent 加密/写入/rename 失败 | 不关 gate、不 activate；旧策略继续，lastSuccess 不变。 |
| CAS 冲突/旧 epoch/重复请求不同内容 | 不覆盖新计划；同 requestId 查询幂等，不出现第二次切换。 |
| activate 后最终写失败 | gate 内零个新请求经候选出口；恢复旧内容 generation 递增后才放行。 |
| 最终写迟迟未完成/回调丢失 | 超时请求被有界拒绝；不盲回滚；读取磁盘 receipt 决定结果。 |
| committed 已落盘、finish/Qt ACK 丢失 | 查询识别成功，释放 gate，不再次应用、不恢复旧配置。 |
| rollback/状态查询失败 | 新请求 fail closed；明确 reconciling/error，不 DIRECT、不自动改系统代理。 |
| 每个事务阶段崩溃重启 | 只从有效 committed 恢复；pending按种类收敛；撤销pending不以旧凭据自连。 |
| rule→global→direct 连点/关停穿插 | 只受理一个 mutation，其他明确 Busy；旧信号无效；UI显示已受理请求的真实结果，不谎称所有点击成功。 |
| 来源更新失败/过期响应/删除正在使用的来源 | 上次数据保留或撤销完整提交；tombstone可解释；相关会话/探测/池实际停止。 |
| 同源再次刷新/异源同名/确认后修改配置 | 自动刷新只改节点；ticket不复用；歧义拒绝、不猜名称、不跨来源借节点。 |
| v1→v2迁移失败/旧程序打开v2 | 原加密文件保留，不能部分升级/自动清空；旧程序明确拒绝新版格式。 |
| 受控独立出口 A/B + 新请求/旧隧道 | 验证路由门禁与实际出口，不用纯Mock证明生效；普通旧隧道保留、撤销旧隧道终止。 |

上述验证使用隔离临时库和受控 peers；本机系统代理/TUN/DNS/私人订阅不变。源码设计与单元测试不能替代用户实际服务与 Windows 接管验收。
