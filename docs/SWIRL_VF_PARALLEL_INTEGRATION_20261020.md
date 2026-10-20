# Swirl-VF 五窗口并行集成记录

## 1. 授权、基线与当前结论

本文件由集成窗口维护。用户于 2026-10-20 授权四个专项分支独立研发，
集成目标仍为 `work/core-completion-20261017`。这项授权更新了历史交接中的
“唯一研发分支”限制；不授权修改 `main`、Swirl Rust Core、无关 UI 或动画。
其他窗口创建并维护自己的分支，本窗口不创建、代写或接管其未提交修改。

首次及 2026-10-20 09:11:14 UTC（17:11:14 UTC+08:00）复查的集成 HEAD：
`e505326486202ad4c8e98bb8b66a17b4547c559f`。
这是本记录的审查基线，不是声称包含本文件的提交 SHA。提交后的实际 SHA、
远端核验和 CI 结果见本文件末尾的追加记录；每次开始仍须重新查询远端。

已实际阅读：

- [最新接续入口](SWIRL_VF_NEXT_HANDOFF_20261020.md)
- [精度检查点](SWIRL_VF_PRECISION_CHECKPOINTS_20261020.md)
- [用户轴交接](SWIRL_VF_USER_AXIS_HANDOFF_20261020.md)
- [工具说明](../tools/swirl_vf/README.md)
- 根目录 `AGENTS.md`、最近 15 个集成提交及相关工作流源码。

| 研发分支 | 远端 HEAD / PR | 本次可审核提交 | 当前状态 | 主责 |
| --- | --- | --- | --- | --- |
| `work/vf-axis-a3` | `d22be86b56cd20a257505be569a21fcea3ef2bbf` | 数值阶段已入 bbb79c1；本次固定 `22a89a1` | 本次仅追加已审查的原生 HVAR 诊断；更新 tip 另审；A3 阻塞开放 | 输入精度、用户坐标映射 |
| `work/vf-metrics-b1` | `d283e2e5ad8d43aa3808e66ac6093c3252c5d9e0` | 首阶段及新 delta 审查中 | 原始度量失败保留；首阶段发现原件逐 GID 数据公开输出，阻断集成；新提交待核验 | CoreText、HVAR/VVAR、垂直度量与原点 |
| `work/vf-rebuild-c1` | `96e99cd72db72b89b7f6d89ef56591a6674db01d` | 新修复 delta 复审中 | 110d903 的 Windows packing/silent-return 阻塞见历史记录；新 SHA 未接受 | HVF/OpenType/TTC 重建与完整性 |
| `work/vf-windows-d1` | `47d6dfc06fa2fddddd1532c1d8370028a6b9da17` | 2 | 构建及真实反序已修并核实；两系统 FreeType 状态相关路径差异、空路径分析器问题仍阻断合并 | DirectWrite、Qt、Swirl 字体适配 |

首次及 09:03:55 UTC 查询时四分支未出现；09:11:14 UTC 已全部出现。
这只描述远端查询结果，不表示其他聊天之前没有在工作或没有本地成果。
上表更新至 09:32 UTC 远端快照，集成 HEAD 为
`bbb79c1e5038d9cfe6b88954094833bae6f7cd4e`。分支持续推进，审核和集成对象
必须固定到下文完整 SHA；不能因 tip 前进就自动包含新提交。09:11 的 A3/C1
第一提交都以 e505 为 merge-base，新增文件互不重名；当时 B1/D1 无 diff 是历史状态。

### 必须保留的技术事实

1. 历史 141 项差异已在固定原生样本内闭合，只保留回归，不重新研发。
2. 两个 anchor 的每个候选各有 26,780 次 portable 轮廓比较在 1/32 FUnit 内，
   属于 5,356 个位置和所选 GID 的有限测试，不是全字库或连续空间验收。
3. A3 有明确前提的输入分辨率障碍，目标 Windows/Qt 实际输入路径尚未验证。
4. **B1 的 849/850 是实测垂直 advance 849 FUnit 对预期 850 FUnit，
   不是 850 项测试中通过 849 项。** 原差值 1 FUnit、门槛 0.03125 均保留。
5. 原件已完成 GID 模型为 0、完成面为 **0/32**，无合格 `Swirl-VF.ttc`。
6. 原始 `WDTH`、`wght`、`HGHT` 标签、轴值语义、范围、默认值、flags、实例与
   面/GID/地区/cmap/UVS/shaping 语义必须独立验证；不得靠改轴或字体内容制造通过。

