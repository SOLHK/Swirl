# UI V2 阶段 2：路由与策略架构草案

基线 `856f11e12a20f992620597fbbddb6eab7d32929d`，开始时工作区干净。本文件是设计，未改产品源码、未运行编译/联网测试；以下 V2 行为均为待实现契约。

## 1. 模型与版本边界

- 沿用现有加密配置存储，不新增独立策略数据库。Node UUID 不变；服务策略/自定义规则 UUID 统一作用域，组 UUID 独立稳定；名称只显示。
- 默认策略固定 ID 为 `policy:default`，永远存在，target 仅 `node/group/unconfigured`；服务和规则 target 可 `node/group/direct/reject`。新配置未知引用拒绝。本文 camelCase 为概念/UI 名，wire 一律 snake_case。
- 默认出口组的传递闭包必须全为代理节点；任何未选择分支含 DIRECT/REJECT 也拒绝，避免 global 意外直连。没有节点时 unconfigured，命中返回 `DefaultUnconfigured`。
- 来源删除后保留原 target kind/id 引用，并用 `missing_targets` 中无凭据 tombstone 标记 `missing_source`，不新增 Missing target kind、不换首节点。命中该引用返回 `MissingTarget`，其余出口正常。
- 服务为 `{id: UUID,name,enabled,priority,domains[],target,catalogKey?,catalogVersion?}`；catalogKey 仅元数据。多个 domains 按 OR。规则另有明确 tier 与 matcher。
- 同 tier 的 priority 唯一且数越小越先；不以名称、UUID或隐式“更具体”规则决胜。默认目录不用关键词匹配。
- domain 是精确匹配；domain_suffix 匹配根域和点边界子域，不能命中 notexample.com。统一 IDNA ASCII、小写与末尾点处理。
- 应用、应用与网站组合目前不可启用；已选定未来组合为所列应用或网站任一命中（OR），必须等可靠进程能力就绪才开放，不能静默退为仅网站。
- 严格分派 schema 1/2，保留 schema 1 `deny_unknown_fields`；不能 untagged 试错后忽略 V2 错误字段。共用 Node/Outbound/协议类型和运行库。

## 2. Rust 五层规则与模式

| 层 | 判定 | 出口 |
|---|---|---|
| L1 | 已知本地网络、回环、用户显式直连目标 | DIRECT |
| L2 | 启用的专属服务匹配 | 服务 target |
| L3 | 校验过的中国域名库或实际拨号候选 IP 命中中国 IP 库 | DIRECT |
| L4 | 其他启用的自定义规则 | 规则 target |
| L5 | 未匹配或仅 CN 分类无法完成 | defaultPolicy |

- 同层可调 priority，跨层固定。普通 DIRECT 服务不能因其出口为 DIRECT 自动晋升 L1；停用/未配置服务不捕获请求。
- `global` = 固定本地集合及安全例外 → defaultPolicy；不包含用户任意 explicit_direct_rules，也不执行服务/CN/其他规则。`direct` = 合法的受接管目标直接出站。
- 本地集版本化：回环、RFC1918、IPv4 link-local、IPv6 ULA/link-local；现有 100.64/10 作为明确共享地址空间例外，不称为中国规则。
- localhost 固定回环；`.local` 需已知本地解析/映射，不能把解析到公网的名字当局域网证据。零地址、多播、自连接 Swirl 监听端点按明确错误拒绝。
- 本地判定使用已知 IP/显式静态映射；不能为每个已命中服务的域名先向系统 DNS 查询。无法获取地址的请求不伪造“本地”证据。
- 编译器检查 exact 重复、suffix/CIDR 包含、目录交叠，返回双方 ID、priority、见证目标与获胜者。同 tier 重复且出口不同、priority重复阻止应用；跨 tier 展示实际遮蔽。
- 反例：把 baidu.com 放进 L4 代理规则，L3 CN 仍优先；不能通过恢复 smartRouting 开关却保留旧错误顺序冒充完成。

## 3. DNS、IPv6、分类证据与循环

