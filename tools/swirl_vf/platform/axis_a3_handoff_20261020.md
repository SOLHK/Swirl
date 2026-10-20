# A3 交接：用户输入分辨率、构造路径与 avar 精度（2026-10-20）

同日后续的独立 201 标签原生实验、相同读回但 replay 轮廓不同的新反例、真实 Tag 类型诊断修复及 D1 证据审计，见 [A3 算术与读回续报](axis_a3_arithmetic_handoff_20261020.md)。本页及原六份 ZIP 保留先前阶段的完整结论，不以新结果覆盖旧失败。

## 当前结论与边界

**输入提前坍缩时的条件性障碍已经成立；通用的 Apple 用户坐标到设计坐标精确映射仍未完成。** 本轮找到原非精确三轴点的局部原生零误差坐标，同时用未参与建模的样本否决了两种可疑的全局修复。真实 Linux normalized API 可以传递两个不同的设计状态，但这不等于已经求出了原字体的全空间映射，更不等于 Windows、Qt/Swirl 或最终字体通过验收。

本窗口使用 `work/vf-axis-a3`。启动时主线程已核验最新集成分支 `work/core-completion-20261017` 的 HEAD 为 `e505326486202ad4c8e98bb8b66a17b4547c559f`，确认专用远端分支不存在后创建；没有覆盖其他窗口的分支。旧 141 项已经有有限样本闭合证据，本轮没有重做该子集。修改范围为 A3 专用实验、测试及独立工作流；`rebuild.py`、`coretext_extract.swift`、共享交接文档和生产映射未修改。没有发布 Apple 字体、来源轮廓或接受新的生产映射。

下文严格区分：原生诊断执行完成、某些数值严格相等、样本误差在 `1/32 FUnit` 内、生产映射通过、最终字体验收。前三项不能替代后两项。所有测量仍使用 `1/32 = 0.03125 FUnit`；没有扩大门槛、改变原轴范围、平滑跳变或添加按样本选择的例外。

## 证据索引与可重现来源

Apple 原件 SHA-256 固定为 `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`，长度 61,473,880 字节。新 Apple 原生实验均在 macOS 27.0.1 arm64、Build `26A434` 上运行，每个 CoreText 字形观测进程验证全部 32 个物理 face 的来源身份，并检查 summary、EOF、退出状态及实验前后源哈希。反序独立进程不等于清空系统缓存。

