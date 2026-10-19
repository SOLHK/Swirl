# Swirl Core 接续交接：REALITY R3、Vision 子阶段与 Windows 对端端口修复（2026-10-19）

## 代码与执行边界

- 唯一开发分支：`work/core-completion-20261017`。提交前读取最新远端 HEAD，只做非强制快进，不写入 `main` 或 `test`。开发保留并发字体提交 `aab06bf`、`501099da`、`7dfbdda`、`b3ac464` 和 `6cba41ff43b989a240191a3731d9d8a5e29908b1`；后两项分别涉及字体 workflow 诊断及 TTC timestamp/字体测试文档，端口修复基于最新字体提交继续。
- 当前已推送修复源码：[`0be68231b15c1e4f69b138cda7bae0a3930d956b`](https://github.com/SOLHK/Swirl/commit/0be68231b15c1e4f69b138cda7bae0a3930d956b)，tree `72cf2ebcb652baeefeb415be66ebe59184725697`。首次 Vision 提交的失败与修复后的结果分别保存。
- 固定验收仍为 **79 项、6 项整项已验收、加权 10.83%**。B13/B14 均为部分实现，独立组件和开发阶段 CI 不等于完整协议档案或产品验收。
- 私有订阅更新开关保持关闭；本阶段没有新的私有订阅或供应商节点请求，没有提交私人凭据/缓存或受限字体二进制。失败代理明确报错，不降级普通 TLS 或 DIRECT。
- 先读本交接、[开发契约](SWIRL_CORE_DEVELOPMENT_CONTRACT.md)、[固定进度](SELF_DEVELOPMENT_PROGRESS.md)、[R3 专项](REALITY_XRAY_INTEROP_20261019.md)和[Vision 专项](VISION_ASYNC_INSPECTION_20261019.md)。后续纯交接提交不能冒领为新的可执行源码 CI。

## 本次源码与精确 CI

| 阶段 | 实际源码提交 | 对应 CI 及已知结果 |
|---|---|---|
| REALITY R3 | [`5ad68bcb22a23573d462cbfd972c7120093f504a`](https://github.com/SOLHK/Swirl/commit/5ad68bcb22a23573d462cbfd972c7120093f504a) | [Rust 39239280852](https://github.com/SOLHK/Swirl/actions/runs/39239280852)：Linux/macOS/Windows 完整 job 均 **success**，包括 Windows Qt 和原生应用编译；[App 39239280949](https://github.com/SOLHK/Swirl/actions/runs/39239280949) **success** |
| Vision R2 首次子阶段 | [`f3ce257f14e59e82977d89ac4be436d08926c6b8`](https://github.com/SOLHK/Swirl/commit/f3ce257f14e59e82977d89ac4be436d08926c6b8) | [Rust 39243009089](https://github.com/SOLHK/Swirl/actions/runs/39243009089)：Linux **success**，macOS/Windows **failure**；Windows 后续 Qt/原生应用门禁未运行。[App 39243009132](https://github.com/SOLHK/Swirl/actions/runs/39243009132) **success**。不能称此 SHA 三平台通过 |
| Vision 外层 TLS record 边界修复 | [`0be68231b15c1e4f69b138cda7bae0a3930d956b`](https://github.com/SOLHK/Swirl/commit/0be68231b15c1e4f69b138cda7bae0a3930d956b) | [Rust 39246770262](https://github.com/SOLHK/Swirl/actions/runs/39246770262)：Linux/macOS **success**，Windows 在旧 DNS fixture 的 UDP 绑定处 **failure**，R3/Vision/Qt 均未执行；[App 39246770049](https://github.com/SOLHK/Swirl/actions/runs/39246770049) **success** |
| Windows TCP/UDP 端口对 fixture 修复 | `随本提交入库` | 最终本地 94 项通过；源码身份待本次提交绑定，精确 CI **尚未执行** |

R3 各平台的 12 项成熟对端测试创建 13 个会话，均无失败/错误/跳过；[Linux](evidence/reality-r3/ci-linux.json)、[macOS](evidence/reality-r3/ci-macos.json)、[Windows](evidence/reality-r3/ci-windows.json)、[App](evidence/reality-r3/ci-app.json) 保留源码、构建、结果和生命周期身份。R3 App 的 226 个归档文件逐项匹配精确 tree 的 Git blob 和执行位。常规 Windows Qt 入口原有 6 个独立 peer hook 跳过，随后 5 个 wrapper 分别执行这 6 个槽位；这些跳过没有改写为通过。App 指现有 Core implementation validation 工作流，不是完整 Qt GUI 验收。

record 修复的 [Linux](evidence/vision-r2/record-ci-linux.json)、[macOS](evidence/vision-r2/record-ci-macos.json) 与 [App](evidence/vision-r2/record-ci-app.json) 已核对 272 Rust + 1 doctest、41 guard、R3 12 项/13 会话和 Vision 4 项的实际成功；App 的 262 个归档文件匹配精确 tree。独立保存的 [Windows 失败](evidence/vision-r2/record-ci-windows-failure.json) 显示 Rust 及 5 项新 record 回归通过，随后旧 DNS 对端选择的 TCP 临时端口落入该 runner 的 UDP 保留段并发生 `WinError 10013`；不能把后续未执行的 R3/Vision/Qt 算作通过。

## REALITY R3 已交付内容

固定官方 Xray `v26.10.17` / `92ccc939aaf4f8965f369cf0b142e005aeaa11d5`、REALITY `v0.0.0-20261014101318-83f621788ca8` / `83f621788ca88b83179810b12baa7ae518aacb83` 和 Go `1.27.2`。构建器验证 Git tree、原始 `go.mod`/`go.sum`、模块校验和与二进制身份；前后执行 `go mod verify`，实际重复构建两个二进制并比较哈希。同平台重建不等于独立跨构建机认证。

正式入库的构建器、Go fixture、Python 互通测试与 `reality-client` 覆盖原生 X25519/混合认证、双方 Finished、双向精确数据、1 MiB 分段和单字节 I/O、空载荷、正常 TLS 关闭、错误 short ID/公钥零应用字节以及超时/取消/回收。合法回显后的裸 TCP EOF 必须报 `UnexpectedEof`，不能冒充 `close_notify`。

该 fixture 使用未修改的官方 Xray REALITY wrapper 和受控本地 TLS 1.3 Ed25519 伪装目标；预置已知空的目标握手后记录缓存，不覆盖任意公网伪装站点、tickets 或浏览器指纹。TLS 组件互通不代表完整 VLESS 配置路径、生产异步 REALITY 适配器或供应商互通。

## Vision 子阶段、真实失败与修复

既有 R1 编解码之上新增跨 record/缓冲区的 ClientHello/ServerHello、版本/套件识别、有界异步双向 framing/padding、部分写/背压、缓冲尾部交接、取消释放，以及上传半关闭后继续接收下行。每方向 Hello 检查缓冲上限 64 KiB；首次子阶段增加 28 项 Rust 测试和完整官方 Xray 的 4 项测试。

成熟测试始终为 **3 项内层 TLS 1.2 双向正例 + 1 项内层 TLS 1.3 Direct 请求安全拒绝**，包括 512 KiB/暂停读取和单字节读取/短写。第 4 项要求 `PermissionDenied`、`server_first_probe`、零应用上传/接收和 `DirectReady=false`，目标先发的 34 字节探针另行计数；这不是 Direct 互通成功。

首次 `f3ce257f` 在 macOS/Windows 的第 4 项真实失败：客户端先收到 `InvalidData`，尚未观察到 `DirectRequested`；R3 与其余 3 项正例通过。原始 [macOS](evidence/vision-r2/first-ci-macos-failure.json)、[Windows](evidence/vision-r2/first-ci-windows-failure.json) 失败和 [Linux](evidence/vision-r2/first-ci-linux.json)、[App](evidence/vision-r2/first-ci-app.json) 成功分开保存。CI 记录与确定性回归支持外层 TLS 批量读取先处理后续 raw record、产生坏 MAC 的原因分析。

修复新增 `TlsRecordIo` 与 `PlaintextChunks`，分别限制密文 record 读取和已认证明文片段交付。真实 TLS 回归证明：已认证 command=2 可先交给 Vision 拒绝，完整 raw 后缀仍未读入外层 TLS；篡改 tag 仍失败，裸 EOF/截断关闭仍是 `UnexpectedEof`。默认产品 TLS 和内层 TLS 不变，没有跳过认证、延时规避或假造 DirectReady。

| 本地门禁 | 实际结果与范围 |
|---|---|
| R3 隔离源码 | fmt/check/严格 Clippy/Release 通过；239 项 Rust + 1 doctest；既有 REALITY Python self-check/TLS 16/19、CI guard 37、成熟对端 12 项/13 会话通过；这些项目无失败/跳过 |
| Vision 首次子阶段 | [本地证据](evidence/vision-r2/local-validation.json)：267 Rust + 1 doctest，新增 28 项；41 guard、4 项成熟测试通过；此本地结果不覆盖随后发生的 macOS/Windows CI 失败 |
| record 边界修复 | [修复本地证据](evidence/vision-r2/record-boundary-local.json)：5 项新增确定性回归，最终 272 Rust + 1 doctest，五项 Rust 门禁与 Release example 成功；成熟 4 项保留原断言、无失败/跳过；本地文件哈希不等于新 SHA 的 CI |

原始失败没有改写。R3 首次磁盘耗尽与 `CurveID` 缺失断言保留在 [R3 证据](evidence/reality-r3/)；[Vision 早期实验](evidence/vision-r2/initial-failures.json) 保留最初 4 个 loopback 阻断失败与两次 38 字节回显负例失败，明确原完整 unittest console 未保存。修复阶段首次本地 workspace 测试因沙箱拒绝 loopback 绑定而失败，同一源码/命令取得已授权网络权限后通过；两次原日志均留存，没有删除或弱化断言。

## Windows 对端端口修复候选

源码 `随本提交入库` 在 Windows 只读查询当前地址族的 `netsh` TCP/UDP excluded-port 表，从两个协议保留段的并集之外显式选择端口，随后同时持有 TCP/UDP socket。Linux/macOS 保持 OS 分配。没有修改系统保留段或吞掉未知 `10013`；查询失败、解析失败或候选耗尽立即失败，实际端口冲突仍最多尝试 8 次。

新增 6 项选择器回归；最终同一文件哈希的本地 DNS 37 项（81.647s）、Shadowsocks fixture 16 项（5.408s）、CI guard 41 项（0.471s），共 **94 项通过、0 失败/跳过**。[本地证据](evidence/vision-r2/port-pair-local.json) 将本轮命令、四个源码文件哈希及原始结果绑定；这不改变成熟对端断言，也不代表 Windows 或新提交 CI 已通过。新精确 CI 状态为 `尚未执行`。

## 下一步实际阻塞

1. 绑定并推送端口 fixture 修复，再核验该精确 SHA 的 Linux/macOS/Windows/App；回填 `随本提交入库` / `尚未执行`，保留此前两个 Windows 失败，不用触发成功代替执行成功。
2. `DirectReady`、原始 socket/缓冲所有权、TLS 状态与剩余字节安全交接仍未实现。HRR 尚不能进入 Direct 候选；收到 command=2 保持明确拒绝。
3. 完成生产异步 REALITY，以及真实 VLESS + REALITY + Vision 组合互通；两个组件各自成功不能拼成组合成功。
4. 再逐阶段接订阅语义 → 归一化 IR → 路由 → Rust runtime → REALITY/Vision → Qt。保留现有 UI/动画/字体和未知参数拒绝；提供商、TUN、长跑/弱网、物理 Windows 与安装包仍独立待验收。

## 保留的上一阶段证据

REALITY R2 源码 [`611edcff6c90d5f6e22637de1a24b4dfde494095`](https://github.com/SOLHK/Swirl/commit/611edcff6c90d5f6e22637de1a24b4dfde494095) 对应 [Rust 39217803242](https://github.com/SOLHK/Swirl/actions/runs/39217803242) 三平台和 [App 39217803202](https://github.com/SOLHK/Swirl/actions/runs/39217803202) 成功；Vision R1 源码 [`5b55ab33dde4c1789547e523b25dcad5abb1cf48`](https://github.com/SOLHK/Swirl/commit/5b55ab33dde4c1789547e523b25dcad5abb1cf48) 对应 [Rust 39220250082](https://github.com/SOLHK/Swirl/actions/runs/39220250082) 三平台和 [App 39220250444](https://github.com/SOLHK/Swirl/actions/runs/39220250444) 成功。它们是 E17 的历史精确证据，本次没有重做该阶段验收，也不能替代新 SHA 的 CI。