- 复用现有 CN MRS 哈希验证、双栈 DNS、TTL、有界缓存和最多 16 个地址；规则库损坏失败关闭，不当作“没有中国目标”。
- 用户现有 DNS 配置原样保留。新增分类 DNS 路径必须显式选择并显示为 `direct_encrypted / via_default_policy / disabled`，不能偷偷换 resolver。
- `BootstrapResolver` 只为代理服务器/控制连接提供地址；分类 resolver endpoint 使用固定 bootstrap IP + 验证 TLS name，不能通过自身查询自己的地址。
- `via_default_policy` 在 Core 直接解析已验证 default 组为具体 leaf，调用 outbound connector 发送 DNS，绕过业务服务/CN分类器；bootstrap 不走同一待判定 resolver。
- DNS crate 定义小型查询传输接口（endpoint、wire bytes、deadline）；Core 实现经代理传输，避免 dns→protocol 的 crate 循环依赖。现有 DNS parser/DoH 验证继续复用。
- 健康检测直接通过被测 leaf，不走业务路由；其 DNS/代理 bootstrap 依赖必须独立于尚待判断健康的组。编译拒绝 DNS/健康依赖环，不能用 DIRECT 启动冷态自动组。
- `direct_encrypted` 明确是直连 DoH/DoT，resolver 知道域名；不能称为 DNS 经代理。无已允许解析路径时不自动用系统/明文 DNS。
- CN 分类专用查询失败时携原域名走默认代理，记录 `classification=unavailable`；若协议仍需要目标 IP 而无允许 resolver，则连接失败。
- 用户强制解析型规则（尤其 REJECT CIDR）无法取得答案时失败关闭，不能借“未知默认”跳过用户阻断规则；Rust 应区分 CN分类与强制规则解析目的。
- 每次请求固定 resolver 证据、答案集合和 configRevision；首个候选按 profile 确定顺序选择，匹配的 IP 必须等于实际拨号 IP。
- 多答案不能“任一个 CN 就全部 DIRECT”。后续重试仅允许同一 rule/service/策略链/leaf 的候选，不在 CN直连与海外代理之间竞速或回退。
- IPv4/IPv6 有界连接竞速只可发生在同一批准出口、尚未发送应用数据前；禁止重放请求。IPv4-mapped IPv6 规范化；NAT64 不猜归属。
- 显式 CN 域名命中时域名规则优先，不能因某个境外答案偷偷改代理；日志同时展示域名判定与拨号 IP，供发现目录错误。
- 系统代理不能控制应用自行 DNS/QUIC 或绕过代理的流量；无泄漏证据只能覆盖进入 Core 的分类/拨号路径，不能扩大成全系统保证。

## 4. 服务目录与跨域粘性

- 目录为本地、版本化、哈希固定的数据，带来源与核实时间；更新给 manifest diff，确认后应用，不能热更新后无提示扩大捕获。
- OpenAI/ChatGPT 与 Claude 独立，不做“所有 AI 服务→OpenAI”；允许列表中的共享验证码、遥测和 CDN 根域不等于服务独占域。
- YouTube 声明专用域/精确 API 子域；Google 集合排除这些已明确拥有的域，例如宽 googleapis.com 不能抢走明确的 youtubei.googleapis.com。
- accounts.google.com 和共享 CDN 无法仅靠 CONNECT/SOCKS 目标判断本次属于哪个网页；不做 TLS MITM/页面来源推断。使用明确共享/Google或默认策略，并显示边界。
- 用户希望共享登录和某服务同出口时，应显式选择同一个具体节点或同一条固定手动路径；仅指向相同负载均衡组并不保证相同leaf，因为服务粘性key不同。目录不能保证某 App 的全部第三方请求均归属同服务。
- 新 load-balance 的 affinity key 为 `(entryPolicyUUID或default, catalogKey或自定义policyUUID或unclassified, groupUUID)`；所有子组沿用同一服务身份，不使用 hostname/源端口割裂同服务。
- 已识别但未设置专属出口的服务可用 catalogKey 作为 default 的粘性桶；未分类流量先共用 default/unclassified 桶，保守保持出口，不冒充跨域 App 识别。
- 稳定 rendezvous 选择 + 有界粘性表（建议8192项、idle30分钟）；组 seed/成员 ID 稳定，改显示名不换出口。活跃连接绝不迁移。
- 未越过子组容差/切换阈值的小幅延迟变化不破坏已粘性出口；leaf不健康/删除、用户改出口、自动子组合法切换或配置使路径失效时仅新连接重选，并记录原因。不得在应用请求失败后自动重放。
- schema1 round-robin 保留旧语义；迁移预览明确“轮询改服务粘性”，不悄悄换算法。

## 5. 全类型组嵌套：不忽略子组策略

