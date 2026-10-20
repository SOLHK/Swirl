# A3 续报：归一化运算顺序、读回损失与真实诊断修复

## 已完成的结论

**本轮用独立 Apple 原生样本否定了“相同 canonical 读回必然复现相同几何”的全局假设。** 两个新算术候选的水平 HVAR 在 201 个位置全部为零，但新 face 30 三轴点仍有直接 HVF 几何误差，且原始请求与 canonical replay 的五个字形 payload 全部不同。读回检查在这个反例上通过，因此必须保留完整 payload 回放验证。

同时修复了 A3 新诊断器与真实 fontTools 表标签类型不兼容的问题。修复后的原生复跑证明：48 个默认轴省略批次可在完整证据下解释，另外 8 个真正不稳定或 payload 不同的批次仍拒绝。没有修改生产构造器、生产映射或生产 guard。

原有输入碰撞的条件性下界继续成立：`499.006199 / 499.006201` 先坍缩为相同目标状态时，最小最坏 advance 误差至少 `0.27374267578125 FUnit`，超过原 `1/32 FUnit` 门槛。新诊断不会恢复已经丢失的信息。完整旧证据与规范分层见 [原 A3 交接](axis_a3_handoff_20261020.md)。

## 提交、CI 与不可改写的原始证据

| 阶段 | 完整源码提交 | CI | 实际状态 |
|---|---|---|---|
| 新算术顺序与入口审计 | `eda37d1c733cb1ced283583434e4123824a2147c` | [39404600942](https://github.com/SOLHK/Swirl/actions/runs/39404600942) | CI success，完整原生运行；新分类器 804 个批次全部提前拒绝 |
| D1 独立安全证据 | `37ca8f8d9cca15e6bee6dd3a8761fc71dab48156` | [39404664873](https://github.com/SOLHK/Swirl/actions/runs/39404664873) | CI success，139 项 A3 加 12 项既有输入测试 |
| 真实 Tag 表键修复与原生复跑 | `9c2fd0092284edc7d346b0c9e1d1208095429b39` | [39405368777](https://github.com/SOLHK/Swirl/actions/runs/39405368777) | CI success；748 strict pass、48 default equivalent、8 rejected |

[首轮原始 ZIP](axis_a3_arithmetic_native_eda37d1.zip) 与 [修复复跑原始 ZIP](axis_a3_arithmetic_native_9c2fd00.zip) 均只含完整安全 JSON，没有重新序列化报告或修改失败。ZIP、JSON、artifact、源码 SHA 与计数见 [独立证据清单](axis_a3_arithmetic_evidence_20261020.json)。两份 JSON 的 SHA256 分别为：

```text
64483c46413e2ed0fe33731ef75dd22132a59a0da112bf791c0bff950da86f4d
d5ea884cdd1c7ffdf0efdf2dd264c3ee05d69550b55d2319565c6d5ebe9201c6
```

复跑与首轮的逐字段比较只允许 `source_commit` 和每个 mode 的 `default_omission_checks` 改变。其他全部值相同，包括所有原生观测、模型残差、旧 strict replay 失败、原表、入口审计计数和构造间比较。首轮分类器失败没有改写成通过。

每次运行使用同一个 61,473,880 字节原件，SHA256 为 `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`。环境为 macOS 27.0.1 arm64、Build `26A434`。每个原生进程校验全部 32 个物理 face、完整表身份、summary、EOF、退出状态，并核验源文件未变。

## 冻结队列与实际工作量

候选和完整输入在启动原生进程之前已固定。201 个标签包含 193 个唯一 `(face, location)`；其中 8 个重复标签来自明确保留的 exact-default 三轴位置，没有悄悄去重。

| 队列 | 标签数 | 用途 |
|---|---:|---|
| 新随机三轴点 | 64 | 32 faces，每 face 两点，固定新 seed |
| 新 normalized16 整数边界 | 36 | 四种原轴范围，各轴的 below / at / above |
| 默认值相邻边界 | 60 | 原始 nextafter 与 ±0.0001，保留全部 binary64 |
| 历史控制 | 41 | 全部 39 个旧 A3 非零位置加原输入碰撞两点 |

160 个新标签对应 152 个唯一新位置。历史控制用于回归，不能冒充独立 holdout；旧 141 项原生闭合子集没有重跑。

两种原始 anchor × 正反序 × original/replay × 五个 GID，实际完成：

- **8,040** 条原生字形记录，四个进程各 402 请求、2,010 字形，均 error 0、exit 0。
- **1,608** 次 constructor-entry binary64 审计，三轴位模式全部与发送值相同。
- **4,020 / 4,020** 对正反序比较完全相同。
- **804** 个 strict replay 批次。
- 93 个预先选定的直接 HVF 位置；每个 mode、每个模型 186 次 glyph 比较。按 `(face, GID, WDTH, wght, HGHT)` 缓存后实际调用 libhvf 160 次。

入口审计位于原始 `anchorInstance` 调用前。它证明提交到构造调用的 Double 位模式保持，不声称看到了 CoreText 私有内部状态。独立进程和反序也不声称清空了系统缓存。

原始轴顺序和范围没有改动。32 faces 的 560 条原始 avar 记录、重复 from 及 raw avar SHA 与旧 identity 原生报告逐项相同。

## 新算术候选的实际结果

设 `T(x)=trunc(x×10000)/10000`，旧 canonical 为 `C=T(T(x))`。三个候选只在**原始 avar 严格恒等的负半轴**改变运算顺序；正半轴保留 binary64，非恒等轴保留旧 float32 规则，后续 normalized16 向零截断、原表序 avar、nearest F2DOT14 不变：

| 简称 | 恒等负半轴的归一化表达式 |
|---|---|
| ENDPOINT | `float32((C-min)/(default-min))-1` |
| OFFSET | `float32(1+(C-default)/(default-min))-1` |
| DIVSUB | `float32(float32(C/span)-float32(default/span))`，`span=default-min` |

这些是明确可证伪的外部模型，不是对 Apple 内部指令序列的观测。没有根据 face、GID 或实测误差挑选分支。

| 模型 | 新 160 标签 HVAR 精确 | 历史 41 标签 HVAR 精确 | 全部最大 HVAR 误差 | 直接 HVF 最大误差 |
|---|---:|---:|---:|---:|
| 旧 binary64 / normalized16 truncate | 159/160 | 22/41 | 0.01220703125 | 0.01195928536685642 |
| 旧 float32 / normalized16 truncate | 159/160 | 21/41 | 0.01220703125 | 0.012252664064817509 |
| ENDPOINT | 160/160 | 41/41 | 0 | **0.009678105302214135** |
| OFFSET | 160/160 | 41/41 | 0 | **0.009678105302214135** |
| DIVSUB | 159/160 | 41/41 | 0.01220703125 | 0.011477029436264274 |
| 全轴 float32 offset 失败对照 | 159/160 | 39/41 | **0.5474853515625** | **0.45322963787256754** |

ENDPOINT/OFFSET 在本轮全部完整设计向量相同，不能据此区分两条公式。它们在 93 个直接 HVF 位置中只有 92 个精确；新位置 51/52、历史位置 41/41。HVAR 201/201 不能替代几何精确性。

Portable 比较还保留实际浮点误差：除下文新 face 30 外，其余 1,000 次 glyph 比较中有 990 次非零，范围约 `5.684341886080802e-14` 至 `4.547473508864641e-13`。这些值没有归零。类型化 legacy 比较中的 `segment_types_differ` 也保留；保留原 Q 控制点的比较有自己的结果，没有覆盖 legacy 失败。

## 新反例一：相同读回，五个 glyph 的 replay payload 全部不同

`face 30 / arithmetic_fresh_30_0` 未参与候选建模：

| 阶段 | WDTH | wght | HGHT |
|---|---:|---:|---:|
| 原始 binary64 输入 | 729.2925740388073 | 660.9898707384746 | 303.5934274824121 |
| 原实例读回及预声明 canonical | 729.2925 | 660.9897 | 303.5933 |

六个模型都预测完整 `q=(7513,5275,-6449)`。四个水平 HVAR 控制误差全部为 0；直接 HVF 对原始 CoreText 的误差却为：GID 5 `0.008711728120943008`、GID 19177 `0.009678105302214135 FUnit`。

两种 anchor、两种请求顺序中，原始与 replay 的读回均通过旧严格规则，但 GID 5/12/56/169/19177 的 `commands`、`bounds` 全部改变；除 GID 12 外还改变 `lsb`。修复后的分类器仍以 `native_replay_payload_not_exact` 拒绝这些批次。

这给出一个明确的 API 边界：**不能把 `CTFontCopyVariation` 的读回值当作原始实例的无损状态键。** 即使把这个读回值重新交给同一原生构造流程，也可能得到不同几何。

首轮及复跑报告没有发布“原始对 replay”的数值几何距离。上述 `0.009678…` 是 HVF 设计参考对原始 CoreText 的误差，不能改写为 original/replay 之间的差值。

## 新反例二：canonical 再次读回仍会改变

`face 22 / arithmetic_fresh_22_0` 的原始三轴为 `(208.47406722792215,300.3333369872149,1.1280770592536593)`，预声明 replay 为 `(208.474,300.3333,1.1279)`。原始读回 HGHT=1.1279，replay 读回 HGHT=1.1278；五个 glyph 的 payload 在这个点没有改变。

因此这属于 `native_readback_replay_not_exactly_stable`，与 face 30 的 payload-only 失败不同。不能以 payload 相同忽略读回稳定性，也不能以读回稳定忽略 face 30 的 payload 差异。

## 新边界与补齐的直接 HVF 证据

face 0 的 `WDTH/HGHT=176.10237966308594` 新边界，canonical 为 176.1023。ENDPOINT/OFFSET 给 q=-10634，DIVSUB 给 -10635。WDTH 的 DIVSUB HVAR 误差为 0.01220703125，直接 HVF GID 5/19177 为 `0.00710927749929624 / 0.011477029436264274`。HGHT 的四个 HVAR 仍为零，但直接 HVF 为 `0.008711729480296526 / 0.009678105301986761`。两个点的 ENDPOINT/OFFSET 直接 HVF 都为零，预声明边界确实区分了公式。

旧 face 12 `identity_fresh_12_1` 本次补上直接 HVF：完整 q `(10237,6362,2366)` 的 GID 5/19177 均为零；旧 float32 的 WDTH q=10238 则为 `0.00710072018603114 / 0.012252664064817509`。这部分现在有真实原生几何证据，而不再只有 HVAR/portable 数据。

## 真实诊断修复与默认轴省略边界

首轮新 helper 错误要求表标签满足 `type(tag) is str`。实际生产 `source_identities()` 保留 `SFNTReader` 的 `Tag(str)` 键；该字符串子类因此被拒绝。修复仅改为 `isinstance(tag,str)`，仍要求四字节 ASCII 标签、合法 SHA256、全部表键及每个 digest 与独立原生身份精确相等。

新增真实 `FontBuilder → 内存字体 → TTFont/SFNTReader → source_identities` 回归先复现失败，再证明两类有效诊断均可走完；缺表、多表、错误 hash、非法标签与 payload 变化仍拒绝。合成 fixture 无 Apple 轮廓且不写字体文件。

修复复跑的 804 批分类为：

| 分类 | 批次 | 含义 |
|---|---:|---|
| `STRICT_REPLAY_ALREADY_PASSED` | 748 | 原严格规则已通过 |
| `DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH` | 48 | 原非默认输入的预声明 canonical 恰为原默认值；所有输入 bits、原表、完整 GID 和 payload 回放精确 |
| `REJECTED`：读回不稳定 | 4 | 新 face 22，两个 anchor × 两顺序 |
| `REJECTED`：payload 不同 | 4 | 新 face 30，两个 anchor × 两顺序 |

48 个默认省略诊断仍携带旧 `FAILED_FINITE_REPLAY / native_nondefault_axis_not_reported` 结果；没有修改成旧规则通过。该分类只对实际完整 batch 成立，不外推到其他字形、轴位置或生产构建。

## Windows 交接的实际进展与缺口

[独立 D1 安全摘要](axis_a3_windows_evidence_20261020.json) 绑定原生源码 `41504fed7ec7ca6d4768389106a03aa9bc5cd36e`、证据提交 `4c0fcaf4a66fd34d3487754dd2f849a278da3a3e` 与 [CI 39401509155](https://github.com/SOLHK/Swirl/actions/runs/39401509155)。D1 原 CI 结论仍为 **failure**。

Windows Server 2022/2025 的完整合成字体观测各 3,568 条；两系统旧输入对有 512 次完整 payload 配对，差异 0。跨系统 3,568 对完整观测也相同。但 D1 使用 `WDTH=HGHT=100` 及不同轴范围，不能替代 A3 Face15 的完整 `(500,wght,500)` 契约。Qt FreeType 的八个实际失败进程、固定对象在 raster 历史后出现三种路径形状、未直接序列化 actual-FLOAT bit 数组的追踪限制都保留。

窗口 5 仍需测量另外两组 A3 精确输入对，以及实际 Windows normalized setter 的 glyph/geometry 行为。现有 [Windows 契约](axis_a3_windows_contract.json) 只追加已核验摘要引用，所有原始未测字段和严格门槛不变。

## 可以交给生产负责人的结论

1. 保留原始 binary64，且不得用标准用户 16.16、FLOAT 或 native readback 提前替换它；不同阶段的信息损失已经各有实测反例。
2. 新默认省略分类器已有真实原生有效与拒绝证据，但只是诊断提案，完整 payload guard 必须继续保留。
3. ENDPOINT/OFFSET 可解释本轮所有水平 HVAR，仍被新几何反例否决为完整精确映射。不能因为最大误差小于 1/32 就称为精确。
4. 设计计算与最后读回截断可能处于不同阶段，是下一条可独立证伪的假设；当前证据不能唯一定位 Apple 私有运算顺序。

**此续报不宣布生产映射通过、连续全空间精确或最终字体验收。没有生成或发布 Apple 来源字体及来源轮廓。**
