# Swirl-VF 最新接续入口：严格用户轴验收与原件重建

**本文件已更新，旧版“剩余 178 组轮廓错误”不再是当前状态。**
首先阅读 `docs/SWIRL_VF_USER_AXIS_HANDOFF_20261020.md`，再阅读
`docs/SWIRL_VF_GEOMETRY_PASS_20261020.md` 与 `docs/SWIRL_VF_TRANSFORM_REPAIR_20261020.md`。

唯一仓库/分支：`SOLHK/Swirl` / `work/core-completion-20261017`。
接续前必须读取真实远端 HEAD，保留并发 Rust Core / UI 修改，不得强推。

## 2026-10-20 本轮后续进展

已推送字体源码阶段 `0531127a0babcd8242b9d7f81db9f5c9c0202d3c`、
`ff3b59190ed1a6c6a628aba9e915aaf9eed18247`、
`4461798c9989d7230affc1d46560f6147b859e8c`、
`c31edaf04f3a6369e90da026b94aa6cf8176f356`。并发 Core 提交
`169e0cad51fc18a2d6fa4f194fafd90128bf2f7b`、
`85f4cb916221fb64b9c07f0cd6fd85bbc7e94883`、
`54908e2902c28ae20e2588fa5347df9b2b3d76e9` 均保留。
完整数值、执行范围和历史失败见
[本轮进展](SWIRL_VF_USER_COORDINATE_PROGRESS_20261020.md)。

- 原生 run [39362516018](https://github.com/SOLHK/Swirl/actions/runs/39362516018)
  在 c31edaf 检查 32 面、2,692 用户坐标、32 个选择 GID，共 86,144 项/model。
  四个全局用户轴映射模型均未全部通过；最好的 signed-zero 候选仍有 150 项失败。
  其中 65 项有可测点误差、最大约 0.45323 FUnit；不能写成全字库通过。
- 同一运行中 6,912 项垂直原点观测保持默认的 native X 坐标，改变 WDTH 后也不变。
  当前字宽的一半并不复现这些 API 观测；奇数字宽还出现半单位差。
  必须继续看实际 CTFrame/CTRun 绘制，不能擅自覆盖原始度量。
- 原生 run [39362516053](https://github.com/SOLHK/Swirl/actions/runs/39362516053)
  仍在原始 WDTH guard 阻断重建，0 面完成、无输出。缓存顺序诊断通过不等于字体完成。
- 本次代码加入独立逐请求验证适配器：原始 `1e-6` guard 默认不变；显式未接受的
  observation 协议必须经过源表身份、非默认轴回读及所有请求 GID 的 typed commands、
  bounds、原始度量精确对照。只有整批通过才输出给重建器。新原生运行尚待核实。
- 严格 849/850 CoreText API 测试继续保留。SourceTables 度量适配仅支持已验证 identity
  avar 的原创标准字体，拒绝 Apple HVGL。尚无原版字体 Windows 11 或 Qt/Swirl 验收。

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
