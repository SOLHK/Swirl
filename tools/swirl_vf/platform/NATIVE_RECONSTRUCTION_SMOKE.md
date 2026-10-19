# 原生重建完整流程的合成测试

`test_native_reconstruction.py` 在 macOS 上执行一条真正的 CoreText → 重建 CLI → 标准 TTC → CoreText 流程，用于发现进程协议、字体构建、序列化和度量接口之间的问题。测试仅使用 `test_coretext_extract.make_fixture()` 自行生成的两字体面数据，不读取 Apple 字体。

## 运行

需要 macOS、Swift 编译器和项目的 Python 依赖。可以重复利用已经构建的 `coretext_extract`：

```bash
python platform/test_native_reconstruction.py \
  --output /private/tmp/swirl-native-reconstruction-check \
  --binary /private/tmp/coretext_extract \
  --require-native
```

省略 `--binary` 会实际编译相邻的 `coretext_extract.swift`。每次必须使用新的输出目录。Linux 等没有 CoreText 的系统会写入 `NOT_RUN`；指定 `--require-native` 时返回非零，不能被 CI 当成原生测试通过。

## 实际检查

1. 生成两面、三轴、三个 GID 的原创测试 TTC，包括不同 UPEM、隐藏宽度/高度轴、空白字形、二次曲线、WDTH/HGHT 联动和非零 tracking。
2. 使用真实 CoreText 提取全部 27 个轴角点/默认值组合及两个相邻分数字重位置。58 条请求共返回 174 个字形，先与已定义的解析公式比较；沿用原生 fixture 的 1/32 字体单位容差。
3. 直接运行 `tools/rebuild.py`，不是模拟 Python 内部调用。批大小为 2，使三个 GID 分成两批，覆盖末批不满的协议路径。输出限定为自动清理目录内的 `Swirl-VF.ttc`。
4. 核对两面顺序、全部 GID、字符映射、UPEM、fvar 原始字节、轴名/范围/隐藏标志、identity avar、默认 hmtx/vmtx、水平原点和垂直原点。原非零 trak 也必须仍在。
5. 要求重建报告包含每个面的训练/独立内部点证据、完整序列化系数验证，以及 TTC 表字节打包验证；拒绝“无损”或 Windows 已验收的错误状态。
6. 对重建 TTC 再执行相同 174 条原生字形测量，比较轮廓控制点、真实曲线边界、前进宽度、LSB 和水平/垂直原点。沿用重建器预先规定的 1 字体单位误差上限，不因失败自动放宽。轮廓比较只消除零长直线和重复的直线闭合边。

## 输出与判定边界

输出保留命令、编译日志、原生响应、重建报告、源码/输入/候选字体的 SHA-256 和 `native_reconstruction_result.json`。输入 fixture 和临时重建字体在成功或异常退出时由临时目录机制清理，不把测试字体留下来冒充正式交付。

唯一成功状态为 `PASS_SYNTHETIC_NATIVE_RECONSTRUCTION_ONLY`。它说明这份原创 fixture 的实际原生转换链路通过了这些检查，不证明原版苹方完成转换，不证明连续空间无损，也不证明 Windows、Qt 或 Swirl UI 通过验收。
