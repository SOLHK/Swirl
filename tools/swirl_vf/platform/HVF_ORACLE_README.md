# Apple HVF 原版轮廓基准工具

这组源码调用 Apple 已公开的 `hvf` C 库，直接把指定 TTC 字体面的 `hvgl`、可选 `hvpm` 交给 Apple 实现。输出不做整数字形取整，也不转成 TrueType；所有曲线坐标用可往返恢复 binary64 的 17 位十进制有效数字记录。

**目前 Linux 工作区只验证了“不支持平台时明确返回 NOT_RUN”的分支，尚未在真实 Mac 编译或运行。** 不能把这组工具存在、Linux 编译成功或人工方形测试通过当作原版苹方转换验收通过。

## 依赖和真实 API

需要 Apple 硬件上的 macOS、包含 `<hvf/Scaler.h>` 的 Xcode SDK、`libhvf` 和 Python 3。公开 C API 标注从 macOS 15.4 提供；表规范页面的支持日期另写 macOS 15.6。工具记录实际运行库版本，具体机器以实际编译和调用结果为准。

- [Apple HVF](https://developer.apple.com/documentation/hvf)
- [打开 renderer](https://developer.apple.com/documentation/hvf/hvf_open_part_renderer)
- [指定 part](https://developer.apple.com/documentation/hvf/hvf_set_render_part)
- [设置设计坐标](https://developer.apple.com/documentation/hvf/hvf_set_axis_value)
- [返回曲线的 callback](https://developer.apple.com/documentation/hvf/hvfrendercontext)
- [FreeType 上游 Apple HVF 集成](https://lists.gnu.org/archive/html/freetype-commit/2025-11/msg00038.html)：仅核对系统头文件、链接方式及 API 语义，没有复制该实现。

## 最小运行

在本目录运行，替换为你的原版字体路径：

```sh
python3 run_hvf_oracle.py --font /path/to/PingFangUI.ttc --out /path/to/private-hvf-run --face 0 --coords=0,0,0 --count 20
```

`--count 0` 提取该字体面 `maxp` 声明的全部字形。每个输出目录只能使用一次，避免覆盖先前证据。另一实例可以复用已编译程序：

```sh
python3 run_hvf_oracle.py --font /path/to/PingFangUI.ttc --out /path/to/private-hvf-run-2 --binary /path/to/private-hvf-run/hvf_oracle --face 0 --coords=-0.314159,0.271828,-0.161803 --count 20
```

**坐标是经过 fvar 归一化及 avar 后的设计坐标，并不是字重 400/500 或 WDTH 500 这种用户坐标。** 工具不擅自修复、排序或消除原版 avar 记录。原版 avar 存在歧义时，必须另外比对 CoreText 的用户坐标结果。

输出包括 `hvf-run.json`（输入前后 SHA-256、OS、源码和程序哈希、真实编译命令及退出码）、`hvf-outlines.jsonl`（每个 glyph/part 的原始 callback）、编译及运行 stderr。

接口可以用 `--parts` 访问内部 part，但当前参数仍按该字体面的 fvar 轴数接收；若内部 part 的局部轴多于 fvar 轴，工具会明确失败。字体面可见 glyph 是主要验收入口。

## 可公开的合成测试

```sh
python3 make_synthetic_hvf.py /tmp/swirl-synthetic-hvf.ttf
xcrun clang -std=c11 -O2 -Wall -Wextra -Werror -mmacosx-version-min=15.4 hvf_oracle.c -lhvf -o /tmp/swirl-hvf-oracle
python3 verify_synthetic_hvf.py --binary /tmp/swirl-hvf-oracle --fixture /tmp/swirl-synthetic-hvf.ttf --out /tmp/swirl-hvf-synthetic-result
```

合成 fixture 来自完全自行绘制的方形，测试 27 个角点/中点组合以及 2 个不在网格上的位置。预期几何位置使用独立的简单仿射公式计算。该测试只证明 renderer 调用、轴传递和回调记录路径可用，未覆盖真实苹方的层级组件和 tangent，也未证明任何原版字形已被等价转换。

`make_synthetic_hvf.py` 需要 `fonttools==4.61.1`。生成物仅用于测试，不是可供安装的标准 Windows 字体。

## 不得混淆的验收范围

| 输出/测试 | 可以证明 | 不能证明 |
| --- | --- | --- |
| Apple HVF 返回 EXTRACTED | 指定输入和设计坐标确实由 Apple HVF 输出了曲线 | avar 用户映射正确、CoreText 自动行为已保留 |
| 合成几何 PASS | Apple API 接入与 3 轴传参通过合成用例 | 原版 177 个 shape、所有 Composite 都准确 |
| 字形 callback | 未缩放的曲线坐标、part 层级和命令类型 | hmtx/HVAR/trak、排版、文本识别、像素清晰度 |
| 非 Mac 的 77 返回码 | 明确的不可运行记录 | 任何 macOS 或 Windows 原生运行成功 |

输出 JSONL 包含原版轮廓，应当与原版字体一样留在用户私有环境。公开仓库只放工具源码、说明和完全自行生成的合成测试数据。
