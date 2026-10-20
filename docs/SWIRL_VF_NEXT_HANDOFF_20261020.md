# Swirl-VF 最新接续入口：严格用户轴验收与原件重建

最新精度接续检查点见
[SWIRL_VF_PRECISION_CHECKPOINTS_20261020.md](SWIRL_VF_PRECISION_CHECKPOINTS_20261020.md)。
本次从真实远端 `056f7ea6dc7cf3a703da63e8522b89d33d1166f4` 继续，
复用已有 A1 v2 逐批严格重放。默认 Swift 校验新增“非默认轴不得缺失”的独立防护；
原生结果待读取后记录，不将 Linux harness 检查写成 CoreText 通过。

**本文件已更新，旧版“剩余 178 组轮廓错误”不再是当前状态。**
首先阅读 `docs/SWIRL_VF_USER_AXIS_HANDOFF_20261020.md`，再阅读
`docs/SWIRL_VF_GEOMETRY_PASS_20261020.md` 与 `docs/SWIRL_VF_TRANSFORM_REPAIR_20261020.md`。

唯一仓库/分支：`SOLHK/Swirl` / `work/core-completion-20261017`。
接续前必须读取真实远端 HEAD，保留并发 Rust Core / UI 修改，不得强推。

## 2026-10-20 本轮后续进展

已推送字体源码阶段 `0531127a0babcd8242b9d7f81db9f5c9c0202d3c`、
`ff3b59190ed1a6c6a628aba9e915aaf9eed18247`、
`4461798c9989d7230affc1d46560f6147b859e8c`、
`c31edaf04f3a6369e90da026b94aa6cf8176f356`、
`24119489f7b85fe58dea53acf3a4a6f467a6e8fa`、
`ef564245f5de600757b7283437c7daf31a1e90e9`、
`4927316c74f935099a5648cefacc13ae0d1f2772`、
`af8df45a9ca3f2ed0d2e623856cb3c8ef85f3974`、
`121d58c3579241305d5a653939f1200573f3a7d2`、
`babc38b12373a6c744a03f727bee230d8341f615`、
`24ae62158ce147602bd1a4a5b6f41a1335325c8f`。并发 Core 提交
`169e0cad51fc18a2d6fa4f194fafd90128bf2f7b`、
`85f4cb916221fb64b9c07f0cd6fd85bbc7e94883`、
`54908e2902c28ae20e2588fa5347df9b2b3d76e9`、
`a3b89050e141557444519c8c17f2a263e6a013fc`、
`5d3ec74d212276726e96be8ecbd4c2f92adc4e53` 均保留。
完整数值、执行范围和历史失败见
[本轮进展](SWIRL_VF_USER_COORDINATE_PROGRESS_20261020.md)。

