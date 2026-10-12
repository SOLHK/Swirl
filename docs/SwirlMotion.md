# SwirlMotion 交互动画

本次动画以 `170188de532a2f3f802abe89bde07c32908ea85d` 的 Qt Quick 界面为基线，在本地 `test` 开发。原有颜色、字体、布局、尺寸、材质及功能入口均沿用；动画结束后变换回到原点。没有新增第三方运行时、光效或模糊。

## 技术评估

| 技术 | 评估与选择 |
| --- | --- |
| Rive | 官方提供 Windows C++ runtime，但 Qt Quick 集成在官方列表中归为社区方案。其状态机适合独立交互资源；本次没有引入尚未在本项目验证的渲染、ABI 和打包依赖。参见 [Rive runtimes](https://rive.app/docs/runtimes/getting-started)。 |
| Spline | 适合 3D 设计和 Web 场景原型；未作为 Windows Qt 的运行时。参见 [Spline FAQ](https://docs.spline.design/basics/faq)。 |
| ProtoPie | 用于交互原型验证；没有将原型播放器嵌入生产程序。参见 [ProtoPie Studio](https://www.protopie.io/support/protopie-studio)。 |
| LottieFiles / Qt Lottie | Qt 能播放受支持的 Bodymovin 动画，但预制时间轴不能替代本次页面生命周期和鼠标交互协调。参见 [Qt Lottie](https://doc.qt.io/qt-6/qtlottieanimation-index.html)。 |
| Qt Quick 原生 | 使用 SpringAnimation、SmoothedAnimation、Transform、Transition、Scene Graph 纹理缓存及小型 C++ 策略对象，保持当前架构。 |

## 组件与生命周期

`SwirlMotion` 统一弹性、阻尼、速度、减少动态效果、触发位置及共享元素上下文。`MotionPolicy` 读取 Windows 的客户端动画设置，监听设置变化，并根据实际帧交换时间降低复杂转场；没有固定 60 Hz 的自定义绘制循环。应用内减少动态效果设置与系统设置均生效。

`SwirlMotionButton` 对 background/contentItem 的绘制节点缩放，布局和按钮自身的命中区域保持原样。按下状态直接改变弹簧目标，释放和连续点击可反向。原有 hover/pressed 颜色只增加过渡，终点颜色保持原值。开关、菜单项与下拉选项采用同一组参数。

`SwirlPageHost` 保持原有 `pageLoader.item` 接口。每个已访问的固定路由只有一个 Loader，缓存其真实 QObject 树，保留编辑内容、草稿、选中项及滚动位置。缓存随窗口销毁，数量由当前有限路由目录决定；它不是任意数量页面的历史快照缓存。功能模块的 moduleId 和工作区的 pageId 绑定到各自 Loader 的固定路由，避免离场页面误改为新路由。

普通转场使用连续的空间位移；离场树保留，绘制使用一次性 Scene Graph 纹理缓存。转场完成后清空纹理源，并启用 live 使资源释放。快速改向时暂停当前弹簧，捕获当前合成视口，接续最新目标；异步回调读取最新路由，过期请求不再决定最终页面。临时 Image 禁用缓存；截图由 C++ 以数值句柄持有，完成后显式释放，测试检查持有数归零。参见 [ShaderEffectSource](https://doc.qt.io/qt-6.10/qml-qtquick-shadereffectsource.html)。

功能中心卡片与功能模块详情之间使用实际卡片和详情容器的场景坐标进行共享元素展开/收回；详情按钮、工具栏历史及 Alt+Left 返回均接入协调器。其他路由使用连续空间转场。共享元素使用现有内容的抓取图，不引入新的静态视觉装饰。

弹窗仍由 Qt Controls 管理焦点、模态输入、Escape 和外部点击关闭。页面离场时关闭其 Overlay 弹窗，避免隐藏页面继续拦截输入。展开位置由触发控件确定；下拉框保持原来的键盘选择行为。重开过程中沿用中间透明度和缩放值。

滚轮、触控板、原生窗口拖动/缩放和外观缩放滑块保持直接输入，没有加延迟队列。列表使用 Qt 的 add/remove/move/displaced 过渡，保留 ListView 虚拟化。小型可编辑模块列表用增量 ListModel 适配器表现 JS 数组的增删和排序；原始业务 records 和保存格式保持不变，大型网络表格不做全量适配。

## 验证方法

构建启用 `-DSWIRL_BUILD_UI_TESTS=ON`，执行现有 CTest 与新增 `swirl-motion`。`--motion-test --motion-output=报告路径` 可运行按压反向、连续切页、窗口尺寸变化、页面/输入/滚动状态保留、弹窗键盘、共享元素正反向、列表增删排序、减少动态效果、缓存复用、内存增长和静止帧数检查。

帧统计从原生 frameSwapped 信号采样，并使用真实 Qt 事件循环等待，避免 QTest 轮询睡眠对 Windows 高刷新率计时造成量化。报告分别保留首次加载/快速切换和已加载页面的帧统计，不能将显示器刷新率直接当作程序 FPS。

`--motion-visual-dir=目录` 输出 61 页 × 两种主题 × 两个尺寸的 244 张静止截图。测试统一关闭透明背景和动态效果，并用独立的空草稿文件固定初始数据。基线程序从原提交的源码快照构建，仅加入同一测试工具，不改基线 QML。每次切换先经过另一种页面 Component，避免旧 Loader 的复用残留混入基线。软件渲染进行逐像素比较，原生 GPU 另做运行和性能检查；GPU 的取整噪声不能代替确定性的视觉比较。

`SWIRL_TEST_DRAFTS` 仅在测试构建中生效，用于隔离测试草稿。生产构建不包含此覆盖和测试入口。

Windows 离屏像素回归需设置 `QT_QPA_FONTDIR=C:\Windows\Fonts`（按实际系统目录调整），让 offscreen 插件使用系统中文字体。基线和当前构建必须使用相同字体目录，避免用缺字方框代替真实文字进行比较。

安装程序沿用项目 NSIS 与 windeployqt 流程，Mihomo 的压缩包和可执行文件均按现有清单校验。可使用现有 `/ISOLATED /S /D=独立路径` 进行安装验证，避免改动正式安装的注册表、快捷方式或目录。