原件身份：61,473,880 字节，SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`。
32 个物理面，每面 47,102 GID；共 1,507,264 个面内 GID 条目，
不是不同唯一字形的计数。原件、衍生字体、原始轮廓/私有观测和字体截图保持私有。
公开仓库只允许源码、原创夹具生成器和逐字段审查后的安全汇总。

## 2. 文件所有权与共享接口

下表中的 VF 相对路径以 `tools/swirl_vf/` 为根。“主责”表示唯一编辑主责，
不排除其他专项审查。未列出的文件先按实际用途登记，不能以目录通配符抢占整个工具树。
专项的新交接分别使用 `docs/SWIRL_VF_A3_*`、`B1_*`、`C1_*`、`D1_*` 命名，
公共交接由集成窗口更新。

| 文件范围 | 唯一主责 | 必须共同审查的接口 |
| --- | --- | --- |
| `platform/probe_axis_*.py`、`axis_*_cases.py`、`axis_geometry_candidates.py`、`analyze_axis_quantization.py`、两类 construction harness；相应 `tests/test_axis*.py` / harness tests | A3 | 与 D1 协定原始请求、API 接收值及位模式的输出格式 |
| `platform/calibrate_avar_metrics.py`、`compare_axis_construction.py` | A3 | 这里的 HVAR 用来反推坐标；B1 审查度量含义，不能另写一套冲突映射 |
| `platform/diagnose_coretext_metrics.py`、`diagnose_coretext_precision.py`、`probe_vertical_origins.py`；对应 precision/origin/failure tests | B1 | C1 的原点可表达性、D1 的实际布局 |
| `tools/source_metrics.py`、`metric_variations.py`、`table_metric_oracle.py`；对应 source/metric/table tests | B1 | C1/D1 必审；表值、raw API 值、布局值分别保留 |
| `platform/test_coretext_extract.py`、`test_native_table_metrics.py`、`make_metric_fixture.py` | B1 | A3/C1/D1 必审；保留旧严格夹具，新增实验另建入口 |
| `platform/probe_coretext_vertical_gpos.py`、`experiment_vertical_gpos.py`、`probe_vertical_layout.py` 及对应 tests | B1 | D1 审查 feature 默认行为与横竖混排 |
| `tools/rebuild.py`、`tests/test_rebuild*.py`、`test_gvar_residual_quantization.py`、`platform/test_native_reconstruction.py`、`NATIVE_RECONSTRUCTION_SMOKE.md` | C1 | A3 的 accepted oracle、B1 的 metric model 不可被 C1 自行放宽 |
| `platform/directwrite_probe.cpp`、`run_directwrite_probe.ps1`、`DIRECTWRITE_README.md`、`directwrite_vertical_layout.cpp`、`probe_directwrite_vertical_layout.py`、`vertical_layout/CMakeLists.txt`、对应 tests | D1 | A3 的输入碰撞试验、B1 的真实布局与 origin 对照 |
| `src/Swirl.Quick/app/FontAxisPolicy.*`、`FontManager.*`、`FontFileInspection.h`、`FontRendering.h`、`FontDisplayContext.*`、`VariableFontPreview.*`、`src/Swirl.Quick/tests/Font*`、`tools/SummarizeFontTests.py`、`tools/tests/test_font_ci_reports.py` | D1 | 仅字体行为；不得调整无关 UI、动画、网络代码 |
| `.github/workflows/font-system-windows.yml` | D1 起草、集成窗口串行写入 | 分支触发和固定 job 条件需同时审查；Qt 与实际 Windows 11 验收分开 |
| `.github/workflows/swirl-vf.yml`、公共 README、四份公共交接、本文件 | 集成窗口 | 四专项共同使用的 CI、事实与合并记录 |

09:11 UTC 实际新增文件登记：A3 主责 `platform/axis_a3_input_cases.py`、
`tests/test_axis_a3_input_cases.py`、`.github/workflows/swirl-vf-a3-input.yml`；
C1 主责 `tools/ttc_staging_contract.py`、`tools/ttc_staging_store.py`、
`tests/test_ttc_staging_store.py`、`.github/workflows/swirl-vf-rebuild-c1.yml`。
这两份专项 workflow 也必须经集成审查，不能由它们的名称推断原生或生产验收。

以下共享文件由集成窗口控制并发修改顺序，专项可提交最小 patch，
不得两个窗口同时整体替换：

- `platform/coretext_extract.swift`：A3 的构造/轴回读和 B1 的度量/API；每次明确函数范围。
- `tools/verified_axis_oracle.py`：A3 主笔，B1/C1 必审完整 raw payload、逐批 exact replay、
  原件/依赖绑定和最终 transcript；不能以“回读通过”替代实例相等。
- `tools/incremental_pipe.py`、`tests/test_native_protocol.py`、`platform/CMakeLists.txt`、
  共享 fixture 生成入口：由实际改动方主笔，全部消费者复核。
- Swirl 总 `CMakeLists.txt`、`main.cpp`、公共 QML 入口：仅接受单独标明的字体接线 patch，
  不与并发 Core 或界面改动整文件互相覆盖。

冻结复用：`tools/hvf.py`、`batch_geometry.py`、`tangent_geometry.py`、
`transform_geometry.py` 及其已验证算法；没有新的独立失败复现时不重写。
`tests/data/axis_mapping_archive_20261020.json` 的历史观测与
`platform/axis_mapping_closure_archive.py` 的身份绑定不得改写来匹配新结果。
anchor 导致的 36 个旧 q 变化必须与原 production 记录并存。

## 3. 依赖顺序与生产阻塞

| 阶段 | 可以立即并行开展 | 进入下一阶段的必要证据 |
| --- | --- | --- |
| A3 + D1 | 使用原创标准夹具记录请求到真实目标 API 的精度传递 | 源请求与 float/Fixed 等实际输入各自位模式、回读、真实轮廓与 advance；明确碰撞发生在哪层 |
| B1 + C1 | UPEM 判别、度量来源与垂直 X 原点表示；独立重建基础设施 | raw API 差异得到验证解释，标准表示保留实际语义，不用常数补偿或 source-table 值替换原观测 |
| C1 | 原创合成字体的序列化、checkpoint、错误拒绝、完整 transcript | 这些有限基础设施测试可先验收；仍不接受原件生产映射 |
| 生产 32 面重建 | 当前 **BLOCKED** | A3 输入/映射、B1 度量及独立 vertical X origin、D1 目标可表达性都通过；C1 的完整性与保密门槛通过 |
| 最终交付 | 候选生成后才能进行 | 原件等价证据 + Windows 11 实机 + DirectWrite + 实际 Qt/Swirl + DPI/字重/三轴/性能全部实测 |

诊断或基础设施阶段可以独立提交和审查。其新增功能及相关回归必须实际通过，
现存的失败必须按同环境/同输入核对为未被隐藏的基线阻塞。
这类合并只能登记为“独立阶段完成，生产阻塞仍开放”，**不得把红色 job 改记成通过，
不得借此启动生产全量重建**。声称 A3/B1 已关闭或字体已完成的提交必须通过相应严格门槛。
若既有分支保护拒绝合并，保留拒绝；本记录不授权修改保护或绕过检查。

## 4. 每次合并的共同门槛

在完整专项 HEAD 及实际合并候选上核对源码；使用 Python 3.12、
`fonttools==4.61.1`、`numpy==2.2.6`。至少执行：

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
git diff --check
```

