# 第一阶段：引擎通信与生命周期

Swirl 的 C++ 业务层通过 `ProxyEngine` 使用代理引擎。`MihomoAdapter` 是目前的实现；
`EngineController` 是 QML 可见的业务门面，只暴露 Swirl 的状态、错误、版本、PID、
运行时间与脱敏配置。QML 不持有 QProcess、QNetworkReply 或 Mihomo JSON。
未来自研引擎实现同一接口，在 main.cpp 注入即可；无需改动 QML 的启停操作。

## 实际行为

- 设置 → 代理：手动启动、停止、检查状态。打开应用或设置页不自动启动引擎。
- 程序绝对路径、固定版本和 SHA-256 可以检查；仅运行符合编译进程序的版本清单的文件。
- 使用 QProcess 的程序路径和参数列表，不调用 cmd、PowerShell 或拼接 shell 命令。
- 启动顺序：锁定并校验文件 → 独占预留端口 → 生成私有配置 → `-v` → `-t` → 正式进程。
- Windows 在 CreateProcess 时原子加入 Job，Job 设置 KILL_ON_JOB_CLOSE；拒绝无法建立归属的启动。
- 配置位于当前用户应用数据目录的随机 session 目录，DACL 只授权所有者和 SYSTEM。
- API 固定为 127.0.0.1，32 字节系统随机密钥，每次启动更新；所有请求带 Bearer 认证。
- API 客户端禁止系统代理、重定向及缓存；请求有超时和 64 KiB 响应限制。
- `/version` 和 `/configs` 都通过检查才进入 Running。API 故障时进程仍存活则显示 Degraded；
  进程退出则进入 Failed。API 恢复后自动恢复 Running。
- 启动总期限涵盖版本检查、配置检查和首次健康检查；重试不会延长期限。
- 停止先 terminate，1 秒后仍未退出则 kill；只有原进程已回收才允许再次启动。
- 停止/失败使旧请求和排队启动步骤失效，避免旧回调改变新一次启动的状态。

控制接口启用不等于建立节点连接。第一阶段运行配置为 direct，所有代理入站端口为 0，
DNS、TUN、自动路由及 Geo 更新关闭。不会修改 Windows 系统代理或网络路由。
总览图表和节点仍是演示，显式提示真实引擎状态在设置页；CaptureService 保持独立。

## 供应链与构建

`packaging/mihomo-manifest.json` 固定官方 v1.19.32 的 Windows amd64-compatible 发布包，
记录官方下载地址、发布包和解压后程序的 SHA-256。清单嵌入 Swirl EXE，旁边的清单仅供查看，
不能改变运行时信任值。`scripts/stage-mihomo.ps1` 先核验发布包，再解压和核验程序；
应用本身不下载或升级引擎。许可证与对应版本源码链接在 THIRD_PARTY_NOTICES.txt。

本地已有发布包时可重复构建，不必再次下载：

```powershell
./scripts/stage-mihomo.ps1 -Destination build/swirl-quick -Archive C:/path/mihomo-windows-amd64-compatible-v1.19.32.zip
ctest --test-dir build/swirl-quick --output-on-failure
# 多配置 MSVC 使用 -C Release，并将已校验 core 目录置于 build/swirl-quick/Release。
```

测试夹具仅构建于 SWIRL_BUILD_UI_TESTS=ON，不进入安装包。契约测试使用真实子进程和本机
TCP 服务模拟故障；`swirl-engine-real` 必须使用清单对应的真实 Mihomo，缺失会失败而非假通过。
`swirl-engine-ui` 使用真实 Mihomo 驱动设置页按钮，测试异常退出同步，并在引擎运行时执行
既有 HTTP/CONNECT 抓包测试。

## 边界与限制

- 仅 Windows x64 固定版本发行；换版本需更新清单并重新验证。不会信任用户随意填写的哈希。
- 端口预留释放到引擎绑定之间仍有操作系统级竞争窗口；随机认证、实际 API 检查和启动期限
  避免错误连接被报告为健康，失败后只清理 Swirl 拥有的进程。
- abrupt crash 可以留下私有 session 配置文件；Job 仍清理引擎。正常停止会删除 session 目录。
- 当前 hash 校验读取最多 128 MiB 本地文件；进程及 API 操作异步，哈希读取在调用线程执行。
- 尚未实现节点、订阅、系统代理接管、TUN、DNS 分流、MITM、重写、脚本或网关。
- 保留当前 HDR 的 Qt GuiPrivate 依赖；部署必须匹配构建使用的 Qt 版本。

第一阶段交付后停止功能开发，第二阶段必须获得明确验收及新指令。
