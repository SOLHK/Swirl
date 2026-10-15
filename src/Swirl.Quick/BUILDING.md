# Swirl Windows 构建与验证

Swirl 使用 C++23、Qt 6 Quick/QML 和独立 Mihomo。主界面按照提供的 Surge 截图重绘，真实功能与尚未接入的入口分开。当前是开发预览版本，不表示 Word 描述的所有高级功能已完成。

## 构建

需要 Windows x64、Qt 6.9+（本机验证 6.10.3，卡片背景采用 6.9 引入的 RectangularShadow）、匹配的 MSVC 2022 或 MinGW 13.1、CMake 3.25+、Ninja；安装包另需 NSIS 3.11。编译器、CMake、Ninja 加入 PATH，不能混用 MSVC 和 MinGW Qt。

```powershell
cmake -S src/Swirl.Quick -B build/quick -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/Qt/6.10.3/mingw_64 -DSWIRL_BUILD_UI_TESTS=ON
cmake --build build/quick --parallel 6
./scripts/stage-mihomo.ps1 -Destination build/quick
ctest --test-dir build/quick -E swirl-system-proxy-recovery --output-on-failure
```

system-proxy-recovery 测试会临时修改并恢复当前用户系统代理，只应在专用测试环境单独运行。本次验证没有运行它。其余网络集成测试使用本机隔离服务。swirl-motion 在 Windows QPA 验证原生弹窗，其余界面测试使用 offscreen 软件渲染。原生窗口测试需要可用桌面。

生产包必须重新配置 SWIRL_BUILD_UI_TESTS=OFF，并使用新 DistDir 部署。编译输出包含 Swirl.exe、SwirlProxyGuard.exe、SwirlGatewayGuard.exe、SwirlScriptRunner.exe；四个文件都要打包。脚本运行器依赖 QtQml，Qt 部署应包含相应动态库。

```powershell
./scripts/build-quick-windows.ps1 -QtDir C:/Qt/6.10.3/mingw_64 -BuildDir build/release -DistDir dist/release -OutDir out -Nsis C:/NSIS/makensis.exe
```

构建脚本校验并暂存固定版本 Mihomo，windeployqt 部署 Qt/QML，复制许可，输出安装程序。不要复用含旧 Qt 插件的 DistDir。Windows 字体不随包分发。

## 截图对照

测试构建可截取真实 QML：

```powershell
./build/quick/Swirl.exe --capture-preview=C:/temp/activity.png --preview-size=914x672 --preview-theme=light --preview-page=activity
./build/quick/Swirl.exe --capture-preview=C:/temp/sort.png --preview-size=914x672 --preview-theme=light --preview-page=gateway --preview-state=device-sort
```

主窗口参考尺寸 914×672 逻辑像素，面板 1300×600，DNS 900×748。实际 PNG 受 Windows DPI 比例影响。其他参考状态：inactive、device-settings、rewrite-on、dns-focus。原生弹窗截图包括弹出窗口超出主窗口的区域；比较时必须对齐主窗口边界，不能拉伸整个联合截图。

Theme.qml 定义颜色、尺寸与动效令牌。页面缓存保留表单和滚动位置；切页释放模态抓取；支持减少动态效果。截图不能代替多显示器切换、长时间压力、真实远程凭据和专用 LAN 验证。

## 功能资料

- [捕获、HTTPS 解密与重写](CAPTURE.md)
- [本地脚本、模块和配置](../../docs/LOCAL_EXTENSIONS.md)
- [当前复刻验证](../../design-qa.md)

系统代理、TUN、DHCP、接口转发与证书信任均由明确的界面操作触发。TUN/网关需管理员权限，网关还需要专用 LAN。不要将草稿页的保存动作解释为真实服务启用。Mihomo、Qt、nghttp2、Fluent 图标和编译器运行时许可随包提供。