| 证据 | 完整源码提交 | CI 与状态 |
|---|---|---|
| 已有输入坍缩反例 | `53ca5ff74e17bfc65e338b460fa2fc4df3801c1d` | [39394042127](https://github.com/SOLHK/Swirl/actions/runs/39394042127)，已完成 |
| 原创输入表示与边界控制 | `6dd81c0cfd6cf2794584210bee7def55aef20e90` | [39398618327](https://github.com/SOLHK/Swirl/actions/runs/39398618327)，success；17 项新测试及 12 项既有输入反例测试，仅数值控制 |
| 三轴 HVAR 局部诊断 | `22a89a154217c5a4ea65788d2994e99e816ffabf` | [39398883017](https://github.com/SOLHK/Swirl/actions/runs/39398883017)，success |
| 九构造路径与输入表示 | `924734943b1da5550c5093a2ae7c50957778fc4d` | [39399731052](https://github.com/SOLHK/Swirl/actions/runs/39399731052)，success |
| identity-avar 独立反证 | `0c603aad04786d4e89cbb6399fc60b06cac7c58a` | [39400020900](https://github.com/SOLHK/Swirl/actions/runs/39400020900)，success |
| A3 安全错误码修复及构造复跑 | `9dd26766f949ded4e5fa8253fc44ae4639a95ea9` | [39400374910](https://github.com/SOLHK/Swirl/actions/runs/39400374910)，success；除 `source_commit` 外与首次构造报告逐字段相同 |
| Linux normalized API 实验 | `d22be86b56cd20a257505be569a21fcea3ef2bbf` | [39400961369](https://github.com/SOLHK/Swirl/actions/runs/39400961369)，success；6 项测试、0 skip |

完整报告哈希、ZIP 哈希、artifact ID 与运行身份见同目录 [证据清单](axis_a3_evidence_manifest_20261020.json)。安全 JSON 归档分别为 [输入分辨率](axis_a3_native_resolution_53ca5ff.zip)、[HVAR](axis_a3_native_hvar_22a89a1.zip)、[首次构造](axis_a3_native_construction_9247349.zip)、[identity 反证](axis_a3_native_identity_0c603aa.zip)、[构造复跑](axis_a3_native_construction_9dd2676.zip)、[normalized API](axis_a3_native_normalized_d22be86.zip)。归档保留失败、非零误差、原始轴元数据和表序；不包含 Apple 字体及原始字形 payload。

## 原始三轴与重复 avar 记录

轴顺序始终为 `WDTH, wght, HGHT`；32 个 face 的 WDTH、HGHT 均为 `(min, default, max) = (1, 500, 1000)`。wght 的原始范围为：

| face 索引 | wght 最小值 | 默认值 | 最大值 |
|---|---:|---:|---:|
| 0–4、10–14 | 100 | 501 | 900 |
| 5–9、15–19 | 100 | 499 | 900 |
| 20–23 | 100 | 500 | 600 |
| 24–31 | 100 | 500 | 900 |

WDTH、HGHT 的原始 avar 均为三点恒等映射。face 15/18 的 wght 是以下 **13 条原始 F2DOT14 整数记录**，括号内为 `(from, to)`，顺序没有整理：

```text
(-16384,-16384), (-16384,-13369), (-12288,-9371), (-8192,-6356),
(-4096,-3080), (-40,0), (0,0), (0,65), (4096,3211),
(8192,6488), (12288,9830), (16384,13107), (16384,16384)
```

face 20 的原始七条记录为 `(-16384,-16384), (-12288,-13107), (-8192,-9830), (-4096,-4915), (0,0), (16384,3276), (16384,16384)`。其余 face 的完整原表保存在 identity 证据的 `original_faces`。

[OpenType avar 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)要求不同、递增的 fromCoordinate，并允许忽略不递增记录。因此这些原始重复记录的 Apple 行为不能仅凭一般规范推导，也不能以字典覆盖、排序去重或平滑插值代替实测。原表保存与目标字体能否直接采用该表是两回事。

## 输入坍缩的严格条件性下界

face 15、其他两轴为 500 时，保留已有原生反例：

| 原始 wght | binary64 bits | 标准 16.16 整数 | float32 bits | 原生读回 wght | 条件 HVAR 设计 q |
|---|---|---:|---|---:|---:|
| 499.006199 | `407f3019641f6449` | 32702870 | `43f980cb` | 499.0061 | 0 |
| 499.006201 | `407f30196638433d` | 32702870 | `43f980cb` | 499.0062 | 65 |

q 表示设计坐标乘 16384，不能当成 `CTFontCopyVariation` 返回的用户坐标。已有 35 GID 中 31 个 payload 不同，GID 5 水平 advance 差 `Δ = 0.5474853515625 FUnit`；本轮五个 GID 的原生构造实验再次保留此差异。

如果确定性目标收到完全相同的输入状态，且没有其他可区分信息，它对两输入只能产生同一个 advance `a`。三角不等式给出：

```text
max(|a - a_low|, |a - a_high|) >= Δ/2
                              = 0.27374267578125 FUnit
                              = 8.759765625 × (1/32 FUnit)
```

所以在这个条件下，两者不可能同时满足原门槛。[OpenType 归一化规范](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization)规定归一化前转为 16.16、归一化及 avar 运算使用 16.16、最后得到 2.14；若目标在该入口先合并两值，后续确定性表映射无法恢复丢失的信息。float32 用户入口对这对输入也产生同一状态。

这不是“F2DOT14 无法表示 q=65”的证明，也不是“所有实现都不能兼容”的证明。保留原始 binary64、独立求出正确设计坐标后，通过 normalized API 提交不同 q，不满足上述输入相同的前提；但独立求 q 的通用算法仍是未解决部分。

## 九种构造路径：实际数值、读回与 payload 分开判断

[构造 driver](probe_axis_a3_construction.py)冻结了 100 个带标签位置（69 个不同的 face/location），覆盖 face 15/18/20 的原始碰撞、独立表示对照、默认值相邻 binary64、十进制边界、原 avar 记录邻点及九个 fresh 三轴点。18 个 CoreText 观测进程共 18,000 条字形记录；每模式 1,000/1,000 个反序比较完全相同。306 个编译后的 Swift scalar 控制与独立 Python 位模式／有理数参考全部相符，NSNumber/CFNumber 也保留了原始 bits，包括负零。

| 模式 | replay 失败 / 200 | 其中有 payload 改变的 batch | 同一原请求相对 copy64 不同的位置 / GID 实例 |
|---|---:|---:|---:|
| copy_binary64 | 56 | 0 | 0 / 0 |
| anchor_binary64 | 56 | 0 | 0 / 0 |
| anchor_binary32 | 154 | 2 | 2 / 10 |
| anchor_fixed16 | 120 | 4 | 1 / 5 |
| descriptor_bulk_binary64 | 56 | 0 | 0 / 0 |
| descriptor_forward_binary64 | 56 | 0 | 0 / 0 |
| descriptor_reverse_binary64 | 56 | 0 | 0 / 0 |
| graphics_binary64 | 166 | 0 | 3 / 15 |
| copy_cfnumber_float32 | 154 | 2 | 2 / 10 |

五种直接／descriptor binary64 路径的 56 个失败全部是 original 阶段的 `native_nondefault_axis_not_reported`，没有 payload replay 失败。28 个带标签位置因保留原 avar 重复标签，对应 18 个不同的 `(face, location)`。例如 face 15 的 `wght=499.0000999999999` 预声明 replay 为 499，原生读回 `{}`，q 为 0，五个 GID 的 original/replay payload 完全相同。现有验证器要求原请求的非默认轴必须显式出现，因此拒绝这些请求。**这是提交总负责人审查的读回接纳边界证据，不是已经批准的生产 guard 修复。失败不改写成通过。**

实际 payload replay 失败发生在显式有损路径。例如 `fixed_only_collision_high` 原值 `499.0062103271485` 经 float32 后提交 `499.0062255859375`，读回 499.0062；预声明 replay 的 499.0062 再经 float32 则成为 `499.006195068359375`，实际读回 499.0061，五个 GID 的 commands/bounds 改变。canonical replay 计划不能无条件移植到不同输入表示路径。该报告只保存 replay 差异字段，不补造未记录的数值差值。

graphics 路径在同一新输入上 q=0，而 copy64、anchor32 均为 q=65；最大 advance 差 0.5474853515625，五个 GID 均改变。它不能简单解释为“只转一次 float32”。各路径还存在构造和 optical 属性继承差异，故结果证明路径差异，不能唯一定位 Apple 内部运算顺序。49 个条件 HVAR q 也仅经过预算内支持检查，报告未保留其反推残差，不能称为 49 个零残差证明。

`9dd26766f949ded4e5fa8253fc44ae4639a95ea9` 修复的是诊断失败证据丢失：A3 本地 wrapper 仅提取精确白名单中的八个原生错误码，未知文本和 payload 不发布。23 项 constructor 测试通过；复跑报告除源码提交字段外与首次报告相同。此修复没有改变构造、映射或门槛。

## 原非精确三轴点：局部精确坐标找到，全局 nearest 被否决

face 18 原输入完整保留为 `(WDTH, wght, HGHT) = (395.1762070327519, 493.5928547043863, 579.3731774437933)`，实际读回 `(395.1762, 493.5928, 579.3731)`。HVAR 实验预声明 34 点、七个模型、27 个邻格，包含单轴隔离、回默认、相邻 binary64／用户16.16／归一化格及八个 fresh 三轴点；三种构造、正逆序共 2,040 条记录，1,020 个反序对及 204 个 replay 审计均稳定。

旧模型 q 为 `(-3441,-138,2601)`。GID 5/12/56/169 的 HVAR 绝对残差分别为 `0.007320106029510498 / 0.008234091103076935 / 0.007321648299694061 / 0.01220703125`；直接 libhvf 对 GID 5/19177 的几何误差为 `0.007109277499239397 / 0.011959285366742733`。这些真实非零误差仍然存在，不能因小于 1/32 而称为精确。

27 格内的 `(-3442,-138,2601)` 使四个 HVAR 控制及上述两个直接 libhvf 几何比较全部为零。仅保留 WDTH 的隔离点仍有 0.01220703125 HVAR 误差，仅保留 wght 或 HGHT 则为零；恢复 WDTH 默认值也消除误差。这将该点的差异定位到 WDTH 格点选择。HVAR 本身对高度不敏感：HGHT 再加减一格仍保持四个 metric 为零，但直接 HVF 几何不再为零。因此局部格点结果不能从四个 metric 单独推断。

全局 `canonical_float32_result_normalized16_nearest` 虽修复原点，只有 32/34 个 HVAR 检查精确：独立 `a3_fresh_holdout_1` 仍误差 `0.003303971141576767`，`holdout_5` 误差 `0.01220703125`。前者直接 HVF GID 5/19177 为 `0.012997507760019289 / 0.011085171032732433`。因此全局 nearest 不能作为精确修复；没有把原点改成按坐标选择的特例。

## identity-avar 规则：未参与建模的 100 点反证

[identity 实验](probe_axis_a3_identity_avar.py)仅在原始表结构严格恒等的轴上尝试直接 nearest F2DOT14，非恒等轴保留旧规则；同时比较 binary32 与 binary64 两种归一化结果。先冻结全 32 face 的 64 个随机三轴点、36 个边界点，再运行；另外保留三个历史控制。两个 anchor 各测完整 103 点，production 仅测三个历史控制，共 4,180 条记录、2,090 个反序对、418 个 replay 审计，全部稳定。

| 模型 | 新 100 点 HVAR 四控制全为零 | 三个历史控制全为零 | 新点最大 HVAR 误差 |
|---|---:|---:|---:|
| 旧 binary64 normalized16 truncate | 100/100 | 2/3 | 0 |
| 旧 float32 normalized16 truncate | 99/100 | 2/3 | 0.01220703125 |
| identity 轴 binary32 直接 nearest | 85/100 | 3/3 | 0.01220703125 |
| identity 轴 binary64 直接 nearest | 86/100 | 3/3 | 0.01220703125 |

两个新规则均修复历史控制，却在独立样本变差，已被否决为通用精确模型。所有这些有限误差仍在原门槛内，这与“精确失败”并不矛盾。旧 binary64 的 100/100 也不能抹去原 face 18 反例或证明全空间精确。

三个需保留的反例：

- face 23 `identity_fresh_23_0`，输入 `(445.1015723732783,356.79453207845853,498.73873997851086)`：旧 q `(-1802,-7038,-41)` 的 HVAR 和直接 HVF GID 5/19177 均为零；identity 规则改成 `(-1803,-7038,-41)`，HVAR 误差 0.01220703125，直接 HVF 误差 `0.007109277499239397 / 0.011959285366629047`。
- face 2 `identity_fresh_2_0`，输入 `(180.7568526190835,728.5226223501476,10.088478435611686)`：旧 q `(-10482,5274,-16085)`，identity 候选仅把 HGHT 改为 -16086。两者四个 HVAR 都为零，但候选直接 HVF GID 5/19177 为 `0.008711731281891844 / 0.009678105302214135`，旧坐标为零。**HVAR 零残差无法验收 HGHT。**
- face 12 `identity_fresh_12_1`，输入 `(812.4237777627202,690.8750329989548,572.2184188469829)`：旧 float32 的 WDTH q=10238，旧 double 为 10237；float32 的 HVAR 误差 0.01220703125、portable 几何最大 0.012252664064817509。此点不在预选直接 HVF 子集中，不能称已有直接 HVF 验证。

legacy 的类型比较失败与保留原 Q 控制点的独立结果均留在报告，没有删除原失败，也没有替换 1/32 控制点门槛。

## 可实现的 normalized 通道：实际 Linux API 证明及局限

[normalized 实验](probe_axis_a3_normalized_api.py)独立编写了只有两个字形、保留三轴范围的合成标准字体，仅在内存中使用，没有读取 Apple 原件。真实加载 HarfBuzz 8.3.0、FreeType 2.13.2；本地 Linux 实测后又在 Ubuntu 24.04 x64、Python 3.12.15 CI 重现。

HarfBuzz 的 design-float32 入口把两个原 wght 都读回为 `499.006195068359375`，合成 GID 1 advance 都为 500。外部已给定 q=0/65 时，[normalized 2.14 API](https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-var-coords-normalized)实际读回 `(0,0,0)`／`(0,65,0)`，原生合成 advance 分别为 500／565。[FreeType normalized 16.16 API](https://freetype.org/freetype2/docs/reference/ft2-multiple_masters.html#ft_set_var_blend_coordinates)实际读回 `(0,0,0)`／`(0,260,0)`；FreeType 部分只验证 getter，没有验证字形 metric 或轮廓。

本地 `/tmp/swirl-a3-normalized-api-proof.json` 的 SHA-256 为 `d9f04e0aa0310e07e670d0b0299a74b74b68c8993a077899e2ee35c9cdcb9eef`，其 `source_commit=null`，不能伪装成 CI 身份；上表中的 d22 提交 CI 已提供独立的提交绑定报告。

这证明了一个可用的通道：应用保留原始 binary64，并在信息丢失前独立确定 q，再向实际 normalized API 提交。它没有证明 Apple 全空间求 q、目标来源轮廓的重建、字体文件自身自动执行该映射、排版与光栅状态同步或 Windows 兼容性。不能把合成 advance 500／565 写成 Apple 字形数据。

## 窗口 5 与生产负责人交接

窗口 5 的独立契约在 [axis_a3_windows_contract.json](axis_a3_windows_contract.json)，保留三组表示分区对照、原始 binary64 bits、预期 float32／16.16 bits、Apple 对照、严格门槛和运行身份要求。Windows 实测仍由窗口 5 负责，不能用上述 Linux 或 Python 计算填充其观测。

窗口 5 应测量实际 `DWRITE_FONT_AXIS_VALUE.value` 调用前的 FLOAT bits、真实返回与字形输出；记录 Windows/build、架构、DLL/API、字体／face 身份和尺寸；执行 A/B/A 与逆序；将原用户坐标、实际 API 输入、读回、推断设计 q 分开。若尝试 normalized 路径，应分别验证 q=0/65 的保留、目标 HVAR／几何与排版／光栅状态一致，不能只凭 getter 验收。

生产负责人收到的是三类待审证据：默认坐标附近的读回拒绝边界、精确 normalized 传输通道、尚未统一解释的原生坐标选择。此次没有获批或实施生产接纳规则变更。后续应继续寻找能区分 WDTH/HGHT 运算顺序的独立原生反例，保留旧、新模型的全部误差；不能靠提高容差、逐点拟合、转换器提前取整、去重原 avar 或重跑旧 141 项宣称完成。

**本报告所有新模型的生产接纳状态均为 false；未生成通过验收的 Apple 来源 Swirl-VF 字体，也没有全空间精确性证明。**
