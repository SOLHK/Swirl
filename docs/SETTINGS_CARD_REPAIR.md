# 设置入口转场与 10pt 窗口轮廓

本次保留现有布局、颜色 token、菜单、品牌图标及窗口控制按钮。主要入口实际位于 `FeatureHubPage.qml`，不是活动页的数据指标。

## 已定位的问题

1. 原 `Main.qml` 先完整显示原生设置窗口，再让另一块矩形代理层独立展开，两层在交接期间同时显示，形成白色大矩形、重影和跳变。
2. 隐藏的设置窗口默认加载 DNS 页面。进入其他设置时，内部 `SwirlPageHost` 另跑一次页面转场，使共享表面前几帧仍显示旧 DNS 内容，标题却已切换。
3. 矩形 `clip: true` 不能保证圆角背景中的子内容沿圆弧裁剪。
4. 减少动态效果下，在 `onClosing` 内再次 `close()` 会形成嵌套关闭，Qt 忽略嵌套请求，留下仍可见的 modal 窗口与已归零的动画状态。
5. 转场改造的输入回归发现，页面迁移到详情窗口后，`SwirlDialog.parent: Overlay.overlay` 仍可能绑定临时窗口的旧 Overlay。原生 Windows 运行中，订阅表单已打开但其可视父窗口仍隐藏，导致表单不可操作和 Escape 误关详情窗。设置页弹窗现在显式绑定声明页面的 `ownerItem`，嵌套放弃修改提示沿用同一 Overlay；原生文件选择框绑定页面当前 `Window.window`。未迁移页面保留原有弹窗行为。

## 实现

`SwirlSettingsTransfer.qml` 用一个临时工具窗口承载同一个真实、缓存的设置页面。单一时钟控制当前矩形、圆角、颜色及内容衔接；原生详情窗口只在终点不透明交接。返回和中断均从当时的几何、圆角、颜色继续，重新读取源卡全局坐标。源卡不可见时使用稳定淡化，其他九宫格卡片不参与布局变形。临时窗口通过原生圆角 region 裁剪，避免整页纹理抓取及内容从四角漏出。

设置页内部关闭独立路由动画，由外层转场统一控制。页面实例、表单与缓存仍保留。临时窗口的 ESC、关闭按钮、减少动态效果和焦点恢复走同一返回路径；正文在交接前不接收输入。

## 圆角及系统能力边界

- `Theme.windowRadius = 10 × 96 / 72 = 13.333333` Qt 逻辑像素；物理半径为该值乘窗口 DPR，不能再乘内容缩放。
- 主窗口及参与交接的设置窗口使用同一精确 HWND region。最大化、全屏时清除 region 并使用直角；还原、改变尺寸或 DPR 时重新计算。
- 同级卡片引用 `Theme.cardRadius`；嵌套分组、输入控件及胶囊保留各自公共 token。
- DWM 提供圆角偏好枚举，没有数值半径接口，不能把默认 ROUND 当作精确 10pt。实机还确认 Desktop Acrylic 会在自定义 region 外填满矩形，造成亮色方角。因此精确轮廓窗口禁用该背景刷层，使用已有中性不透明回退材质。保存的透明度偏好不被改写；不支持的组合不会被描述成实时玻璃。
- 精确 region 无法获得匹配的系统自动阴影，因此使用同进程、输入穿透、不激活的纯视觉兼容阴影。周界像素按尺寸/DPR/焦点缓存，移动复用缓存；不抓桌面，不用持续定时器，也不拦截拖拽或缩放命中。

官方能力说明：[DWM 圆角及限制](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-rounded-corners)、[DWM_WINDOW_CORNER_PREFERENCE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_window_corner_preference)。

## 验证方法

测试构建提供 `--hero-test --hero-output=<目录>`，覆盖九个入口、真实 ESC/关闭按钮中断、返回重开、不同入口、窗口缩放后的源坐标、隐藏源降级、缓存与减少动态效果。录像帧记录采集时间戳；截图读回不用于计算 FPS。独立设置转场测量记录首次/缓存命中、进入/返回、首帧等待、被动 frameSwapped 间隔、长帧、CPU 与内存，不代表硬件呈现帧率。

跨窗口输入回归核对弹窗实际 Overlay 归属、订阅表单编辑和嵌套放弃确认。性能测试可使用 `--hero-settings-only --hero-settings-rounds=12 --hero-no-recording` 记录较长的缓存、对象及进程资源样本；不强制 GC 或释放图形缓存来制造稳定结果。窗口截图只在可见且已暴露的窗口上读回，避免违反 Qt 多窗口截图前提；输入测试等待实际交接和返回完成。

`--window-radius-test --window-radius-output=<目录>` 核对实际 Win32 region、最终合成角像素、兼容阴影、命中穿透、移动缓存、最大化、全屏、还原及内容缩放。不同 Qt 进程缩放测试只代表相应 DPR 下的几何/合成验证，不能冒充修改 Windows 全局缩放后的全部系统行为验收。

当前网络现场与限制见 [网络验收记录](NETWORK_RELIABILITY_6A.md)。构建、实际结果、提交与 CI 状态以对应交付报告为准。
