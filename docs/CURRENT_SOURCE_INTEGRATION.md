# 当前本地源码整合与便携包

## 正确的源码基线

本次直接更新用户指定的目录：

```text
C:\Users\sysfr\Documents\Codex\2026-10-15\files-pasted-by-the-user-solhk\work\Swirl
```

原始基线是 `0ae36d6f2ac3ef55921f7927e06b6cc9401b99e3`，包含当前 PR12 界面、Swirl 自研引擎、Mihomo 兼容引擎、规则、DNS、TUN、HTTP/2、脚本、独立设置窗口与完整统计。先保存完整 Git bundle 和源码 ZIP，再从该基线创建本地 `test` 分支，局部整合本轮修复。原 `feat/phase3-system-proxy-ui` 引用保留。没有合并或发布 `main`，没有推送远端。

上一包 `e759c6d` 基于较旧的远端 `test`，不应继续作为当前 UI 的验收版本。新包以本文件指定源码目录为唯一构建来源；`BUILD.txt` 记录目录、基线和最终提交号，CMake 缓存也核对同一目录。

## 保留当前界面的静态证据

- `qml/Theme.qml`、`qml/components/SwirlSidebar.qml`、`qml/pages/OverviewPage.qml` 与 `0ae36d6` 的 Git 内容一致。
- 75 个图标、5 个字体相关资源逐项哈希一致。
- 保留 `Main.qml` 现有路由、provider 注入、独立设置窗口、未保存内容确认、扩展与网关对象。
- 保留 `SwirlEngineManager`、`SwirlProxyEngine`、`SwirlProtocolRegistry`、`SystemProxySession` 与独立 `SwirlProxyGuard`，未引入第二个系统代理接管器。
- 保留 HTTP/2、脚本执行器、网关 Guard、真实日/月统计、国家地区与来源筛选、独立节点测试和多格式导入。

这些是源码比对结论，不代表人工视觉验收通过。交付证据中另附逐文件比对结果。

## 本轮局部修复

### 网络

当前自研隧道原有 120 秒空闲强制断开、节点切换整体重启、HTTP Upgrade 被拒绝等路径会影响长任务。本次移除已建立流的短空闲计时，保留握手期限；增加双向队列背压和 TCP 读写半关闭管理，支持 WebSocket Upgrade 字节透传，启用 TCP KeepAlive。

同一可执行引擎与已加载节点配置内的切换只影响新连接，旧流保持原出口。需要更换引擎或加载新凭据时明确要求用户手动重连，后台订阅刷新不再直接重启活跃引擎。单条新连接失败时，已有流存在则延后全局兼容回退，避免切断其他任务。

控制 API 短暂异常不再释放系统代理、取消节点请求或清理数据隧道。抓包及订阅入口在数据面仍运行时继续使用已打开的代理端口，不因控制接口暂时失败切成直连。

沿用当前 `SystemProxySession` 的 WinINet 与注册表双视图、DPAPI 恢复记录、进程身份和独立 Guard；增强未知读回、通知失败和部分写入的快照保留。来源不明时不覆盖其他软件，也不声称恢复成功。

用户主动点击后可检查本地端口、CONNECT、TLS 证书、HTTP 或 WebSocket 101/Accept 及随机 Ping/Pong。日志保留必要的时间和关闭代码，不记录 URL 查询参数、帧正文、密钥或关闭原因正文。仅凭加密隧道的 FIN/RST 无法准确区分上游节点与服务端，报告明确保留“来源未确定”。

Qt TLS 上游不能在保留读侧的同时独立发送 TLS `close_notify`；依赖 TLS EOF 定界的协议仍有能力限制。普通具有自身消息边界的 HTTPS/WebSocket 不依赖这类 EOF 结束请求。设置 → 代理提供“优先使用 Mihomo 兼容引擎”，用户断开后主动修改并重连，不改变节点、规则、DNS 和 TUN 配置。它不保证修复 Codex 服务端故障。

更详细的实际机制与限制见 `NETWORK_RELIABILITY_CURRENT.md`。

### 字体和动画

沿用当前已存在的 Windows 原生文字渲染、整数逻辑尺寸、SDR 与前景直接绘制，没有移植旧包的整体 HDR/遮罩结构。当前自动字体顺序在 Windows 为 HarmonyOS Sans SC → Microsoft YaHei UI → 系统字体，在 macOS 为 HarmonyOS Sans SC → PingFang SC；资源缺失时安全回退，逐字体真实字形预览，恢复自动选择；手动字体偏好保留。

原卡片正反几何机制来自 `b7f058f`。适配当前功能中心的真实设置入口，使用已有可逆过渡时钟展开实时 Glass 表面与原生标题，再与保留的独立设置窗口交接；关闭时反向返回。保留 Activity 的共享标题入口、Registry、缓存与确认逻辑。不固定 FPS，也不因累计慢帧永久关闭动画。

详见 `FONT_AND_MOTION_REPAIR.md`，其中记录删除历史、最新 UI 的适配方式和人工验收边界。

### 节点和活动页

在当前页面上修复表头与滚动区域、整数列边界、选中绑定、键盘操作、完整名称提示；保留增量节点模型和延迟动画。右侧详情与请求按内容占用高度，操作统一为两列，URL 与端口尺寸协调。

活动页保留真实今日/月累计、趋势与排行模型，调整状态胶囊、卡片留白和窄窗口重排，排行卡按内容增长；实际运行节点按 `activeNodeId` 显示。停止、等待采样、采样中断分开表示。已结束的连接快照不计入活动连接和活动进程；控制采样中断不伪装成连接已结束。

## 构建与验证

Windows x64 / C++23 / Qt 6.10.3 / MinGW 13.1 Release。编译包含当前全部辅助程序、C++、注册 QML、原有测试源码及新增回环用例；交付程序再次以 `SWIRL_BUILD_UI_TESTS=OFF` 构建。

执行范围仅为静态检查、编译、纯内存统计与本地诊断文件测试。10 项统计业务用例和 6 项诊断文件业务用例已通过；QtTest 合计包括初始化和收尾为 20 个通过条目。没有运行需要真实系统代理、节点、Codex、网络或图形界面的测试。QML 静态检查返回 0，项目动态上下文提示不等于零警告。

压缩包会检查 CRC、运行库、`core/mihomo.exe`、3 个辅助 EXE、规则与许可，并确认不带 Qt6Test.dll；另提供 SHA-256 和修改清单。`scripts/build-current-portable.ps1` 可重建此交付，脚本不会启动 GUI 或真实连通性测试。

## 使用与人工验收

完整解压新便携包到新目录，再由用户启动 `Swirl.exe`。Qt 运行库、`core`、`rules` 与辅助 EXE 需要一同保留。没有覆盖当前已安装或运行的 Swirl。

打开 `docs/manual-acceptance.html`，逐项填写实际结果、通过/未通过/未测试、问题描述并导出 JSON。本页使用新的本地记录标识，旧包的验收结果不会自动当成本包通过。所有人工项目初始为未测试。