建档基线有 448 项回归及 6 项 audit；新增阶段的实际数量见执行记录。
必须分别记录 discovered/executed/passed/failed/skipped；
当前历史公共 CI 的 `Ran 448, OK (skipped=7)` 是 **441 个执行通过 + 7 个跳过**。
HarfBuzz 涉及的改动必须安装并记录实际 `uharfbuzz` 版本后执行对应七项，不能记作通过。
`NOT_RUN` 的原生诊断是未运行，不能用 Linux 单测覆盖来声称 macOS/Windows 实测。

每个独立阶段的交付记录必须包含：

1. 分支名、完整 base/head SHA、实际 diff、文件所有权冲突、全部测试修改。
2. 实际 checkout SHA；PR 另列目标 base、专项 head、merge candidate SHA，三者不混写。
3. 运行环境、命令、退出码、发现/执行/跳过数、失败项；无省略的样本/字段/未知字段检查。
4. workflow run / attempt / job ID、实际终态和日志；没有运行、运行中、取消、跳过都不等于通过。
5. 工件 ID、文件名、ZIP SHA-256、保留期限及读取结论；先校验摘要再解释内容。
6. 阻塞关闭依据、仍开放项目、下一步；不得仅根据工作流名称或 `success` 推断生产接受。

否决项：删除失败样本/断言、增加容差、用 `continue-on-error`/`|| true` 吞失败、
伪造原生环境、以空集合获得绿色、把表度量冒充 API 度量、覆盖失败记录、
改原轴大小写/范围/语义、删面/删 GID/删 HGHT、替代字体/伪粗体、公开私有字体数据。
人工审查完整 diff；现有扩展名 guard 只扫描 `tools/swirl_vf`，不能代替全 diff 的保密审查。

### A3：输入精度与映射

- 保留六点反证及 controls，特别是 `wght=499.006199` / `499.006201`、
  两个 canonical 值、default 和共同 Fixed 值。已有源证据无需重新发明。
- 保留 `test_axis_input_resolution.py`、`test_axis_mapping_closure_archive.py`、
  `test_axis_mapping_closure_cases.py`、`test_verified_axis_oracle.py` 的负例。
- 原生入口为 `platform/probe_axis_input_resolution.py /private/PingFangUI.ttc --output ...`；
  它是源端诊断，不能替代 D1 真实目标测试。新目标夹具与二进制必须独立绑定身份。
- 对碰撞输入核对真实路径、advance、origin、blank GID、未知 payload 字段和反序重放；
  相同回读字符串不是输出等价证据。
- 生产关闭必须处理已测字宽分裂 `0.5474853515625` FUnit 与有前提的
  `0.27374267578125` 下界；保留 `face18 / fresh_triple_7` 的非精确 HVAR
  `0.01220703125`。旧 32 面诊断没有直接检查该点，现由 22a89a1 的固定原生子集
  补齐：截断误差仍在；nearest 仅修好该点，在新 holdout 仍不精确。不能用逐点例外
  或平滑改变原语义，不能把该点定位写成全局映射接受。
- 原 `1/32`、严格回读 `1e-6`、原始 avar 顺序/重复项、完整 summary/EOF/exit 均不改变。

### B1：度量与原点

- 最小新增判别：UPEM 1000 / 1024、相同 phantom 坐标、default height 1000 /
  minimum 850，分别用各自 UPEM 字号测量四个组合。预声明两种预测并保留原始实际数值。
- 不把已经完成的 size/CTRun/VVAR/static 试验重复运行后写成新的修复。
- 现有严格入口：

```sh
python tools/swirl_vf/platform/test_coretext_extract.py --output /private/b1/coretext --require-native
python tools/swirl_vf/platform/diagnose_coretext_metrics.py --output /private/b1/metrics --binary /private/b1/coretext/coretext_extract --require-native
python tools/swirl_vf/platform/diagnose_coretext_precision.py --output /private/b1/precision --require-native
```

- 关闭门槛覆盖横/竖 advance、两方向 origin、LSB、空白字形、半单位原点、内部多轴点，
  并验证 HVAR/VVAR 与 gvar phantom 不重复应用。
- 保留 `test_table_pass_keeps_visible_one_unit_native_API_failure`、
  `test_erasing_raw_error_or_dropping_a_record_is_rejected`、
  `test_changed_native_curve_cannot_pass_using_correct_metric_tables` 等负例。
- `table_metric_oracle.py` 对标准 glyf/已验证 identity avar 的有限接受不能直接扩展为 HVGL。
  原件 vertical X origin 的 100 FUnit 差异与 `1e-5` 表达门槛独立保留。

### C1：重建基础设施

- 全套回归之外，重点审查 `test_rebuild*.py`、`test_gvar_residual_quantization.py`、
  `test_native_protocol.py`、`test_incremental_pipe.py` 的实际负例。
- 必须验证训练/default 量化预算、独立 holdout、拓扑变化、完整 phantom/metrics/gvar
  supports+deltas、TTC 面顺序和打包字节、最终 native transcript、恢复身份与路径碰撞。
- `platform/test_native_reconstruction.py --output ... --binary ... --require-native`
  受 B1 严格 gate 阻塞时登记 `BLOCKED_BY_B1`，不能说合成重建已运行。
  `test_native_table_metrics.py` 的显式表度量 + 原生路径结果单列，保留 raw API 失败。
- 保留 `rebuild.py` 对 `diagnostic_readback_observation_only` 的生产入口拒绝，
  包括所有恢复/后续会话；不得让诊断观察绕过映射接受。
