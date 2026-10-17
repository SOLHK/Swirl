# Rust DoT 阶段验收与后续接手记录

日期：2026-10-17。用户授权通过 GitHub 继续 Rust 开发，不使用 Gemini；个人 Windows、私有节点和手机远程控制测试留待其电脑环境执行。

## 代码基线与本轮修改

- 起点：`test` 的 `fbebb2813efd3292e0af01011db236f2c96bae38`。
- 接续已有 `work/rust-dot-20261017` / [PR #22](https://github.com/SOLHK/Swirl/pull/22) 的 DoT 实现，未重复重写。
- 验证代码：`4dca7268bfd63db6b942f169811fa6d09e3388e0`。
- PR CI 实际 checkout：`aa2945568756c9012080377a2586c8e6807d2721`；其 tree 与上述代码提交相同，均为 `e342ed7193c93f20a612cfbdcaca621cd8b995fa`。
- 已使用非强制快进将 `test` 从 `fbebb28` 更新到 `4dca726`；本记录是其后的纯文档提交。没有更新 `main`。

DoT 复用 Rust DNS 报文校验、A/AAAA/CNAME 与正向 TTL 缓存，加入 rustls 认证、明确 IP bootstrap、独立 TLS 对端测试和现有 Qt 配置字段映射。实现和限制详见 [RUST_DOT.md](RUST_DOT.md)。

接手时原 DoT 工作流已通过，但 Qt 兼容回归存在 engine-contract 和 node-ui 失败。旧证据中出现 PortConflict，测试却仅用 TCP 监听探测 mixed 端口，没有保证对应 UDP 端口可绑定。本轮新增测试专用 `LoopbackPortLease`，同时保留控制 TCP、mixed TCP 和 mixed UDP 的不同端口组合，在启动被测子进程前才释放。保留所有原断言和超时，没有跳过失败测试或修改生产 UI。

具体修改：

- `src/Swirl.Quick/tests/LoopbackPortLease.h`：有界端口租约，禁用测试 socket 的系统代理继承。
- `src/Swirl.Quick/tests/EngineTests.cpp`：统一使用租约；增加释放后可重新绑定、UDP 占用必须拒绝启动两个测试；失败时保留实际引擎错误。
- `src/Swirl.Quick/tests/NodeUiChecks.cpp`：相同 mixed 端口分配原则及启动失败诊断，原 164 项界面检查保留。

这修复了测试对 TCP/UDP 可用性的错误假设；没有采集旧运行器的 Windows 排除端口表，不能进一步断言由某一条具体系统排除规则造成。

## 已实际完成的验证

### Rust 与 Qt/Rust 集成

[工作流 39013184990](https://github.com/SOLHK/Swirl/actions/runs/39013184990) 的 Linux、macOS、Windows job 均成功。包含 fmt、check、clippy、workspace test、release 构建和独立协议对端。

Windows MSVC job `117339842438` 的日志确认：

| 验证 | 结果及边界 |
|---|---|
| Rust workspace 测试 | 46 项通过，0 失败、0 ignored |
| 独立 DoT 对端 | 11 项通过，含 IPv6 bootstrap、证书拒绝、碎片报文、超时、TTL、CNAME、NXDOMAIN、原子更新和旧流保持 |
| 独立代理协议对端 | 共 28 项；初次无 Qt 时跳过的 SS/VLESS 两项在 Qt 构建后的独立步骤补跑并通过，不重复计数 |
| Qt/Rust CTest | `swirl-rust-qt-integration` 通过；该构建没有暂存 Mihomo |
| 订阅采集/离线 | 23 项中 22 通过，C++ 私有导入器 opt-in 1 项跳过 |
| Codex 管理 | 11 项中 10 通过，真实已安装 CLI opt-in 1 项跳过；未修改用户真实配置 |

Rust MSVC 构建仍打印 lib/bin 调试 PDB 输出文件同名警告，Qt 仍打印使用私有头文件的版本绑定警告；未隐藏这些已知警告。成功构建不等于无警告。

### 兼容构建和既有界面回归

[工作流 39013184987](https://github.com/SOLHK/Swirl/actions/runs/39013184987) 的构建、20 个 CTest、总览输入、HTTP 捕获、启动冒烟和多尺寸离屏预览检查均已通过。本记录写入时，后续生产 EXE/安装包编译仍在运行，不能把该工作流整体记作完成。推送 `test` 后的自动重跑也应单独查看。

实际下载检查的 [证据 artifact 12094342194](https://github.com/SOLHK/Swirl/actions/runs/39013184987/artifacts/12094342194)：

- `LastTest.log`：20/20 个 CTest 通过。
- `engine-contract.txt`：28 passed、0 failed、1 skipped；其中两个新增端口测试均通过。这里跳过的真实 Mihomo用例在单独 `engine-real` 驱动运行，不等于 Rust 使用 Mihomo。
- `engine-real.txt`：3 passed、0 failed。
- `Swirl-node-ui-diagnostics.txt`：164 checks、0 failures。
- ZIP CRC 校验通过，SHA-256：`ddd09016e284e7af78db41ff4f68d5ea45f40964af303bddc655e4feff3bd71a`。

兼容引擎回归只用于防止破坏保留的历史构建，不能算成 Rust 对相应协议的原生验收。离屏检查也不代表用户电脑的真实视觉和交互验收。

## Windows Rust 产物

[artifact 12093861808](https://github.com/SOLHK/Swirl/actions/runs/39013184990/artifacts/12093861808) 来自上述 Rust CI，ZIP CRC 和摘要已核对。

- ZIP SHA-256：`11bb2ab230709e8fd71bde64bf9e26eb4f2fb288afbf0619891a91aff24f9c60`。
- `swirl_api.dll` SHA-256：`abad6f0bf258d574aac9ed1764fc537ce894ec65b867fe7bf42b79213cc13af2`。
- 包含 Rust DLL、stdin harness、订阅 inspector、Cargo.lock 和既有本地管理工具。
- **不是完整 Swirl 桌面安装包**，不包含 Qt 主界面运行环境。不能将它或旧兼容安装程序当作完整 Rust 产品交付。

## 留给电脑环境的验收

先同步 `origin/test`，保存已有工作区修改；读取 [接续说明](CONTINUE_DEVELOPMENT.md)、[开发约束](SWIRL_CORE_DEVELOPMENT_CONTRACT.md) 和 [DoT 边界](RUST_DOT.md)。

使用 `SWIRL_USE_RUST_CORE=ON` 构建。默认 OFF 仍是历史兼容构建；不可用默认安装包的成功代替 Rust 验证。MSVC/MinGW 的 Qt 与 C++ 工具链不能混用，DLL、harness、inspector 及 Qt 适配器应来自同一构建基线。

尚未在个人环境验证：真实公网/私有 DoT 服务、私有节点 TCP/UDP、Codex 远控、手机操作、弱网与长期运行。已有订阅缓存可继续离线使用，本轮没有访问私有订阅、不需要重新开启十分钟下载窗口。

DoT 当前直连明确 DNS 端点，域名认证名需明确 IP 或精确本地映射；没有通用系统 DNS bootstrap、代理策略路由、明文回退或完整 DNS 分流。DoH、负缓存、混合模式、自动策略组、MRS/进程规则、缺失协议传输及 TUN 仍未完成。

建议下一实现阶段是 DoH 与明确的 bootstrap/路由语义，然后推进负缓存和 DNS 分流；不要重新写已验证的 UDP/TCP/DoT 报文与 TTL 基础。继续保持 UI、私有数据和 `main` 不变。
