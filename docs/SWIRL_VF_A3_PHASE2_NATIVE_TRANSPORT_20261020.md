# A3 第二阶段：原生结果恢复、normalized 通道与准确交接

日期：2026-10-20。分支：`work/vf-axis-a3`。本文记录已完成的实际执行，不是生产验收。

**代码检查点为 `7cd579d645c5db437afcfeea63cc490fad494571`；本文件为其后的文档提交。`mapping_accepted=false`、连续全空间未验收、字体转换未验收，`Swirl-VF.ttc` 未完成。** 必须在接续开发时重新查询远端 HEAD，不从本文的旧 SHA 重建分支。

## 1. 本窗口实际提交与并发保护

| 本窗口已推送完整 SHA | 实际内容 | 验证与下一步 |
|---|---|---|
| `b3b8b183bf63fbfb7771b783118c522148ba0478` | A3 专用只读源码恢复工作流，导出精确源码、完整近期 diff、只读 D1 快照 | CI 39405567087 成功，142 项 A3 + 12 项输入测试；随后开发原创 normalized 控制 |
| `73a5bc831c46b25c3480c9d28eae4216b5add2b3` | HB/FT 实际 C API 输入、HVAR/轮廓探针，9 项测试，Linux/Windows 原生 CI | 本地 151+12 项测试；CI 39406852651 三个 job 成功；随后归档实际工件 |
| `25819080e67908eecb7fb3a4ba532b689f88e2c9` | 原始三平台合成工件、哈希绑定、独立审计器、9 项负向/证据测试 | 独立新增测试通过，但组合 CI 暴露归档命名冲突：198 项中 197 通过、1 失败；如实保留 |
| `7cd579d645c5db437afcfeea63cc490fad494571` | 仅重命名三份新增合成 ZIP，更新自身清单/触发路径，新增命名隔离回归 | 本地和 CI 均为 199 项 A3 + 12 项输入测试全通过，零失败、零跳过；后续只审查诊断/证据合并 |

启动时 HEAD 为 `37ca8f8d9cca15e6bee6dd3a8761fc71dab48156`。期间检测并保留了并发提交：`9c2fd0092284edc7d346b0c9e1d1208095429b39` 的 Tag 身份修复、`4288431dec9ca7c4ed3d36ca763095c2666745b4` 的 201 点归档、`6d6a7b5eec6e2c7a630dfd4f692e29a7ecc52115` 的 140 点实验、`cb17be48336884f6b5e8c485a2f06b5958d4d968` 的新实验归档。后两项是本窗口独立读取和复核的并发成果，不冒充本窗口新增源码。

一次带 expected_sha 的非强制更新因 HEAD 已前进而被拒绝；重新读取完整差异后，仅把自身七个新增/修改文件接在实际新 HEAD 上。未 force push，未改写并发提交，未写入集成分支、D1 或其他分支。未修改生产 rebuild.py、coretext_extract.swift、B1/C1/D1 生产代码、Rust、UI 或动画，也未重跑旧 141 项原生闭合子集。

## 2. 201 点：真实终态不是生产通过