- 当前重建器是 native-instance approximation：重表达 identity avar、HVAR/VVAR 等。
  序列化自洽不等于源语义相等，`lossless_conversion=false` 不能改成 true。
  源轮廓 `1/32`、origin 表达 `1e-5`、既有重建轮廓/度量 `1 FUnit` 是不同检查，
  互不替代；不得混淆它们宣称满足更严格的用户目标。

### D1：Windows、DirectWrite、Qt / Swirl

- 现有 `directwrite_probe.cpp` 先把请求转换成 float，轴回读有相对容差，
  接受 `WDTH` 或 `wdth`；现有结果仅是 smoke，不能证明 A3 微小输入保留或源标签正确。
- 新精度检查必须记录 binary64 请求、实际 API float/Fixed 值及位模式、回读、
  精确实际轮廓与 fractional advance/layout 输出及单位，禁止仅凭整数 design metrics。
- 直接按源 `fvar` 检查 `WDTH`/`wght`/`HGHT`、flags/ranges/default/order/named instances；
  引擎额外合成的 `wdth` 要分别报告。保留 PowerShell 的大小写敏感 hashtable 处理。
- Windows 合成入口为 `make_standard_fixture.py` / `make_metric_fixture.py` 加
  `run_directwrite_probe.ps1 -AllGlyphs -Render`；真实 vertical layout 使用现有独立探针。
- Qt 6.10.3 / MSVC 环境、metadata fixture、隔离 offscreen 字体目录按
  `.github/workflows/font-system-windows.yml` 执行；`SWIRL_FONT_TESTS_ONLY=ON` 构建、
  `ctest -R '^swirl-font-' --no-tests=error`、`SummarizeFontTests.py --require-windows`
  都要有实际结果。微小轴输入用例必须显式必跑，顶层绿色不能代替用例执行。
- Windows Server 合成测试不算 Windows 11 实机、安装、ClearType 或 Swirl 成品通过。
  现有自动 PNG 是 face 0 默认实例的灰度渲染，不能外推到全部面/字重/实际屏幕。

## 5. 本轮实际 CI 配置变更与边界

已审查的旧 VF workflows 只监听集成分支，未配置 PR。
本轮仅扩展公共合成 `.github/workflows/swirl-vf.yml`：

- push 精确覆盖集成分支和四个专项分支。
- 普通 `pull_request` 目标仅为集成分支；三个 job 仅运行同一仓库、四个指定 head 的 PR。
- 保留原 paths、`contents: read`、`persist-credentials: false`、`github.sha` checkout、
  全部 job steps、超时、依赖、失败传播、CoreText gate、artifact 范围及 concurrency。
- 未使用 `pull_request_target`，未扩展原始字体工作流或生产重建工作流。

push 使用所在分支的 workflow；专项窗口必须先纳入此配置，旧提交不会自动补跑。
PR 验证的是 merge candidate；只验证 head 的工作流不能代替合并后的共同结果。
paths 仍只覆盖本 workflow 和 `tools/swirl_vf/**`，纯文档或仅 Qt 应用文件的修改不会触发。
`font-system-windows.yml` 的分支及 job 条件尚未接入 D1，由 D1 起草后串行审查；
因此 **D1 Qt 分支 CI 目前仍有缺口**，不登记为通过。
其他原生专项仍需明确的精确 SHA 运行证据；本次基础 CI 扩展不等于它们已运行。

