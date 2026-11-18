# 0.2.31：修复主界面启动失败

0.2.30 的规则分流选择面板为 `Column` 显式设置了 `implicitWidth`。
Qt 在实例化这个位置器时拒绝向只读属性赋值，导致 `OutboundModeControl`
不可用，进而让 `Main.qml` 加载失败，主窗口无法创建。

修复删除该赋值。面板本身仍有明确宽度，列表和说明文字仍使用
`modeMenu.availableWidth`；Column 根据子项计算隐式尺寸。
不调整规则行为、其他视觉设计或网络模块。

定位证据：用户安装目录 EXE 哈希与 0.2.30 交付一致，快捷方式指向正确；
用户正常启动日志记录 `QQmlApplicationEngine failed to load component`。
经用户明确同意，仅运行一次空白配置的隔离启动定位，获得：

```
Main.qml:156:17: 类型 OutboundModeControl 不可用
OutboundModeControl.qml:160:28: 无效的属性分配：“implicitWidth”是一个只读属性
ExitCode=1
```

没有使用用户配置、操作代理、进行截图或视觉验收。静态 qmllint 分析没有发现
这处运行时只读赋值错误，不能将它或编译成功当作启动已验证。
本修复编译及打包状态见安装包交付报告。修复后没有再次启动程序，
没有运行自动化测试、网络测试或 DPI/动画验收。

用户检查：退出旧 Swirl，安装 `Swirl-0.2.31-Setup.exe`，双击桌面图标。
确认窗口出现、版本为 0.2.31；展开“规则分流”，检查三项和底部说明显示正常，
点击外部或按 Esc 能关闭。其他外观和动画按 0.2.30 的清单自行检查。
