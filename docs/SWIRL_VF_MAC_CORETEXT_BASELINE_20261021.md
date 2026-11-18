# Swirl-VF：本机 CoreText 基线与字体加载阻塞

2026-10-21 在用户 Mac 上实际编译、执行，源码基线为 `5ee610d`。这是本机结果，
不是新提交的 GitHub CI 结果。完整安全汇总及所测源码哈希见
[证据](evidence/SWIRL_VF_MAC_CORETEXT_BASELINE_20261021.json)。

## 核实后的环境与原件

系统实际为 **macOS 26.3 / 25D125 / arm64**；Xcode 26.6、Swift 6.3.3、SDK 26.5、
HarfBuzz 14.6.0、Python 3.12.15、fontTools 4.61.1。SDK 版本不等于系统运行时版本。
原件 61,473,880 字节，SHA-256 为
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`，测试后未变。
fontTools 确认 32 面、每面 47,102 GID，均有 `WDTH/wght/HGHT`；字重默认值和上限
必须逐面读取，不能统一假定 500/900。

## 实际结果

| 检查 | 本机结果 |
| --- | --- |
| 原件 CoreText 全表身份核验 | 0/32，全部不可用 |
| 原件 URL 描述符入口 | 返回 nil，零描述符 |
| 原件内存数据描述符入口 | 返回空数组，零描述符 |
| 原件 CGFont 数据入口 | 创建失败 |
| 系统 PingFangSC-Regular 阳性对照 | 可加载，49,533 GID，无 hvgl 表；仅作系统字体服务对照 |
| 合成字体生产轴校验器 | 22/22 通过 |
| 合成字体严格原始度量门槛 | 失败：首个点垂直进宽 849，期望 850，门槛保持 1/32 FUnit |
| 原生 binary64 JSON 往返 | 1,038 个数，生产编码器零位差；本机 legacy 路径也为零位差 |
| 三种合成表编码 × 四个字号的度量诊断 | 完成 2,088 条字形观测，仍有超限误差 |
| 两面三字形合成字体完整重建和原生回读 | 通过；58 请求、174 字形，所测控制点/表度量/包围盒差为零 |
| Python 回归 | 595 项，7 项跳过，无失败；另有 6 项审计测试通过 |

四个字号是 UPEM 的 0.25/1/16/64 倍。每种编码每个字号均为 174 条观测。
gvar-only 每个字号有 106 条超过原度量门槛，显式 HVAR/VVAR 和 bearing-map 编码各为 6 条；
换字号没有消除这些已测源单位误差。合成重建使用明确的源表度量，原始 CoreText API 失败
单独保留，不能把这两项合并成严格 API 通过。合成候选为 3,424 字节，测试后已删除。

原件没有进入轴坐标或字形采样阶段，不能报告原件 864 点通过。现有 macOS 27.0.1
成功证据属于其原有环境。运行时字体格式支持差异是待验证假设；本次三个加载入口的
失败不能独立证明根因，也不能证明原件损坏。继续原件精度测试需要先取得能通过该原件
32 面身份核验的原生运行环境；不得拿同名系统字体填充结果。

## 已复现并修复的问题

旧 `diagnose_axis_readback.py` 在任何面不可用时由 Swift 顶层抛错，实际进程退出 -5，
Python 随即抛错，没有落盘结构化结果。现已先检查全部物理面：有不可用面即保存
`BLOCKED_SOURCE_IDENTITY`、真实核验数量、不可用索引、三种入口结果和系统版本，
在构造任何轴实例前停止。CLI 返回 2，区分成功完成的观察诊断。
输出另绑定实际生成 Swift harness 的 SHA-256。五项新增回归覆盖零/部分可用、
矛盾计数、阻塞时不可丢弃观测、报告持久化和原有轴误差阈值。

本机用修复后程序再次实际运行：报告保存成功、0/32、零轴/字形观测、退出 2，
没有 Swift trap。生产提取器、重建器及原有阈值未修改。

## 复现与接续

在项目 `.venv` 中运行，下列原件诊断当前应返回 2，并保存报告。输出路径需全新；
原件、轮廓转储和候选字体仍留本机私有目录。

```sh
.venv/bin/python tools/swirl_vf/platform/diagnose_axis_readback.py \
  /Users/mac430/Fonts/PingFangUI.ttc --output /private/tmp/new-axis-readback.json
.venv/bin/python tools/swirl_vf/platform/test_coretext_extract.py \
  --output /private/tmp/new-synthetic-strict --require-native
.venv/bin/python tools/swirl_vf/platform/diagnose_coretext_precision.py \
  --output /private/tmp/new-synthetic-precision --require-native
.venv/bin/python tools/swirl_vf/platform/test_native_table_metrics.py \
  --output /private/tmp/new-synthetic-table --require-native
```

第一阶段用户消息在“最终目标”处截断，已请求补充。此次完成的是可独立验证的
本机基线和诊断修复，没有声称原件精度验收、全字体重建、Windows 或 Swirl UI 验收完成。

实现前查阅的成熟开源主参考：

- [HarfBuzz CoreText 后端](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-coretext-font.cc)：交叉核对原生 advance/origin API 使用；独立实现，没有复制代码。
- [fontTools instancer](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/varLib/instancer/__init__.py)：区分标准表实例与 CoreText API 度量；不将解析成功当作原生可加载。
- [Apple URL 描述符 API](https://developer.apple.com/documentation/coretext/ctfontmanagercreatefontdescriptorsfromurl(_:))、[内存数据描述符 API](https://developer.apple.com/documentation/coretext/ctfontmanagercreatefontdescriptorsfromdata(_:))：采用无安装的原生加载对照。
