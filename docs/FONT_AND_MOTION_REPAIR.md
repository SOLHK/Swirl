# 当前 UI 上的字体与连续动画修复

本次以用户提供的 `0ae36d6f2ac3ef55921f7927e06b6cc9401b99e3` 源码为基线，在 `test` 上局部修改。保留现有侧栏、UI token、独立设置窗口、Liquid Glass 材质、前景文字直接绘制、页面缓存、`SwirlTransitionRegistry` 与 `SwirlTransitionCoordinator`。没有覆盖成旧版 `test` 的页面或 HDR 合成结构。

## 字体

当前基线已经使用 `NativeTextRendering`、`SwirlText`、全提示与整数逻辑尺寸，前景也已脱离整体遮罩纹理；这些正确路径继续保留。本次发现并修改的剩余问题是：

- `FontManager` 的自动默认值只选 HarmonyOS，并在字体资源加载失败时 `qFatal`。现在先选已安装或本地导入的 PingFang SC，再选内置 HarmonyOS Sans SC，最后回退到 Windows UI 字体。缺失可选字体不阻止应用启动。
- 自动恢复原先写入固定的 HarmonyOS 偏好，现在删除手动偏好，恢复自动选择策略。用户主动手动选择的字体仍持久保存。
- 字体列表原先只有字体名称；现在每行用自己的实际字体显示中文、拉丁与数字预览，缺失字符由系统补全。仍保留搜索、当前字体预览、本地文件导入和许可查看。
- `SwirlHeroTitle` 原先在动画中产生小数字号。现在逐帧使用整数像素字号，保留原来的原生字形实时绘制，不缩放文字截图，也不统一加粗。

内置 HarmonyOS 三字重和许可继续使用用户源码已有的原文件。没有分发苹方，没有修改 Windows ClearType 或系统缩放，没有引入字体云服务。100%、125%、150%、200% 和用户 16 英寸 2K 显示器的视觉结论仍待用户人工填写。

## 一镜到底的历史与适配

原卡片到详情容器的 `navigateFrom`、`returnShared`、`heroStart` / `heroEnd` 正反几何路径来自 `b7f058f2f584602e6764fd28a808c3eb1c5ab088` 的 `SwirlMotion.qml` 与 `controls/SwirlPageHost.qml`。`9d6c0ffa51b0a1f336e6fcd4a225d20331c4b1d6` 删除该整卡共享过渡，`de28acb405a4863b27c065bf9232d062efc36171` 整合了相同删除；`2e270dec3ef3ef961871d76b7941fdc12dcc8f3b` 后来加入仅标题的 `SwirlHeroTitle`。

当前用户 UI 的功能中心已经改为打开独立设置窗口，不能用旧版整页结构覆盖它。本次将原卡片几何路径适配到现有 `settingsTransition` 的同一可逆时钟：

- 点击现有设置卡片时，按真实卡片与设置窗口位置展开最新 Glass 材质，并实时绘制标题；末段与原生设置窗口交接。
- 关闭、Escape 与原有未保存表单确认仍由最新设置窗口处理；同一时钟反向返回原卡片，并恢复原有键盘焦点。
- 保留独立窗口、页面状态缓存和原来的设置路由，不把所有页面改成卡片动画。
- 三参数 `navigateFrom(item, route, targetKey)` 继续兼容 Activity 的上传、下载、总流量、连接和进程标题路径。显式提供 `motionSurface` / `motionTitle` 的卡片可使用原卡片几何路径；模块详情提供其真实容器和标题端点。
- `SwirlPageHost` 测量新页面端点前执行布局 polish，保留缓存与状态恢复机制，并保留返回源页面避免端点被回收。

材质和字形均直接绘制，不放大含文字的整卡截图，软件后端同样可运行。`MotionPolicy` 继续监听真实屏幕刷新率，但不再因累计 12 个慢帧永久关闭复杂交互；没有固定 FPS 的绘制循环。

原 `SwirlTransitionCoordinator.moveTo()` 停止旧时钟时会短暂发出 `moving=false`，这可能让设置窗口把反向重开误认为关闭完成。本次增加一次 retargeting 状态，使反向操作保持运动状态连续，落定终值后才公布停止；Registry 的分配、活跃状态和清理机制继续保留。

## 验证边界

相关 QML 使用 Qt 6.10.3 的 `qmllint` 静态检查，返回 0；动态上下文与对象属性仍可能有项目已有的非阻断提示。更新字体自动选择的现有 `FontTests.cpp`，按本机是否提供 PingFang 判断默认策略，独立验证 HarmonyOS 资源包含三字重。C++、QML 与测试目标由统一 Windows 编译验证。

本次没有运行 GUI 人工验收、真实订阅/节点测试、代理连通性、Codex 重连或视觉验收。原生窗口交接、动画方向和实际显示清晰度须由用户验收，不能由静态检查或构建成功替代。
