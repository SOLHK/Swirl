# CoreText 原版字形参照提取器

`coretext_extract.swift` 接受一份用户本地提供的 TTC／TTF／OTF，通过 CoreText 在**原始用户轴坐标**下提取轮廓与度量。程序不安装字体、不改变系统字体缓存、不修改原文件。输入文件及输出的轮廓 JSONL 均不得随可公开工具代码一同上传。

它为后续转换提供原生参照，尤其用于验证 Apple 原文件中带重复／逆序记录的 `avar` 实际效果。它不使用 fontTools 折叠后的 `avar` 字典推测 CoreText 行为。

## 构建与运行

需要 macOS 的 CoreText／CoreGraphics／CryptoKit 与 Xcode Command Line Tools：

```bash
swiftc -O platform/coretext_extract.swift -o coretext_extract
./coretext_extract /private/path/PingFangUI.ttc < requests.jsonl > private-oracle.jsonl
```

stdin 每行为一条请求，最大 1 MiB，每批最多 4096 个字形：

```json
{"request_id":"face0-mixed01","face_index":0,"location":{"WDTH":631.25,"wght":523.75,"HGHT":711.125},"glyph_ids":[0,1,2,100,200]}
```

`face_index` 是原始 TTC 目录顺序，**不是** CoreText 枚举顺序。程序先解析原文件目录，再以 CoreText 返回的原始 `name` 表寻找候选，并核对该面的全部原始表 SHA-256、UPEM 和 GID 数量。身份不一致的字体面无法用于提取；不会静默回退为同名系统字体。

输出首行为 metadata，包含原文件 SHA-256、操作系统版本、所有原始字体面与 CoreText 身份核对结果。每个字形各占一行；最终有 summary。日志写 stderr。出现错误后继续处理独立的其他请求，但最后返回非零退出码。

## 小数回读与独立逐批验证

普通调用仍使用原有 `1e-6` 回读检查。`constructInstance` 仅负责实例构造和身份核验，
`makeInstance` 继续执行原检查。显式参数 `--axis-observations` 会输出
`axis_observations_only=true` 的**未接受观测**；重建器和度量适配器拒绝直接使用这种数据。

`tools/verified_axis_oracle.py` 提供单独的验收层。它首先核对实际源 SHA、字节数、全部
物理面的所有表哈希及完整 fvar（包含 flags/hidden），每次请求要求全部源轴显式给定。
请求与回读只要精确不相同，必须符合已命名的正数四位截断候选；这只是本构造方式的
可证伪候选，并非 Apple 公开 API 契约。未知规则或缺少非默认轴回读会失败。

适配器随后用首次回读坐标构造一次独立实例，要求回读精确稳定，并逐个比较整批所有
GID 的原始命令类型、顺序、数值、bounds、路径状态及全部原始度量。没有 epsilon、
循环寻找另一坐标或按点选择映射。晚到的一个 GID 失败时，整批均不释放给重建器。
通过的记录保留原始 requested/reported、轮廓和度量，另附验证出处。

供现有构建器调用的可执行入口可由 `make_launcher(path, native_binary)` 创建。
它绑定适配器源码、管道实现、原生二进制和 Python/fontTools 版本；重建检查点因此
不会静默跨用另一版 oracle。结束时的外部 request/GID 计数与内部 replay 计数分开。
重建器必须验证 summary、EOF、退出码和原件未变后才可发布最终 TTC。

原件 CI 还单独运行 `probe_axis_first_writer.py`，让两个新进程以相反顺序创建请求值
和事先计算的截断值实例。它能检查所选字形的顺序依赖，不能证明系统字体服务的全局
缓存已经清空。所有此类诊断及适配器仍不等于完整 avar/HVGL 映射或连续空间验收。

## 轮廓与度量定义

每个实例明确设置全部源 `fvar` 轴，未提供的轴用源默认值；未知标签、超出范围或非有限数值直接报错。程序核对 `CTFontCopyVariation()` 报告值，但不会把“轴值被接受”解释成“该轴的所有字形已正确变化”。

从已经核对身份的 CTFont 创建实例，并保留原来的 optical size 选择，以免把字号增加到 UPEM 时切换到其他 UI Text／Display 字体。返回路径使用该面的原始 UPEM 作为字体大小，矩阵为 identity，不额外平移，坐标为字体单位、y 轴向上、原始水平原点为 `(0,0)`。

