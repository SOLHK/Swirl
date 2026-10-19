# Swirl-VF 字体工程：2026-10-20 跨窗口接续交接（已实际推送）

## 远端基线与安全范围

* 唯一允许修改的仓库/分支：`SOLHK/Swirl` / `work/core-completion-20261017`。
* 当前阶段源码提交：`8b22ce6064d5de2c39a1d125208710c4c87037d3`。接续前**必须先读取远端最新 HEAD**；Core 开发也会在该分支并行推进，不得强推、覆盖或回滚其提交。
* 唯一原版：用户的 macOS 27 `PingFangUI.ttc`，61,473,880 字节，SHA-256 `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`；本地用户副本必须只读，且不得提交公开仓库。
* 32 个物理字体面，每面 47,102 GID；原始可变轴为 `WDTH`、`wght`、`HGHT`。不可删 HGHT，不可将 WDTH 擅自改为百分比，不可丢失任意地区版本，不允许改名冒充转换成功。
* 最终目标名称固定 `Swirl-VF.ttc`；**截至本交接，尚未生成通过验收的正式字体**。

## 已实际推送的进展

`42304dadbcb62af761e82fcabc439fb54e618da1`：实现 Apple 原生观察支持的 Type-2 切线投影与更深层子部件变换顺序。旧原生样本 22/22 tangent、28/28 hierarchy 的记录重测通过；但新 48 组未用于建模的测试出现 35 组失败。

`8b22ce6064d5de2c39a1d125208710c4c87037d3`：逐案检查确认上述 35/48 都是投影参数超出控制点线段端点导致。将无限直线投影修正为端点有界的最近点投影，新增 54 组端点及微小越界独立样本；没有移除原来的 48 组样本或放宽 1/32 FUnit 门槛。GitHub macOS runner 固定为 `xcode-27`，以使用 macOS 27 上与原件哈希匹配的系统字体。提交只包含 4 个字体相关源码/CI 文件，未修改 Core/UI。提交前本地原样 53 项 Python 回归通过。

## 实际 CI（以 workflow 页的最终记录为准）

* [run 39296798626：tangent geometry](https://github.com/SOLHK/Swirl/actions/runs/39296798626)：**总状态 failure 是真实原版几何门禁失败**，不是合成切线测试失败。原创切线测试 124/124 通过，最大误差约 2.2737367544323206e-13 FUnit；有序层级旋转/子部件平移回归通过。所有旧 48 组与新增 54 组都实际执行。
* 同一 run 的 Apple 原件 hash `39d42a...` 匹配且复测前后不变。严格的 32 GID × 34 轴位置 = 1,088 组原件轮廓验收：**910 通过、178 失败**，失败均为 `control_point_error_budget_exceeded`，最大点误差仍约 223.93679441137425 FUnit。此前同一 1,088 样本的对照为 660 通过、428 失败（384 超预算、44 段类型不符）。这是相同固定抽样的改善，**绝非全字体完成率**。
* [run 39296798608：Swirl VF public probe](https://github.com/SOLHK/Swirl/actions/runs/39296798608)：Python 成功；Windows DirectWrite 原创三轴 TTC 测试成功；`apple-oracles` 因原 CoreText 1/32 FUnit 的严格垂直度量测试失败（原始样例 849 对预期 850），依然失败。不能因无关测试通过而把整体 CI 标记成成功。
* 可复现来源及前序诊断：`docs/SWIRL_VF_GEOMETRY_REPAIR_20261020.md`、`docs/SWIRL_VF_GEOMETRY_HANDOFF_20261020.md`、`docs/SWIRL_VF_HANDOFF_20261019.md`、`tools/swirl_vf/README.md`、`tools/swirl_vf/platform/verify_tangent_projection.py`、`tools/swirl_vf/tools/hvf.py`、`tools/swirl_vf/tools/tangent_geometry.py` 和 `tools/swirl_vf/tools/batch_geometry.py`。

## 接续研发顺序（必须实际执行，不是写提示词）

1. 先审查当前远端 HEAD、CI 失败工件及同文件并发修改；保留 Core 分支的新增提交。重新运行原来的 1,088 样本判定，不修改样本选择和 1/32 FUnit 门槛。
2. 分析剩余 178 组错误按 GID、轴坐标、部件树、旋转、Type 0/1/2、曲线封闭与轮廓匹配的分布。GID 6、7、104 的 Type 0/1 层级旋转曾出错，不能把剩余问题一概归因于 Type 2。区分真正轮廓差异、循环起点比较、局部坐标和 CoreText/Apple API 度量差异。必要时新增**完全原创几何**最小复现，先经 macOS 27 原生 oracle 证实再改算法。
3. 每次修复同步验证标量/批量路径；保留 22 + 48 + 54 组切线输入和 28 组层级输入，重新跑源端 1,088 样本。禁止删失败项、扩大容差或用别的字体填补字形。
4. 继续修复 `avar` 的源用户坐标精度、CoreText 原点/前进量、`HVAR/VORG` 的等价重表达和三轴完整插值。原版所有 32 面存在重复 `wght avar` 原始坐标，需按原始记录并由 Apple 求值验证；不能简单字典覆盖。
5. 在源端校验可靠后才运行 `tools/swirl_vf/tools/rebuild.py` 完整 TTC 构建，逐面/GID 保留 Unicode、GSUB、来源映射、真实度量，校验独立非采样点、混合轴与保存后的 `glyf/gvar`；当源端无损不可证明时必须标成近似重建，保留实际误差。
6. 只有最终 `Swirl-VF.ttc` 经过真实 DirectWrite、Windows 11、Qt/Swirl 加载和五档物理 DPI/性能验收，才报告 Windows 可正常使用和 Swirl 原版适配完成。
7. 每个有意义的阶段先测试、保存日志和交接文件，再用 GitHub 写权限提交到上述分支；提交后确认 SHA、复查 Actions。未完成部分必须如实列出。禁止公开提交苹果原件、Apple 衍生字体、私有原版轮廓转储与任何凭证。

## 非成果说明

本地的 14,000 GID 默认点可移植解析无异常的扫描仅说明程序执行和有限值检查，不是 Apple 原生几何一致性或 Windows 安装通过。Apple 字体本体的使用、修改与再分发须单独审查许可。当前尚无已验收 `Swirl-VF.ttc`；切勿仅靠通过合成字体测试或重命名原件作正式交付。
