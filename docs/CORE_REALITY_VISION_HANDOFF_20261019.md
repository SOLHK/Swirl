# Swirl Core 接续交接：REALITY R2 + Vision R1（2026-10-19）

## 正确代码基线

- 仓库：`https://github.com/SOLHK/Swirl`
- **唯一开发分支**：`work/core-completion-20261017`。不要修改/合并 `main` 或 `test`，也不要 force push。
- 本文档对应的**实际源码快照**：`5b55ab33dde4c1789547e523b25dcad5abb1cf48`，tree `ffa4bba1b98bf22b60ca6d53d3d90b156f97b6ad`。
- 本文件是交接资料，不改变该源码快照。新窗口先读取远端当前 HEAD；如果后来有人提交，快进并保持所有并发文件，不能回退。
- 按 `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md`、`core/README.md`、`docs/SELF_DEVELOPMENT_PROGRESS.md`、`docs/REALITY_TLS_ENGINE_20261019.md`、`docs/VISION_FRAMING_FOUNDATION_20261019.md` 接续。
- 当前固定验收基线仍为 **79 项、6 项整项已验收、加权 10.83%**。这是整项验收率，**不是代码完成百分比**；协议档案不能因为局部组件通过就冒称完成。

## 已推送源码与精确 CI

| 阶段 | 源码提交 | GitHub Actions 已核实结果 | 实际范围 |
|---|---|---|---|
| REALITY TLS R2 | [`611edcff`](https://github.com/SOLHK/Swirl/commit/611edcff6c90d5f6e22637de1a24b4dfde494095) | [Rust Core #76](https://github.com/SOLHK/Swirl/actions/runs/39217803242) Linux/macOS/Windows **success**；[App #73](https://github.com/SOLHK/Swirl/actions/runs/39217803202) **success** | 原生认证 ClientHello、rustls TLS 1.3 双向记录、安全关闭；独立 Python/OpenSSL 对端正反例；Windows Qt 与完整 `Swirl.exe` 编译通过 |
| Vision R1 | [`5b55ab33`](https://github.com/SOLHK/Swirl/commit/5b55ab33dde4c1789547e523b25dcad5abb1cf48) | [Rust Core #78](https://github.com/SOLHK/Swirl/actions/runs/39220250082) Linux/macOS/Windows **success**；[App #75](https://github.com/SOLHK/Swirl/actions/runs/39220250444) **success** | 每方向增量帧编码/解码、完整终止边界、固定向量、严格 VLESS `xtls-rprx-vision` Addons、原有无 flow 请求回归 |
| 并发字体测试 | [`9984a5d`](https://github.com/SOLHK/Swirl/commit/9984a5ddbae072bfec2aa5c7f94604ac77ca8471) | [Font Windows](https://github.com/SOLHK/Swirl/actions/runs/39217984537) **success** | D3D11 真实渲染后端纹理复用断言；已被 Vision 提交保留 |

上述每个成功结论均针对所列精确 SHA；不能把这些绿色运行借给未来的新源码。Vision R1 本地独立全工作区测试为 239 项单元/集成 + 1 doctest；Release 二进制 15 套 Python 回归 211 通过，5 项无 Qt 而明确跳过；CI 防退化测试 33 通过。曾有旧缓存缺失 `swirl_core` rlib、rustdoc E0463；完全新的 target 目录无源码/断言修改即通过，原始失败仍须保留。

## 未完成，绝对不能标成通过

1. **成熟 XTLS/REALITY 服务端互通的可重复 CI**：前一阶段对话记录称本地的成熟对端实验做过混合密钥交换、X25519 双向 32,769 字节，以及错误 short ID、公钥共 4/4；但截至本交接基线，**其对应测试源码、上游 Go 可执行文件身份、真实版本和三平台 CI 不在仓库，故尚未完成交付**。不要把该描述当作已审核源码或 CI 通过。应重新取证并入库。
2. **REALITY 产品出口仍未启用**：当前 TLS 组件不是浏览器/uTLS 指纹替代；未证明完整 VLESS/REALITY/Vision 配置能从导入、IR、路由、运行时、Qt 经真实服务端连通。未知选项、指纹和不安全组合保留、明确拒绝；绝不剥掉参数、降级普通 TLS 或转 DIRECT。
3. **Vision 仅 R1 帧组件**：未实现内层 TLS 分类和有资格的零拷贝/直传切换、底层套接字/缓冲所有权、生产 padding 策略、异步部分写、取消关闭和独立真实 Vision 对端验证。收到 command=2 只是 `DirectRequested` 事件，**不代表可以直传**。
4. 私有订阅全格式语义/真实来源链、私有提供商实际联网、TUN、长时间弱网/高负载、Windows 物理显示及安装包验收均不能从上述 CI 推断。**订阅更新开关保持关闭**，既有加密缓存可离线使用；未经新授权不要重新抓取。

## 下一个窗口首要执行步骤

1. 通过现有 GitHub 权限读取开发分支 HEAD、源码、工作流与验收文件；尊重并发字体修改。不仅给用户提示词：有实际权限就直接开发、测试、提交并推送。提交前须先获取最新 HEAD，用预期 SHA 的非强制推进保护并发修改。
2. 首先使成熟 REALITY 对端测试**真正成为可复现的仓库用例**：固定且核对未修改的 XTLS/Xray-core 和 REALITY 上游提交、Go 模块版本/校验和，使用无敏感信息的 loopback 合成服务端和测试 CA，不更改系统证书库/代理。覆盖原生混合/X25519、握手双方 Finished、双向数据和规范关闭，以及短 ID/公钥错误不得传递应用字节、超时/资源清理。源文件/脚本及 Windows、macOS、Linux CI 缺一不可；失败按实际阶段保留日志并修复，而不是改断言放水。此项工作在本次交接时**尚未推送**。
3. 再实施 Vision R2：内层 TLS eligibility、请求/响应双向增量 framing、bounded async I/O 及只有在验证状态满足时才允许的转换，确保同一帧剩余 bytes 不丢、不会重放或回退。先独立对端，通过后再接产品 Runtime/Qt/订阅。
4. 每阶段运行 `cargo fmt --all -- --check`、`cargo check --workspace --locked`、`cargo clippy --workspace --all-targets --locked -- -D warnings`、`cargo test --workspace --locked`、Release 构建、独立 Python peers，及适用的 Windows Qt/完整应用 CI。对用户明确区分 **本地成功、云端成功、真实提供商成功、物理设备成功** 四种证据层级。
5. 持续更新本交接文档或创建新交接文档，精确记录源 SHA、测试输入、通过/失败/跳过、局限和下一项阻塞，不修改冻结 79 项分母。不得向公开仓库提交私有订阅 URL、原文、密钥、缓存或受限苹方二进制。

## 执行边界

继续独立 Rust Core 自研；成熟开源仅作协议行为/许可证参考，不拷贝整套代理内核冒称 Swirl 自研。保留现有 Qt/UI/字体工作和主版本功能；按最小改动解决真实问题。所有新代码与 CI 结果由对应的准确提交核验。