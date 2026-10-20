# Swirl-VF B1 度量交接：原生判别完成，生产修复未成立

## 验收结论

**849/850 的失败已定位在 CoreText 原生度量返回路径，具有度量来源和 UPEM 相关性；
尚未建立可接受的生产修复。原件垂直 X 表示阻塞仍在，原件重建仍为 0/32 面。**

本轮完成源码新增、独立原创实验、真实 macOS 验证、专项测试和逐阶段 GitHub
提交推送。所有变更在 `work/vf-metrics-b1`；起点为集成 HEAD
`e505326486202ad4c8e98bb8b66a17b4547c559f`。生产 Swift 提取器、生产重建器、
A3 映射、D1 Windows 代码及原有严格阈值没有修改。144 个读取的集成基线文件
逐一验证 Git blob SHA，全部未变。

本文件所在提交归档最终证据。最后一次真实原生代码测试 SHA 为：

```text
ac8e750bbcd174b5d1ba38214c646e5c55203ded
```

## 1. 849/850 的已知根因与证据边界

原创夹具保持相同的字体设计坐标和 phantom 高度语义：默认 1000、最小 850，
仅比较 UPEM 1000 和 1024。每份字体三个 glyph，测量矩形为 GID 2。

四个独立观测渠道均保留原始记录：

1. CoreText 直接水平/垂直 advance，包括向量和返回总值。
2. CoreText 垂直原点 translation。
3. 实际 witness path，独立反算坐标及可见轮廓。
4. 实际垂直排版位置及相邻 glyph 间距。

API 原始点数、binary64 位、点数到设计单位的精确有理数换算、OpenType 存储整数、
连续设计空间参考和布局结果分别保存。没有中间重复舍入。

首次原生测量：26 份字体，624 个 fixture-coordinate 观测，1,248 条正反序原始
记录，624 对精确重放。核心结果：

| 度量路径 | UPEM | 默认高度 | 最小高度 |
| --- | ---: | ---: | ---: |
| gvar | 1000 | 1000 | **849** |
| gvar | 1024 | 1000 | **850** |
| VVAR | 1000 | 1000 | **850** |
| VVAR | 1024 | 1000 | **850** |

849 已经存在于 API 的原始 binary64 数值中，并进入实际布局间距。
它不是 JSON 显示、Python 转换或下游统一减一产生的差异。

首次结果之后冻结的候选，使用分别舍入的 phantom delta：

```text
R = nearest integer, half ties away from zero
H = 1000 + R(60*y) - R(-90*y)
gvar candidate = trunc(floor(H*65536/UPEM)*UPEM/65536)
VVAR candidate = trunc(1000 + 150*y)
```

后续 16 份字体、52 个不同归一化坐标组合、550 个 fixture-coordinate 观测，
完成 1,100 条正反序记录与 550 对精确重放；高度候选匹配
**gvar 308/308、VVAR 242/242，共 550/550**。候选在全部后续原生测量前冻结，
未根据测量结果重新拟合。

关键独立判别点 y=53/64：

| UPEM | gvar 实测 | VVAR 实测 | 连续参考 |
| ---: | ---: | ---: | ---: |
| 1000 | **1125** | **1124** | 1124.21875 |
| 1024 | **1125** | **1124** | 1124.21875 |

这排除了“非默认位置统一减一”。但是最终整数输出不能唯一识别内部 16.16 位宽；
这是一条通过有限独立样本的行为模型，不是 Apple 内部实现的源代码证明。

**550 个后续观测的严格连续度量验收仍全部失败。**
VVAR 修复该整数端点的表现，并未恢复分数高度精度；UPEM 1024 也没有让所有度量通过。
原始预选 origin-Y ceil-bbox 候选被 96 个反例否定。预先列出的 nearest-bbox
竞争式在 308 个 gvar 路径观测中匹配，但仍有等价的 bearing 舍入表达式，不能据此
唯一定位内部 bbox 算法。

详见 [首次原生结果](evidence/swirl-vf-b1/STAGE1_RESULTS.md)、
[独立复验结果](evidence/swirl-vf-b1/FOLLOWUP_RESULTS.md)、
[两字体最小复现](evidence/swirl-vf-b1/MINIMAL_REPRO.md)。

## 2. 各表实际作用

以下结论只覆盖本轮明确构造的控制变量和 macOS 27.0.1：

