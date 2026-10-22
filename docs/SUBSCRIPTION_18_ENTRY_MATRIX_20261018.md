# 18入口订阅验收矩阵

生成时间：2026-10-18T08:04:33.261222+00:00

新窗口18/18入口已采集并通过格式/节点解析；17个加密响应，1558条节点记录（含重复来源）。新缓存真实联网测试0条、成功0条、失败0条；成功率未定义。完整产品链已验收0/18。

软件名称严格取自原始授权清单的 client 标签；正文格式另列，不用 YAML/INI/Base64 猜软件，也不声称客户端标签证明了实际生成软件。

|入口|清单原始标签|实际正文格式|协议记录|TCP候选|格式/节点解析|完整产品链|新缓存联网 测/成/败|历史实测证据|
|---:|---|---|---|---:|---|---|---|---|
|1|Clash standard|clash-yaml|SS 90|90|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|2|Trojan Clash standard|clash-yaml|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|3|Clash compatible|clash-yaml|SS 90|90|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|4|Trojan Clash compatible|clash-yaml|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|5|Surge|ini|SS 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|6|Trojan Surge|ini|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|7|Shadowrocket|ini|SS 90|90|通过|未验收|0 / 0 / 0|旧远端#9固定1–3：Windows HTTPS 3/3；同样本Linux TCP 0/3，未进入HTTPS|
|8|Trojan Shadowrocket|ini|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|9|Shadowsocks SIP002|base64|SS 90|90|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|10|Trojan URI|base64|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|11|Surfboard|ini|SS 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|12|Trojan Surfboard|ini|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|13|Quantumult X|ini|SS 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|14|Trojan Quantumult X|ini|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|15|Loon|ini|SS 90|90|通过|未验收|0 / 0 / 0|旧本地Loon入口15节点1–3：Windows HTTPS 3/3|
|16|Trojan Loon|ini|TROJAN 90|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|17|Hiddify|base64|VLESS 59|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|
|18|Singbox|base64|VLESS 59|0|通过|未验收|0 / 0 / 0|无可归属的已读历史实测证据|

## 当前执行缺口

- SS入口1/3/7/9/15各90条为TCP候选，共450条；候选不是联网成功。
- SS入口5/11/13各90条要求TCP Fast Open，当前未实现。
- Trojan入口2/4/6/8/10/12/14各90条要求关闭证书验证，因此拒绝执行；入口16另有未映射或无效参数。
- 入口17/18各59条VLESS REALITY，来自同一URL，仍保留两个原始入口。REALITY未实现；每入口报告531个未识别字段记录。
- 18份真实正文的整份DNS/策略/规则/Qt/联网链均未验收；当前自包含Clash合成夹具的成功不能填入这些入口。

## 历史成功与编号映射

明确的历史Windows严格HTTPS成功只有两组各3条样本记录：清单入口7（Shadowrocket）关联旧远端#9不可变样本；入口15（Loon）旧本地缓存前三节点。不能据此宣称六台独立服务器、全部90节点成功，或新065548缓存已实测。

旧远端#9 → 原始清单入口7，证据是 RUST_WINDOWS_FIXED_SS_20261018_VERIFIED.json 的 url_mapping；同报告 local_cache_index=8 只是历史缓存枚举顺序。它不等于清单入口8，也不等于当前入口9。此次内存逐URL比较确认065548、053145与原始C盘清单顺序完全一致，故映射可沿用；未打印URL。

固定旧SS Windows执行checkout：2b2044bb43ee5da8596b9e6f99418790df666245；产品实现：cafdd62a556165bb5796fcac7f9fd8ef95643143；报告标记的三平台测试源码：b903b8b1d9c5e0c40c3dee5033447900665d1835。历史Linux同三样本TCP失败保留为环境对照，不算新缓存失败。

Loon历史Windows实测源码：4ea41397386bed2678f8af41ba110965037f421d；证据记录TLS1.3、HTTP200、证书校验、正常关闭及原生会话结清全部3/3。

新解析报告本身没有绑定可执行文件SHA/源码SHA；采集文档记载接续checkout为d3bf1eb且复用既有编译产物。此处不把checkout冒称本次解析二进制的精确源码。

## 证据文件

- new_corpus: `D:\Codex\outputs\capture-065548-corpus.json`；SHA-256 `5d4d905274df760c9d7f6e17ad02c4b8256877772e5ea6858e1273e4b34db100`
- new_integrity: `D:\Codex\outputs\capture-065548-integrity.json`；SHA-256 `152be7ae6f6accf9de8b95f52f9185060e513c094b70ea5103dbc7c620e41b44`
- historical_fixed_windows: `D:\Codex\work\Swirl\docs\evidence\RUST_WINDOWS_FIXED_SS_20261018_VERIFIED.json`；SHA-256 `f533af32846c21f6f1e30374ab97d34a2050aa7642b83174226a555f5516b18b`
- historical_loon_windows: `D:\Codex\outputs\core-continuation-loon-network.json`；SHA-256 `2c0dccb0e7eb0cc92e199882bf652ef48a603ffbc4ef034bc007822f8993da15`
- capture_checkpoint_document: `D:\Codex\work\Swirl\docs\RUST_CAPTURE_065548_20261018.md`；SHA-256 `988c463ed001ec6c522019d46e09f6b7c77d14bca0053a6596527f0d082e522e`
- historical_fixed_document: `D:\Codex\work\Swirl\docs\RUST_WINDOWS_FIXED_SS_20261018.md`；SHA-256 `ff89b308f5eae0a01a61923b54ea7513374d621368397ca02628f71ceae8b331`

矩阵初版仅解密清单元数据。后续版本在内存重放18入口（17个加密响应），检查器仅输出默认脱敏报告，未落盘明文、未刷新供应商、未请求真实节点。

解析不等于 Qt 完整配置导入：INI 非节点正文语法及完整语义仍未全部验证。最新原生产品仅接受有限的自包含 Clash 策略组/规则配置；此矩阵没有将合成夹具验收外推至真实18份文档。

## 精确解析器绑定

2026-10-18 08:21 UTC 离线重放：18/18格式/节点解析通过，1558条记录、450条TCP候选，逐项汇总与初次报告一致。源码提交 `fbef3993e9decc68c8be93a17551536ea9013fd8`，Rust源码树 `8e3b3e57e212affa2c7b391128fe45d58629c89c`。`swirl-inspect.exe` SHA-256：`55a3ad7fab5c9b1fa1eafdf1ae5aaff9a40626629fa1461f868c6e5776988ac5`。Cargo确认既有二进制对当前未变化Rust源码是最新产物；没有把复用产物伪称为新编译版本。

完整绑定及各入口完整性/未验证区段计数见 `docs/evidence/SUBSCRIPTION_18_ENTRY_REPLAY_FBEF399.json`。这是原生离线检查器证据，不是18份完整Qt产品配置执行或真实联网验收。
