pragma Singleton
import QtQuick
QtObject {
    property string currentPage: "overview"
    property bool sidebarCollapsed: false
    property bool proxyOn: false
    property bool systemProxyOn: false
    property bool tunOn: false
    property bool detailOpen: true
    property string mode: "规则"
    property string policy: "自动选择"
    property string selectedNode: "新加坡 · 01"
    property string selectedNodeRegion: "SG"
    property string selectedNodeProtocol: "Trojan"
    property int selectedNodeLatency: 38
    function selectNode(node) {
        selectedNode=node.name; selectedNodeRegion=node.region || "--"
        selectedNodeProtocol=node.protocol || "未检测"; selectedNodeLatency=node.latency || 0
        addEvent("选用演示节点 "+node.name,"accent")
    }
    property string toast: ""
    property bool demoLoading: false
    property bool demoError: false
    property bool demoEmpty: false
    property bool autoSwitch: false
    property int historyIndex: 0
    property var navigationHistory: ["overview"]
    property date sessionNow: new Date()
    property var recentEvents: []
    property real demoDown: 0
    property real demoUp: 0
    property int demoConnections: 0
    property int demoTick: 0
    property real totalGB: 2.84
    readonly property var navigationGroups: [
        {title:"",pages:[{id:"overview",title:"总览",icon:"home"},{id:"proxies",title:"代理节点",icon:"pin"},{id:"policies",title:"策略组",icon:"layers"},{id:"rules",title:"规则",icon:"document"},{id:"subscriptions",title:"订阅管理",icon:"refresh"},{id:"profiles",title:"配置文件",icon:"file"}]},
        {title:"网络",pages:[{id:"dns",title:"DNS",icon:"globe"},{id:"toolbox",title:"网络检测",icon:"gauge"},{id:"connections",title:"连接记录",icon:"clock"}]},
        {title:"工具",pages:[{id:"inspector",title:"HTTP 检查器",icon:"code"},{id:"capture",title:"抓包",icon:"capture"},{id:"traffic",title:"流量分析",icon:"bars"},{id:"scripts",title:"脚本与配置",icon:"terminal"},{id:"external",title:"外部工具",icon:"folder"}]}
    ]
    function navigate(id) {
        if (currentPage === id) return
        navigationHistory = navigationHistory.slice(0,historyIndex+1).concat([id])
        historyIndex = navigationHistory.length-1
        currentPage = id
    }
    function goBack() { if(historyIndex>0) currentPage=navigationHistory[--historyIndex] }
    function goForward() { if(historyIndex<navigationHistory.length-1) currentPage=navigationHistory[++historyIndex] }
    function addEvent(title,tone) {
        recentEvents=[{time:Qt.formatDateTime(sessionNow,"HH:mm"), title:title, tone:tone}].concat(recentEvents).slice(0,5)
    }
    function initializeHistory() {
        sessionNow=new Date()
        function at(minutes) { return Qt.formatDateTime(new Date(sessionNow.getTime()-minutes*60000),"HH:mm") }
        recentEvents=[{time:at(1),title:"已断开演示连接",tone:"neutral"},{time:at(2),title:"连接到 新加坡 · 01 (Trojan)",tone:"accent"},{time:at(2),title:"开始建立演示连接",tone:"success"},{time:at(2),title:"演示订阅更新完成",tone:"success"},{time:at(3),title:"切换到 自动选择",tone:"success"}]
    }
    function setConnection(on) {
        proxyOn=on
        demoDown=on ? 3.2 : 0; demoUp=on ? 0.7 : 0; demoConnections=on ? 12 : 0
        addEvent(on ? "已建立演示连接" : "已断开演示连接",on ? "success" : "neutral")
        toast=on ? "界面演示已连接，不会启用系统代理。" : "演示连接已断开，当前实时流量为零。"
    }
    function tickTraffic() {
        sessionNow=new Date(); demoTick++
        if(proxyOn) {
            demoDown=3.2+Math.sin(demoTick*0.7)*0.7
            demoUp=0.65+Math.sin(demoTick*0.5)*0.2
            demoConnections=12+demoTick%5
            totalGB+=(demoDown+demoUp)/1024
        } else { demoDown=0; demoUp=0; demoConnections=0 }
    }
    readonly property var groups: [
      {title:"控制中心", pages:[
        {id:"overview",title:"总览",icon:"home",sub:"网络概览"},
        {id:"dashboard",title:"仪表盘",icon:"chart",sub:"实时数据与历史趋势"},
        {id:"profiles",title:"配置文件",icon:"folder",sub:"配置管理与历史版本"}]},
      {title:"代理与路由", pages:[
        {id:"proxies",title:"代理节点",icon:"globe",sub:"节点和可用状态"},
        {id:"policies",title:"策略组",icon:"layers",sub:"流量分流策略"},
        {id:"subscriptions",title:"订阅管理",icon:"refresh",sub:"远程订阅源"},
        {id:"rules",title:"分流规则",icon:"list",sub:"规则匹配与决策"},
        {id:"dns",title:"DNS",icon:"server",sub:"解析器、Hosts 与查询"}]},
      {title:"网络检查",pages:[
        {id:"capture",title:"抓包",icon:"capture",sub:"真实 HTTP 会话与 CONNECT 隧道"},
        {id:"connections",title:"连接记录",icon:"activity",sub:"网络会话"},
        {id:"inspector",title:"HTTP 检查器",icon:"inspect",sub:"请求与响应"},
        {id:"traffic",title:"流量分析",icon:"chart",sub:"流量统计与分布"},
        {id:"tls",title:"TLS / HTTPS 解密",icon:"shield",sub:"HTTPS 检查设置"}]},
      {title:"调试工具",pages:[
        {id:"rewrite",title:"重写规则",icon:"edit",sub:"HTTP 请求修改"},
        {id:"map",title:"本地与远程映射",icon:"route",sub:"响应映射"},
        {id:"breakpoint",title:"HTTP 断点",icon:"pause",sub:"拦截与修改"},
        {id:"replay",title:"HTTP 重放",icon:"play",sub:"重放请求"}]},
      {title:"自动化",pages:[
        {id:"scripts",title:"脚本",icon:"code",sub:"JavaScript 与控制台"},
        {id:"modules",title:"模块",icon:"grid",sub:"扩展与组件"},
        {id:"automation",title:"自动化任务",icon:"clock",sub:"触发条件与定时任务"}]},
      {title:"实用工具",pages:[
        {id:"toolbox",title:"工具箱",icon:"tool",sub:"网络诊断"},
        {id:"api",title:"本地 API / 命令行",icon:"terminal",sub:"开发者集成"},
        {id:"gateway",title:"网关与设备",icon:"network",sub:"局域网与网络接口"}]},
      {title:"系统",pages:[
        {id:"logs",title:"日志",icon:"list",sub:"事件与诊断"},
        {id:"settings",title:"设置",icon:"settings",sub:"外观与偏好设置"}]}
    ]
    readonly property var zhDictionary: ({
        "System proxy": "系统代理",
        "Default strategy": "默认策略",
        "Process bypass": "进程绕过",
        "Proxy authentication": "代理身份验证",
        "Resolver selection": "解析器选择",
        "Encrypted DNS": "加密 DNS",
        "Fake-IP handling": "虚拟 IP 处理",
        "TUN entry point": "TUN 入口",
        "Interface selection": "网卡选择",
        "Route exclusions": "路由排除",
        "Gateway DNS": "网关 DNS",
        "HTTP port": "HTTP 端口",
        "SOCKS port": "SOCKS 端口",
        "API port": "API 端口",
        "Port conflict alerts": "端口冲突提醒",
        "Sensitive data redaction": "敏感数据脱敏",
        "Local encryption": "本地加密",
        "Certificate trust": "证书信任",
        "Diagnostic consent": "诊断授权",
        "Build information": "构建信息",
        "Third-party components": "第三方组件",
        "Project links": "项目链接",
        "Enable feature": "启用功能",
        "Default behavior": "默认行为",
        "Advanced options": "高级选项",

        "Filter host, IP, process or policy": "搜索域名、IP、进程或策略",
        "Export": "导出",
        "Clear": "清空",
        "Click a row to examine a connection": "点击一行查看连接详情",
        "HOST": "域名",
        "IP ADDRESS": "IP 地址",
        "PROCESS": "进程",
        "PROTO": "协议",
        "POLICY": "策略",
        "UPLOAD": "上传",
        "DOWNLOAD": "下载",
        "LATENCY": "延迟",
        "SINCE": "开始时间",
        "STATE": "状态",
        "No matching connections": "没有匹配的连接",
        "Adjust the search or status filter": "请调整搜索条件或状态筛选",
        "Connection details": "连接详情",
        "Terminate connection": "终止连接",
        "All states": "全部状态",
        "Host": "域名",
        "Latency": "延迟",
        "Downloaded": "已下载",
        "Process": "进程",
        "Activity and throughput": "实时活动与吞吐量",
        "Export report": "导出报告",
        "Total Download": "总下载量",
        "Total Upload": "总上传量",
        "Avg. Latency": "平均延迟",
        "Connections": "连接记录",
        "Network throughput": "网络吞吐量",
        "Download and upload · local representative series": "上传与下载 · 本地模拟趋势",
        "● DOWNLOAD": "● 下载",
        "● UPLOAD": "● 上传",
        "Top destinations": "热门目的地",
        "Open connections": "查看连接",
        "DOMAIN": "域名",
        "REQUESTS": "请求数",
        "Traffic distribution": "流量分布",
        "Protocol percentages are illustrative.": "协议占比为模拟数据。",
        "Last hour": "最近 1 小时",
        "24 hours": "最近 24 小时",
        "7 days": "最近 7 天",
        "30 days": "最近 30 天",
        "CONFIGURATION DEMO": "配置演示",
        "Synthetic configuration records only. Existing YAML and subscription data are never read or overwritten.": "仅使用模拟配置，不读取或覆盖现有 YAML 与订阅数据。",
        "Import": "导入",
        "New profile": "新建配置",
        "CURRENT PREVIEW CONFIGURATION": "当前演示配置",
        "Manual selection · no network engine initialized": "手动选择 · 网络内核尚未启动",
        "LOCAL FIXTURE": "本地示例",
        "Validate": "检查配置",
        "Export demo": "导出演示",
        "Update remote": "更新远程配置",
        "Search profiles and sources": "搜索配置和订阅来源",
        "PROFILE NAME": "配置名称",
        "SOURCE": "来源",
        "VERSION": "版本",
        "UPDATED": "更新时间",
        "UNSAVED DEMO CONTENT": "尚未保存的演示内容",
        "Save preview": "保存预览",
        "Compare": "对比",
        "Restore": "恢复",
        "Profile summary": "配置摘要",
        "Use profile in UI": "在界面中使用",
        "View editor": "查看编辑器",
        "Create configuration preview": "新建配置预览",
        "Name": "名称",
        "New profile name": "新配置名称",
        "Cancel": "取消",
        "Add demo": "添加演示",
        "Configurations": "配置列表",
        "Editor": "编辑器",
        "Version history": "历史版本",
        "Backups": "备份",
        "All sources": "全部来源",
        "Local": "本地",
        "Remote": "远程",
        "Active proxy strategy": "当前代理策略",
        "Selected endpoint: ": "当前节点：",
        "TEST NODES": "演示节点",
        "Test all": "全部测速",
        "Add node": "添加节点",
        "Find a node or region": "搜索节点或地区",
        "PROXY ENDPOINT": "代理节点",
        "REGION": "地区",
        "PROTOCOL": "协议",
        "LATENCY (ms)": "延迟（毫秒）",
        "HEALTH": "健康状态",
        "Endpoint inspector": "节点详情",
        "Synthetic node · No connection established": "模拟节点 · 未建立真实连接",
        "Protocol        ": "协议　",
        "Latency             ": "延迟　",
        "Strategy            ": "策略　",
        "Select in demo": "选用此节点",
        "Edit endpoint": "编辑节点",
        "Add proxy endpoint": "添加代理节点",
        "Endpoint label": "节点名称",
        "e.g. Singapore · 03": "例如：新加坡 · 03",
        "Save demo": "保存演示",
        "All regions": "全部地区",
        "Appearance": "外观",
        "Personalize how Swirl looks and behaves": "自定义 Swirl 的外观与使用方式",
        "LOCAL UI PREFERENCES": "仅本地界面设置",
        "PREFERENCES": "偏好设置",
        "Color theme": "界面主题",
        "Choose light, dark or follow Windows": "选择浅色、深色或跟随 Windows",
        "Windows backdrop material": "窗口玻璃材质",
        "Uses DWM on supported Windows 11 systems": "在支持的 Windows 11 上启用 DWM 背景",
        "Reduce motion": "减少动画",
        "Disable most transition animations": "减少界面切换动画",
        "Interface scale": "界面缩放",
        "CHANGES ARE LOCAL TO THIS UI PREVIEW": "更改仅作用于当前界面预览",
        "Preview configuration, not applied": "仅预览设置，不会应用到系统",
        "Open advanced options": "打开高级选项",
        "System": "跟随系统",
        "Light": "浅色",
        "Dark": "深色",
        "General": "常规",
        "Proxy": "代理",
        "TUN": "虚拟网卡",
        "Ports": "端口",
        "System Integration": "系统集成",
        "Startup": "启动",
        "Notifications": "通知",
        "Data Management": "数据管理",
        "Privacy & Security": "隐私与安全",
        "Keyboard Shortcuts": "快捷键",
        "About Swirl": "关于 Swirl",
        "Search URL, path, or request method": "搜索 URL、路径或请求方法",
        "Import HAR": "导入 HAR",
        "Export HAR": "导出 HAR",
        "HTTP CAPTURE DEMO": "HTTP 抓包演示",
        "Record": "记录",
        "METHOD": "方法",
        "STATUS": "状态码",
        "PATH / QUERY": "路径 / 查询",
        "HTTP": "HTTP 版本",
        "TIME": "耗时",
        "SIZE": "大小",
        "Request waterfall": "请求瀑布图",
        "Synthetic timing breakdown · select a request for full details": "模拟耗时分布 · 选择请求查看详情",
        "Replay": "重放",
        "Breakpoint": "断点",
        "All methods": "全部方法",
        "DEMO DNS ENGINE": "DNS 模拟引擎",
        "Requests are local fixtures · no name resolution occurs": "仅展示本地数据，不进行实际域名解析",
        "Test Resolver": "测试解析器",
        "Primary resolver": "首选解析器",
        "DoH · DNSSEC option · synthetic endpoint": "DoH · DNSSEC 选项 · 模拟解析地址",
        "Protocols enabled": "启用协议",
        "IPv4 + IPv6 · Fake-IP Preview": "IPv4 + IPv6 · 虚拟 IP 预览",
        "Clear demo": "清空演示",
        "Search DNS domain, answer or record type": "搜索域名、解析结果或记录类型",
        "TYPE": "类型",
        "ANSWER": "解析结果",
        "RESOLVER": "解析器",
        "RESULT": "结果",
        "DNS inspection": "DNS 检查",
        "Copy answer": "复制结果",
        "Edit mapping": "编辑映射",
        "Resolver test": "解析器测试",
        "Domain name": "域名",
        "This test returns an explanatory demo result. No DNS packets are sent.": "这是模拟测试，不会发送 DNS 请求。",
        "Run demo": "运行演示",
        "Edit DNS mapping": "编辑 DNS 映射",
        "Hostname": "主机名",
        "Target / answer": "目标地址 / 解析结果",
        "Apply demo": "应用演示",
        "Query Log": "查询记录",
        "Resolvers": "解析器",
        "Hosts": "Hosts 映射",
        "Cache": "缓存",
        "ORDERED DEMO RULESET": "模拟规则列表",
        "Priority is evaluated top to bottom in this preview.": "规则从上到下按优先级匹配。",
        "Test rule": "测试规则",
        "New rule": "新建规则",
        "Search pattern, type or target strategy": "搜索匹配内容、类型或策略",
        "PRIORITY": "优先级",
        "MATCH PATTERN": "匹配条件",
        "HITS": "命中次数",
        "No matching rules": "没有匹配的规则",
        "Rule inspection": "规则详情",
        "Enable rule": "启用规则",
        "Edit selected": "编辑所选",
        "View match details": "查看匹配详情",
        "Rule editor": "规则编辑器",
        "Rule type": "规则类型",
        "Match pattern": "匹配条件",
        "Target policy": "目标策略",
        "Changes are local to the UI; no routing rules are installed.": "仅修改界面数据，不会设置系统分流规则。",
        "Rule matching test": "规则匹配测试",
        "Host or IP to evaluate": "输入域名或 IP 地址",
        "Demo evaluator only.\\nNo real DNS lookup or proxy routing occurs.": "仅执行模拟匹配。\\n不会实际解析 DNS 或转发流量。",
        "Close": "关闭",
        "Evaluate": "开始测试",
        "All policies": "全部策略",
        "SUBSCRIPTIONS · MOCK DATA": "订阅管理 · 模拟数据",
        "No remote URLs are requested or saved.": "不会访问或保存远程 URL。",
        "Update all (demo)": "全部更新（演示）",
        "Add subscription": "添加订阅",
        "Search subscription providers": "搜索订阅来源",
        "Auto update": "自动更新",
        "Updated ": "最近更新 ",
        "Details": "详情",
        "Refresh": "刷新",
        "Provider inspector": "订阅详情",
        "Edit provider": "编辑订阅源",
        "View update errors": "查看更新错误",
        "Subscription source": "订阅来源",
        "Display name": "显示名称",
        "My subscription": "我的订阅",
        "HTTPS URL (stored only in preview memory)": "HTTPS 地址（仅保存在预览内存中）",
        "Real subscriptions, credentials and tokens are not downloaded or saved.": "不会下载或保存真实订阅、凭据和令牌。",
        "Every 6 hours": "每 6 小时",
        "Every 12 hours": "每 12 小时",
        "Daily": "每天",
        "Weekly": "每周",
        "Off": "关闭",
        "STRATEGY PREVIEW": "策略预览",
        "Selection and fallback states are local UI data.": "选择与故障转移只影响本地界面。",
        "Test policies": "测试策略",
        "Add group": "添加策略组",
        "Selected strategy": "当前策略",
        "Group type: ": "策略组类型：",
        "Apply selection": "应用选择",
        "Filter groups": "筛选策略组",
        "POLICY GROUP": "策略组",
        "GROUP TYPE": "分组类型",
        "ACTIVE ROUTE": "当前线路",
        "Routing relationship": "路由关系",
        "↓     resolves to": "↓     解析至",
        "Choose endpoint": "选择节点",
        "View details": "查看详情",
        "Create policy group": "创建策略组",
        "Group name": "策略组名称",
        "My policy group": "我的策略组",
        "All types": "全部类型",
        "Manual Select": "手动选择",
        "Latency Test": "延迟测试",
        "Failover": "故障转移",
        "Load Balance": "负载均衡",
        "SYNTHETIC TRAFFIC": "模拟流量",
        "Aggregates are fixtures, not system counters": "统计数据来自演示，不是系统计数器",
        "Download": "下载",
        "Upload": "上传",
        "Domains": "域名",
        "Applications": "应用程序",
        "Transfer volume over time": "传输量变化",
        "● DOWN": "● 下载",
        "● UP": "● 上传",
        "Top consumers": "主要流量来源",
        "DESTINATION / OWNER": "目标 / 使用方",
        "Custom range": "自定义时间",
        "Nodes": "节点",
        "HTTPS inspection": "HTTPS 检查",
        "The switch previews the future MITM workflow. No root certificate is generated, installed, trusted or revoked.": "开关仅演示 HTTPS 检查流程，不生成、安装或信任根证书。",
        "LOCAL CA: NOT INSTALLED": "本地 CA：未安装",
        "TLS SESSIONS: 0 REAL": "真实 TLS 会话：0",
        "Preview decrypt toggle": "演示解密开关",
        "Certificate manager": "证书管理",
        "Add domain": "添加域名",
        "Filter host patterns": "筛选域名匹配规则",
        "HOST PATTERN": "域名匹配",
        "RULE": "规则",
        "ACTION": "操作",
        "No host patterns": "暂无域名匹配规则",
        "Try another filter, or add a demo domain": "调整筛选条件或添加演示域名",
        "Certificate & session": "证书与会话",
        "Trust certificate": "信任证书",
        "Revoke trust": "撤销信任",
        "CA certificate manager": "CA 证书管理",
        "NO CERTIFICATE MATERIAL AVAILABLE": "暂无证书材料",
        "In this UI-only build, Swirl does not generate certificates, access Windows certificate stores, or intercept HTTPS traffic. These buttons only demonstrate the future workflow.": "此版本仅包含界面，不生成证书、不访问 Windows 证书存储，也不会拦截 HTTPS 流量。",
        "Certificate preview": "证书预览",
        "Add HTTPS host pattern": "添加 HTTPS 域名规则",
        "Host pattern": "域名匹配表达式",
        "Only a local UI fixture will be added.": "仅添加本地演示数据。",
        "Included domains": "包含的域名",
        "Excluded domains": "排除的域名",
        "Include": "包含",
        "Exclude": "排除"
})
    function zh(value) {
        if (value === undefined || value === null) return ""
        var key = String(value)
        return Object.prototype.hasOwnProperty.call(zhDictionary,key) ? zhDictionary[key] : key
    }
    function page(id) {
        if(id==="external") return {id:"external",title:"外部工具",sub:"尚未接入外部程序"}
        for (var i=0;i<groups.length;++i)
            for (var j=0;j<groups[i].pages.length;++j)
                if (groups[i].pages[j].id === id) return groups[i].pages[j]
        return groups[0].pages[0]
    }
    function notice(label) { toast=label + " · 仅供界面演示，尚未连接内核" }
}