- 目标是四种父组×四种子组的16种组合；未完成相应测试前相关新增选项不可启用，不能用简单 flatten 宣称完成。
- 沿用最多128组/16层/32自动组/并发4；自动组成员≤64，手动组成员≤512，总成员边≤4096，实际去重 `(leaf,healthProfileDigest)` 任务≤512。运行节点闭包仍≤512；展开后超限拒绝，不截断。
- 手动组只用 selected 分支；失败不换首项。自动组各自使用明确 health URL/interval/timeout/status/tolerance，未知、超时、过期均不健康。
- 各自动组 profile 对可达具体 leaf 建立检测任务，相同 profile+leaf 去重；父 profile 成功不能覆盖子 profile 失败。结果绑定 leafConfigDigest/profileDigest/revision。
- 解析函数显式接收祖先允许的leaf集合：先与本组profile健康集合求交，再递归评估成员并执行本组策略。manual始终只有selected分支；url-test在受约束候选中按容差选，fallback在受约束候选中取首个健康分支，load-balance使用受约束健康集合。
- 不能先将child固定为A再求父健康交集：如果A不满足父profile而B同时满足父子条件，child自动策略可以选B；manual选A则仍失败。派生缓存key至少含groupId、祖先profile集合摘要和health/selection epoch，不能将一种父上下文的结果复用到另一种。
- 父 url-test 比较子分支时用交集中可能输出叶的最慢已测耗时，作为保守上界；不能测 A 最快却把请求交给未测 B。高级状态明确该指标。
- 父 fallback 按成员顺序；父 load-balance 按服务粘性；实际 leaf 必须满足所有祖先 profile。DIRECT仅显式非默认组可含，REJECT/tombstone不能健康。
- 子拓扑、手动或自动selected、profile变化增加selection epoch并令父派生状态失效；父粘性旧路径不再符合child策略时，仅新流重选。先取快照再 await，完成后按epoch合并，不持锁跨网络等待。自动组可能因父上下文不同而有多个实际leaf，UI不得伪报一个全局当前节点。
- 用有界位集合/缓存复用子图计算，不枚举全部路径；单次解析也有操作预算，超限 `PolicyResolutionBudget`，绝不退DIRECT。

V2新建自动组的高级参数默认值：沿用检测地址 `https://www.gstatic.com/generate_204`、interval_ms=300000、timeout_ms=5000、expected_status=204；新增success_threshold=1、failure_threshold=2、switch_cooldown_ms=30000，url_test的tolerance_ms=50，其他类型tolerance_ms=0。范围沿用interval 1000..3600000、timeout 100..30000且不大于interval、expected_status 200..299、tolerance 0..10000；两个threshold均1..10，cooldown 0..3600000。健康结果最迟在 `2*interval_ms+timeout_ms` 后过期；未知/过期不健康。冷启动需达到成功阈值才可转发；失败阈值只统计探测，撤销/配置失效立即不可用。当前出口不健康时不被cooldown锁住，直接选已健康候选或报不可用；cooldown仅抑制健康出口之间的优化/恢复切换。v1值与算法按迁移预览保留，不能静默填入新阈值。阈值、profile及健康epoch均由Rust管理。

## 6. 删除、旧会话与迁移

- 删除来源必须清凭据、原文缓存及节点凭据；引用保留安全 tombstone。默认不改选、空自动组 `PolicyUnavailable`，仅受影响流量拒绝。
- 删除确认展示影响的默认/服务/组；撤销先禁止新连接，再取消相关会话/探测/连接池，最后释放旧 Arc。不可变快照必须配 nodeId/sourceId 撤销 token，不能无限保留已撤销凭据。
- 普通模式/策略修改只影响新会话；来源删除是明确撤销，不沿用旧会话继续服务规则。
- schema1 原加密 blob/version保留，离线生成预览；不下载订阅。节点UUID不变；名称引用仅在迁移时映射稳定组ID，歧义拒绝。
- 旧SWIRL映射原selectedNodeId；MATCH、DIRECT/REJECT、no-resolve、顺序和导入profile语义完整记录。不得把所有DIRECT规则自动升L1。
- 预览列出 CN重启、私网升优先级、L3遮蔽旧L4、default proxy-only、global本地例外、DNS路径和LB算法差异；确认前继续 `LegacyOrdered` 并明确待迁移。
- 默认含DIRECT/REJECT不能自动删分支：用户明确改代理或保留旧配置/直连模式。未知/不可执行旧字段原文保留且明确未应用，不虚报已迁移。
- 确认后候选完整验证、原子应用；失败保留原保存态和运行态。禁止通过默默删除不支持规则“修复”迁移。

