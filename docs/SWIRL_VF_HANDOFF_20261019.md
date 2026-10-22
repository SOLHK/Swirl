# Swirl-VF：实际开发状态与原件验收缺口

更新日期：2026-10-19。限定分支 `work/core-completion-20261017`。

## 首要结论

**原版字体已实际审计，转换工具和 Swirl 接入代码已提交；尚未生成已验收的
Apple 衍生 `Swirl-VF.ttc`。** 不要将公开 CI 的原创测试字体重命名后交付，
不要把本文件或某项合成测试通过当作原件完整保留的证明。

源文件精确大小为 61,473,880 字节，SHA-256：

`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`

本次工作只读保留原件。公开仓库包含独立代码、生成合成夹具的程序与必要文档，
不包含原版字体、Apple 衍生字体或原版轮廓转储。字体数据和完整原件差异报告
保留在用户私有交付中。字体使用及再分发许可见 `tools/swirl_vf/research/LICENSING_REVIEW.md`。

## 已实际完成的代码

- HVGL 3.1 / HVPM 1 有界结构解析、引用和树校验；原件的 70,047 个 part 已解码。
- 原始 `avar` 逐记录读取，不让字典覆盖重复输入；32 个源面都存在该问题。
- CoreText 物理字体面及原始表身份检查、原始轴坐标请求、轮廓和度量 JSONL 提取。
- 标准 `glyf/gvar` 重建、原始三轴范围与 GID 保留策略、独立内部点和自适应细分。
- 所有模型训练点和检查点接受同一量化预算；序列化后核对完整轮廓/phantom/gvar
  系数；TTC 打包后核对全部面和表。失败不发布正式文件。
- 应用本地 TTC 加载、按真实家族选择、QFontInfo 轴回读、QRawFont 表字节来源验证、
  同名冲突和静态回退拒绝、重复加载和重启恢复检查。保留既有语义控制器、UI 和 Core。

`rebuild.py` 是实例重建程序，所有成功状态仍明确 `lossless_conversion=false`。
它尚未在这份原件上执行完整原生转换。`WDTH` 和 `HGHT` 的原始标签及用户范围
应保留，不能将大写宽度直接解释成百分比，更不能删除高度轴。

## 精确提交和运行证据