实施前参照 GitHub 官方
[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、
[PR events / merge SHA](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
和 [runner security](https://docs.github.com/en/actions/reference/security/secure-use)。
分支/路径过滤与 PR 合并候选检查用于本仓库既有工作流，没有复制外部实现。

## 6. 已读取的实际 CI 证据

| 源码完整 SHA | Run | 实际结果及含义 |
| --- | --- | --- |
| `e505326486202ad4c8e98bb8b66a17b4547c559f` | [39394872342](https://github.com/SOLHK/Swirl/actions/runs/39394872342) | Core implementation validation：completed/success；不是字体功能验收 |
| `e505326486202ad4c8e98bb8b66a17b4547c559f` | [39394872349](https://github.com/SOLHK/Swirl/actions/runs/39394872349) | 首次读取 in_progress；09:12:23 UTC 已核实 completed/success，三个 job 全部 success |
| `53ca5ff74e17bfc65e338b460fa2fc4df3801c1d` | [39394041948](https://github.com/SOLHK/Swirl/actions/runs/39394041948) | 首次读取 in_progress；09:05:52 UTC 已核实 completed/success，三个 job 全部 success |
| `53ca5ff74e17bfc65e338b460fa2fc4df3801c1d` | [39394041915](https://github.com/SOLHK/Swirl/actions/runs/39394041915) | completed/failure；Python 441 执行通过 + 7 skip，audit 6 通过，Windows 合成 success；Apple raw 849 vs 850 失败 |
| `53ca5ff74e17bfc65e338b460fa2fc4df3801c1d` | [39394042127](https://github.com/SOLHK/Swirl/actions/runs/39394042127) | completed/success：六点输入障碍诊断完成；不接受生产映射 |
| `9f4d9882255bd36f804d0bd639966ad65677fc31` | [39392843365](https://github.com/SOLHK/Swirl/actions/runs/39392843365) | 已核实 completed/success；交接中“仍运行”已过时；完整工件已下载校验与读取，见下 |
| `9f4d9882255bd36f804d0bd639966ad65677fc31` | [39392843364](https://github.com/SOLHK/Swirl/actions/runs/39392843364) | completed/failure；91 批 / 5,824 观测，face 0/GID 0 vertical X origin 100 FUnit 差异；0 模型/0 面/无 TTC |
| `9f4d9882255bd36f804d0bd639966ad65677fc31` | [39392843518](https://github.com/SOLHK/Swirl/actions/runs/39392843518) | completed/failure；默认 strict extractor 的小数 WDTH 回读失败，不能与 verified adapter 的 origin 失败混称 |
| `6dd81c0cfd6cf2794584210bee7def55aef20e90` | [39398618327](https://github.com/SOLHK/Swirl/actions/runs/39398618327) | A3 专项 completed/success；数值输入 contract，不是 native/production 接受；审查实际测试范围 |
| `b0c3500afd58a5ecc55bc09dec259ba4b21bb7a6` | [39398766503](https://github.com/SOLHK/Swirl/actions/runs/39398766503) | C1 专项 completed/failure；Linux/Windows success，macos-14 staging tests 失败；保留阻塞 |

### 9f 的 32 面重复诊断已核实终态

Run 39392843365 于 08:38:56 UTC 更新为最终 success，artifact **12251401718**。
下载 ZIP SHA-256 实测并匹配 GitHub：
`e344554bbfad4729fc8428ae759596de174c1611b2b352eba557dcb9b43d12d0`。
实际 JSON 状态为 `COMPLETED_NATIVE_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE`，
`mapping_accepted=false`、`font_generated=false`。

- 六进程，321,360 条实际记录；160,680 对反序 payload 精确相等；32,136 批重放零失败。
- 固定 `canonical_float32_normalized16_truncate` 候选在每个 anchor 下的 HVAR
  5,355/5,356 精确，最大误差 0.01220703125；portable 26,780 次 preserved-Q 比较零失败，
  最大 0.011959285366742733。旧比较器各 16 个类型拒绝继续报告。
- 同一候选预声明的每 anchor 1,050 次直接 HVF 检查零误差；旧 141 点每 anchor
  282/282 直接检查精确。不要把另一候选或 production 的统计归给这个模型。
- production 重现旧 3,048 个 q；各 anchor 的 36 个旧 q 变化保留。
  `fresh_triple_7` 不在预声明直接 HVF 子集，不能据上述数字宣布该点直接原生通过。
- 这是此前运行的终态审查，没有重复执行已闭合的旧 141 研究，没有解除 A3/B1。

另下载并核验前次 b549 工件 12250517308，ZIP SHA-256 为
`e29c2b663330845e16135ec35e760f7a4cf70a99814db0e4ff9e2ac30404f018`。
两份解压 `closure.json` 均为 283,873,695 字节，递归逐字段比较只有 `/source_commit`
从 b549 变为 9f 一处差异；仅规范化该字段后，全部数值、逐条记录、身份、计划、
汇总和接受标记完全相等。前次 JSON SHA-256 为
`9440365ac6f57461fc2cbeeb802ebf849b1b7e4953d0f16a9561f101c51c4bb9`，
本次为 `5700c36792f1271bcc22e72ff9a266ccbda8b00f8e834377f2dfc0985e209fcc`。
此比较证明这次已完成重复运行的证据一致，不扩展有限样本的结论范围。

其他已下载核验工件：

| 工件 | ZIP SHA-256 | 已核实用途 |
| --- | --- | --- |
| Apple synthetic 12250677293 | `2b82019e4bd2ed3801e36d6586aa0aca231fb54d304e69172d9e33af6dd4e8f8` | 保留原始 849 vs 850 失败及独立诊断 |
| Windows synthetic 12251385598 | `3823e4a3c9c47c002e874efe7c6d215dd9f6aa195bec8928403160bd92cea857` | Windows Server 2022 build 20348；三面夹具与两面 metric 夹具通过；原件相等/安装/UI 未验 |

## 7. 安全集成与全量交付顺序

1. 重新读取集成 HEAD 和专项 HEAD，固定两者完整 SHA；读取 merge-base、全部提交/diff，
   检查共享文件、越界修改、敏感数据、测试绕过及错误完成声明。
2. 未提交修改保持原窗口所有；必要时在独立 checkout 准备 merge candidate。
   PR 目标只能是集成分支，不开启未审查的自动合并。
3. 冲突逐段定位至并发接口/语义；不得 whole-file ours/theirs、强制合并或 force push。
   已发布专项分支不通过重写历史来消除冲突，可由其作者合并新基线或提交追加修复。
4. 获取 head 与候选的必要测试和真实 CI 终态；凡涉及原件使用授权私有环境，
   不把公开 Actions 工件名当作私有数据可上传的许可。
5. 以已审查 parent/tree 构造提交；GitHub ref 更新使用 `force=false` 与预期旧 HEAD。
   若远端变化，重新读取 diff 并重新构造候选，不能覆盖并发 Core 提交。
6. 每完成一个验证阶段立即提交记录并回读远端 SHA/提交父链/文件列表；
   后续 CI 另追加实际终态，不伪造当前提交自身 SHA 或未来运行结果。
7. 只有第 3 节全部生产阻塞关闭后，才批准 C1 生产 32 面重建。
   所有面/GID、原轴和地区映射完整；训练、holdout、原生复测、序列化、打包都计数。
8. 最终对同一私有候选哈希在 Windows 11 安装/文件加载、DirectWrite、实际 Qt/Swirl
   backend、100/125/150/175/200% DPI、跨屏、字重、三轴、横竖/中英混排及性能实测。
   现有 128 MiB 应用字体上限若阻挡候选，先测量资源成本，不能删面或字形凑体积。

## 8. 本窗口执行记录

本轮只修改协调文档、交接入口和公共合成 CI 触发/PR 来源检查，
未修改任何字体算法、测试断言、容差、原始字体、Rust Core、UI 或动画。

- 独立 checkout 基线为 `e505326486202ad4c8e98bb8b66a17b4547c559f`，初始工作区干净。
- Python 3.12.14、fonttools 4.61.1、numpy 2.2.6、uharfbuzz 0.56.3。
- 本地 audit：6/6 通过。
- 首次全套回归：448 项、0 skip、1 个 error；原有
  `test_production_cli_preserves_legacy_and_explicit_nondiagnostic_metadata`
  的 `marker='absent'` 子进程超过原 20 秒限制。保留真实失败；同用例未改代码、
  未改 20 秒限制，定向复测 1/1 通过（2.272 秒）；全套原样复测 **448/448 通过、
  0 skip、30.253 秒、exit 0**。首次超时未被删除；这不是生产代码修复。
- 工作流 YAML 结构及机器比较通过：授权分支/base 正确；新增 PR 来源条件之外，
  三个 job 的全部原有内容、permissions、concurrency 与基线完全相同。
- 本地与独立只读复核均确认不扩大原件工作流，不吞 B1 失败，不把跳过算作通过。

后续实际提交、远端核验和终态在此追加；未结束/未审查项目不能作为通过证据。

### 8.1 管理基线已推送并回读

实际提交 [50dae9c56ae4f4a64ec18295a92466d4bd141df2](https://github.com/SOLHK/Swirl/commit/50dae9c56ae4f4a64ec18295a92466d4bd141df2)，
父提交为 e505；GitHub ref 更新采用 `expected_sha=e505...`、`force=false`，返回 success。
随后重新读取远端 HEAD、提交 compare 和本文件内容，均匹配。只有本文件、
`SWIRL_VF_NEXT_HANDOFF_20261020.md` 和 `.github/workflows/swirl-vf.yml` 三个文件变化。

该精确提交的 [39399304891](https://github.com/SOLHK/Swirl/actions/runs/39399304891)
已为 **completed/failure**：Python 448 discovered、441 passed、7 skipped，audit 6/6；
DirectWrite synthetic success；Apple job **118549729338** 仍实际报
`actual=849, expected=850.0, tolerance=0.03125`。原严格门槛未被绕过，后续严格
reconstruction smoke 没有因诊断步骤成功而被记成执行成功。

Apple 工件 **12253467177** 已实际下载，278,104 字节，ZIP SHA-256：
`c6ed99a9b062a2958f6a73bb0572288c1ab2f55dce0ac42730392f0992392c42`，
保留至 2026-10-27 09:15:55 UTC。Windows 工件 **12253711881** 的 GitHub digest 为
`74b0a9f2fed68608384181d9cd25042e46043f0bd898ec6d9c0c3731bd20f3c2`；
此处仅登记服务返回的 digest，不能混写为已下载核验。

Core implementation validation **39399304869** 已 completed/success；
Rust Core **39399304790** 在 09:24 UTC 仍 in_progress，不记通过。
最初交接中的两个未完成 Core run 39394872349 / 39394041948 已取得终态，见第 6 节。

### 8.2 第一阶段：固定 A3 数值输入合同

本次精确集成源提交：
`6dd81c0cfd6cf2794584210bee7def55aef20e90`，源父提交为 e505；
目标父提交为 `50dae9c56ae4f4a64ec18295a92466d4bd141df2`。
在独立 worktree 上执行正常双亲 merge candidate，只有以下三个新增文件，无冲突：

- `.github/workflows/swirl-vf-a3-input.yml`
- `tools/swirl_vf/platform/axis_a3_input_cases.py`
- `tools/swirl_vf/tests/test_axis_a3_input_cases.py`

已读完整源码与测试；保留 binary64 请求、float32 与 Fixed16.16 碰撞的区分、
独立对照、原始轴标签、raw avar 顺序与固定 holdout。没有改生产映射、旧测试、容差、
共享文件或字体内容。该阶段只完成数值合同，native/production 接受仍为 false。

实际验证：

- 源 SHA CI [39398618327](https://github.com/SOLHK/Swirl/actions/runs/39398618327)，
  job **118547460910**：completed/success，17/17，0 skip；该工作流没有工件。
- 独立专项本地复核 17/17，0 skip。
- 目标 50dae9c + 源 6dd81c0 的完整候选回归：**465/465 passed、0 failure、
  0 error、0 skip，33.408 秒，exit 0**。依赖版本与第 8 节一致，包含真实 HarfBuzz 执行。
- 合并候选 audit **6/6**、0 skip，`git diff --check` 通过。
- 数值合同集成不关闭 A3 条件障碍；B1 849 vs 850、0/32 面、无正式 TTC 均保留。

源分支在审核期间已继续推进。`22a89a154217c5a4ea65788d2994e99e816ffabf`
已获得独立原生诊断审查，但不属于本次固定 6dd81c0 合并；更新 tip 9dd2676
同样不能因分支名相同而自动进入候选。每个后续阶段另做 diff、测试和记录。

### 8.3 C1 在 110d903 的阻断审查

精确提交 `110d903ac95a0e793911610a0c99c061d199df8a` 是新增 pack/validate/preflight
基础设施阶段，不能只描述为上轮 macOS 修补。新增 C1 staging、fixture、preflight、
contract/pack/validate 测试及专项审查文档归 C1 主责；未改共享 rebuild/hvf/extractor。

[39399445734](https://github.com/SOLHK/Swirl/actions/runs/39399445734) 最终 **failure**：
Linux job 118550192611 与 macOS 118550192970 的 C1 专项均 110/110、0 skip；
Linux 全套 558 discovered、551 passed、7 skipped，audit 6/6。
macOS 测试将自有临时根 `resolve()`，保留任意 staging 路径的 symlink 拒绝，修复已核实。

Windows job **118550193381** 实际 110 discovered、100 passed、3 failures、7 errors。
七个 error 均在 packer 读取 SFNT 前的 `source_changed_before_open`：路径 `lstat`
与 handle `fstat` 的 `(st_dev, st_ino, st_size, st_mtime_ns, st_ctime_ns)` 比较不等。
日志未记录具体哪个字段不同，不能假称根因已定位。三个负例因同一提前错误失去目标覆盖。
必须先取得 Windows 实际字段对照，保留身份、SHA、table checksum 与复制前后完整性检查。

旧 `test_ttc_staging_store.py` 的 symlink 创建失败后 Windows `return` 仍存在；
独立故障注入已复现 testsRun=1、success=True、skipped=0 而关键断言未执行。
必须改为明确的覆盖结果并取得实际保护测试，不能用 silent-return 计通过。

另核实两项原创重现：当前共享 rebuild 的 GDEF VarStore referenced delta **25→50**，
以及旧 whole-face manifest 的 stale writer 丢掉已确认 face entry。重现测试通过代表
缺陷存在，不是修复完成；C1 没有擅自改共享实现，两项均列为开放生产阻塞。
preflight 继续 BLOCKED/exit 2、0 面、font_generated=false、production=false。
**本阶段不合并，等待 C1 owner 的修复提交及三个系统终态。**

### 8.4 D1 首次提交的阻断审查（后续修复见 8.8）

精确提交 `562cbc998d03ad36c7e8b25fa7c614a3b17168ae` 新增九个文件：原创精度夹具、
DirectWrite/Qt 探针、PowerShell/CMake、专项 tests/workflow/说明，均归 D1 主责；
没有修改 Core、应用 UI 或共享源文件。

[39399001699](https://github.com/SOLHK/Swirl/actions/runs/39399001699) 两个系统最终 **failure**。
Server 2025 在 CMake configure 阶段失败：强制使用的 Visual Studio 17 2022 generator
未安装，因此不能说已运行此系统的 native probe。Server 2022 编译并执行了部分真实
DirectWrite/Qt 实验；四个 Qt FreeType private/installed、forward/reverse 探针各输出
12 条观察后报 `Identical API inputs produced different actual pair outputs`。

另有必须修复的独立反序验证漏洞：Qt 探针在构造 `QGuiApplication` 后才读取
`app.arguments()` 中的 `--reverse`；Qt 把它作为内建 RTL 选项消费。工件中四个
名为 reverse 的 Qt run 实际 header 都是 `reverse:false`，case 顺序与 forward 相同。
DirectWrite 反序正常，不能替 Qt 抵消这项缺口。应改用独有参数或先解析，并由 harness
核对请求的顺序与实际 header/完整 case 顺序；现有 `PASS_QT_SYNTHETIC` 不能证明反序。

已下载 ZIP SHA-256：Server 2022
`9c84239a7b50044730b311c49a8a589880214e8b905754baa7aeaff8bfdfcdeb`；
Server 2025 `f39146d519a544c642d99b9fa6dc9cd731e21388300196192371ba246e2d191c`。
**本阶段不合并，等待 D1 owner 修复真实失败、反序覆盖与 runner 构建选择。**
Windows 11、实际 Swirl、DPI/安装/成品语义验收继续未完成。

### 8.5 A3 第一阶段已推送及实际集成 CI

实际 merge [bbb79c1e5038d9cfe6b88954094833bae6f7cd4e](https://github.com/SOLHK/Swirl/commit/bbb79c1e5038d9cfe6b88954094833bae6f7cd4e)
的双亲为 50dae9c 与完整源 6dd81c0；完整 SHA 分别见上节。GitHub tree 与本地候选
`git write-tree` 完全相同；`force=false`、预期旧 HEAD 更新返回 success。
远端 HEAD、双亲和 compare 已回读：只有三个 A3 新文件与本文件变化，未覆盖并发代码。

[39400874977](https://github.com/SOLHK/Swirl/actions/runs/39400874977) 已 completed/failure。
Python job **118554973331**：465 discovered、458 passed、7 skipped，audit 6/6；
DirectWrite **118554973309** success；Apple **118554973496** 仍为同一
`actual=849, expected=850.0, tolerance=0.03125` 失败。
本地 465/465、零跳过与 CI 的七项可选跳过分别登记，不互相偷换。

两份工件均已下载并核对 SHA-256：

| Artifact | ZIP SHA-256 | 保留至 UTC |
| --- | --- | --- |
| Windows 12254923261 | `4ceb7d02dfd61738288fcdf97e5e6e18f17e695fb36c4496825d55c6d7405e2f` | 2026-10-27 09:29:16 |
| Apple 12254718190 | `199bdfb0e71a128e15a4f3c7c986e56fc91f7447882262ee874ea8a661f90169` | 2026-10-27 09:29:01 |

另已实际下载并核验 50dae9c 的 Windows 12253711881，哈希与 8.1 的 API digest 相同。
09:30 UTC，bbb79c1 的 Rust Core 39400874981 与 Core implementation 39400875148
尚在运行；此前 50dae9c 的 Rust Core 39399304790 也尚在运行，均不记通过。

### 8.6 第二阶段：固定 A3 三轴 HVAR 原生诊断

本次精确源提交 `22a89a154217c5a4ea65788d2994e99e816ffabf`，源父提交 6dd81c0；
目标父提交 `bbb79c1e5038d9cfe6b88954094833bae6f7cd4e`。
仅新增以下三个 A3 专属文件及更新本记录，无共享源码修改、无冲突：

- `.github/workflows/swirl-vf-a3-hvar.yml`
- `tools/swirl_vf/platform/probe_axis_a3_hvar.py`
- `tools/swirl_vf/tests/test_axis_a3_hvar.py`

已逐文件审查完整代码、测试、阈值和公开字段。所有候选公式、34 个位置、27 格邻域
在原生启动前声明，不拟合逐点修正。源 SHA 的导入依赖与合并候选相同。
目标候选完整回归 **479/479 passed、0 failure/error/skip、53.640 秒、exit 0**。
候选 audit **6/6、0 skip**，`git diff --check` 通过。

源 CI [39398883017](https://github.com/SOLHK/Swirl/actions/runs/39398883017)
已 completed/success；unit job **118548334102** 14/14、0 skip；
原生 job **118548435545** 在 xcode-27 实际执行；日志 checkout 均为完整源 SHA。
工件 **12254500323** 已下载：ZIP 55,318 字节，SHA-256
`63f4f3c36a37a9690efcf2bdc754fad9d3659d6fb83c0ed9f8a6a91d1db542b1`；
`hvar.json` 2,900,094 字节，SHA-256
`cfcab697ff93d6756e1fb2840d4836428f2bf8a37f85752a4d70f4be1a0ae84a`。
保留至 2026-10-27 09:13:11 UTC；源字体、生产 Swift 和生成 harness 的身份均已核对。

实际范围为面 18、34 个位置、5 个 GID（5/12/56/169/19177）、三种构造的正反序
共六个独立进程。每进程核验 32 面身份；总计 408 次请求、2,040 条 glyph 记录，
**1,020/1,020 反序 payload 精确相同、204 批 replay 零失败**；
只有 **60 次唯一直接 HVF 调用**，缓存复用比较数不冒充独立调用。

原 `fresh_triple_7` 的六种截断候选仍保留 HVAR 最大误差 0.01220703125，
该点现已直接比较 HVF/CoreText。nearest 在该点的有限 metric/直接轮廓对照为零，
但每构造 34 个位置仅 **32/34** HVAR 精确；两个新 holdout 仍有
0.003303971141576767 与 0.01220703125 误差。因此不是通过的全局映射。
其每构造 170 项 portable 比较均在原 1/32 内，最大约 0.014040801358532917，
属于有限预算内比较，不能改称精确或连续空间等价。

工件只含坐标、原轴/avar 顺序元数据、GID、误差、计数和 hash；不含字体、二进制表、
轮廓命令/点或原始绝对 advance/bounds/API metrics。原始 avar 元数据确实存在，
因此不描述为“无任何原件派生元数据”。不重复公开上传该工件。
`mapping_accepted=false`、`continuous_space_accepted=false`、`font_generated=false`、
原件不变和 **0/32** 均保留。更新 tip 的其余阶段没有自动纳入本次合并。

### 8.7 B1 公开数据边界阻断（首阶段）

审查源 `9836e89130694fdc336c4f4d7de22259c51741f6` 发现
`b1_original_metric_check.py` 将原件逐 face/GID 的 raw native metrics、存储度量及
逐字形比较写入详细报告，并进入公开 CI stdout/artifact。这超出聚合误差/计数汇总范围，
与用户的衍生私有数据禁公开要求及工具 README 的公开边界不符。
不在本记录重述原始数值，不复制或重新上传这些报告，**该阶段不合并**。

B1 须把原件详细观察保留在授权私有环境，公开产物采用明确的聚合安全字段白名单，
测试必须证明原始度量/逐 GID 记录不会进入 stdout/artifact，同时保留真实失败结论。
技术上已有的严格 849 vs 850 仍失败；诊断执行成功不能关闭 B1。
09:32 UTC 的后续 HEAD `d283e2e5ad8d43aa3808e66ac6093c3252c5d9e0` 另行复审，
不能先假定后续提交已解决数据边界。复审已确认该提交没有修复公开输出，反而将原件
60 个逐 GID 记录写入 `docs/evidence/swirl-vf-b1/stage1/original-summary.json`，
并由同目录 `strict-job-118551394339.log` 重复公开；相关内容已进入源分支 Git 历史。

首个已核实公开入口为 run **39399674995** / job **118551394339** 的
`B1_ORIGINAL_SUMMARY_JSON` stdout，以及 artifact **12255036417** 中的
`b1-original-metrics.json`。记录真实不等于适合公开。该文件包括 60 行原件观察，
本记录只登记文件身份与数量，不复述其原始数值。B1 必须先修公开 schema 和输出路径；
仓库维护者还需处理已经公开的 CI 工件/日志和 Git 历史，追加删除文件不能抹除旧历史。
本窗口不擅自删除其他窗口证据、不重写源分支历史，不把含该数据的祖先合并入集成分支。

### 8.8 D1 第二次提交的真实修复与剩余失败

精确源 `47d6dfc06fa2fddddd1532c1d8370028a6b9da17` 的
[39400461390](https://github.com/SOLHK/Swirl/actions/runs/39400461390) 已 completed/failure。
Server 2022 job **118553585274**、Server 2025 **118553585584** 均实际编译和执行。
31/31 Python tests 本地及 CI 通过；新 `--reverse-order` 的 header 和实际首轮顺序
已从工件验证，Server 2025 工具链发现也已验证。8.4 的这两个问题已修，不再作为当前失败。

每个 Server 的 16 个 native 进程中，12 个通过，4 个 Qt FreeType 失败。
同一 API 位模式的 pair 在 forward/reverse 下产生相反的 **1/64 px** 路径差异；
独立诊断在相同请求的 raster 前后观察到路径变化。原始 advance/metrics/raster 相同，
raw path/含路径的布局字段不同。这是所测路径的状态相关差异，不是恢复被量化的小数精度。
不得通过预热、扩大容差或删比较制造通过。

新增分析器另将合法的单一 MoveTo 空格路径错误要求为 `[]`；独立调用分析器核验
真实成功 JSONL 已复现误拒绝。需要按空路径语义增加回归，不得放宽可见轮廓断言。
这项被总报告 FAILED 的提前退出遮住，修主失败时仍须同时处理。

已下载工件：2022 **12254492969**，ZIP SHA-256
`e01ba6a4b6a26fa88c9da81a87c9a4bb105b6e41da5c2c2ada7293694dbbcab4`；
2025 **12254657939**，
`365110cfb1a998aa1eb534454f5a527ac94cd1bf9ab8e16d227ee5029c6961e5`。
两者来自原创六字形夹具，不含 Apple 字体或私有衍生数据。
仍暂不合并。专项 workflow 的 D1-only branch/job 条件和未覆盖的实际编译依赖
也须在后续集成时修正；不能把 Windows Server 的有限成功外推为 Windows 11/Swirl 验收。
