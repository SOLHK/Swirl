# Swirl UI 视觉验证

验证日期：2026-10-11。实现分支：test。C++23、Qt 6 Quick/QML 与 Mihomo 架构保留；应用 C++、代理核心、抓包服务与数据模型未修改。测试点击辅助函数经用户明确授权调整。

## 参考与设计规则

Product Design 以用户提供的 Apple Music 原始截图作为可见材质基准，以两张已确认 Swirl 效果图作为总览布局基准。原图仅用于本地观察和采样，没有复制到仓库或应用。

frontend-design 规则：浅色画布与内容 `#FFFFFF`；侧栏底色 `#ECECEC`；灰色选中底 `#DADADA`；正文 `#171717`；次要文字 `#586174`；一般强调 `#0069D9`，大号下载数字 `#007AFF`。沿用 Microsoft YaHei UI 和 Segoe UI；48px 页面标题、23px 分组标题、18px 导航字、62px 速度数字。侧栏 286px，导航行固定 42px，卡片圆角 12px，搜索圆角 10px，窗口圆角 18px。保留现有风筝品牌与图标家族。

侧栏实现 tint alpha 为 0.94，仅是本次可调整实现参数；不是 Apple alpha 的测量结果。主内容面完全不透明。关闭透明效果时使用不透明中性灰。深色主题采用中性深灰及相同层级，主要按钮用独立颜色令牌保障白色标签的可读性。

主状态布局：总览标题及代理状态/历史节点延迟 → 下载与上传速度 → 当前代理、模式及策略 → 系统代理、DNS、网络连接状态。原有趋势图、活动连接、累计流量、事件、快捷操作和工具入口保留在下方滚动区。速度、代理及网络连接仍为演示数据，真实 HTTP 抓包能力和现有草稿功能保持。

## 构建与验证

- Windows build 29648；Qt 6.10.3 MinGW，Release C++23 构建通过。
- 33 项实际输入/节点/搜索/导航/草稿检查通过。点击辅助函数先把滚动目标移入视口，原有断言没有删除或弱化。
- 32 项 HTTP/CONNECT 抓包集成检查通过。
- 全页面启动 smoke 通过，无 QML 加载失败。
- 已实际启动 Windows 窗口，并检查浅色、深色、1000×650 最小窗口底部可达性及代理页。
- Windows GPU 渲染截图和本机桌面合成截图均已查看；文档使用窗口渲染输出，不包含其他应用或桌面图片。
- Qt offscreen 首次扫描整个 Windows 字体目录时输出一条 `FT_New_Face` 调试提示；改为仅使用临时字体夹具后最终输入检查通过，未将 Windows 字体打包或提交。

## 颜色与像素比较方法

Apple 原图为 780×471，Swirl 效果图为 1584×993；PNG 没有提供 DPI、ICC 或显示缩放元数据。Swirl 效果图窗口裁切框为 (60,40)-(1524,970)，得到 1464×930，和本次 Qt 窗口渲染输出尺寸一致，不进行拉伸。

本机 native capture 在窗口四周增加 8px，按 (8,8)-(1472,938) 裁切，得到 1464×930。本机桌面为 150% 缩放，以 QT_SCALE_FACTOR=2/3 获取有效 DPR 1。现有桌面壁纸为 3840×2400，和参考底图不相同；未替换壁纸或系统设置。

材质比较只选无文字/图标/边框的代表区域；将 Apple 侧栏内部位置按侧栏宽高比例映射到本机侧栏，记录区域 RGB 均值和中位数。误差是两区域 RGB 均值差的通道平均绝对值，取值范围 0–255；第三个本机样本框为 (223,798)-(260,815)，缩小到侧栏安静区域以排除分隔线；其他框与均值/中位数见输出测量 JSON。这不是在相同底图条件下逐像素对齐得到的 alpha 测量。

