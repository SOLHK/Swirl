# 0.2.9：原生阴影计算与长帧隔离

继续 `work/swirl-ui-v2-20261024`，基于 `356de1c96081c903e8ca2f2f4d557a30ece8b471`（0.2.8）。节点、策略和订阅页面已有重构成果；本轮聚焦阶段 6 的实际性能，不重新执行阶段 1/2，不改 main、其他开发窗口、Rust Core 接口或现有安装。

## 产品变化

Windows 兼容阴影的原解析函数每次尺寸变化都会重新计算窗口外围的 superellipse 距离、覆盖率及高斯衰减。改为 GUI 线程拥有的 `WindowShadowRenderer`：按精确物理半径和 DPR 缓存活动／非活动两个小内核，尺寸变化只复制角区、填充恒定边缘与透明内部。没有使用插值或镜像上下阴影，保留下移 2.5dp 的非对称阴影、原强度、透明中心及 14dp 外轮廓。

仍需写入整幅 ARGB 图及上传既有 HWND；不能称 O(1) 或零成本。内核只保留两张，半径／DPR 变化使两者失效；极小尺寸走原解析函数，修正原函数在空的内部区间向后跳造成的非终止风险。无效／溢出尺寸和分配失败返回空图，原生适配层安全隐藏阴影并保留重试机会。材质、窗口 Z 顺序、输入穿透、最大化、动画、缓存与所有业务功能保持。

参考 Qt 官方 [BorderImage 九区复用](https://doc.qt.io/qt-6.10/qml-qtquick-borderimage.html) 的可观察组织方式，独立实现 CPU 像素复制；不引入新框架或依赖。继续使用既有 UI/Motion skills，新增 Qt C++ Review 的确定性扫描及六域审查；扫描包含既有风格提示，不能称零 lint。

## 验证契约

`SwirlWindowShadowTests` 使用冻结的独立原函数，220 组整图 ARGB 零容差比较，覆盖 DPR 1/1.25/1.5/1.75/2、普通及六组历史缩放尺寸、奇数物理像素、切片边界、极小尺寸、活动状态与缓存复用。只为极小输入的原非终止区间加正长度保护。另检查缓存失效、透明内部、垂直偏移及 17 组无效输入；整个 QtTest 为 243 项。纯数学 DPR 测试不代替用户的人工 DPI 矩阵。

新增 UI_TESTS 专属 `RouteBench`，隔离纯切页、固定活动页缩放和混合操作。GUI 线程记录独立导航／resize 请求、返回及实际状态变化、阴影重建计数、incubation 数量；render 回调仅按值持有原生采样状态，不读 QML。停止锁形成写者屏障，随后断开回调并序列化，不将 disconnect 当 join。全部 setup、静止、阶段交叉和恢复间隔保留；失败预热不进入测量。上限及丢样计数、探针开销和实际进程退出码另行校验。

## 测试环境的边界

首批原生基线通过后，never-activated Windows desktop 的 D3D 帧调度出现停滞，旧解析算法及完整旧 Motion 场景也能重现；不是阴影优化修复失败的单一证据。失败 trace、81 项级联失败、后续预热失败及一次旧 Motion fixture 的访问冲突全部保留，不计为通过。

仅改 qWaitFor 或仅 setup 请求帧不足以恢复；basic loop 能完成检查但只有 3 帧，不能冒充有效性能结果。使用同一测试进程环境 `QT_D3D_NO_VBLANK_THREAD=1` 和 `QSG_NO_VSYNC=1` 后恢复有帧的可比较运行。两项仅用于诊断／采样，产品不设置它们。schema 2 记录这些参数，不能跨 render loop、VSync 或预热协议混算改善。setup 的 16ms 帧请求在测量前停止，测量保持精确事件循环，没有常驻重绘。

参考 [Qt 6.10.3 Windows 更新服务](https://github.com/qt/qtbase/blob/v6.10.3/src/plugins/platforms/windows/qwindowswindow.cpp)、[VBlank 服务](https://github.com/qt/qtbase/blob/v6.10.3/src/gui/rhi/qdxgivsyncservice.cpp) 和 [Qt threaded render loop](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/scenegraph/qsgthreadedrenderloop.cpp)。这些源码支持诊断路径，尚未捕获本机驱动底层失败码，不宣称已修复驱动问题。

原生 frameSwapped 是排入呈现的节奏，不是显示器实际呈现、GPU 耗时或输入到光子的延迟。无 VSync 的有效样本也不能证明稳定 60FPS。Profiler 与 native 时间轴不强行对齐，静止终点的 32ms pageCommit 保留；本轮不将它或隐藏页面绑定短路混入阴影修复。

原始二进制快照／失败与成功记录在忽略目录 `D:/Codex/measurements/swirl-ui-v029-20261025/`；分析、lint、审查与 CI 下载在 `work/ui-v029/`。对照基线是明确标注的临时旧函数 bypass 版本，保留源码变体与 EXE/DLL 哈希，不冒充精确提交的生产包。最终同提交验证、CI 17 套核心／安全／网络／阴影测试、安装器和包身份由独立交付记录确认。

本机代理、TUN、路由、DNS、已有安装和私人来源均不改动。真实供应商、Codex 私人联网、应用识别、TUN、人工 DPI、多屏和长期稳定性仍独立验收。下一阶段继续处理切页终点／隐藏缓存绑定及实际活动窗口的呈现验证；不得为了跑分删除动效、取消缓存或隐去失败。当前无需更换模型。
