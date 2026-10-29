# Swirl release promotion (开发 → test → main)

当前采用常规 PR 晋级流程。此前 0.2.16 文档记录的一次性 main 删除／重建方案不适用于当前发布；不得据此强推、删除分支或更改默认分支、保护规则。本轮所有者已明确授权：完成深色侧栏修正、旧外部内核运行路径清理和展示更新后，先集成 test，再按下述同 SHA 检查与 release-approved 门禁合入 main。这不构成创建正式 Release 或后续发布的通用授权。

1. **集成**：从开发分支向 test 发 PR，使用普通 merge commit；保留 test 上的 VF 与其他独立提交，不 force-push 或 reset。
2. **验收**：合入 test 后，按 test 的最终完整 SHA 核查以下四个 push workflow 均为 success：Build Swirl Qt Quick UI (Preview)、Swirl Rust Core、Validate Qt-only source tree、Qt HTTP client security。不得拿开发分支或旧 SHA 的绿色检查代替。
3. **发布 PR**：只允许同一仓库的 test → main PR，不得使用 release/work 分支直接合入。PR 必须为非 draft，PR HEAD 必须仍是当前 test HEAD。
4. **所有者批准**：四项 CI 完成后，由仓库所有者在 test → main PR 添加 release-approved（标注时间必须晚于所有必需 CI 的完成时间；重新运行或新提交后必须重新标记）。production-gate 检查最近一次 release-approved 标注确实由仓库所有者添加。删除/添加标签可重新触发审核，不能仅靠标签存在就通过。
5. **合并**：production-gate 成功，且 main 分支所有 Required Status Checks 成功后，人工点击 Merge pull request（merge commit）。不得自动发布正式安装包。合并后独立验证 main SHA、构建、产品 Rust DLL 与 EXE 身份以及安装包。

## 必须配置的 GitHub Ruleset

当前 GitHub App 无仓库 administration 权限，**无法修改 ruleset**。仓库所有者需打开 [main 规则](https://github.com/SOLHK/Swirl/rules/24847349)，保留禁止删除/非快进、仅 PR merge 的规则，启用 Require status checks to pass，至少设置 production-gate 为必需检查；推荐同时设置 build-qt-ui、build、windows-rust、Windows Qt 6.12.0 product regression 等实际稳定产生的检查名，保存前从真实 PR 的 Checks 栏核对。否则工作流失败仍有可能被直接合并。

建议额外保护 test 分支，禁止 force-push，要求 PR，避免正式候选的历史遭无审查改写。

## 失败或变更时

- CI 失败：修源码再合入 test，产生新 SHA，重新验收，不降低测试标准。
- test 新增提交：原放行失效，需重新核对所有 workflow，重新批准。
- 审批标签添加过早：CI 全绿后以所有者身份移除并重新添加，触发 production-gate。
- 历史文档提及 Mihomo/Clash 不等于产品捆绑内核；不要删除合法订阅格式转换、加密数据迁移与兼容性回归。