| 提交 | 变更与实际验证 |
| --- | --- |
| [`aab06bf`](https://github.com/SOLHK/Swirl/commit/aab06bfef1ceb41fb0e2173b19a9a6efa0b88efb) | 首次工具和 Swirl 接入；[Windows Qt run 39244199561](https://github.com/SOLHK/Swirl/actions/runs/39244199561) 实际成功：62 通过、9 跳过，完整应用构建成功，独立 offscreen 导航 61/61。 |
| [`501099d`](https://github.com/SOLHK/Swirl/commit/501099da4c3df3fa5c3d8e6ad18a4311e4219fc0) | 修复真实 Apple SDK 编译问题及 PowerShell `WDTH`/`wdth` 大小写读取冲突。DirectWrite 原生任务成功。 |
| [`7dfbdda`](https://github.com/SOLHK/Swirl/commit/7dfbdda51e1210b827d76c2c2ccf37f0c544eaf5) | 保留 CoreText 严格失败的请求/GID/坐标/原始响应，阈值未放宽。 |
| [`b3ac464`](https://github.com/SOLHK/Swirl/commit/b3ac46414ed3921d18b1cf8e9a143c545c8085fb) | [run 39248465012](https://github.com/SOLHK/Swirl/actions/runs/39248465012)：新增独立三路径度量诊断；诊断完成，原严格 CoreText 检查仍失败。 |
| [`6cba41f`](https://github.com/SOLHK/Swirl/commit/6cba41ff43b989a240191a3731d9d8a5e29908b1) | [run 39249102939](https://github.com/SOLHK/Swirl/actions/runs/39249102939)：修复真实 TTC 打包时间戳改写；Python 36+6 项通过，DirectWrite 成功，Apple HVF 29 点通过，CoreText 原严格检查仍失败、原生重建 smoke 跳过。 |

本阶段曾两次遇到远端并发 Core 提交，分别以 `f3ce257` 和 `0be6823` 为新基线，
核对变更路径无重叠后追加字体提交。没有覆盖这些 Core 变更。

## 原生度量诊断的结论与边界

macOS 26.6.2 / Xcode 26.6 上，原生 CoreText 完整返回 174 个合成字形记录，
但与原先定义的理想模型比较时，1/32 字体单位的严格门槛失败，例如垂直前进量
849 对预期 850。原失败日志和门槛均保留。

独立诊断对照 gvar-only、数学等价 HVAR/VVAR、静态实例三条路径，共 144 项
字形观测。HVAR/VVAR 的 1044 项标准 VarStore 系数校验误差为零，原有表字节
未被修改（head 校验和除外）。增加度量表后，超出原预算的观测从 29/48 减至
6/48，端点 849→850 得到修正；分数水平前进量最大误差从约 0.201945 降至
0.001176 字体单位。但分数垂直前进量仍有 0.3375 字体单位偏差，未通过原门槛。

空白字形在默认/静态情况下返回原点 (0,0)，与简单的半宽/顶部原点假设不符；
静态奇数进宽 735 的水平垂直原点返回 367，而表的半宽是 367.5。静态路径有
20/48 项不满足其自身编码表的原点比较，其中 16 项为空白原点、4 项为奇数半宽。
这些是实测返回行为；尚未证明它们是 CoreText 的普遍 API 契约或全部来自提取器。

下一步应区分原始标准表度量、平台整数返回值与轮廓几何原点，处理空白字形，
并评估输出 HVAR/VVAR 的必要性。**不可统一加 1、忽略失败字段或扩大阈值来
制造通过。** 上述诊断完成状态为 `DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE`。

## 仍须完成的字体本体工作

1. 原件含 23 个 Type 2 切线段，当前可移植渲染器尚未完成其经过独立验证的
   求值；层级内部坐标、平移与旋转也须与同一原件的 Apple 输出比较。
2. 必须实测 CoreText 对每面异常原始 `avar` 的真实用户坐标解释。不能依据
   字典结果、另一个字体面或旧系统字体替代。
3. 必须处理上述度量返回语义并运行原件完整重建。当前源端不支持 MVAR/VVAR
   或变量布局存储的重映射时会拒绝该路径；本次原件没有这些表，不能把它们写成被删除。
4. 验证全部 32 面、47,102 GID/面、Unicode/UVS/GSUB、命名实例、轴组合和未采样
   内部点。采样误差界不等于连续设计空间数学无损。
5. `trak` 原表保留策略与请求取消单字度量 tracking 的 undocumented 属性，不等于
   已证明 Windows/Swirl 排版等价；不要在未确认现有 shaping 行为前重复加字距。

最小缺失条件是一个能私有读取上述 SHA 原件、成功加载全部面的受支持 macOS
环境，优先原件来源 Mac。公开 CI 只接收原创几何夹具，不提供原版私有数据通道。
拿到环境后仍需先校准、再转换、再验收，不保证首次运行就产出合格字体。

## Windows、Swirl 与性能状态

DirectWrite 已在 Windows Server 2022 build 20348 上实际测过原创三面/三轴 TTC：
186 个实例、全部合成 GID、五档软件 DPI 的深浅背景共 10 张 PNG。Qt 6.10.3
原生窗口路径还实测了 D3D11 QRhi / Microsoft Basic Render Driver、彩边、资源复用、
物理面身份与自定义轴变化。其余 61 页导航是另一条 offscreen 路径。

原版转换文件的 Windows 11 实机、系统安装、完整字符 shaping、实际 UI 五档 DPI
和启动/内存/拖动/滚动/布局性能基线均未执行。不能把几何方形 PNG 说成苹方清晰度样张。
当前 Swirl 的 128 MiB 文件上限仍在；若完整目标更大，应依据真实资源测试处理，不能裁剪。
自动策略中的大写 `WDTH`/`HGHT` 保持原默认坐标；针对本次苹方的智能参数调优未验收。

## 复现入口

- 审计、重建与全部 Python 命令：`tools/swirl_vf/README.md`。
- Apple 原生提取：`tools/swirl_vf/platform/CORETEXT_ORACLE.md`、`HVF_ORACLE_README.md`。
- CoreText 三路径诊断：`tools/swirl_vf/platform/diagnose_coretext_metrics.py --help`。
- DirectWrite：`tools/swirl_vf/platform/DIRECTWRITE_README.md`。
- Qt 本地构建与物理来源检查：`docs/SWIRL_VF_NATIVE_ADAPTER_20261019.md`。

正式输出名称只允许 `Swirl-VF.ttc`，构建器不覆盖输入或已有正式输出。完整原件
审计、差异状态、初次失败及修复后日志随用户私有工程包交付，不放入公开仓库。
