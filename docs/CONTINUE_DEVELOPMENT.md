# Swirl 接续开发入口

更新日期：2026-10-17。本轮从 `fbebb28` 接续，实现 Rust 严格 DoT（DNS over TLS）和现有 Qt 加密 DNS 字段映射；UDP/TCP/A/AAAA/CNAME/TTL 基础继续复用。详见 [DoT 实现、限制和验收](RUST_DOT.md)。DoH、域名 bootstrap 策略及 DNS 分流仍未完成。代码及功能以本文件所在的 `test` 提交为准，历史测试记录不代表本轮真实节点验收。

## 当前接手注意事项

- 用户已授权在 GitHub 上继续开发并推送 `test`，不使用 Gemini；个人 Windows/私有节点测试等其 Codex 额度恢复后再做。
- 新增 DoT 的配置验证、Rust 网络实现、11 项独立 TLS 对端测试，以及 Qt 现有字段映射测试。CI 运行记录在 [PR #22](https://github.com/SOLHK/Swirl/pull/22) 和对应提交 Actions 中；不得将测试文件存在当作已执行。
- DoT 目前使用明确 IP bootstrap，域名 URL 需已有精确本地 IP 映射；保持证书认证名。没有系统 DNS 引导、明文回退或经代理策略发送 DoT。DoH、混合 DNS 模式、负缓存等后续单独推进。
- 页面、布局、动效、系统代理和私有订阅未改动。无需重新开启订阅下载窗口。
- 在电脑上继续时先同步 `origin/test`，核对基线及未提交修改；以 `SWIRL_USE_RUST_CORE=ON` 构建，不能把默认历史兼容构建当作 Rust 验收。

## 仓库是否完整

**当前已实现的软件项目源码已提交到 SOLHK/Swirl 的 `test`。**
这与“所有规划功能已完成”不同：Rust 全量迁移仍在进行。
开始前执行 `git fetch origin`、核对 `origin/test`、工作区状态及当前分支，避免从旧的 `main` 继续。

仓库包括 Qt/C++/QML 界面和平台代码、Rust 七个 crate、Cargo.lock、依赖清单、
本地合成测试、GitHub Actions、字体/图标、规则资源、vendored nghttp2 源码及构建脚本。
没有需要另行取得的私有源码子模块，也不依赖本机工作目录里的未提交代理内核代码。

编译器、Qt SDK、Rust 工具链、Cargo 第三方包、Python 测试依赖和生成的 EXE/DLL
不是项目源码，需按文档安装/恢复。默认兼容构建的 Mihomo 二进制由
`scripts/stage-mihomo.ps1` 按提交的 manifest 下载并校验；Rust 构建不得使用它回退。
历史 `build-current-portable.ps1` / `build-quick-windows.ps1` 面向兼容构建，不能直接当 Rust 打包脚本。
本机交付 ZIP 不一定等于 GitHub Releases 上最近的旧版安装程序，必须核对提交和内核身份。

历史完整性检查：`72d5bd5` 纯 Git 导出包含 630 个文件，无源码子模块、LFS 占位文件或
构建缓存之外的被忽略文件；从独立导出目录读取 Cargo workspace 得到全部 7 个 crate，
Qt/Rust CMake configure/generate 成功。此检查不声称重新完成了一次全量编译，已有构建测试见下文。

私有订阅 URL、令牌、节点凭据、DPAPI 缓存、用户配置、SDK、构建缓存、临时交付脚本
和本机验证日志刻意不进 Git。它们不是缺失的源码。接手者可用仓库内合成服务端继续开发，
不得为补齐仓库而上传用户私有材料；云端也无法解密本机 Windows 用户的 DPAPI 缓存。

## 必须延续的约束

1. 每完成一个可验证阶段，提交并推送 **test**，然后核对远端提交。不得推送、合并或重置 main。
2. 保留现有 UI 布局、视觉和交互；继续 Rust 自研数据路径，不包装完整外部代理内核冒充自研。
3. 独立实现和审查，不要求常规 Gemini 审核。用户现已允许换开发者/模型继续，旧“唯一集成人”描述不是阻止接手的理由。
4. 未知参数保留并报告；不关闭 TLS 校验、不伪造兼容性、不静默直连或自动重放请求。
5. 原有订阅已在本机缓存；无须为离线开发重新打开订阅更新窗口。若确需新材料，一次性集中收齐。
6. 分开记录解析、参数转换、合成对端、私有节点、UDP、TUN、性能和跨平台证据。未测不能称通过。
7. 用户额度有限，优先完成具体实现与必要验证，不反复重审历史方案。每阶段更新本文件或对应能力文档。

完整要求见 [合并开发约束](SWIRL_CORE_DEVELOPMENT_CONTRACT.md)。历史文档如与本文件或后续用户指令冲突，以较新指令为准。

## 当前实现与代码位置

| 位置 | 已实现 |
|---|---|
| `core/crates/swirl-protocol` | HTTP/CONNECT/SOCKS5 入站；HTTP CONNECT、SOCKS5、Trojan TLS、SS AEAD TCP/UDP、simple-obfs HTTP、基础 VLESS v0 TCP/TLS |
| `core/crates/swirl-routing` | 顺序域名/后缀/关键词、目标端口、来源/目标 CIDR、MATCH；手动 selector |
| `core/crates/swirl-dns` | 自研 Rust DNS 报文/UDP/TCP/严格 DoT/A/AAAA/CNAME/TTL；有界系统解析、精确 hosts、各代缓存隔离及共享并发上限 |
| `core/crates/swirl-core` | 有界运行时、不可变会话配置、原子节点/组/配置更新、旧 TCP/UDP 保留原出口、流量统计 |
| `core/crates/swirl-subscription` | typed IR、Clash YAML/JSON、sing-box JSON、URI/Base64、部分 INI 识别与保留、脱敏能力报告；新增有界严格 DoT 配置；并非所有格式都可执行 |
| `core/crates/swirl-transport` / `swirl-api` | 验证 TLS、背压/半关闭；ABI v1 JSON 控制、stdin harness、离线 inspector |
| `src/Swirl.Quick/engine/RustCoreEngine.*` / `RustDnsConfiguration.h` | 现有 Qt 控制层到 Rust DLL；规则、手动组、本地 DNS 与显式 DoT 映射；明确拒绝未迁移会话 |
| `tools/` | 私有采集/离线分析、独立协议/DoT 对端、Codex 本地代理配置管理与测试 |

关键边界：[规则与手动组](RUST_NATIVE_ROUTING.md)、[本地 DNS](RUST_LOCAL_DNS.md)、[DoT](RUST_DOT.md)、
[SS-02 审核处理](SS02_REVIEW_DISPOSITION.md)、[Codex 管理](CODEX_PROXY_MANAGEMENT.md)。
手动组没有新增 UI 选择按钮；默认首成员或明确 default-selected，API 支持 select_group。
智能 MRS 路由尚未迁移，因此启用该默认设置的会话仍会被 Rust 拒绝；不可静默降级为全局。

## 从 GitHub 独立构建

```sh
git clone --branch test https://github.com/SOLHK/Swirl.git
cd Swirl/core
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked -p swirl-api
```

Rust workspace 可在 Windows/Linux/macOS 验证；Qt Rust 桌面打包当前只支持 Windows。
Windows 示例在仓库根目录执行，Qt 路径需替换为实际 SDK。Qt MinGW 库必须搭配 MinGW，
Qt MSVC 库必须搭配 MSVC。CMake 3.25+，Qt 6.10.3（含 ShaderTools），Rust stable、匹配 C 编译器及 Python 3.11+。

```powershell
cmake -S src/Swirl.Quick -B build/rust-qt -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/Qt/6.10.3/mingw_64 -DSWIRL_USE_RUST_CORE=ON -DSWIRL_BUILD_UI_TESTS=ON
cmake --build build/rust-qt --target Swirl SwirlRustCoreTests --parallel 6
ctest --test-dir build/rust-qt -R '^swirl-rust-qt-integration$' --output-on-failure
py -3 -m pip install cryptography==50.0.2
$env:SWIRL_RUST_HARNESS=(Resolve-Path build/rust-qt/rust-target/release/swirl-api.exe).Path
$env:SWIRL_RUST_INSPECTOR=(Resolve-Path build/rust-qt/rust-target/release/swirl-inspect.exe).Path
$env:SWIRL_RUST_QT_TESTS=(Resolve-Path build/rust-qt/SwirlRustCoreTests.exe).Path
py -3 tools/tests/test_rust_core.py
py -3 tools/tests/test_shadowsocks.py
py -3 tools/tests/test_dns_tls.py
py -3 tools/tests/test_subscription_capture.py
py -3 tools/tests/test_codex_management.py
```

Qt DLL 需在 PATH 或由 windeployqt 部署。MSVC 多配置输出的 EXE 位于 `Release/`，调整上述路径。
核心 DLL、harness 与 inspector 必须来自同一次构建。Python 脚本中需 C++ 私有导入器或真实 Codex CLI
的可选测试需要额外环境变量；跳过项必须报告。不要把普通 CTest 中 SS/VLESS 外部对端的跳过项当通过，
上面的 Python 测试设置 Qt 路径后会运行对应槽。

Rust 预览部署至少需 Swirl.exe、swirl_api.dll、各辅助 EXE、Qt/QML 运行库以及适用许可证。
使用 windeployqt --release --qmldir src/Swirl.Quick/qml 部署，**不暂存 Mihomo**。
制作普通用户安装包前重新构建 `SWIRL_BUILD_UI_TESTS=OFF`；开发预览不得称正式完成版。
完整 MSVC CI 命令见 [Rust workflow](../.github/workflows/rust-core.yml)。

## 已有验证与仍需做的工作

DoT 阶段的实际提交、CI 与待个人电脑验收范围见 [DoT 文档](RUST_DOT.md) 和 [PR #22](https://github.com/SOLHK/Swirl/pull/22)。不沿用旧数字证明新实现；此轮未访问私有节点或修改个人 Windows 网络。

上一自定义 UDP/TCP DNS 阶段：本机 Rust 43 项、独立协议 28 项（含 IPv6 DNS 服务端和 TCP 重试）、
采集/离线 23 项及 Qt Rust CTest 通过；fmt/check/clippy 通过。DNS 核心报文与网络执行代码
在 `core/crates/swirl-dns/src/wire.rs`，Qt 只转换已有设置。该历史阶段没有验证真实公网 DNS、
私有节点 DNS、DoH/DoT、EDNS 或 DNSSEC；对应提交跨平台结果查看 Actions。

`72d5bd5` 本机 Windows GNU/Qt 6.10.3：39 项 Rust、23 项独立协议（含 Qt SS/VLESS 对端）、
23 项采集/离线测试，以及 Qt Rust CTest 通过。fmt/check/clippy 通过。独立 SDK PATH 的预览启动、
ZIP CRC、包内 DLL 哈希及私有内容扫描通过。GNU 链接器仍有 `.drectve` 警告，未隐藏。
这些本机结果不替代对应提交的 GitHub CI；查看 [该提交 Actions](https://github.com/SOLHK/Swirl/actions?query=branch%3Atest)。
规则阶段 `7c7b884` 的旧版节点 UI 164 项通过；该修复已包含在当前源码。
本地缓存 14 份导出、12 个不同文档离线解析通过；本轮没有新增私有节点 TCP/UDP 联网验收。

建议后续按阶段实现并分别推送：

1. DoH、bootstrap 策略、系统/自定义混合模式、分流与负缓存：明确 IP 的 DoT 已补充，继续定义加密解析的路由和多地址重试；不要重复重写 UDP/TCP/DoT 报文与 TTL 基础。
2. 自动测速、fallback/load-balance：有界健康检查、明确选择语义、不重放已有请求、保留旧连接，不能把 manual 解析冒充自动组。
3. 智能规则库/MRS、进程规则与 DNS 分流；保持原始配置和未知字段，禁止静默略过。
4. WS/gRPC/XHTTP、REALITY/Vision、VMess/SS2022、QUIC 等缺少的协议/传输，分别提供互操作证据。
5. TUN、LAN、网关、权限/系统代理所有权接管与异常恢复；不擅自改用户当前网络。
6. 完整订阅到产品配置的 Rust 接管、长期/弱网/性能验证，最后才移除旧内核依赖。

不要重写已完成模块或删掉兼容构建来制造“全自研完成”。所有阶段仍需保留 UI 与用户数据。
