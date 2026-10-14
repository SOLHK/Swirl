# 图形依赖与工具验证（2026-10-15）

主环境：Windows 11 x64、Qt 6.10.3、MinGW 13.1、C++23、CMake/Ninja Release。候选代码和构建目录位于独立研究目录；生产继续使用 Qt Quick/QML/RHI，不引入第二套 UI 框架。

| 项目 | 固定版本与许可 | 实际结果 | 生产使用 |
| --- | --- | --- | --- |
| Qt Quick / Qt RHI / ShaderTools / MultiEffect | 6.10.3；动态 Qt LGPL-3.0，模块许可随包 | Release 着色器编译、D3D11 原生输入、GPU 时间戳比较、RenderDoc 抓帧 | 是 |
| Qt Quick Effect Maker | v6.10.3，3e8b0f9；工具 GPL-3.0-only/商业，构建文件 BSD | 复用匹配 Qt 的已构建工具，通过本地无界面导出入口重新加载原创 SwirlClickLight.qep，导出 vert/frag/qsb，退出 0 | 工具不随包，仅原创短暂点击高光着色器 |
| RiveQtQuickPlugin2 | 4ff14b434400cc2a32b4dd3e45bc20f9d657389a；MIT | 补齐 FXC 后 CMake 成功、原始 DirectX 着色器编译成功；真实 MinGW 编译在 DirectX COM 接口处失败，见下文 | 否；使用原生 QML 状态反馈 |
| FluentUI for QML | 7e33a2f672d18239ef49ab960075b1137a1d18e7；MIT | Qt6/MinGW Release 插件真实编译链接成功；显式输出到独立研究目录 | 否；只研究交互；未复制字体、图标或运行库 |
| alex47/Dual-Kawase-Blur | 41c41b3059b3c37ff843822a0dc0e892825927c6；GPL-3.0 | 下载并核验 README/许可证；研究算法，未将 OpenGL 示例代码链接到 Qt Quick | 否；Swirl 模糊着色器独立编写 |
| Google Skia | 59f566489c0dc9c7b6a42bceaaefb5a8be19aaee；BSD-3-Clause | 检查许可及官方 Path/轮廓文档，比较圆弧与四阶超椭圆几何；未编译完整 Skia | 否 |
| Qt Quick Shapes | 与 Qt 6.10.3 相同发行版 | 研究 PathCubic/CurveRenderer 的轮廓与重建成本；主窗口采用独立 SDF 着色器，普通卡片按用户要求保留原有圆弧曲率 | 不增加运行模块 |
| PresentMon / DXGI 统计 | PresentMon 官方 Windows 2.6.0，签名有效；MIT；DXGI 为系统接口 | ETW 60Hz 有效；早期 120/240Hz 遮挡与后续 UAC 取消均记录。最终使用自身 flip swapchain 的呈现计数/QPC 统计，不以 Qt frameSwapped 代替显示 FPS | 开发工具，不随包；DXGI 采样代码仅用于测试 |
| RenderDoc | 官方便携版 1.46；MIT，另含工具自身第三方许可 | 成功注入隔离 Swirl 测试进程，获得 4 个 D3D11 RDC 帧，转换为 API XML 并统计目标纹理/绘制调用 | 工具不随包；MIT API 头文件仅供 SWIRL_UI_TESTS 编译 |
| HarmonyOS Sans SC | OpenHarmony resources 0d79cad76b37ba0f3ccb1323c83833c78e0860de；HarmonyOS Sans Fonts License Agreement | 官方 Regular/Medium/Bold 原样文件、哈希固定、Qt 加载、切换/导入/持久化和本机 UI 检查 | 是；完整声明随包及应用内展示，详见 FONTS.md |

## Rive 具体编译证据

Windows SDK Microsoft.Windows.SDK.CPP 10.0.28000.2705 已在研究目录解压，实际执行 x64/fxc.exe 成功。解决了上一轮仅因缺少 FXC 就停止配置的问题。

原始插件配置使用现有 Qt/MinGW 完成，构建进入数百个运行库和着色器目标后，在 DirectX-Headers/RPC 头文件以及 COM 按值结构返回接口处失败，例如 `ID3D12Resource::GetDesc()` 与 MinGW 暴露的 `GetDesc(D3D12_RESOURCE_DESC*)` 不一致。另做独立 OpenGL-only 实验后，插件 Windows D3D11 桥仍引用已排除的运行库，链接失败。未将实验修改带入 Swirl，也未声称通过 Rive 渲染验证。

本机未找到可用 MSVC + 匹配的 Qt MSVC 套件；可选 MSVC/Rive 渲染仍未验证。生产不依赖该实验，因此现有编译链与已通过的功能继续可用。

插件及其固定运行库的 MIT、HarfBuzz Old MIT、SheenBidi Apache-2.0、Yoga MIT、Luau MIT/Lua、libhydrogen ISC、miniaudio MIT/Unlicense、DirectX-Headers MIT、PLY BSD 许可均保留在研究副本；没有 .riv、样例字体、样例音频或市场动画进入生产包。

## 材质与几何决策

Swirl 通过 Windows IDesktopWallpaper 读取当前屏幕壁纸，按填充/适应/居中/平铺/跨屏模式映射，再由 Qt RHI 多级降采样/上采样进行模糊。壁纸解码与 GPU 模糊分别缓存；纹理按 512/768/1024 档位限制。只有壁纸、屏幕、质量或模糊强度变化触发更新。窗口移动改变取样坐标，不重复读取整个桌面。

按用户最新要求，主窗口只保留一层均匀的淡蓝色半透明材质，不叠加侧栏/工作区染色矩形和渐变。该层保留真实窗口 alpha，桌面可透出。模糊来源为壁纸，不能将此描述为对所有后方应用窗口进行实时模糊；没有常驻桌面捕获。DWM 仅保留原生边框行为与阴影，不启用 Acrylic/Mica。

窗口/大容器使用独立四阶超椭圆 SDF、导数抗锯齿和统一遮罩；普通卡片按用户最终反馈保留原有 Surge 参考圆弧与 20 逻辑像素半径。软件渲染提供不透明圆角回退。

参考原始地址：
- https://github.com/qt/qtquickeffectmaker/tree/v6.10.3
- https://github.com/jebos/RiveQtQuickPlugin2
- https://github.com/zhuzichu520/FluentUI
- https://github.com/alex47/Dual-Kawase-Blur
- https://skia.org/docs/user/api/skpath_overview/
- https://doc.qt.io/qt-6.10/qtquick-shapes-qmlmodule.html
- https://github.com/GameTechDev/PresentMon
- https://renderdoc.org/
- https://github.com/openharmony/resources
