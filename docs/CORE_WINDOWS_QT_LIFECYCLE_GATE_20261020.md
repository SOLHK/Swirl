# Windows Qt REALITY 生命周期门禁增量（2026-10-20）

本阶段在已推送的 Windows Qt 公网门禁之后补充产品链生命周期与失败路径。原有受控 Qt 产品测试及 A/B × HTTP CONNECT/SOCKS5 × 公网 HTTP/HTTPS 八项请求的 C++ slot 文本保持不变。

新增 `realityLifecycleProductChainAgainstIndependentPeer` 接收独立 Python 夹具的合成订阅，经过应用 NodeImportService、NodeImporter、NodeStore 的真实 Windows DPAPI 保存、对象销毁/重建、参数及原始配置重载，最后由 EngineController/ThreadedEngine/RustCoreEngine 启动进程内 Rust Runtime。每项都直接向本机 Rust 监听端口发送完整 CONNECT 或 SOCKS5 协议，避免 Qt 对 loopback 目标的隐式代理绕过。未修改 Rust 协议实现。

## 现有 Chrome133 + Vision Qt CI 组新增四项

- **TLS 1.2**：两种入口访问同一独立 HTTPS origin；Qt 固定 TLS 1.2 并验证测试 CA、证书名称；目标必须完成双向 TLS 关闭，Xray 必须记录认证、VLESS 接受与 Vision padding/unpadding，两个 Direct 计数必须为零。
- **错误凭据**：先通过两种入口完成有效节点 HTTP 正对照，再分别导入有效格式但错误的 short-id、public-key、servername、UUID。每次新建实际加密缓存并重载，要求无成功 HTTP、目标无新请求且备用 B 没有被接受的 VLESS 会话。VLESS 响应在首读时验证，允许本机代理 ACK 之后立即关闭；不能把 ACK 当成成功认证。
- **主动取消**：目标声明还缺一个上传字节，客户端收到已发送负载的精确回显后调用应用 controller.stop；要求本机流关闭、监听端口释放，以及独立目标在 Xray 清理之前记录取消、已接收字节和目标关闭。
- **可验证的 DOMAIN / MATCH REJECT**：使用应用 DNS 设置保存两条精确本地映射。相同监听端口、相同两个域名先在 DIRECT 模式经两种代理入口得到正确 HTTP 响应，再启动 rule 模式，必须得到协议规定的拒绝回复；独立目标只能看到四次正对照，A/B 均不得接受 VLESS。原有域名拒绝断言仍保留。

这四项仅加入已有 `--qt --vision --fingerprint chrome` 正式组，与原测试合计精确 **5 项**。另外两组 Qt profile 仍明确选择各自原测试，没有将未选项报告为跳过通过。所有跳过、选中测试数量不匹配、非零进程退出或不完整证据均使门禁失败。现有进程等待、请求等待和 CI job 总时限没有放宽。

每次 Qt 调用保存退出码、超时状态及白名单字段的部分请求证据：合成节点 A、目标域名/端口、代理入口/端口、静态失败阶段、数值错误、耗时和关闭状态。完整证据位于原 Chrome133 Qt artifact，继续绑定实际源码 SHA。错误不会因进程非零或超时而丢失已产生的部分报告。无供应商订阅、UUID、私钥或明文缓存写入 artifact。

## 本地实际执行的验证

对应机器可读记录：`docs/evidence/CORE_WINDOWS_QT_LIFECYCLE_LOCAL_20261020.json`。

| 检查 | 实际结果与范围 |
| --- | --- |
| 生命周期报告安全及完整性 | 8/8 通过；验证缺失矩阵、跳过策略、证书、取消、拒绝、ACK 后认证失败及失败进程证据保留 |
| 已有公网 Qt 报告回归 | 9/9 通过 |
| 工作流防弱化及生成器 | 56/56 通过；生成前后 hash 相同 |
| C++ | 新 slot 原文经 Qt 6.4.2 moc 和 C++23 语法检查通过；仅语法，不代表 Windows DPAPI 或完整 Qt 应用构建 |
| TLS1.2 / 错误凭据独立夹具 | 2/2 Linux 组件诊断通过，使用当前本地 Rust 二进制及既有、与锁文件一致的 Xray 二进制 |
| 取消目标关闭独立夹具 | 1/1 Linux 组件诊断通过；stop 后 1005 ms、peer 清理前，目标记录 44 字节边界、实际收到 43 字节、取消和关闭，活动目标连接为零 |

组件诊断复用了已验证上游 hash 的旧 Xray 构建，保留其原 build-manifest 源码提交；没有改写 manifest，也没有将它计作新 SHA 的正式 CI 或 Windows 结果。首次沙箱尝试因禁止创建本机 socket 而未执行协议，失败记录保留；获准的本机 loopback 执行随后实际通过。

**尚待实际 Windows CI**：新五项正式组、DPAPI、Qt 编译及新 SHA 的完整 Swirl.exe。公网八项的真实结果仍必须读取对应新 SHA CI 及独立 Xray 出口证据；不能由本地报告单测推断。物理 Windows 11 与私有供应商认证、Vision Direct、A/B 和联网验收仍未在聊天环境执行。历史 DNS、DoH、策略探测超时根因不在本阶段宣告解决；冻结总验收仍为 79 项、6 项完全通过、10.83%。

上游行为沿用 `test_reality_runtime.py` 已列明的 pinned Xray / REALITY 主实现与仓库许可证记录；未复制第三方实现。Qt 入口和 SSL API 行为参照官方文档：<https://doc.qt.io/qt-6/qnetworkproxy.html>、<https://doc.qt.io/qt-6/qsslsocket.html>。