指定 CI [39404600942](https://github.com/SOLHK/Swirl/actions/runs/39404600942) 已 completed/success，源码 `eda37d1c733cb1ced283583434e4123824a2147c`。实际 native job `118567521503`、工件 `12255423793` 的日志和原始 ZIP 均已读取。ZIP SHA256：`951092a6f3116dcf26b4a799a3d0d260a3b5ca59a3c4f44389ca277e7f5c64c1`。

201 个标签对应 193 个不同的完整 face/三轴位置。160 个新样本实际由 64 个随机点、36 个边界点、60 个默认值点组成；不能把全部 160 个称为随机点。另有 41 个历史控制。两个 anchor、两个相反顺序共四进程，各 402 请求、2010 条 glyph record，error=0、exit=0；共 8040 条字形记录、1608 次实际构造入口审计、4020/4020 对完整正反序相同、804 个严格重放批次。原始三轴 binary64 入口位模式全部保留，未用打印的小数或回读值替代入口审计。

每个 anchor 的预声明 HVAR 比较：

| 模型 | 精确位置/201 | 超过 1/32 的位置数 | 最大残差 FUnit |
|---|---:|---:|---:|
| 旧 canonical | 181 | 0 | 0.01220703125 |
| 旧 canonical float32 | 180 | 0 | 0.01220703125 |
| endpoint-negative-float32 | 201 | 0 | 0 |
| offset-negative-float32 | 201 | 0 | 0 |
| divsub | 200 | 0 | 0.01220703125 |
| all-axes-float32 offset | 198 | 1 | 0.5474853515625 |

HVAR 每个位置检查四个 GID。endpoint/offset 的轮廓比较并非全零：每 anchor 的 portable 1005 glyph 比较及预选 direct HVF 186 glyph 比较，最大残差均为 `0.009678105302214135 FUnit`，虽低于 1/32，仍必须保留为非零。direct HVF 为 93 个位置各两个 GID；完整向量缓存后实际 libhvf 调用总计 160 次。不能把每个模型报告的比较数当成互相独立的原生调用数。

原严格重放每 anchor 保留 28 个失败，共 **56 个失败**：默认轴省略 48 个、face22 的 HGHT 回读漂移 4 个、face30 的回读稳定但 payload 不同 4 个。首跑分类器另有 `original_table_binding_incomplete`：真实 reader 使用 `fontTools.Tag` 字符串子类，旧诊断身份验证拒绝了它；这是诊断层拒绝，不是原生请求执行失败。

修复后的实际复跑 [39405368777](https://github.com/SOLHK/Swirl/actions/runs/39405368777)，源码 `9c2fd0092284edc7d346b0c9e1d1208095429b39`，native job `118570021118`，工件 `12256825953`，ZIP SHA256 `3a4239c867d1e745550c189d7624f1d79b6beb4f8b3d36b405eec5a8aca96e56`。完整报告与首跑逐字段核对，只有提交号和分类器结果改变。新分类为 748 个原 strict 已通过、48 个仅默认省略的有限等价诊断、8 个仍拒绝；**没有把原 56 个 strict 失败改写成成功**。

指定证据 CI [39404664873](https://github.com/SOLHK/Swirl/actions/runs/39404664873) 也已成功，实际范围为 **139 项 A3 + 12 项输入反例测试**，包含 Linux 原创控制和冻结工件验证；它不是新一轮 Apple 或 Windows 原生执行。

更详细的不可改写测量见 [算术交接](../tools/swirl_vf/platform/axis_a3_arithmetic_handoff_20261020.md) 及其原始工件/清单。

## 3. Apple 新机制线索：设计阶段与最终回读分离

已独立读取并发 140 点实验的源码、实际 native job `118575682081` 日志和归档字节；[CI 39407084146](https://github.com/SOLHK/Swirl/actions/runs/39407084146) 成功，源码 `6d6a7b5eec6e2c7a630dfd4f692e29a7ecc52115`，工件 `12257063377`，ZIP SHA256 `f14dc7d77ca586d3cd3b4774f1332ec66ac885f5fe273779b2d770ebf136ac7c`。

冻结队列为 124 个独立新位置加 16 个历史/派生控制；140 个完整三轴位置均唯一。实际 5600 条 glyph record、1120 次入口审计、2800 对精确反序比较、560 个 strict batch，四进程零执行错误。68 个位置在原生运行前已选择 direct HVF，缓存后 128 次实际调用。

候选 `ONCE_ALL` 在设计映射中采用所有轴的一次 `T(x)`，而不是最终回读计划 `T(T(x))`；`T(x)=trunc(binary64(x*10000))/10000`，除法也按 binary64，不允许换成 Decimal 或重排操作。原始 CoreText 请求仍为完整 x，回读/重放计划没有改动。identity 识别、负半轴 float32 endpoint 运算、非 identity float32 归一化、normalized16 截断、原顺序 avar、F2DOT14 规则均保持预声明版本。

每个 anchor：ONCE_ALL **HVAR 140/140 精确**（新 holdout 124/124）；预选 **direct HVF 136/136 glyph 精确**（68 个位置）。只对 identity 轴采用一次截断的 ONCE_IDENTITY 为 HVAR 139/140、direct HVF 67/68 位置精确，未把这个新失败补成单点规则。ONCE_ALL portable 的 700 次比较中仍有 694 次非零，最大 `6.821210263296962e-13 FUnit`；旧 legacy segment-type 失败亦保留。

新 face0 完整输入 `(500,415.09865,500)` 区分两种候选：T1 wght=415.0986，T2=415.0985，候选 q 分别为 -3893/-3894；ONCE_ALL 的实际 HVAR 和预选 HVF 残差为零，identity-only 的最大 HVAR/HVF 残差分别为 `0.0032958984375/0.005370084551486798`。face30 原始 `(729.2925740388073,660.9898707384746,303.5934274824121)` 的候选 HGHT q 从 -6449 改为 -6448，两个预选 GID 的直接 HVF 残差降至零；其 original/replay HVAR 相等而五个 glyph payload 仍不同。

**这支持阶段分离，不是直接读出了 CoreText 私有 q，也不能唯一确定内部指令。** 新队列仍有 **52 个 strict 失败**：48 个回读相同但 payload 不同，4 个 face22 回读漂移；不能由候选度量/轮廓匹配取消它们。水平 HVAR 对 HGHT 的盲区仍需几何检测。

默认 201 点协议回归 [39407084001](https://github.com/SOLHK/Swirl/actions/runs/39407084001) 已成功；完整报告与 9c2fd 的报告比较，仅 source_commit 不同。ONCE_ALL 在旧 201 向量上的离线比较不是整套新模型的额外原生验收。详见 [设计阶段交接](../tools/swirl_vf/platform/axis_a3_prereadback_handoff_20261020.md)。

## 4. 本窗口新增：Windows 实际 normalized 字形通道

[CI 39406852651](https://github.com/SOLHK/Swirl/actions/runs/39406852651) 在 Linux、Windows Server 2022、Windows Server 2025 三个 job 全部成功。两份 Windows 实际日志与全部原始工件已独立读取、重算和归档，不只读取 workflow 颜色。

原创 fixture 只有 .notdef 和 square：wght 正 normalized q 同时控制 HVAR advance 和 gvar 右边界。使用完整三轴 `WDTH/wght/HGHT`，范围/默认为 `1/500/1000`、`100/499/900`、`1/500/1000`，identity avar，UPEM16384。这些是明确原创范围，不冒充任何 Apple 原件的完整结构。q sweep 只改变 wght，未覆盖三轴动态组合。

HB 在实际 C 调用前记录 int normalized 数组或 float design 数组及位模式，检查原生 advance 和 extents。FT 使用正确平台 c_long ABI（Windows 4 字节、Linux 8 字节），记录实际 blend/design 数组，调用 FT_Load_Glyph，检查 advance、全部四个轮廓点、tags、contour。回读相等但字宽/轮廓被修改的负向控制必须失败。

每平台两独立进程、18 个请求、两个引擎，共 **72 个实际观测、36 个反序对、64 个 normalized 字形检查**。Windows 合计 **144/72/128**，四进程，另有 72 个跨 Windows 版本 payload 对；Linux 的 72 个观测不混算成 Windows。三平台完整 authored payload 均相同。外部 q=0/65 的实际 advance=500/565，轮廓不同；原始碰撞输入经 design float32 或 design Fixed16 仍合并。

| 平台 | Job | Artifact | 原始 ZIP SHA256 |
|---|---:|---:|---|
| Linux | 118574758864 | 12256872753 | `f2066dad3df176c1e823d600b4feb97d4838137c857fb7df10bc710bd240e3d2` |
| Windows 2022 | 118574908949 | 12257861744 | `d3fe9129de206c9a74a5a1999de25b952e0ef6649510c4bc39abbbe531ae33b7` |
| Windows 2025 | 118574909027 | 12257711903 | `b63ada4c3164f96d8e4eab162e4187a707977ea717a93ed15a94311aa6306ee5` |

Windows 实际 HB14.6.0/FT2.15.0，Server build20348/26100；Linux HB8.3.0/FT2.13.2。Windows DLL 哈希、包清单、Python 版本、完整 ABI 和工件成员哈希均见 [证据清单](../tools/swirl_vf/platform/axis_a3_normalized_runtime_evidence_20261020.json)。MSYS2 未来安装可能获得不同包；本轮通过版本和 DLL 哈希固定事实，不声称安装器重跑必然逐字节相同。

**本实验仅验证已知 q 的运输及原创字形输出。** 未由原始 binary64 推导 Apple q，未验证 DirectWrite/Qt/Windows11/Swirl，没有原版字体转换接受。所有生产 flags 均为 false。已有较早契约里“Windows normalized 尚未测”的状态是历史冻结快照，不能改写；新增证据用本清单独立补充。

## 5. 真实失败及修复，未降低任何旧门槛

归档提交 25819080 将原创 ZIP 命名为 `axis_a3_native_runtime_*.zip`，进入了旧 Apple 证据测试严格枚举的 `axis_a3_native_*.zip`。CI [39408637314](https://github.com/SOLHK/Swirl/actions/runs/39408637314) 实际 198 项中一项失败，本地同样复现；证据 CI [39408637276](https://github.com/SOLHK/Swirl/actions/runs/39408637276) 也失败。

7cd579d 仅把三份自身 ZIP 改名为 `axis_a3_normalized_runtime_*.zip`，更新自身 manifest/workflow，加一项命名集合不相交测试。ZIP 字节、SHA256、旧 Apple 原件、旧严格枚举及旧失败均不改动。修复后 [39409293910](https://github.com/SOLHK/Swirl/actions/runs/39409293910) 实际日志为 199+12 项全通过，另一个证据 CI [39409293908](https://github.com/SOLHK/Swirl/actions/runs/39409293908) 同样成功。

可从仓库根目录重复执行：

```sh
python -m unittest discover -s tools/swirl_vf/tests -p 'test_axis_a3*.py' -v
python -m unittest discover -s tools/swirl_vf/tests -p 'test_axis_input_resolution.py' -v
python tools/swirl_vf/platform/axis_a3_normalized_evidence.py
```

前两条实测为 199 和 12 项，均零失败/跳过；第三条重算原工件，输出 `VERIFIED_AUTHORED_CHANNEL_ONLY`、144 Windows observations、mapping_accepted=false。没有声称整个 Swirl 应用测试通过。

本窗口文件：两个 workflow（recovery、normalized-runtime），两个 Python 模块（probe_axis_a3_normalized_runtime、axis_a3_normalized_evidence），两个测试文件（test_axis_a3_normalized_runtime、test_axis_a3_normalized_evidence），一份 normalized_runtime_evidence 清单，三份 `axis_a3_normalized_runtime_{linux,windows2022,windows2025}_73a5bc8.zip`，以及本文。新增源码测试共 19 项，另外的计数增长来自已保留的并发 A3 成果。

## 6. D1 只读交叉验证：不能用成功退出码代替有效证据

最新已读取快照 `205af02ce1db6c9ec525d8962b44e7681ee37ffe`；读取此前源码和该提交完整 diff，没有修改 D1。其 [CI 39408729626](https://github.com/SOLHK/Swirl/actions/runs/39408729626) 两个 Windows job 均 failure，Qt SDK6.10.3。最新实际工件：

| 平台 | Artifact | ZIP SHA256 |
|---|---:|---|
| Server2022 | 12258706023 | `efb7b0252ac2eb3ea46bc4a37f38b4917aa9830606f983ace824630189e1ff3f` |
| Server2025 | 12258251456 | `814088f7a224bcd5636ed3e175e44b08acb5a1b12f077acc683071ff4f1797cb` |

两份 ZIP 均已下载核对上述哈希并读取 d1-analysis.json/d2-analysis.json。每 OS 的 D1 报告仅接受 12/16 个完整进程、3568 个观测，四个 Qt FreeType 进程失败并排除；accepted 子集的反序及私有/安装字体比较相等，不能使 global FAILED 变绿。

DirectWrite 的用户轴值实际经过 FLOAT，Qt setVariableAxis 也使用 float；不能用上游 double 文本替代 C++ 实际数组证据。原创 D1 字体轴范围、默认、GID、UPEM 与 Apple face15 不同。已有输入折叠证据只支持已测接口/原创字体的条件结论，不是对原 Apple TTC 的 Windows 验收，也不能用 QFont 请求属性回读代替引擎内部状态。

205af02 修复的是 D2 显式导入 Qt6GuiPrivate；本轮 D2 确实编译成功，但两台机器各 96 个进程虽然 exit0，全部被 validator 以 `Unverified physical runtime` 拒绝，**有效 observations=0、control/guard comparisons=0、mechanism_confirmed=false、production_fix=false**。这和上一次 f7e841 配置阶段失败/未执行不同。该 runtime 身份失败及 Qt 状态诊断由 D1 负责人继续处理，不在 A3 修改其代码或放宽验证。

原始 TTC、Windows11 desktop、真实 Swirl UI 均 NOT_RUN。A3 新 HB/FT normalized 通道成功不补填这些缺口。

## 7. 生产方向、阻塞与下一步最小任务

原 pair 的 binary64 bits 分别为 `407f3019641f6449`、`407f30196638433d`，在 float32 均为 `43f980cb`，用户 16.16 均为 32702870。真实 Apple GID5 advance 差 0.5474853515625，因此只保留已经合并输入且没有侧信道的确定性目标，至少一端误差不小于 0.27374267578125，超过 1/32。该证明是有条件的，不能推成所有 OpenType 或 Windows API 均无解。

可继续实施的应用端候选链是：**保留原始 binary64 三轴请求及缓存键 → 在任何有损用户输入转换前计算经原生验证的完整 q → 向 HB/FT normalized 入口传递 q → 以同一实例状态完成 shaping、轮廓与绘制。** 本轮只验证中间 transport 及原创单动态轴输出；ONCE_ALL 只是有限 Apple 支持的上游候选。并未完成这条端到端链，更没有一个已验证、可直接投产的原版等价字体表示。量化、静态实例或有损兼容模式必须明确标记近似，不能通过平滑原跳变、修改原轴或放宽精度冒充等价。

仍阻塞：全三轴/所有相关 GID 的映射与几何门禁；原始 avar 重复记录的有序行为；相同 readback 不同实例的缓存/重建语义；Windows normalized 全三轴、实际 shaping/Qt 集成；D1 失败和 Windows11/UI 未测；原版全 TTC 重建与跨平台完整门禁。本轮没有生成完整原版 TTC。

窗口 1 可合并**诊断、原创夹具、严格测试、证据与文档**，必须同时带上 7cd579d 命名修复及依赖文件，并保留并发 201/140 成果；不要据此改生产映射或接受标志。由窗口 1 在最新集成 HEAD 上做合并和完整测试，本窗口没有直接推送集成分支。

下一阶段最小可执行任务：先刷新 A3/D1 HEAD 和差异；固定 ONCE_ALL 原公式，预声明其在既有 201 队列及新的完整三轴 boundary holdout 上的检查，不从已有误差逐点拟合；分别核对 raw input bits、构造入口、实际 readback、HVAR、预选直接 HVF 和 strict replay。Windows 侧先把原创 normalized fixture 扩展到三个独立动态轴及组合项，保持完整 input arrays、字宽和完整轮廓检查；由 D1 负责人修复物理 runtime 证据绑定后再评估 Qt 诊断。任何新生产候选须先原创对照、再 Apple 原生对照、最后经总负责人协调。

## 8. CI 统计的明确口径

以下是本文逐一检查的 11 条 A3 run，不是整个仓库全部历史 run；workflow 统计不计 cleanup step 的 skipped。

| Run | 终态 | 范围 |
|---:|---|---|
| 39404600942 | success | 原 201 点 native arithmetic，保留失败 |
| 39404664873 | success | 139+12 证据/输入测试，不是 Apple native |
| 39405368777 | success | Tag 分类修复后同一 201 点 native |
| 39405567087 | success | 源码恢复与 142+12 基线 |
| 39406852651 | success | 三平台原创 HB/FT normalized，3 jobs |
| 39407084146 | success | 并发 140 点 prereadback native |
| 39407084001 | success | 参数化后默认 201 native 协议回归 |
| 39408637276 | failure | 25819080 证据检查失败，未删除 |
| 39408637314 | failure | 25819080 组合测试归档命名冲突 |
| 39409293908 | success | 7cd579d 修复后证据检查 |
| 39409293910 | success | 7cd579d 修复后完整 199+12 测试 |

该清单为 **成功9、失败2、跳过0、运行中0**，两条历史失败已由后续成功修复但不从历史中扣除。另行只读核验的最新 D1 run39408729626 为失败（两个 Windows jobs 均失败）；把它并入这份限定审计集则为成功9、失败3、跳过0、运行中0。后续分支或 CI 前进不由本快照自动覆盖，必须重新查询。
