# Swirl 1.0 UI 测试版验收记录

日期：2026-10-12。工作分支：`test`。基线：远端 `cfb4d4d`。此文记录当时 Qt 1.0 UI 的实机验收；之后按所有者要求将 Qt 版本同步到 `main` 并删除旧 .NET 代码。**本页测试结果来自原 UI 构建时的证据，不代表清理后的代理核心功能通过测试。**

## 交付和功能边界

Windows x64 NSIS 安装程序：`Swirl-Setup.exe`，文件版本 `1.0.0.0`，应用版本 `1.0.0-preview`。

安装程序大小：21,258,722 字节。SHA256：`b075ef1ea69b5611dc8cebbf0ba6d4660cf75311e3e4c43654ce9bab2889a233`。安装程序未代码签名。

Qt 前端仍未接入 Mihomo 的真实代理连接、系统代理、TUN、节点延迟及流量统计。这些数据与开关均标记为演示；断开演示会清零速率、连接数及系统代理/TUN 演示状态。本机网络卡类型和接口名为实际读取值，未将示例 Wi-Fi 名称冒充真实 SSID。

真实 HTTP 抓包、CONNECT 隧道记录及 HAR 导出继续保留。其余现有配置、规则、订阅、模块草稿和工具入口保留；侧栏“全部”和搜索仍可进入扩展工具。进程、请求日志为演示工作区入口。

