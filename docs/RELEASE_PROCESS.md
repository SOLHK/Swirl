# Swirl 分支与发布流程

> **正式版冻结规则：未获得仓库所有者明确指令“推送正式版”，任何人或自动化都不得向 `main` 推送、合并、发布或创建正式发行版。**

## 分支用途

| 分支 | 用途 | 允许的操作 |
| --- | --- | --- |
| `main` | 正式版与稳定源码 | 仅收到所有者明确发布指令后，通过经审核的 `test → main` PR 发布 |
| `test` | 预发布、集成与 Windows 测试 | 接收通过初步验证的开发成果；自动运行测试并提供预览构建 |
| `feat/*`、`fix/*` | 功能开发与错误修复 | 日常提交，向 `test` 提交 PR，绝不直接指向 `main` |

新功能默认路线：`feat/*` / `fix/*` → `test` → Windows 编译与测试 → 所有者确认 → `main`。

## 测试分支验收

1. Windows x64 CI 构建、Qt Quick QML 启动与 24 页面 smoke test 全部通过。
2. 下载 `Swirl-Quick-UI-win-x64` 测试包，在 Windows 真机手动验证布局、交互、浅色/深色、100%/125%/150%/200% DPI。
3. 验证核心功能时，另行执行 .NET Windows 构建和回归测试，不将仅 UI 的测试结果冒充后端验证。
4. 检查工作流无敏感信息泄漏，确认程序安装包和文档准确注明 Qt 界面 Demo 功能边界。
5. 问题在开发分支修复，再同步至 `test`；任何失败不得晋级。

## 正式发布前的强制步骤

- 必须收到仓库所有者明确的“推送正式版”或同义指令，默认视为**未批准**。
- 创建从 **`test` 到 `main`** 的非草稿 PR，禁止功能开发分支直接提出正式版 PR。
- 确认 `test` 的同一份候选提交已完成测试，且正式版 PR 没有额外未测试的改动。
- 所有者明确授权后，给 PR 添加 `release-approved` 标签，才允许 `Guard production release` 检查通过。
- PR CI 成功并人工核对后，由所有者明确要求才执行合并；不能自动合并或直接推送主分支。
- 合并后才允许依照明确授权创建正式版 Release；`test` 的 Actions 构建包一律称作 **测试版**。

## GitHub 网页端必须配置的仓库规则

当前 GitHub App 连接不包含管理分支保护规则的权限，**此 Markdown 不是实际 GitHub 分支保护**。仓库所有者必须在 [Settings → Rules → Rulesets](https://github.com/SOLHK/Swirl/settings/rules) 添加规则，并确认状态为 **Active**。

### 规则 1：Protect main (required)

- Target branches：`main`
- Restrict deletions 和 Block force pushes
- Require a pull request before merging（禁止直接推送）
- Require status checks to pass：`production-gate`、Windows 构建与 Qt UI CI（检查名称以 GitHub 实际运行名称为准）
- Require conversation resolution（如设置可用）
- 不设置自动合并，不设置任何通用的自动发布权限
- 若只有一个维护者，慎用“必须由其他人 Review”以免自己无法发布。需要至少一名独立审核者才启用该选项。

### 规则 2：Protect test (recommended)

- Target branches：`test`
- Restrict deletions 和 Block force pushes
- 新功能通过 PR 进入 `test`；要求 Qt CI 成功
- CI 预览包仅供测试使用，不自动发正式 Release

**注意：只有 GitHub 仓库 Ruleset / Branch protection 真正启用后，才具备防止误推正式版的技术性强制保护。** 工作流、标签与文档本身不能阻止拥有写权限的人员直接推送未保护的 `main`。
