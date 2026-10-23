# S3 MAX → Ultra 研发交接（进行中）

## 代码基线与整合关系

- 当前开发分支：`work/swirl-s3-max-ultra-20261023`。第一次检出时目标远端分支不存在；不重置或强推。
- 指定 UI 基线：`work/ui-window-node-performance-20261023` / `7056dea1c920cee57208c1aae54b3550a850f758`。
- U1 来源：`work/subscription-unified-integration-20261023` / `384dfe7d15a6f37e206f6db0e4768fa07d4f717d`。
- 共同祖先：`b8aa4f6f40a091697e89ae4c8291789661edca60`。采用双亲合并保留 ancestry，逐项解决冲突。
- 全部相关来源 HEAD 与已包含关系见 [s3-source-inventory.json](s3-source-inventory.json)。
- 旧 `work/u1-public-close-diagnostic-20261023` 基于较早 U1；不整分支合并，避免撤销 F6 的 MRS/测试门禁。严格关闭断言保留。
- 本检查点仍在开发；最终代码 SHA、CI 及验证数量将在后续验证完成后更新。本文件不能提前充当验收报告。

## 本阶段实际改动

1. 以 U2 的完整 UI 历史为第一父提交，整合 U1 原生协议、Rust-only 运行路径、统一导入 ABI、JSON 预览、DPAPI 事务、订阅取消和 Qt HTTP 安全修复。
2. 保留 U2 的 NodeViewModel、搜索/筛选/收藏/详情、异步平台发现、节流刷新和分层 Esc。原窗口、侧边栏、玻璃、阴影、裁剪与抗锯齿源码由 [s3-ui-baseline.json](s3-ui-baseline.json) 固定，`python tools/Verify-S3UiBaseline.py` 校验。
3. 只在既有导入/编辑界面接入 JSON 确认、取消和只读连接参数；保留 U2 页面主体和布局。
4. 保留 U1 单例 RustCoreLibrary 的 ABI/源码/内容身份校验，增加经过 x64 编译器检查的 MinGW→GNU Rust 配对，维持现有 UI 工具链；MSVC 继续使用 MSVC Rust DLL。
5. 删除历史 Mihomo 运行时、打包入口、专用暂停/路径观测脚本与未使用许可证资产；取消许可证打包豁免。保留拒绝外部内核的负向检查和订阅格式解析。
6. 统一候选版本为 `0.1.6`，NSIS 显式取 PRODUCT_VERSION.txt，防止 EXE/安装器版本漂移。
7. 新分支接通源保护、三平台 Rust/原生互通、严格网络回归、Windows Qt fixture 和产品/安装包工作流；修改到的第三方 Actions 固定到 SHA。

## 当前验证状态

- Windows GNU Rust workspace 首轮：678 passed（含 1 doctest），0 failed、0 ignored；合并工作树验证，尚非最终提交验收。
- Rust-only source guards：8 passed。
- 最初离线依赖检查缺少 `http`；按锁文件联网补齐后 workspace 通过。
- Qt 完整构建进行中。Windows MinGW 与 CI MSVC 是不同环境，不相互代替。
- VMess 严格半关闭、公开 Shadowsocks 严格 TLS 关闭、Windows Hysteria2 重连/取消需要本轮重新执行。
- 私人订阅、令牌、真实供应商节点及用户安装后联网：NOT TESTED，由用户执行，不收集私人凭据。

## Ultra 接续规则（最终交付前继续补全）

- 禁止覆盖新版 QML，禁止修改窗口外框/侧边栏曲线；先运行 UI 源码保护检查。
- 禁止恢复 Mihomo/旧 C++ 代理内核，不能用 HTTP 200/204 取代严格 TLS/协议关闭成功。
- 以实际当前源码和独立服务端证据区分 L1 格式、L2 转换、L3 启动、L4 传输、L5 用户真机。
- 跨平台加密存储、TUN、自动更新等未完成能力必须单列任务；不得重复实现已经合并的原生协议和转换接口。
- 每次交付保留完整 SHA、实际命令、通过/失败/跳过数和终态 Actions 链接，不能沿用旧提交绿灯。

## 实现参考

- [Tokio 双向转发与半关闭语义](https://docs.rs/tokio/latest/tokio/io/fn.copy_bidirectional.html)
- [Xray VMess AEAD/认证分块参考](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/common/crypto/auth.go)
- 独立服务端版本及哈希继续由 `tools/tests/*peer-lock.json` 锁定，不把参考核心交付为产品运行时。
