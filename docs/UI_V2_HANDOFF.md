# Swirl UI V2 当前交接

## 位置与当前阶段

- 工作树：`D:/Codex/work/Swirl-ui-v2-20261024`
- 分支：`work/swirl-ui-v2-20261024`
- 产品基线：`4c8c9e076976e5cfb62f103daecdf2afc121eeb3` / 0.2.3。
- 阶段 1 审计完成；阶段 2 技术设计完成，**用户确认仍待完成**。确认后下一阶段是阶段 3 节点资源库开发。不要将设计提交解释为实现或新安装包。
- 先读 [阶段 2 主契约](UI_V2_STAGE2_ARCHITECTURE.md)、[UI 实施](UI_V2_STAGE2_UI.md)、[Rust 路由](UI_V2_STAGE2_ROUTING.md)、[事务/API](UI_V2_STAGE2_API.md)。[阶段 1 总表](UI_V2_STAGE1_AUDIT_20261024.md)保留源码证据。以 `git status`、`git rev-parse HEAD` 核实最新状态。

## 用户已确认

- 原生 Qt 6/QML + Rust Core；保留窗口尺寸、侧栏结构，**窗口与侧栏圆角统一改为 14dp**。
- 节点页是资源库：点击/详情/收藏/测速都不能选择运行出口。出口统一在策略页。
- 订阅只管理来源；完整配置不得未经确认覆盖用户 DNS、规则、策略。
- 策略页是“服务分配｜策略组”，永存默认策略可选节点或四类策略组。
- 每阶段说明完成项、分支/提交、测试、下一阶段和模型建议；不自动换模型。
- 不改 main/test/其他窗口，不强推；保护本机现有代理/TUN/路由/DNS及私人数据。

## 阶段 2 已形成的实施契约

1. 修正 customRules 非空即关闭 smartRouting 的结构；Rust 固定“本地及显式国内直连 → 专属海外 → 中国库 → 其他自定义 → 默认策略”。未知目标走默认，故障不擅自 DIRECT。
2. 统一 DefaultPolicy、ServicePolicy、稳定 groupId/ruleId 与 node UUID；保留旧数据并处理来源删除、引用失效、冲突和迁移。不要依赖显示名。
3. 自动订阅节点事务与完整配置显式确认分离；定时刷新不覆盖网络策略。
4. Qt/Rust 同进程DLL采用纯prepare、加密intent、新请求admission gate、CAS activate、最终QSaveFile、finish真实回执；单在途mutation，忙时不排last-wins队列。写结果不确定时不能盲回滚，commit后撤销失败不能恢复凭据。全局仅保留固定本地例外。
5. 四类组复用现有核心；补默认出口指向组、高级参数、循环校验、自动组嵌套及负载均衡服务粘性。TUN/进程识别当前不支持，界面明确限制，实施需单独平台契约。
6. 复用现有 NodeViewModel、SwirlDataTable、SwirlMotion、SwirlPageHost；加入来源分区、可打断空间过渡、焦点回归。14dp 变更需同步轮廓/遮罩并有针对性几何测试，不能仅改一个看似相关 token。

## Skills 与工具

- Hallmark：`C:/Users/sysfr/.agents/skills/hallmark/SKILL.md`。
- UI UX：本仓库 `.agents/skills/ui-ux-pro-max/SKILL.md`，已安装，不重复安装。
- Motion：`D:/Codex/skills/motion-design/SKILL.md`，已安装固定官方 SHA `f9a8a041b85185ee4881b3471d3415e939aac772`；未全局注册，直接读绝对路径。
- Qt：`C:/Users/sysfr/.codex/skills/qt-qml/SKILL.md`。详情见 [技能记录](UI_V2_SKILLS.md)。
- Python：`C:/Users/sysfr/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`；裸 `python` 是 Store 占位。
- 现有 Qt 缓存使用 6.10.3；QML Preview MCP 未连接且需要 6.12+，不为预览擅自升级工具链。

## 阶段 3 的实施入口

- 主要修改 ProxiesPage、NodeViewModel、SwirlDataTable，新增 NodeSectionModel 和来源标题组件；必要时提取临时详情，保留原导航ID。
- 一个ListView显示section/node虚拟行，按来源分区后组内排序；稳定ID保存焦点/滚动；单击浏览与查看详情不得调用chooseNode/connectNode。
- 原策略页继续提供选择出口，避免阶段3产生功能真空；阶段4前先落地自动订阅不得覆盖策略的后端保护，完整订阅页面归阶段5。
- [验收映射](contracts/ui-v2-acceptance-cases.json)共40项，覆盖19组需求，全部planned。阶段3重点C06/C07/C08/C35，再运行受影响现有表格与节点回归。

## 验证与交付边界

- 阶段2运行7项portable guard、4份架构文档的内部链接/样例身份与引用/验收覆盖一致性检查；40项产品验收未执行。阶段1的99文件UI边界结果是历史证据。无产品代码变动，不重复编译或声称当前运行验收通过。
- 0.2.3 仍是诊断版；真实节点抽测失败、Codex 未验收。不要把旧包或受控测试作为 V2 实际联网证据。
- 新版本交付递增 PRODUCT_VERSION，核对 EXE/DLL/manifest/source SHA；安装包与人工教程一同交付，不覆盖现有安装。
- 新分支不在 v018-network-candidate 的 push 分支名单；实施阶段按需 dispatch 或做经安全检查的触发修改，不在审计阶段重复构建。
- `D:/Codex/build-swirl-019-tests-20261024` 的 CMakeCache 绑定原工作树，不能重新指向新树或覆盖其他窗口缓存。为本工作树分配独立构建目录，复用可验证的依赖/CI缓存。
- 视觉 DPI 由用户验收；保留严格协议失败，测量真实 60FPS/长时稳定性而非推断。

阶段2设计待用户确认。确认后提醒“阶段 2 完成，建议切换 GPT-6.1 Sol Ultra 开始实际开发”；不自行切换，也不把缺少答复视为批准。
