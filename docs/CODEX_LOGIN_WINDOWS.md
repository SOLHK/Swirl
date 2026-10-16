# Windows Codex 登录连接诊断

## 本次现场结论（2026-10-16，UTC+8）

09:20:16，Codex 日志确认收到 `/auth/callback`，`state_valid=true`；随后请求
`https://auth.openai.com/oauth/token`，09:20:18 尝试系统代理回退，09:20:20
报告 `is_connect=true`、`is_timeout=false` 的令牌交换传输失败。
因此本次错误发生在后台请求令牌时，浏览器回调已成功到达本机。Google、ChatGPT
网页可用不能证明这个后台请求也能成功。它与模型输出阶段的 WebSocket/SSE 重连是不同阶段。

同一时段 Swirl 曾记录握手失败，但旧日志只留下 `RouteHandshakeFailure`，不足以
确定 DNS、TLS、上游节点还是其他连接层原因；不能把时间接近当作唯一归因。

随后使用原选中节点的加密副本，在独立端口启动同源码生产引擎，关闭 TUN/LAN/网关。
使用本机实际安装的 `codex.exe app-server`，独立 `CODEX_HOME`、文件凭据存储，
不打开浏览器，以生成的合法 state 和**故意无效的诊断授权码**触发令牌交换：

| 路径 | 令牌端点结果 | 含义 |
|---|---|---|
| Swirl + Windows 系统代理，无代理环境变量 | HTTP 401，约 0.80 秒 | 后台 HTTP 客户端能连接到令牌端点 |
| Swirl + 子进程显式代理环境 | HTTP 401，约 0.84 秒 | 显式代理路径也能连通 |
| 原 Clash + 子进程显式代理环境 | HTTP 401，约 0.55 秒 | 对照路径连通 |

401 是无效诊断码的预期拒绝，**不是账号登录成功**。未提交真实授权码、访问令牌或
用户密码，未生成 `auth.json`，测试进程均退出。临时系统代理由独立恢复守护保护，
结束后四项原值恢复到 Clash 7897，加密节点副本删除。此时未重现原传输失败，
不能宣称根因已消除，也不能据此保证 TUN、完整桌面重启或长期流式输出通过。

## 独立 EXE 启动方法

安装包包含 `SwirlCodexLauncher.exe`，开始菜单入口为“通过 Swirl 启动 Codex”。
它不依赖 PowerShell 7 或 Qt DLL，可单独复制。先在 Swirl 连接节点并启用系统代理，
确保 Windows 当前代理确实指向 Swirl；启动器读取**当前**显式代理，不自动切换节点或
覆盖其他代理软件。如果当前仍为 Clash 7897，它使用的也是该端口。

1. 保存工作，并自行完全退出 Codex 桌面。
2. 确认 Swirl 节点连接和系统代理已启用。
3. 双击 `SwirlCodexLauncher.exe`，在新启动的 Codex 中重新登录。

启动器为新进程设置 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`，均为同一 HTTP
回环代理，HTTPS/WSS 通过 CONNECT；`NO_PROXY` 仅包含 localhost、127.0.0.1、::1，
本机授权回调保持直连。它不改变持久环境、Codex 配置、Windows 代理、DNS 或证书，
不会停止已有程序。发现旧桌面进程时拒绝启动，避免 Electron 复用旧环境。

代理必须在 WinINET 和当前用户注册表中均启用且一致，端口必须监听。PAC、自动检测、
远程地址、带凭据地址、协议映射或不一致配置会被拒绝。纯 TUN 模式请直接启动 Codex，
本启动器不是 TUN 配置工具。更新节点端口后，应自行退出并重新启动 Codex。

可从终端运行 `SwirlCodexLauncher.exe --check-only`；退出码 0 表示可启动，2 表示
桌面已存在，3 表示校验失败。此模式不启动 Codex、不显示弹窗。非 Store 桌面安装可用
`--codex "C:\path\ChatGPT.exe"` 指定本机桌面 EXE，不接受后台 CLI。

这提供了一条可检查的显式代理启动路径，**不能把当前未复现的 OAuth 传输错误写成
已根治**。完整真实账号登录需要用户在新桌面进程中完成验收，不能用诊断 401 替代。

## 新日志与回归

Mihomo 警告现在只从 `error:` / `error=` 后的原因识别 DNS 失败、TLS EOF、证书失败、
认证拒绝、TCP 拒绝/重置、超时及 EOF。不会因节点或规则名含 DNS/TLS 就错误归类。
只允许记录已知 OpenAI 公共目标域名，保留原因而不保存原始端点、节点名、凭据或正文。
未知原因明确保留为未知，不把观察到的断开直接归咎于目标服务。

回归覆盖真实子进程环境继承、父进程环境不变、监听/失效端口、代理校验、既有桌面
只读拒绝，以及错误日志通过真实控制接口传入时的脱敏和同一 TCP 隧道继续传输。
现有长连接转发和节点管理策略未在本轮更改。

```powershell
ctest --test-dir <build> -R '^swirl-(codex-proxy-launcher|diagnostic-export|engine-contract)$' --output-on-failure
```

参考：[OpenAI 登录文档](https://developers.openai.com/codex/auth/)、
[Codex 登录实现](https://github.com/openai/codex/blob/6b991972c5b539198dcea9bac4fc14e57559c3af/codex-rs/login/src/server.rs)。
上游问题 [18647](https://github.com/openai/codex/issues/18647)、
[24045](https://github.com/openai/codex/issues/24045) 描述的流中断并非本次 OAuth 交换失败的
唯一解释；未照搬社区建议修改系统、Codex 或其他代理软件配置。
