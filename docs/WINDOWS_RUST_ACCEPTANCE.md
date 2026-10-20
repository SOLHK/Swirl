# Windows Rust 内核身份与真实联网验收

`Swirl.exe` 左侧常驻身份标签显示运行中的实际引擎。停机时标签明确写“构建类型”；系统代理标签仍只说明 Windows 系统代理的归属。诊断快照及本机导出 ZIP 的 `identity.json` 另包含完整源码 SHA、`Swirl.exe` 路径和 SHA-256、实际引擎类型及 PID，不包含节点或凭据。

在 Windows 上构建 `SWIRL_USE_RUST_CORE=ON` 且 `SWIRL_BUILD_UI_TESTS=ON` 的程序并部署 Qt 运行库后，把**已有**加密 NodeStore 和选择 sidecar 复制到 Git 工作区外。不要把原始状态文件、订阅或运行时状态上传。调用：

```powershell
./tools/Invoke-WindowsRustAcceptance.ps1 `
  -SwirlExe 'D:\path\to\build\Swirl.exe' `
  -EncryptedStore 'D:\private\nodes.dpapi' `
  -WorkDirectory 'D:\private\acceptance' `
  -ExpectedSourceSha '<完整提交 SHA>'
```

脚本在连接前将本轮测试会话设为全局路由，不改生产默认路由、QSettings、系统代理或 TUN。它要求测试版进程路径和哈希、进程内 Rust 状态、加载的 `swirl_api.dll`、以及 `127.0.0.1:17988` 监听 PID 一致。六项 curl 测试使用显式代理并清除 curl 子进程继承的代理环境变量；`--noproxy=` 排除 `NO_PROXY`，HTTPS 不关闭证书验证。每项记录 `proxy_used`、监听 PID、退出码、状态码、耗时、正文校验与 TLS 验证。正常结束只停止本轮启动的 Swirl，核查端口释放、Mihomo PID、用户代理配置及环境变量哈希未变。

六项请求 PASS 只证明本轮 Shadowsocks 节点经过 Swirl Rust 前端成功请求。若 Mihomo 仍运行，或有 TUN／透明路由迹象，独立性固定为“未证实”。系统代理由另一应用接管本身不说明显式 curl 请求经过 Mihomo。要验证彻底独立，需另行在用户许可且 Mihomo 停用、路由迹象排除时重复对照。59 条 VLESS/REALITY 节点的原生资格仍为 0/59；此工具不把 Shadowsocks 结果归给它们。

实现参考了 [Clash Verge Service 对内核 PID 的显式跟踪](https://github.com/clash-verge-rev/clash-verge-service/blob/main/src/service/core.rs) 和 [curl 对 `--noproxy` 的定义](https://github.com/curl/curl/blob/master/docs/cmdline-opts/noproxy.md)。仅参考其可观察行为，代码独立实现。
