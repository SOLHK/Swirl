# Swirl 许可证与商业授权制度审查

审查日期：2026-10-30。源码基线：
[`4ad8a23b7fd59f0f8c09f1e3547548b16baaf4e9`](https://github.com/SOLHK/Swirl/commit/4ad8a23b7fd59f0f8c09f1e3547548b16baaf4e9)。
本次只提出许可证、版权通知和授权管理文档变更，不对既有发行包作合规通过声明。

## 官方文本与规则边界

根目录 LICENSE 直接取自
[PolyForm 官方 1.0.0 纯文本](https://polyformproject.org/licenses/noncommercial/1.0.0.txt)，
未附加、删减或改写条款。下载原件 SHA-256：
`ffcca38841adb694b6f380647e15f17c446a4d1656fed51a1e2041d064c94cc8`。

[官方许可证页面](https://polyformproject.org/licenses/noncommercial/1.0.0) 的
Notices 条款要求传递条款副本或官方 URL，并传递许可方提供的所有
`Required Notice:` 纯文本行。NOTICE 分别提供 SOLHK 版权行和 Swirl 来源行。
核验制度只用于额外商业授权，不给该许可证已允许的非商业活动新增审批条件。

PolyForm Noncommercial 不应标为 OSI 认可的开源许可证：其用途限制与
[OSI 定义第 6 项](https://opensource.org/osd) 允许商业领域使用的要求不一致。
第三方许可、法定例外、已有效授予的历史权利均须分别保留。

## 历史许可与权属：未全部解决

- 审查了基线 `main` 的完整可达历史（829 个提交）中的根目录
  LICENSE、COPYING、NOTICE、COPYRIGHT 同类文件路径，以及 README 中许可相关历史。
  未发现仓库级旧许可证文本；这不是“从未授予任何权利”的证明。
  旧 C#/WPF、外部内核时期的发行及其他分支、标签、仓库外聊天和私下合同
  未完成逐一法律审计。公开仓库本身不证明任意用途获准，参见
  [GitHub 的无许可证说明](https://choosealicense.com/no-permission/)。
- Git 作者名包括 Steam、Codex、Swirl Core Automation、SOLHK、mac430 等。
  作者名或机器人身份不能证明版权已归 SOLHK。尤其
  [`971c1d750d061983fa7147e16f1098420e03cb46`](https://github.com/SOLHK/Swirl/commit/971c1d750d061983fa7147e16f1098420e03cb46)
  以 mac430 名义修改了字体工具、测试及文档；本次未发现可确认其身份关系、
  版权转让或覆盖本次再许可及另行商业授权的贡献者协议。
  不能断言 mac430 是独立第三方，也不能假定其贡献已归 SOLHK。
  维护者须核实同一主体、雇佣关系或取得适当许可；本次没有补造这些证明。
- `.agents/skills/ui-ux-pro-max/` 包含已有技能、脚本和数据，未见该目录自带的
  独立 LICENSE 文件。上游来源及完整再分发条件未核清，不能一并宣称为 SOLHK
  原创或改授 PolyForm。资料、截图和其他设计参考的来源也不能仅凭 Git 记录
  确定权属。NOTICE 明确将无权再许可的材料排除在本次许可声明之外。
- 目前没有公开登记的商业授权，登记表没有虚构记录。未访问私下合同或
  电子签账号，未核验任何实际商业授权。新制度不能追溯撤回有效的旧许可或合同。

在上述权属问题解决前，不能把本 PR 视为整个仓库均已完成有效再许可，
也不能据此承诺 SOLHK 可以对仓库全部材料授予额外商业权利。

## 第三方许可证检查

本次保留所有既有第三方文本、文件头、许可选择及修改通知，未对其加上
非商业限制。下表是发现与核验入口，不是全部第三方义务已经履行的证明。

本地对当前锁文件的 190 个非工作区包版本逐一读取原始 crate 归档中的
Cargo.toml 许可声明：189 个注册表归档的 SHA-256 与 Cargo.lock 一致；
vendored rustls 原始归档的 SHA-256 与 SWIRL-PATCH.md 所记上游来源一致。
未命中缓存的 9 个归档从 crates.io 官方分发地址下载后再比对，未执行包代码。
190 个归档的比对均成功且均有许可声明。此检查核实的是来源与声明，
不证明所有传递/内嵌材料、许可选择、实际链接及分发义务已经检查完毕。
尤其 AND 组合条款须共同满足，存在宽松许可选项也不能忽略相应通知。

| 材料 | 已有证据与许可 | 处理及未解决事项 |
| --- | --- | --- |
| rustls 0.23.46 及 Swirl 补丁 | `core/vendor/rustls/LICENSE-*`、`SWIRL-PATCH.md`；Apache-2.0 OR ISC OR MIT | 补丁已明确同许可提供；保留其商业使用权限，不能以新根许可证收回。 |
| Rust 锁文件中的依赖 | `core/Cargo.lock`、`core/DEPENDENCIES.json`、`packaging/licenses/rust-*.txt`、`docs/evidence/x14-a6-ss2022/dependency-licenses/` | 历史清单有 134 个包版本；当前锁文件有 190 个非工作区包版本（含 vendored rustls），相差 56。包含跨平台、构建、开发及可选依赖，不能当作全部运行时依赖数。旧清单及部分新增依赖通知不能证明最终二进制通知完整。 |
| Qt 6.12.0 | `src/Swirl.Quick/packaging/THIRD_PARTY_NOTICES.txt`、`licenses/LGPL-3.0-only.txt`、`licenses/GPL-3.0-only.txt` | 现有声明为动态链接 LGPLv3；须保留替换、重新链接、调试修改所需的逆向工程及对应源码等权利。须按实际部署模块核对许可及 Qt 自带第三方材料，不能仅凭“动态链接”认定全部履约。 |
| MetaCubeX/meta-rules-dat | `src/Swirl.Quick/packaging/rules/LICENSE`、`manifest.json`；固定提交 `83c8208bdfae92b1caaa29745f51f233b6f1847e` 的 GPLv3 MRS 数据 | GPLv3 数据保留原许可及其商业权限；还需核查生成这些 MRS 的对应源码/首选修改形式及分发义务。单有 GPL 文本、哈希和仓库首页不能证明履约完整。是否仅为聚合应按实际组合方式判断，不因 GPL 数据存在就断言整个 Swirl 必须 GPL，也不能将形成 GPL 派生作品的部分改为非商业许可。 |
| HarmonyOS Sans | `assets/fonts/LICENSE_HarmonyOS_Sans.txt`、`packaging/licenses/HarmonyOS-Sans.txt`、`docs/FONTS.md` | 专用协议允许随非字体软件分发未修改字体；禁止修改或单独分发等条件继续适用。不是 MIT/OFL，Swirl 商业授权不替代字体协议。 |
| fkYAML / nghttp2 / RenderDoc 头文件 | `third_party/fkYAML/node.hpp` 文件头及 `packaging/licenses/fkYAML-MIT.txt`；`third_party/nghttp2/COPYING`；`tests/third_party/renderdoc_app.h` | MIT 声明保留。测试与开发材料同样不应被根许可证误覆盖。 |
| OpenSSL / FreeType / MinGW / winpthreads | 既有 `THIRD_PARTY_NOTICES.txt`、`packaging/licenses/`、`tools/openssl-runtime.lock.json` | Apache-2.0、FTL、GPLv3 加 GCC Runtime Library Exception 及适用独立许可继续有效；以实际构建/部署为准，本次没有重建或审计安装包全部文件。 |
| 已有 Fluent 图标通知及开发参考 | `assets/icons/ui/FLUENT-LICENSE.txt`、`packaging/licenses/fluentui-MIT.txt`、`docs/ANIMATION_DEPENDENCY_RESEARCH.md` | 保留已有通知。文档称部分运行时及资产未采用，不能因此删除仓库已有权利人声明，也不能把参考资料自动视为可再许可原创。 |

上表中的 `assets/`、`packaging/`、`third_party/`、`tests/` 简写相对于
`src/Swirl.Quick/`。Qt 义务另参考
[Qt 官方 LGPL 说明](https://www.qt.io/development/open-source-lgpl-obligations)。
GPL/LGPL 的具体义务以仓库保留的完整许可证原文为准。

## 分发与验证缺口

现有 `scripts/Stage-WindowsRustProduct.ps1` 复制第三方通知和许可目录，
但未显式携带本次新增的根目录 LICENSE/NOTICE 或传递新的 Required Notice 行。
本次禁止修改构建配置与程序，因此没有调整脚本、安装程序或 UI。
未来发行必须确保收到任何软件部分的人同时收到 PolyForm 条款或官方 URL
以及两行 Required Notice，并履行各第三方的独立义务。仅合并本 PR 不能
证明旧安装包或未来自动生成的安装包满足这些要求。

未接入腾讯电子签 API、建立服务器或进行真实合同验签。
[腾讯官方合同管理说明](https://cloud.tencent.com/document/product/1323/92778)
提供人工验签及存证入口；文件未篡改的结果不替代主体、授权链及合同效力核查。
文档规则也不能保证外部 AI 系统服从，不能作为实际授权完成的证据。

基线 `.github/workflows/guard-production-release.yml` 只接受同仓库
`test → main` 且符合既有批准流程的 PR。本次按要求从独立工作分支创建
目标为 `main` 的文档审查 PR，因此不满足该现有晋级门禁；未修改工作流，
也未提交到 `main` 或 `test`。创建 PR 不代表门禁已通过或允许合并。

## 本次验收范围

提交前实际执行了 30 项文档静态检查，均通过：包含官方独立重下载与索引中
LICENSE 的字节一致性、原 AGENTS 内容及追加形式、通知行、空登记与必需核验
要素、本地文档链接、变更路径白名单，以及上述依赖来源/清单差异核查。
这些通过结果只覆盖下列文档验收，不消除本报告列明的未决授权风险。

- 逐字节比对 LICENSE 与官方纯文本；核对 NOTICE 的 Required Notice 格式及传递要求。
- 交叉检查许可、通知、空登记表、AI 政策与 AGENTS 规则：不新增非商业审批门槛，不虚构授权，不将第三方改授非商业许可。
- 检查 AGENTS.md 的既有内容完整保留，仅追加新规则。
- 检查变更路径仅为许可证及文档；所有既有源码、构建配置、UI、Rust Core、第三方许可和现有功能保持原样。
- 未运行编译或产品功能回归：本次没有程序或构建变更。静态检查不等于法律权属、安装包合规或真实商业授权通过。

文档制度可以提交审查；版权归属、历史授权、第三方完整分发义务和发行包
通知仍有上述待解决事项，应在声称整体再许可/商业授权能力或发行合规前处理。
