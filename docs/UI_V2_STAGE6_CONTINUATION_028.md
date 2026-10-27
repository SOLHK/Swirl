# 0.2.8：三页一致性与原生性能继续验证

接续 GitHub `63adc0787676f8ff73fa6e9c1a757b09c7752faf`（0.2.7）。阶段 1/2、节点资源库、V2 策略事务和订阅管理均有既有成果，本轮不重做这些架构，也不把历史交接中的“下一阶段”误当当前状态。继续 `work/swirl-ui-v2-20261024`，不改 main，不改其他窗口。

## 本轮实质变化

- 节点列表增加逐行收藏和省略号操作，复用实际收藏保存、节点详情、独立请求测试、编辑和安全信息复制。节点右键进入同一真实菜单，去掉原默认菜单中只弹提示的查看／导出占位入口。没有新增连接／切换出口操作。
- 主筛选变为全部、实际测试可用、收藏；最近使用保留在高级筛选，与收藏明确互斥并同步开关。标题显示实际总数；去掉重复的整页详情／收藏命令条。清空图标从不支持的 close 修为 dismiss。
- SwirlDataTable 的操作槽为 opt-in，未传入时保留其他页面行为。一个复用 ListView 继续管理节点和来源，操作槽只为非分区、非池化行实例化；稳定身份变化或池化会关闭菜单。详情前同步当前可见行，避免点 B 的操作却从 A 行飞出／返回。
- 策略服务和组使用严格对齐的出口列、44dp 省略号命中区及分组删除菜单。默认策略为置顶扁平行，手动组直接显示已配置成员名。自动组不虚构统一运行节点，实际请求出口继续从真实连接详情读取。选择器的真实选中、不可用状态和保存回执保持。
- 共享按钮、图标按钮、搜索、下拉、分段及提示框统一中性表面；保留公开属性、原尺寸、动态字体、危险／禁用／按压及键盘行为。鼠标不留下蓝框，键盘使用中性轮廓。下拉用单向箭头、真实勾选与中性选中背景。
- 隐藏 HTTP 请求详情不再在 Main 启动时创建。首次请求异步加载，Esc／导航取消尚未打开的意图；首次完成后保留同一实例、过滤和选择状态。捕获服务本身及已有代理接口不变。

## 性能证据的正确口径

使用已有 Hallmark、UI UX Pro Max、Motion、Qt UI Design/QML/Review/Profiler skills，沿用原生 QML、既有字体与 motion tokens，没有新增 UI 框架。窗口和侧栏尺寸／14dp、导航入口、活动页主布局及模式胶囊保持。

本轮先保留了上一轮 0.2.7 的实际测试 EXE/DLL 快照及完整 trace：`D:/Codex/measurements/swirl-ui-v028-20261025/baseline-63adc07/`。该二进制在源码提交前构建，保留原 generated identity 和哈希，不冒充精确同 SHA 的生产包；仅作明确标注的基线。旧 trace、失败和警告全部保留。

旧 profile 明确显示隐藏 CaptureInspectorPage 在启动直接创建约 174.5ms，是本轮延迟加载的依据。旧解析器将动画记录的整数 FPS 倒数列作帧时间，且跳过使用 timing1..4 的 SceneGraph 事件；因此旧报告中的这些数值不能直接证明可见掉帧。原生 frameSwapped 的长间隔是真实呈现间隔，但旧记录没有 active／idle 端点，不可称为已定位的动画掉帧。

独立分析工具保存在 `work/ui-v028/AnalyzeQmlTimeline.py`，不改全局 skill parser。Qt 6.10.3 的 sg0、sg3、sg6 分别映射 renderer、render-loop、GUI polish/sync；timing 是相邻时间戳差，GUI timing3 包含等待同步。事件区间可能重叠，禁止相加。旧 trace 在1500ms之后的 render-loop 最大6.344ms并不能解释所有原生长间隔，也不证明稳定60FPS。

新原生采样保留原全部聚合，新增有界逐帧时间、route、moving、pending、阶段与快照年龄，明确端点不等于完整活动历史。所有 QML 属性由 GUI 线程读取；render 回调只访问按值持有的 shared_ptr 原生状态。断开后在途回调不会访问已销毁的栈变量；停止时锁内复制数据，JSON 转换在采样结束后。记录探针开销，不跨不同工作负载计算整体改善百分比。测试只将低于窗口最小高度的请求钳到同一实际高度，避免无意义的 Windows 几何警告。

## 验证范围与剩余边界

本地原始记录位于忽略目录 `work/ui-v028/`。新增节点行操作的真实保存／详情／出口隔离检查、capture 首次确实异步加载／取消／重开／保留状态／modal 清理检查；原有网络、事务、Esc、减少动态效果断言保留。六项独立 QML 审查覆盖绑定、布局、生命周期、委托、状态和渲染；不是把确定性风格扫描当零问题。

本轮曾发现 Tooltip 继承层覆写 deferred contentItem/background 后，由字体 Binding 提前读取内容留下未完成的 Qt 创建计数。处理方式是让 SwirlToolTip 本体完整声明中性内容／背景，字体窗口直接来自 parent；调用者不再覆写 deferred 内容。没有延长等待或屏蔽警告。最终是否消除由重跑日志确认，不能仅凭代码判断。

提交前检查点：节点616/0、策略252/0、动效202/0，三进程退出0，修正后的日志没有QML警告或未完成创建的退出警告。动效含13项新捕获详情生命周期断言，逐帧样本463条、丢弃0；原生P99仍55.4451ms、有7个超过50ms间隔，不能称稳定60FPS，最终同提交profile另行记录。100/500/1000/2000节点的大列表首轮404项断言通过但含11项未完成创建计数，旧报告保留；提示框修正后的最终大列表重跑和CI结果由交付记录说明。7项portable boundary与尺寸／侧栏源码边界通过。

交付前结果、最终 source SHA、CI、包版本与摘要另有精确交付记录，不由本文件推定通过。完整回归交给同提交 GitHub CI，Windows 生产包关闭 UI 测试入口，核对 EXE/DLL/源码身份与清单。

本机代理、TUN、路由、DNS、现有安装和私人来源均不改动；没有重下载私人订阅。受控 HTTPS／Rust 收包、原生界面、安装器 fixture 和真实供应商／Codex账号服务是不同证据。应用进程识别、TUN、私人联网、完整 DPI／多屏、长期稳定及主观视觉仍独立验收；不把这些未完成项掩盖为 UI 阶段通过。当前无需切换模型。

参考：[Qt deferred 创建](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quicktemplates/qquickdeferredexecute.cpp)、[Qt profiler 定义](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/util/qquickprofiler_p.h)、[Qt render loop](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/quick/scenegraph/qsgthreadedrenderloop.cpp)。清单／菜单组织延续已记录的 [VS Code](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace) 与 [GNOME Software](https://github.com/GNOME/gnome-software/blob/main/src/gs-updates-page.ui) 可观测模式，独立实现 QML。