`commands` 原样区分 `moveTo`、`lineTo`、`qCurveTo`、`curveTo`、`closePath`。没有把三次曲线偷偷转成折线或二次曲线。若 CoreText 返回 nil 路径，只有源 glyf／HVF 结构能够证明字形没有可绘制轮廓时才按空字形接纳；其他 nil 结果明确报错。支持 HVF 空字形判定的条件是公开 3.1 头布局且不存在 hvpm 映射；未支持的映射不能靠默认值猜测。

| 输出字段 | 含义 |
|---|---|
| `bounds` | 实际曲线包围盒 `[x,y,width,height]`，不是控制点包围盒 |
| `lsb` | 实际曲线 `minX` 相对原始水平原点的几何边距；不冒充原始 hmtx 存储值 |
| `horizontal_origin_x/y` | 0／0，路径 API 使用的原始水平绘制原点 |
| `advance_width` | 禁用 tracking 后的 CoreText 水平进宽 |
| `advance_height` | CoreText 垂直方向 API 返回的 `CGSize.width`；该 API 的度量预旋转到宽度分量 |
| `vertical_origin_x/y` | `CTFontGetVerticalTranslationsForGlyphs` 原始向量的相反数，转为 y 向上的字形原点 |
| `horizontal_advance_vector` | 水平 API 返回的原始 width／height |
| `vertical_advance_vector` | 垂直 API 返回的原始 width／height，保留符号 |
| `vertical_origin_translation` | 垂直原点 API 返回的原始向量，保留符号 |

构建 TrueType 时，控制点 `xMin` 可能不同于真实曲线 `bounds.x`，不能直接把两者混用来计算 phantom origin。转换器必须使用明确的原点字段，单独处理存储 LSB 和实际几何边距。

## tracking 与垂直度量的技术依据

仅使用 `CTFontGetAdvancesForGlyphs` 并不能保证没有 `trak`。提取器参照成熟 Skia 的技术方式，把 **`NSCTFontUnscaledTrackingAttribute=0`** 放入 descriptor 来禁用 tracking，并在 metadata 标注这是未文档化的属性。它必须通过带非零 `trak` 的原生测试验证，不能凭设置属性即宣布奏效。

API 方向的处理由 Apple 的函数说明及 HarfBuzz 的 CoreText 后端交叉核对。HarfBuzz 使用垂直 API 的 `.width` 作为 advance，并对原点位移的两个分量取负。这里仅采用接口的坐标解释，未引入其他字体字形数据。

- [Apple CTFontGetAdvancesForGlyphs](https://developer.apple.com/documentation/coretext/ctfontgetadvancesforglyphs(_:_:_:_:_:))
- [Apple CTFontGetVerticalTranslationsForGlyphs](https://developer.apple.com/documentation/coretext/ctfontgetverticaltranslationsforglyphs(_:_:_:_:))
- [Skia 的 tracking／optical size 处理，固定提交 d2b9e48baf1697760afc1dc8ea3ad40110b8cacc](https://skia.googlesource.com/skia.git/+/d2b9e48baf1697760afc1dc8ea3ad40110b8cacc/src/utils/mac/SkCTFontCreateExactCopy.cpp)
- [HarfBuzz CoreText 度量，固定提交 22f77d48abc35c1e053d02f1ada0d8f1ce1b8423](https://chromium.googlesource.com/external/github.com/harfbuzz/harfbuzz/+/22f77d48abc35c1e053d02f1ada0d8f1ce1b8423/src/hb-coretext-font.cc)

## 原生回归测试

```bash
python platform/test_coretext_extract.py --output /private/test-output --require-native
```

测试脚本自行生成两字体面的标准可变 TTC。其几何完全由本项目的矩形／二次曲线测试代码定义，含三个轴、跨轴变化、不同 UPEM、空字形、明确的垂直度量，以及恒定非零 tracking。测试 27 个轴端点／默认值组合及两个相邻的非整数字重内部点，逐项对照解析可计算的轮廓和进宽。误差阈值预先规定为 1/32 字体单位，用于容纳原生内部的 26.6 量化。

脚本将编译日志、请求、原始原生响应、stderr 和 JSON 验收报告全部保存。Linux 会明确记录 `NOT_RUN`；使用 `--require-native` 时返回失败。**合成字体的 macOS 测试通过也不能代替本次原版苹方的 CoreText 运行结果，更不能代替 Windows／Qt 验收。**
