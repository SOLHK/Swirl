# DNS / Shadowsocks 测试对端的端口配对与失败证据（2026-10-19）

## 两次实际 Windows 失败

本阶段修复测试基础设施中的具体缺陷，不改变 Rust DNS、Shadowsocks、
REALITY、路由或 Qt 产品行为。三个较早源码阶段的成功与失败分开保留：

| 精确源码 | Rust 工作流 | 实际 Windows 失败 | 后续执行边界 |
| --- | --- | --- | --- |
| `daad7a057ab2c4b347c3ab142ce88af6528cb8f6` | [39200717679](https://github.com/SOLHK/Swirl/actions/runs/39200717679)，job `117892931813` | `test_dns_negative.py` 运行 30 个测试函数，出现 20 个 error 及 1 个后果性 assertion failure；error 均在 UDP 先选端口后的 TCP bind，`WinError 10013` | Qt 构建、CTest、独立 Qt 对端和完整原生应用未执行 |
| `e0534f4e9ea23ae38797f95ff7026f00e2f2a1e8` | [39201185263](https://github.com/SOLHK/Swirl/actions/runs/39201185263)，job `117894296898` | `test_udp_association_pins_distinct_ss_exit_across_health_and_configure` 构造 `SsPolicyPeer` 时失败；旧代码只留下 `RuntimeError('cannot allocate a local TCP/UDP fixture pair')`，底层 errno 未记录 | DNS 后续菜单、Qt 构建、CTest、独立 Qt 对端和完整原生应用未执行 |

两次 Windows 的 fmt、check、Clippy、188 个 Rust 单元/集成测试、1 个 doctest、
Release 构建及独立 REALITY 向量检查均已通过。Linux/macOS 各自通过完整既有
197 个 Python 测试，明确跳过 5 个 Qt 钩子。不能因此把这两次 Windows 作业
写成成功，也不能把报告上传步骤的 `No files were found` 当作 Qt 测试产物。

第二次失败不能归因于“UDP 先分配”：`SsPolicyPeer` 当时已经先分配 TCP。
该次日志无法恢复真实底层错误码，因此不声称两次失败具有同一个系统原因。

## 修改与边界

- `tools/tests/dns_peer.py` 先绑定并持有 `TCP(loopback, 0)`，再绑定同号 UDP。
  两种协议各自选择动态端口；UDP 分配成功本来就不保证该端口能用于 TCP。
- `tools/tests/test_policy_groups.py` 中的 `SsPolicyPeer` 保留 TCP 先分配，
  通过 `ExitStack` 清理所有部分构造失败，包括原先会泄漏 TCP 的非 `OSError`。
- 两个分配器只对 `EADDRINUSE` / Windows `10048` 做最多 **8 次**尝试。
  `10013`、普通权限拒绝、资源不足与其他错误原样抛出；第八次碰撞保留
  最后的原始异常。异常 note 给出对端类型、TCP/UDP、合成回环候选地址及尝试号。
- 成功取得两端后才启动服务线程。没有启用地址/端口重用、修改产品超时、
  缩小 DNS/UDP 数据边界、降低成功转发数量或改变原来的失败断言。
- `.github/workflows/rust-core.yml` 在该 Windows peer 步骤失败后，只读运行
  `netsh ... show dynamicport` / `show excludedportrange`，记录 IPv4/IPv6 的
  TCP/UDP 分配事实。原测试步骤的失败和退出码保留，不修改系统配置。

这是一项有明确边界的分配和诊断修复。TCP 选出的端口仍可能不能用于 UDP；
端口配对的实际 Windows 结果必须由新源码 CI 证明。不能把 `10013` 一概当成
可忽略的碰撞，也不能靠增加次数或打开 `SO_REUSEADDR` 制造通过。

## 独立回归

同一批最终回归先对旧实现运行，确实复现 UDP 选出的 TCP 不可用端口、
Windows 错误码被吞、末次错误丢失及部分 socket 泄漏，再验证修复。

新增/增强的 5 个 DNS 分配器函数和 3 个 SS 分配器函数覆盖：

- IPv4/IPv6 的真实 UDP 请求与带长度前缀、分段写入的 TCP 请求，使用最大
  合法 DNS 名称，逐字节核对独立响应及两种传输的实际查询记录。
- 两个端点上的 POSIX/Windows 碰撞，在第 1 次、第 7 次失败后成功，或
  第 8 次仍失败；核对准确次数、最终异常身份及所有失败 socket 已关闭。
- 两端权限错误不重试，不启动线程；原始 `errno` / `winerror` 不被包装抹去。
- 非 socket 异常与资源不足立即失败，释放已创建的另一半。

Linux 使用真实回环 socket 的独立复审还单独重现了两项 SS 缺陷：旧代码把
一次 UDP `10013` 吞成八次后的无错误码 `RuntimeError`，非 `OSError` 留下
一个 TCP socket；新代码均保留原异常，一次后退出且零遗留 socket。
这种受控错误注入不是 Windows 真实端口保留实测。

本地复核使用 Linux、Python 3.12.14、Rust 1.99.1 和之前实际构建的隔离
Release CLI；Windows CI 使用 Python 3.14.8。结果如下：

| 门禁 | 实际结果 |
| --- | --- |
| 两处分配器专项回归 | 8 通过、0 失败、0 跳过；是下面两套的子集，不重复累加 |
| `test_dns_negative.py` 完整套件 | 31 通过、0 失败、0 跳过，80.064 秒 |
| `test_policy_groups.py` 完整套件 | 16 通过、0 失败、0 跳过，5.387 秒；原失败的实际 UDP 策略固定转发通过 |
| 三个修改 Python 文件的 `py_compile`、`git diff --check` | 通过 |
| Cargo fmt / check / Clippy / workspace test / Release 构建 | 全部通过；188 单元/集成 + 1 doctest，0 失败、0 ignored |
| `ApplyCoreDevelopment.py --check` | 25 个既有守卫测试通过，更新前后工作流字节一致 |

Rust 生产源码及 Release CLI 未因本次 Python 修复改变。新增测试函数共 4 个，
既有产品转发断言保持原样。以上为提交前的本地检查点；以下新增的三平台
完整菜单与 Windows Qt/完整原生应用结果来自修复提交自己的 CI，不能从
本地受影响套件或旧绿色运行外推。

修复提交的 CI 结果在本阶段完成后追加，并汇总到
[本轮结构化证据](evidence/REALITY_FOUNDATION_AND_IMPORT_20261019.json)。
原始失败记录不会被成功的后续提交覆盖。

## 修复提交的精确 CI 结果

源码 `a429d5bc2efe31f10cfb61d16b16ffbde2a8fc40`、tree
`66ea18bfc6daf76b5985ac94742d1e12d0a64ae5` 的
[Rust 运行 39202767158](https://github.com/SOLHK/Swirl/actions/runs/39202767158)
于 `2026-10-19T05:27:53Z` 全部成功。三个平台的 checkout、日志和本次
产物身份分别核对，没有从旧提交继承测试结果。

| 门禁 | 此次实际结果 |
| --- | --- |
| Linux / macOS / Windows Rust | 各 188 单元/集成 + 1 doctest；fmt、check、Clippy、Release 和独立 REALITY 向量全部通过 |
| 三平台共有 Python 菜单 | 各 201 通过、5 个 Qt 钩子跳过，0 失败/错误；8 个分配器函数是该菜单子集 |
| Windows 额外合成 capture / 独立 management | 分别 25 通过/1 跳过、10 通过/1 跳过；不访问私有订阅 |
| Windows CTest | 原生 3/3、兼容 2/2；原生包含独立 storage-paths 测试 |
| 原生 Qt integration XML | 47 通过、0 失败、6 个依赖独立对端的跳过，排除初始化/清理 |
| 原生 import / 兼容 import / 兼容 DNS guard XML | 分别 11、11、2 通过，无失败/跳过；导入坏输入持久化函数在两种模式均实际执行 |
| 独立 Python Qt 对端 | 5 次分别通过，实际覆盖 6 个 Qt peer 槽位；此前的跳过不冲抵 |
| 完整原生应用 | `SWIRL_USE_RUST_CORE=ON`、Release `Swirl.exe` 于 `05:27:47.685957Z` 编译成功 |

Windows 共记录 248 次 Python 调用：241 通过、7 跳过。这个累计包含先跳过、
后单独运行的钩子调用，不能当成 248 个互不重复的测试。四份 Qt XML 合计
71 个实际通过、6 个跳过；storage-paths 和五个 Python 钩子另外记录。
新增只读 netsh 诊断因实际 peer 步骤成功而没有运行，没有修改 Windows 端口配置。

[App 运行 39202767154](https://github.com/SOLHK/Swirl/actions/runs/39202767154)
也成功：189 Rust、25 guard、69 network 通过，5 跳过。下载的实际测试 SHA
及源码 tar 的 182 个 regular 文件逐字节匹配该提交。这个较小菜单不能替代
上面的完整 Rust 工作流。Linux 公网产物的三个既有 DIRECT HTTPS/原生 DoH
检查成功，包括严格证书验证与会话关闭；它们不验证 REALITY/Vision 或提供商。

本次 Windows Qt artifact `12164194762` 的 ZIP SHA-256 为
`ae2a40bba772956bca25eccf06cee76353971f574bd00fd1f083447c2a257e26`。
Windows 原始作业日志 SHA-256 为
`6a76d65a49a26b7853ee77e107f0ae1e9c969ad0b469fa03d497fecfce532f88`。
逐份 XML、其他平台、App 与公网产物的身份和计数见统一证据。

## 依据与未扩大范围

- [Microsoft Winsock bind](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-bind)：
  端口零分配及 TCP/UDP、IPv4/IPv6 的独立动态范围。
- [Microsoft Windows Sockets 错误码](https://learn.microsoft.com/en-us/windows/win32/winsock/windows-sockets-error-codes-2)：
  `10013` 同时可能涉及权限与排他绑定，不等价于普通地址占用。
- [固定 CPython 3.14.8 socketserver](https://github.com/python/cpython/blob/v3.14.8/Lib/socketserver.py)：
  构造失败清理自身 socket，成功对象的上下文管理负责另一半资源。

这里只独立实现和验证测试对端生命周期，没有复制上游代理源码或新增依赖。
尚无新 CI 失败证据的其他历史同端口测试保持原范围。固定验收仍为
79 项、6 项已验收、10.83% 权重；本修复不新增协议或完整订阅验收。
没有供应商刷新、私有节点请求或 Windows 物理设备操作。
