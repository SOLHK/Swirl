# 第二阶段：真实代理节点连接

基于 test 分支合并后的 PR #9（170188de），功能分支 feat/phase2-real-node。所有引擎调用经 C++ EngineController → ProxyEngine → MihomoAdapter，QML 不持有 Mihomo API 或进程对象。

## 使用

1. 代理节点 → 添加节点，填写名称、SOCKS5 / Shadowsocks / Trojan、服务器和端口。
2. SOCKS5 可无认证；有认证时同时填写用户名和密码。Shadowsocks 支持 aes-128-gcm、aes-256-gcm、chacha20-ietf-poly1305。Trojan 填写密码和可选 SNI，始终校验证书。
3. 选择节点后点“连接 / 切换节点”。界面分别显示进程/API 状态、节点检测状态和实际请求状态。启动成功不等于节点可用。
4. 点“测试请求”会先让引擎检测所选节点，再通过 127.0.0.1 上的本机 mixed HTTP/SOCKS 端口执行真实请求。测试 URL 可修改。HTTP 状态和失败反馈来自真实响应，不做直连回退。
5. 外部应用须自行指定 http://127.0.0.1:7898（或界面指定端口）为代理。Swirl 不更改系统代理、DNS、TUN 或路由。
6. 运行时点击节点行会通过认证 API 切换，并再次读取当前选择确认。新连接使用新的节点；既有连接可继续使用原节点。切换无法确认时停止引擎，避免误用出口。
7. 断开后可编辑或删除节点。编辑不回显密码，留空保留已有凭据；“替换凭据”可明确覆盖或清除 SOCKS5 认证。节点库使用当前 Windows 用户的 DPAPI 加密和原子保存，不存在明文回退。

Clash 订阅中的单个受支持节点可按以上字段手动填写。本阶段不实现订阅 URL 导入、自动更新、VLESS、插件或 Clash 完整配置导入。请勿在 issue/日志/截图中附上订阅令牌或凭据。

## 安全约束

- 编译期固定 Mihomo v1.19.32 版本、SHA-256；执行前锁定文件校验。
- 控制 API 只监听 127.0.0.1，使用每次启动随机认证密钥。
- 独立进程由 Windows Job 原子归属管理；启动失败、超时、退出和停止均处理。
- 动态配置位于仅所有者与 SYSTEM 有权限的会话目录；节点和 API 凭据不进入公开摘要或日志。
- 无节点启动仍保持第一阶段的全部代理入口关闭、direct 模式、DNS/TUN 禁用。
- 有节点时仅打开本机 mixed-port，MATCH 固定节点组，不启用系统网络接管和直连回退。
- 界面演示行、合成流量、历史延迟、假连接成功和虚构响应已删除。未实现页面保留原视觉框架，数据为空或“—”，执行按钮禁用。模块草稿是实际本地保存功能，不代表网络服务已运行。

## 可复现测试

启用 SWIRL_BUILD_UI_TESTS 后运行 CTest。SwirlNodeTests 使用真实 Mihomo、两个受控 SOCKS5 TCP 中继和独立 HTTP/TLS 终点；TLS 流量仅转发，客户端显式信任测试证书，不修改 Windows 证书库。源端口映射验证出口 A/B，禁止非测试终点。测试覆盖 DPAPI 保存/重载/编辑/损坏保护、参数校验、HTTP/HTTPS 链路、认证中继、切换、故障、重复启停和端口释放。Swirl --node-self-test 驱动真实 QML 控件验证节点操作。

本机受控链路证据不能证明真实远程网络可用。Shadowsocks/Trojan 已经通过真实 Mihomo 配置校验及启动，尚未使用远程凭据验证端到端转发。

协议和 TLS 服务接口参考：[Mihomo](https://wiki.metacubex.one/en/config/proxies/)、[Qt QSslServer](https://doc.qt.io/qt-6/qsslserver.html)。