| 区域 | Apple RGB 中位数 | 本机 native RGB 中位数 | 平均通道误差 |
| --- | --- | --- | --- |
| 侧栏区域 1 | [238.0, 233.0, 230.0] | [234.0, 234.0, 234.0] | 2.671 |
| 侧栏区域 2 | [236.0, 235.0, 234.0] | [234.0, 234.0, 234.0] | 1.238 |
| 侧栏区域 3 | [237.0, 236.0, 234.0] | [234.0, 234.0, 234.0] | 1.662 |
| 内容留白 | [255,255,255] | [255,255,255] | 0.000 |

三个侧栏代表区域的平均通道误差为 **1.857/255**。当前侧栏约为中性 `#EAEAEA`，与 Apple 截图中由底图引起的暖灰存在小差异；不通过人为加暖色来伪造底图透出。

将已确认 Swirl 效果图窗口裁切与 QML 窗口输出对齐，RGBA 输出先在白底上合成，全窗口 RGB MAE 为 **11.414/255**。该分数包含字体、图标、现有风筝标志、真实演示值、保留的模式/策略控件及布局差异，不能当作侧栏材质匹配分数。没有宣称像素级完全一致。

## UI UX Pro Max 检查

正常文字以 4.5:1、大片文字和有意义非文本元素以 3:1 作为检查目标。以下为主题令牌的理论 sRGB 对比度，不代替任意壁纸合成条件或完整辅助技术测试。

| 检查 | 对比度 |
| --- | --- |
| `light_primary_on_content` | 17.93:1 |
| `light_secondary_on_content` | 6.22:1 |
| `light_selected_label_on_sidebar_selection` | 4.62:1 |
| `light_large_download_value` | 4.02:1 |
| `light_upload_value` | 4.79:1 |
| `dark_primary_on_content` | 15.29:1 |
| `dark_secondary_on_content` | 9.43:1 |
| `dark_selected_label_on_sidebar_selection` | 5.26:1 |
| `light_focus_on_field` | 5.98:1 |
| `dark_focus_on_field` | 7.06:1 |

选中态使用底色、文字颜色、字重及 Accessible.selected；焦点边框独立，导航不改变行高。状态同时有文字，下载/上传同时有标签和箭头，背景颜色不承担唯一语义。保留键盘搜索和导航、主题/透明设置及减少动效。新按钮使用 Accessible.name；未声明完成全部屏幕阅读器认证。

## 严格像素匹配限制

- 只有合成截图，缺少参考窗口下方的完整底图、模糊核、alpha、macOS 合成材质和显示条件，不能唯一反推透明度。
- Windows DWM 与 macOS 合成器的模糊、色彩混合、圆角和字体抗锯齿不同；本次不修改现有 C++ backdrop 实现。
- 保留 Swirl 现有风筝品牌和图标，演示值取现有状态，没有硬编码效果图中的 8.6、1.2、28ms。
- 为保留功能，模式/策略选择和下方趋势/工具继续可达；新增的示例标识及功能入口与纯效果图不完全相同。
- 未提供深色参考图；深色版本按层级和可读性验证，不声称和 Apple 深色界面逐像素匹配。

## 本次修改文件

- `src/Swirl.Quick/qml/Main.qml`
- `src/Swirl.Quick/qml/Theme.qml`
- `src/Swirl.Quick/qml/components/SwirlBrandIcon.qml`
- `src/Swirl.Quick/qml/components/SwirlGlassPanel.qml`
- `src/Swirl.Quick/qml/components/SwirlNavigationItem.qml`
- `src/Swirl.Quick/qml/components/SwirlSidebar.qml`
- `src/Swirl.Quick/qml/controls/SwirlButton.qml`
- `src/Swirl.Quick/qml/controls/SwirlPillSurface.qml`
- `src/Swirl.Quick/qml/controls/SwirlSearchField.qml`
- `src/Swirl.Quick/qml/controls/SwirlToggle.qml`
- `src/Swirl.Quick/qml/pages/OverviewPage.qml`
- `src/Swirl.Quick/tests/OverviewChecks.cpp`
- `README.md`
- `src/Swirl.Quick/BUILDING.md`
- `docs/UI_VISUAL_VALIDATION.md`
- `docs/screenshots/overview-qt-light.png`
- `docs/screenshots/overview-qt-dark.png`

已有 UI UX Pro Max 集成文件保持原内容，在发布时一并保留。