- 最新已核实字体提交 `af8df45a9ca3f2ed0d2e623856cb3c8ef85f3974`。
  run [39371704891](https://github.com/SOLHK/Swirl/actions/runs/39371704891)
  的实际原件重建已通过全部 91 批 / 5,824 条原件采样观测，32/32 面身份通过，
  停在 face 0 / GID 0 的标准 vmtx 垂直 X 原点表示检查：training sample 1，
  `WDTH=1, wght=501, HGHT=500`，实际绝对偏差 **100 FUnit**，原 1e-5 门槛不变。
  没有新轴回读失败；尚未到达完整 oracle summary。已接受观测与完成模型分开记录；
  **0 个 GID 模型完成、0/32 面完成，无 TTC**。
- run [39370313682](https://github.com/SOLHK/Swirl/actions/runs/39370313682)
  实际完成原创合成 2/2 面、各 3/3 GID TTC，三轴完整；每面 27 training+38 holdout，
  最大轮廓误差 0.010986328125 FUnit、表度量误差零。完整原生终结通过（260 批、
  390 接受记录，内部 520 请求/780 记录），保存重开、打包及 174 条原生复测通过。
  3,424 字节测试 TTC 实际生成后已清理，**不是苹果原件成品**。严格原生度量仍为
  849/850 失败；SourceTables 与原生路径 174 项及两组各 6 项静态检查通过。
  API 原始误差保留，Apple job 仍为 failure；SourceTables 值不冒称原生 API 值。
- run [39366216066](https://github.com/SOLHK/Swirl/actions/runs/39366216066)
  的 378 单字、42 混排真实绘制已完成。245 非空变化对支持固定默认 X 原点；
  当前字宽/2 解释最大错位约 100 FUnit。不是简单 API 小数显示问题，不能覆盖原点。
- 新边界 run [39368769062](https://github.com/SOLHK/Swirl/actions/runs/39368769062)
  已完成 12,800 原件所选 GID 记录与 600 原创合成记录；五个预声明候选、相反
  创建顺序和独立进程的全部类型化路径、原始度量均零差异。定义
  `T(x)=trunc(binary64(x*10000))/10000`，有限集合 T/T(T) 覆盖 1,800/1,800
  有效轴观测；全部 120 个事先计算 C=T(T(x)) 的实例真实回读精确稳定。
  原件和合成的关键 wght 未同值交叉，不能断言差异由字体格式引起。
- 本检查点据此实现固定 v2：原生调用前声明 C；实际 C 回读必须精确等于 C；
  整批每个 GID 的全部原始轮廓与度量必须零误差匹配。原请求数据不替换、
  原 `1e-6` 不放宽、无递归重试或第三次构造。25/25 适配专项回归已通过；
  原件首批 91 个位置和完整原创合成重建已验证该规则，后续所有 GID 仍须逐批验证。
- run [39371704981](https://github.com/SOLHK/Swirl/actions/runs/39371704981)
  的 Windows Server 原生任务实际完成 **4,608 布局 / 11,520 字形观察**。
  默认竖排 `vert` / `vkrn` 将原创夹具最大 X 漂移从 98 降至 **0.5 FUnit**；
  `vrt2` 默认无补偿。默认横排、GSUB/地区映射、度量与字宽均保持；默认混排
  128 个旋转空格/Latin run 完整相等。实际 GPOS 仍有量化，不能称 1/32 通过。
  HB 实测默认只启用 `vert`，不能把单一引擎行为当跨平台契约。
  Mac 同轮因 `.excludeSynthetic` 被 SDK 禁用而编译失败，后由 `121d58c` 修复。
  新 run [39372726963](https://github.com/SOLHK/Swirl/actions/runs/39372726963)
  已编译通过，第一 source 进程横排 168 项完成，但竖排 168 项全部被实际字体身份
  或完整文本布局检查拒绝，尚未执行 candidate。后续实际诊断 run
  [39373773102](https://github.com/SOLHK/Swirl/actions/runs/39373773102) 已确认：
  请求 8-GID 原创字体，竖排实际却选为 47,102-GID 系统苹方，表哈希守卫正确拦截。
  当前将唯一当前原创 fixture URL 注册到隔离进程的 `.process`，并核验退出前注销。
  所有 actual-run 身份及完整文本检查保留，须再跑原生证明回退解决，不能推断 GPOS 功效。
- 本检查点 Python **319/319**（包含实际 HarfBuzz、无 skip）、audit **6/6**。
  Windows 数量已经实际完成；CoreText 的 2,016 次仍是待执行请求数。
- 另修复 gvar 残差双重舍入：原创可表达反例的误差从 1.400071 降至 0.014142
  FUnit，保存重开后也通过。原有 1 FUnit 重建预算与 1/32 原算法门槛均未放宽。
- `c31edaf` 的四个全局用户轴映射模型仍均未全部通过，最好的候选仍有 150 项失败。
  SourceTables 适配仍拒绝未验证的 Apple HVGL 映射。无 Windows 11 或 Qt/Swirl 验收。

不要把新的 observation 参数直接交给重建器，也不要把候选坐标规则当作 Apple 官方契约。
原有 141 项 HVAR 量化疑点仍保留。

## 已实际完成

- 生产轮廓修复提交 `5cbf5715d99c1046e80c1c3e45a4ec2ab8946f1f`：
  主变换/极值变换有序组合、旋转中心插值、Type-0 平行因子的原生等价求值。
- Apple 原生 run 39306798698：同一原件、同一 GID/坐标/比较器和 1/32 FUnit 门槛，
  **1088/1088 通过，0 失败**；最大误差 1.7053025658242404e-12 FUnit。
- 原有切线 124/124、层级 28/28、新变换 120/120 全部原生通过。
- 用户轴诊断源码 `2f3c34b9bd57f0612f95e1d37c27b98726941cce`，回归提交
  `34eee448c592bc49147136f5d79fa67cfc4a9cb9`。本地 117+6 项测试通过。
- 原生 HVAR run 39309709636：32 面、3048 组用户坐标、12192 项字宽观测。
  按源默认值归一化、原始 avar 顺序求值、零坐标保持零的解释匹配这些观测，
  最大字宽差 0.005915052594446024 FUnit。尚不等于用户轴轮廓映射通过。

## 已执行但未完成的原件重建

run 39308178976 真实执行 `rebuild.py` 与原生产 CoreText 提取器，32 面身份均核对成功，
在第一面遇到 `coretext_did_not_report_requested_axis_value:WDTH` 后停止，0 面完成、无候选字体。
例如请求 600.5859375，API 原始 Double 回读 600.5859。不能放宽原检查假装通过。

最新公共 probe run 39309952086 的 Python / Windows DirectWrite 原创夹具成功，
但 CoreText 严格度量仍失败，合成原生重建被跳过。没有通过原版字体的 Windows 11 或 Qt 验收。

## 不变的原件与目标

原件 61,473,880 字节，SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`。
32 面，每面 47102 GID；原始轴 `WDTH`、`wght`、`HGHT` 全保留，禁止删 HGHT、替换字体、
伪造字重、改变字形来通过测试。公开仓库不得包含原件、Apple 衍生字体、私有轮廓或凭证。

正式目标仍是 `Swirl-VF.ttc`，**尚未生成通过完整验收的成品**。
下一步直接处理用户轴到设计坐标的轮廓对照、精确舍入/重复 avar 语义、CoreText 度量/原点，
再推进完整字库重建与实际 Windows 11/Qt 验收。无需重新开发已通过的变换修复。
历史失败和前序工作见其原交接文档及新的详细交接，不得将诊断成功写成字体完成。