检查结果：当时 Qt 工程没有名为 `ProxyEngine` 的 C++ 核心抽象层；先前的 .NET 业务实现并未接入 Qt。**原 .NET 工程随后已从当前分支移除**（保留在 [备份分支](https://github.com/SOLHK/Swirl/tree/backup/pre-qt-only-20261012)）。真实 Mihomo 接入和独立 C++ 引擎接口仍需另行开发，不把演示提供器当作核心适配器。

## 技术方案与主要文件

使用现有 C++23 / Qt 6.10.3 Quick/QML 工程，MinGW-w64 13.1、CMake 4.4.4、Ninja 和 NSIS 3.11。没有新建替代原仓库的空工程。

```text
单一原生窗口
├─ 左侧中性覆盖层 + DWM Desktop Acrylic
└─ 右侧不透明内容区
   ├─ 六项摘要
   ├─ 网络延迟 | 实时速度
   ├─ 流量分布 | 应用排行 | 域名排行
   └─ 当前代理/最近连接 | 系统状态/快捷操作
```

| 文件 | 主要修改 |
|---|---|
| `app/WindowsBackdrop.h/.cpp` | 原生材质能力/设置检测、HRESULT 回退、原生激活通知、工作区最大化、边缘命中、系统菜单与截图前景校验 |
| `qml/Main.qml` | 一体窗口、单一外轮廓、拖动阈值、标题栏双击、Alt+Space、主背景不透明；小窗口换行与滚动，默认不缩小字体 |
| `qml/Theme.qml` | 统一颜色、圆角 18、几何裁剪、4px 基准、12px 间距、16px 卡片留白；软件渲染效果回退 |
| `qml/components/SwirlSidebar.qml` / `SwirlNavigationItem.qml` | 参考图导航与分组、灰色选中、深色文字与图标、Ctrl+K、真实窗口按钮 |
| `qml/components/SwirlBrandIcon.qml` | 原始 SVG 直接显示，取消背景底板、边框、阴影 |
| `qml/pages/OverviewPage.qml` | 总览全部模块、真实网卡信息、演示标记、时间筛选、节点选择、趋势入口与最近连接表格 |
| `qml/controls/*`、既有页面 | 使用同一主题与圆角规则；软件渲染时保留按钮底板和开关圆点 |
| `app/SvgIconProvider.*`、`assets/icons/ui/*.svg` | 可按主题重新着色并按物理像素尺寸渲染的通用 SVG 图标；不处理品牌 SVG |
| `demo/DemoDataProvider.*`、`qml/AppState.qml` | 活动网卡读取、明确的演示连接状态与开关逻辑 |
| `tests/WindowChecks.*` / `OverviewChecks.cpp` | 背景变化、模糊边缘、窗口按钮、标题栏双击、最大化、缩放及演示一致性回归 |
| `CMakeLists.txt`、`packaging/Swirl.nsi`、构建脚本/CI | 新资源、Windows 库、原生专项测试开关、1.0 UI 预览文件版本与新波浪图标 |

浅色设计令牌：内容 `#F7F7F8`、卡片 `#FFFFFF`、文字 `#17181B`、次级文字 `#596273`、边框 `#E5E5E8`、选中 `#E3E4E7`。侧栏基础色 `#E9E9EC`，仅在原生材质启用时使用 0.82 中性覆盖层。中文用 Microsoft YaHei UI，数字用 Segoe UI。暗色主题作为原有偏好继续保留，并在所有页面一致应用。

## Windows 原生背景合成

使用 `DwmSetWindowAttribute` 属性 38、值 3（`DWMSBT_TRANSIENTWINDOW`），配合 `DwmExtendFrameIntoClientArea` 的全客户区延伸。由 DWM 负责系统背景与原生阴影/外角，QML 绘制左侧中性覆盖层和右侧不透明内容区。没有采用 Mica、静态壁纸、桌面截图循环模糊或整体窗口降透明度。

Qt 6 的 alpha 无边框 HWND 会带 `WS_EX_LAYERED`，且吞掉 `WM_NCACTIVATE`。本轮为加速渲染移除该 layered 路径，并将原生激活通知传给 `DefWindowProcW`，使系统 Acrylic 能进入激活状态。保留 `WS_THICKFRAME`、`WS_SYSMENU`、最小化和最大化样式。初始宽高在 QML 初始化后解除比例绑定，避免最大化时高度被覆盖。

应用透明设置关闭、系统透明设置关闭/不可读、高对比度、软件渲染、节电、远程会话或 DWM 调用失败时使用不透明侧栏。软件渲染还关闭不支持的 GPU 阴影层，保留控件本体。Windows 10 不强行调用未公开的 Acrylic 接口，按能力降级。

官方接口说明：[DWM_SYSTEMBACKDROP_TYPE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type)、[Acrylic 的系统回退条件](https://learn.microsoft.com/en-us/windows/apps/design/style/acrylic)。

## SVG 来源

实际侧栏 Logo：`src/Swirl.Quick/assets/icons/swirl_wave_mark.svg`。

Git blob SHA：`103c08a25e88255483cd2b08a2399f79d9db0ec2`，与远端基线一致，SVG 内容未修改。通过 Qt SVG 渲染同一图形生成透明 ICO；安装快捷方式使用新资源名 `Swirl-brand-100.ico`，避免继续引用旧风筝缓存。

仓库另有 `swirl_wave_light.svg`、`swirl_wave_dark.svg`。窗口应用图标和侧栏均直接使用无底板的 mark。通用 UI 矢量资源位于 `src/Swirl.Quick/assets/icons/ui/`。应用/域名排行使用文字徽标，未逐个复制参考图中的第三方品牌 Logo。

## 本机实际验证

系统 build `29648.1000`，实际系统 DPI 150%，Windows Qt 加速渲染。注册表产品名保留了旧的 Windows 10 名称，因此兼容能力依据 build、DWM 返回值和真实合成结果确认，不依据该产品名猜测。

| 验证 | 结果与证据 |
|---|---|
| Windows Release 编译 | 通过；生产 EXE 不包含测试框架 |
| 鼠标/键盘交互 | 39 项通过，0 失败：离线计数、演示开关一致性、模式、趋势、节点、Ctrl+K、导航、草稿/导入导出和小窗口底部可达 |
| 真实 HTTP 抓包 | 32 项通过，0 失败：回环监听、HTTP 转发、CONNECT、错误与输入边界 |
| 原生窗口专项 | 41 项通过，0 失败：前景校验、红蓝窗口变化、移动、边缘模糊、回退、暗色、标题栏双击、三个按钮、工作区及原生命中 |
| 页面加载 | 61 个页面通过，无 QML 加载/绑定警告；安装后的独立 EXE 同样通过 |
| 背景颜色变化 | 红蓝真实窗口切换：侧栏 RGB 通道绝对差合计 43，右侧内容差 0 |
| 移动测试 | 在真实红蓝分区窗口上移动 Swirl，侧栏随遮挡区域变化 |
| 真正模糊 | 背后颜色分界为锐利边缘，侧栏采样形成 47 像素的中间色过渡 |
| 关闭应用透明效果 | 侧栏不再随背后红蓝颜色变化；不透明回退通过 |
| 最大化/还原 | 最大化逻辑尺寸 `1707×1019`，与本机工作区相同；绿色按钮及标题栏双击还原通过 |
| 原生菜单 | 自动检查原生菜单存在；computer-use 实际按 Alt+Space 观察到 Windows 菜单 |
| 软件渲染 | 原生截图与完整控件已检查；状态为 `Opaque: software renderer` |
| 安装/更新/卸载 | 28 项通过：旧版本运行时拒绝覆盖、同目录更新、配置哨兵保留、EXE 哈希一致、独立运行、图标资源、隔离卸载及用户注册表保留 |

短时移动采样：60 次位置更新，约 1417ms，进程 CPU 时间 15.625ms（约 1% 单核时间），私有内存未增加。此为短样本，不等于长期泄漏、GPU 占用或连续拖动延迟的完整性能验证。

原生背景专项只在显式测试模式中临时把自己的测试窗口置前，避免采样被其他窗口遮挡；正常应用不置顶。`--capture-native-frame` 也仅在明确的截图命令下短暂置前，前景不成立或截图失败会报错，不用 Qt 渲染图冒充原生合成结果。

## DPI 与截图

| 比例 | 实际截图 DPR | 验证方式 |
|---|---|---|
| 100% | 1.0 | `QT_SCALE_FACTOR=0.6666667`，1280×900 逻辑窗口 |
| 125% | 1.25 | `QT_SCALE_FACTOR=0.8333333`，1280×900 逻辑窗口 |
| 150% | 1.5 | 本机实际系统 DPI，1464×930 逻辑窗口 |
| 200% | 2.0 | `QT_SCALE_FACTOR=1.3333333`，1000×650 逻辑窗口 |

以上均为安装后 EXE 的真实 Windows 前景合成截图。100/125/200% 为应用级缩放验证，未改变系统显示设置，不冒充不同物理显示器上的测试。最小窗口底部已滚动到最近连接、快捷操作和趋势入口。

与参考图对照：单一窗口、左右自然连接、六项摘要、延迟/速度、三列流量分析、代理/连接及系统/快捷操作层级一致；按用户文本将导航选中改为灰色、中性白主背景和原始 wave SVG。原生外角由系统决定；DWM 曲率、Windows 字体与参考图并非逐像素一致。小尺寸允许换行、滚动和部分文案省略，未自动缩小字体。

## 未验证与剩余边界

- Windows 10 实机、Windows 11 稳定 build 22621、更多系统版本：未验证。代码提供按能力回退，不能据本机成功宣称全部系统通过。
- 实际切换系统透明效果、高对比度、节电与远程桌面：未验证；不改动用户这些系统设置。已验证应用透明开关和软件渲染回退。
- 更换系统壁纸：未执行。真实不同颜色窗口、移动和模糊分界已验证。
- 多物理显示器与跨显示器 DPI 迁移：未验证。仅本机系统 DPI 与应用级缩放已验证。
- 长时压力、实际 GPU/驱动失效及 GPU 占用：未验证。Qt 软件渲染路径已验证。
- 此次 Qt UI 验收未覆盖旧 .NET/Mihomo 后端。当前分支已删除旧后端源码；Qt 安装程序仍不是已接入完整核心的正式代理客户端。
- NSIS 存在一条既有 `LegalCopyright` 版本信息缺少标准字段的提示，构建退出码为 0；安装更新/卸载已验证。

## 复现

```powershell
cmake -S src/Swirl.Quick -B build/swirl-quick -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/Qt/6.10.3/mingw_64 -DSWIRL_BUILD_UI_TESTS=ON
cmake --build build/swirl-quick --parallel
./build/swirl-quick/Swirl.exe --interaction-test
./build/swirl-quick/Swirl.exe --capture-self-test
./build/swirl-quick/Swirl.exe --smoke-test
./build/swirl-quick/Swirl.exe --window-test --window-test-output=C:/Swirl-validation
```

原生专项需要解锁的真实 Windows 桌面，不用于 offscreen CI。常规鼠标/键盘、抓包和页面加载继续进入 CI。`scripts/build-quick-windows.ps1 -InputTests -NativeBackdropTests` 可先检查再生成生产安装程序。
