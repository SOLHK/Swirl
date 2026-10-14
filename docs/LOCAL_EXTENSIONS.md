# Swirl 本地脚本、模块与配置

本页描述 Swirl 自己的格式，不兼容 Surge 脚本 API 或 .sgmodule。

## 本地脚本

“更多 → 脚本”可以新建、编辑、导入 .js、保存、删除和执行。脚本定义 main(input)，输入为 JSON 对象或数组，返回 JSON 可表示的值；日志用 console.log / console.error。

```javascript
function main(input) {
    console.log("processing", input.name);
    return {name: input.name, enabled: true};
}
```

由 SwirlScriptRunner.exe 独立执行：5 秒期限、128 MiB 进程内存上限、64 KiB 输出上限、100 条日志（每条 512 字符）。调用方退出时 Windows Job 终止运行器。源码上限 256 KiB，输入上限 64 KiB，最多保存 100 个脚本，名称不能重复。

运行器不注入文件、网络、进程或 Qt 对象 API。资源限制不是操作系统安全沙箱。当前只支持手动本地执行，没有 HTTP 脚本挂钩、定时执行或 Surge $request / $response 接口。

## 配置模块

“更多 → 模块”导入本地 JSON 文件，再启用或调整顺序。

```json
{
  "schema": 1,
  "kind": "swirl-module",
  "name": "Local test",
  "description": "Local DNS and routing overrides",
  "overrides": {
    "dns": {"mode": 0, "hosts": [{"name": "fixture.test", "value": "127.0.0.1"}]},
    "rules": ["DOMAIN,fixture.test,DIRECT"]
  }
}
```

可覆盖 dns、rules、groups。下面的已启用模块优先；每个字段整体替换，不逐项合并数组。启用前经过引擎配置验证。全部停用后恢复启用第一个模块之前的基础配置。修改模块必须断开引擎；模块启用期间基础 DNS、规则和策略组编辑受限。

## 配置文件

“更多 → 配置”保存、编辑、切换、导入和导出配置。保存 DNS、规则、策略组与出站模式；节点及凭据由节点库独立管理。

```json
{
  "schema": 1,
  "kind": "swirl-profile",
  "name": "Local profile",
  "mode": "rule",
  "network": {"rules": ["DOMAIN,fixture.test,DIRECT"]}
}
```

模式为 rule、global、direct。切回 Default 恢复第一次切换前的配置。切换前必须断开引擎并停用模块。

脚本、模块与配置库存储在当前 Windows 用户的 DPAPI 加密文件中，使用原子文件替换。切换先写持久化意图，再写引擎配置；异常退出后重启会继续未完成切换。损坏或无法解密的库保留原文件并阻止覆盖。导出的配置 JSON 为明文。

## 验证

swirl-local-extensions 验证独立执行、异常值、超时、DPAPI 重载、配置导入导出、模块优先级、基础配置恢复、中断恢复，以及模块 DNS/路由经过真实 Mihomo 的本机 HTTP 请求。