## 7. 最小实施位置与能力声明

| 位置 | 改造重点 |
|---|---|
| `swirl-subscription/src/lib.rs`、`policy.rs` | 保留schema1与协议类型；新增V2文档、typed target、全图/默认闭包/预算验证。 |
| `swirl-routing/src/lib.rs` | 新增LegacyOrdered/V2Layered编译计划；共享matcher/MRS；返回结构化RouteDecision。 |
| `swirl-core/src/lib.rs:142-169,287-327` | 复用Plan/SessionPlan原子替换；增revision/索引/解析链/撤销token。 |
| `swirl-core/src/policy.rs` | 复用health workers；新增DAG profile交集、粘性和去重任务。 |
| `swirl-dns`、`dns_tls.rs` | 复用固定bootstrap IP+TLS校验；显式resolver角色/传输端口，杜绝递归与暗中降级。 |
| `swirl-api/src/lib.rs` | 兼容旧ABI；新增V2验证/应用事务与revision，具体命令由主API草案统一。 |
| `RustCoreEngine.cpp:27-184,222-277` | 保留native node converter；停止Qt拼层级，default不再强制具体节点。 |

计划首个V2路由闭环：五层域名/IP规则、默认node/group、真实模式、基本服务目录、全类型有界组和服务粘性；按实施顺序逐项打开。当前TUN、进程匹配、应用+网站组合均为不可启用能力，接口返回capability=false和原因，不编造应用归属。

实际连接记录最少含 `revision/mode/ruleId/tier/servicePolicyId/catalogKey/groupChain/leafNodeId/sourceId/chosenIp/dnsProfile/dnsPath/classificationState/rejectionCode/affinityReason`。仅Core真实结果更新UI；无副作用静态预览必须标DNS/健康未知，不能当真实收包证据。

## 8. 必测反例与验收（实施时执行）

| 用例 | 通过条件 |
|---|---|
| 新增OpenAI规则+CN域名/IPv4/IPv6 | 专属代理与CN DIRECT并存；接收端收到对应出口。 |
| CN分类DNS失败 vs 强制REJECT解析失败 | 前者default并标未分类；后者拒绝，不绕过。 |
| DNS多答案跨CN/海外、IPv6首地址失败 | 匹配/拨号同IP；不跨规则/出口竞速或回退。 |
| via-default DNS、冷态自动组 | 无递归、无系统/明文/直连降级；健康检测独立推进。 |
| global本地、direct、未配置default | 本地例外保留；direct真直连；未配置明确拒绝。 |
| Google宽域与YouTube精确域、共享验证码域 | 分组边界正确；冲突含见证，不泛化共享根域。 |
| 同一服务多域100次新连接 | 健康期间leaf一致；实际连接链可核对。 |
| 16种父子组组合、不同profile、child换leaf | 每层策略不丢失；旧健康结果不能批准新leaf。 |
| 隐藏循环、超深、探测展开超限 | 拒绝候选，旧计划继续。 |
| 默认组未选分支含DIRECT/REJECT | 新配置拒绝，不能在global意外直连。 |
| 模式修改 vs 来源删除 | 前者旧会话固定；后者相关会话/探测撤销且凭据清除。 |
| schema1未确认迁移、失败应用 | 旧规则行为逐项一致，无无声CN/DNS/LB变化。 |
| 进程/组合策略能力false | 不可启用，不降为仅域名假成功。 |

受控peer、真实用户网络、系统代理与TUN验证分别记录；不能以UI文字或受控HEAD成功证明真实App联网。新用例证据归属实现SHA，系统设置变更用可丢弃Windows CI；私人凭据不出本机。

参考边界（本次查阅，尚非完整目录）：[OpenAI官方网络名单](https://help.openai.com/en/articles/9247338-network-recommendations-for-chatgpt-errors-on-web-and-apps)、[Claude官方应用端点](https://support.claude.com/en/articles/13198485-enforce-network-level-access-control-with-tenant-restrictions)、[Google多产品共享端点](https://knowledge.workspace.google.com/admin/drive/drive-and-sites-firewall-and-proxy-settings)。允许列表不等于路由独占归属；资料中的TLS inspection不是Swirl本次实现。