| 表或控制 | 实际结果 |
| --- | --- |
| hhea ascent +91 | 全局 CT ascent 改变；测试 glyph advance 不变 |
| vhea ascent +91 | 测试 glyph 度量渠道没有变化 |
| OS/2 typo ascent、USE_TYPO_METRICS、二者组合 | 测试 glyph 度量渠道没有变化 |
| HVAR | 消除本组水平 advance 量化差异，影响其派生 X；不修复垂直高度 |
| VVAR | 整数高度端点恢复；分数高度走直接截断路径，仍不严格等价 |
| VORG，原创 glyf 诊断控制 | Y 取存储值；同时观察到 X 固定在存储默认字宽中心附近 |
| phantom 整体平移、固定可见轮廓 | 高度差异仍存在，排除了简单轮廓位置/可见高度解释 |

VORG 只存 Y。默认存储 advance=1001 的独立控制中，无 VORG 的默认 X=500.5，
添加 VORG 后 X=500，并在不同 WDTH 下保持。这个半整数点还不能唯一证明 trunc
而排除 ties-to-even 等规则。

OpenType 规定 VORG 用于 CFF/CFF2，TrueType glyf 消费者应忽略它。
因此原创 glyf/VORG 控制提供 CoreText 行为证据，尚不是可移植生产方案。
[vmtx 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/vmtx)、
[VORG 规范](https://learn.microsoft.com/en-us/typography/opentype/spec/vorg)。

## 3. 坐标单位实验修复了什么

原始 HGHT 请求 0.828125，CoreText 读回 0.8281。严格相等检查拒绝该请求，
没有将它算为有效度量。请求与读回的 binary64 分别为：

```text
requested: 3fea800000000000
reported:  3fea7fcb923a29c7
```

独立原创控制仅将 fvar HGHT 用户单位范围从 -1/0/1 改为 -16384/0/16384；
原归一化坐标和预测不变。53/64 对应精确原生用户坐标 13568。
全部其他表 payload 逐字节核对，严格轴读回继续要求相等。

旧失败进程的 51 条完整前缀与新单位结果，四渠道 **204/204 数值和 bits 全等**；
字体身份对象因各自 fvar 不同而单独对各自源表核验。旧失败第 52 条没有补值，
旧 partial/no-reverse 报告没有升级为验收通过。

这是实验坐标身份与诊断可观测性的修复，原始度量失败没有被修正或掩盖。

## 4. 原件垂直 X：独立阻塞保持可重复

原件 SHA-256：

```text
39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890
```

严格原件度量采样覆盖 face 0、15、31，GID 0、1、5、19177，默认及 WDTH/HGHT
极值，共 15 请求、60 个独立记录。32 个物理面身份均验证，但不是 32 面度量通过。

源表参考可比较的 face 31 有 20 条，其中 8 条因垂直 X 失败；face 0/15 的
40 条源表参考因原始 avar default anchor 歧义被保留为不可比较，未制造通过。

不依赖这个 A3 源表参考问题，未修改的生产 `with_phantoms` 表示检查仍发现
**24/60 个独立失败**；后续原件/原件复跑再次精确复现同一失败集合，
48/120 是两次测量，不能写成 48 个独立样本。

| 存储默认宽 | 当前宽 | 原生垂直 X | 当前宽/2 | 差异 |
| ---: | ---: | ---: | ---: | ---: |
| 1000 | 800 | 500 | 400 | +100 |
| 1000 | 1200 | 500 | 600 | -100 |
| 600 | 480 | 300 | 240 | +60 |
| 600 | 720 | 300 | 360 | -60 |

这 60 条原件高度全部为 1000、Y 原点全部为 860。不能把合成字体的 849/850
直接描述为这些原件 glyph 的实测高度，更不能称已完成原件修复后的独立验收。

当前生产模型要求 `vertical_x = horizontal_origin_x + current_advance/2`；
这组源数据与该表示约束不兼容。vmtx 没有独立 X 字段；DirectWrite 的 glyph
度量契约也使用水平原点加当前 advance 的一半。
[DirectWrite 定义](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_metrics)。
本轮没有运行或修改 D1 Windows 验收，不能据此宣称跨平台通过。

## 5. 原件 VORG 消融：拒绝原因进一步定位

首轮原件/无 VORG 私有副本/原件复跑，成功记录数为 **60/0/60**。
无 VORG 副本在启动阶段拒绝，没有可用的跨变体度量差值。

随后只做启动层四条件原生实验，新增 glyph 与度量请求均为 0：

| 条件 | 描述符 | 物理面绑定 |
| --- | ---: | ---: |
| 系统原件 | 268 | 32/32 |
| 字节完全相同的私有原件副本 | API 返回 nil，0 | 0/32 |
| 同一路径的无 VORG 私有副本 | API 返回 nil，0 | 0/32 |
| 系统原件复跑 | 268 | 32/32 |

系统原件 A/A 的两份 62,119,485-byte 原始 JSON 逐字节相同。系统路径上的每个
CTFont 均直接读取到 8-byte VORG，源 URL 和全部保留表身份匹配。

两私有副本都在描述符 API 返回 nil 处结束，尚未创建 CTFont。因此：
**不能将前轮拒绝归因于 VORG 删除；也不能将“没有实例可查询”写成 VORG API nil。**
文件位置、元数据和系统加载条件尚未被分别隔离，未证明具体保护机制。
详见 [启动层结果](evidence/swirl-vf-b1/STARTUP_RESULTS.md)。

## 6. CI 终态与测试数量

| Run | 实际测试 SHA | 终态 | 关键结果 |
| --- | --- | --- | --- |
| [39399674995](https://github.com/SOLHK/Swirl/actions/runs/39399674995) | 9836e89130694fdc336c4f4d7de22259c51741f6 | **failure** | 624 对原生判别完成；旧 849/850 与原件严格门禁仍失败 |
| [39401640475](https://github.com/SOLHK/Swirl/actions/runs/39401640475) | 03c34a68a6ad52035097d123a9e5ecd2948e310f | **failure** | HGHT 严格读回拒绝；完整前缀保留，不作为完整验收 |
| [39403338270](https://github.com/SOLHK/Swirl/actions/runs/39403338270) | aeb2574879ca76290f9e22c2e319f27f422e7ae6 | **failure** | 550 对复验完成；96 个 Y 候选反例；原件 X 仍失败；私有副本 0 记录 |
| [39405669524](https://github.com/SOLHK/Swirl/actions/runs/39405669524) | ac8e750bbcd174b5d1ba38214c646e5c55203ded | **success** | 四条件启动诊断完成；0 新度量、0 新重建面 |

最终源测试：**592 项运行，585 通过、7 项可选 HarfBuzz 跳过；audit 6/6 通过。**
新增 B1 专项共 **144 项**。本地协议测试、原生观测数量和原件完成数量分开计数。

已推送的阶段提交：

- `9836e89130694fdc336c4f4d7de22259c51741f6`：首轮独立夹具、四渠道、严格原件检查。
- `d283e2e5ad8d43aa3808e66ac6093c3252c5d9e0`：首次原生证据。
- `03c34a68a6ad52035097d123a9e5ecd2948e310f`：冻结独立复验与原件 VORG 消融。
- `3b8f113d811413464fe38136ca1dd43feedf5397`：完整首次原始归档及失败前缀。
- `aeb2574879ca76290f9e22c2e319f27f422e7ae6`：严格坐标单位控制。
- `bdbd6a04bfb23d340e495ab5bb3933f572d96cbe`：550 观测、反例和原件拒绝证据。
- `ac8e750bbcd174b5d1ba38214c646e5c55203ded`：启动层四条件控制与最小复现说明。

## 7. 保留的原始证据与下一步

原始 849/850 失败日志继续逐字节保留：

```text
docs/evidence/swirl-vf-b1/legacy-39394041915-apple.log
SHA256 52c3643f2ce26def0db59c32e96ed42861b82ef0a0d4b7918f3945ac62b51694
```

首次、失败前缀、独立复验、原件消融、启动控制的完整原生 ZIP 都已下载并校验
SHA-256/ZIP CRC，保存于本分支 evidence/archives；每阶段保留原始 job log、
summary 和 provenance。原件字体与轮廓未上传。

下一步的实质前提：

1. **生产表示方案需要总负责人协调。** 在当前标准 glyf/phantom 的 X 约束下，
   现有原件样本已给出明确不兼容输入；继续加密同一采样或添加统一补偿不会建立
   等价。共享入口按任务要求保留未改，不能由 B1 自行采用非标准 VORG 绕过。
2. 若继续原件 VORG 因果实验，先找到能将未改私有副本稳定绑定到 32 面的原生加载
   方法，再只改变 VORG。当前 URL 路径不满足这个前提，重复 60 条度量没有新信息。
3. 有真实编码/表示修复后，冻结未参与拟合的原件 face/GID/位置组合进行严格复验，
   再推进全 32 面、全 GID、Windows 与 Qt/Swirl 验收；完整轮廓验证不能替代度量。
4. 保留 1/32 的原生度量预算、1e-5 的 X 表示检查及原始失败对照。

**最终状态：已完成有原生证据的 B1 判别和诊断改进；真实生产度量修复尚未成立，
仍阻止原件重建，0 个完成模型、0/32 面、没有可接受的原件 Swirl-VF.ttc。**
