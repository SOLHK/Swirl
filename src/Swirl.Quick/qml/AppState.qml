pragma Singleton
import QtQuick
QtObject {
    property string currentPage: "overview"
    property bool sidebarCollapsed: false
    readonly property string connectionState: engineController.stateText
    readonly property bool proxyOn: engineController.requestSucceeded
    readonly property bool systemProxyOn: false
    readonly property bool tunOn: false
    property bool detailOpen: true
    readonly property string mode: engineController.activeNodeId.length?"固定节点":"直连"
    readonly property string policy: "固定节点"
    readonly property string selectedNode: engineController.selectedNodeName
    readonly property string selectedNodeRegion: "—"
    readonly property string selectedNodeProtocol: "—"
    readonly property int selectedNodeLatency: -1
    function selectNode(node) { engineController.chooseNode(node.id) }
    property string toast: ""
    property bool loading: false
    property bool hasError: false
    property bool empty: false
    property bool autoSwitch: false
    property int historyIndex: 0
    property var navigationHistory: ["overview"]
    property date sessionNow: new Date()
    property var recentEvents: []
    property real measuredDown: 0
    property real measuredUp: 0
    property int measuredConnections: 0
    property int measurementTick: 0
    readonly property real totalGB: 0
    readonly property var navigationGroups: [
        {title:"",pages:[{id:"overview",title:"总览",icon:"home"},{id:"proxies",title:"代理节点",icon:"pin"},{id:"policies",title:"策略组",icon:"layers"},{id:"rules",title:"规则",icon:"document"},{id:"subscriptions",title:"订阅管理",icon:"refresh"},{id:"profiles",title:"配置文件",icon:"file"}]},
        {title:"网络",pages:[{id:"dns",title:"DNS",icon:"globe"},{id:"toolbox",title:"网络检测",icon:"gauge"},{id:"connections",title:"连接记录",icon:"clock"}]},
        {title:"分析与调试",pages:[{id:"inspector",title:"HTTP 检查器",icon:"code"},{id:"traffic",title:"流量分析",icon:"bars"},{id:"processes",title:"进程",icon:"sliders"},{id:"gateway",title:"设备",icon:"calendar"},{id:"requestlogs",title:"请求日志",icon:"help"},{id:"tls",title:"HTTPS 解密",icon:"shield"},{id:"rewrite",title:"重写",icon:"route"}]}
    ]
    readonly property var allPageIds: groups.reduce(function(all,g){return all.concat(g.pages.map(function(p){return p.id}))},[]).concat(["featurehub","external","processes","requestlogs"]).concat(FeatureCatalog.entries.filter(function(f){return f.id.indexOf("feature-")===0}).map(function(f){return f.id}))
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
    function initializeHistory() { recentEvents=[]; sessionNow=new Date() }
    function setConnection(on) { if(on)engineController.connectNode(engineController.selectedNodeId);else engineController.disconnectNode() }
    function tickTraffic() { sessionNow=new Date() }
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
        "Download and upload · local representative series": "上传与下载 · 本地趋势",
        "● DOWNLOAD": "● 下载",
        "● UPLOAD": "● 上传",
        "Top destinations": "热门目的地",
        "Open connections": "查看连接",
        "DOMAIN": "域名",
        "REQUESTS": "请求数",
        "Traffic distribution": "流量分布",
        "Protocol percentages are illustrative.": "协议占比为。",
        "Last hour": "最近 1 小时",
        "24 hours": "最近 24 小时",
        "7 days": "最近 7 天",
        "30 days": "最近 30 天",
        "Import": "导入",
        "New profile": "新建配置",
        "CURRENT PREVIEW CONFIGURATION": "当前配置",
        "Manual selection · no network engine initialized": "手动选择 · 网络内核尚未启动",
        "LOCAL FIXTURE": "本地",
        "Validate": "检查配置",
        "Update remote": "更新远程配置",
        "Search profiles and sources": "搜索配置和订阅来源",
        "PROFILE NAME": "配置名称",
        "SOURCE": "来源",
        "VERSION": "版本",
        "UPDATED": "更新时间",
        "Save preview": "保存预览",
        "Compare": "对比",
        "Restore": "恢复",
        "Profile summary": "配置摘要",
        "Use profile in UI": "使用配置",
        "View editor": "查看编辑器",
        "Create configuration preview": "新建配置预览",
        "Name": "名称",
        "New profile name": "新配置名称",
        "Cancel": "取消",
        "Configurations": "配置列表",
        "Editor": "编辑器",
        "Version history": "历史版本",
        "Backups": "备份",
        "All sources": "全部来源",
        "Local": "本地",
        "Remote": "远程",
        "Active proxy strategy": "当前代理策略",
        "Selected endpoint: ": "当前节点：",
        "TEST NODES": "节点",
        "Test all": "全部测速",
        "Add node": "添加节点",
        "Find a node or region": "搜索节点或地区",
        "PROXY ENDPOINT": "代理节点",
        "REGION": "地区",
        "PROTOCOL": "协议",
        "LATENCY (ms)": "延迟（毫秒）",
        "HEALTH": "健康状态",
        "Endpoint inspector": "节点详情",
        "Protocol        ": "协议　",
        "Latency             ": "延迟　",
        "Strategy            ": "策略　",
        "Edit endpoint": "编辑节点",
        "Add proxy endpoint": "添加代理节点",
        "Endpoint label": "节点名称",
        "e.g. Singapore · 03": "例如：新加坡 · 03",
        "All regions": "全部地区",
        "Appearance": "外观",
        "Personalize how Swirl looks and behaves": "自定义 Swirl 的外观与使用方式",
        "LOCAL UI PREFERENCES": "仅本地界面设置",
        "PREFERENCES": "偏好设置",
        "Color theme": "界面主题",
        "Choose light, dark or follow Windows": "选择浅色、深色或跟随 Windows",
        "Windows backdrop material": "侧栏透明材质",
        "Uses DWM on supported Windows 11 systems": "保留柔和透明的侧栏背景",
        "Reduce motion": "减少动画",
        "Disable most transition animations": "减少界面切换动画",
        "Interface scale": "界面缩放",
        "CHANGES ARE LOCAL TO THIS UI PREVIEW": "界面偏好自动保存",
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
        "Record": "记录",
        "METHOD": "方法",
        "STATUS": "状态码",
        "PATH / QUERY": "路径 / 查询",
        "HTTP": "HTTP 版本",
        "TIME": "耗时",
        "SIZE": "大小",
        "Request waterfall": "请求瀑布图",
        "Replay": "重放",
        "Breakpoint": "断点",
        "All methods": "全部方法",
        "Test Resolver": "测试解析器",
        "Primary resolver": "首选解析器",
        "DoH · DNSSEC option · synthetic endpoint": "DoH · DNSSEC 选项 · 解析地址",
        "Protocols enabled": "启用协议",
        "IPv4 + IPv6 · Fake-IP Preview": "IPv4 + IPv6 · 虚拟 IP 预览",
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
        "Edit DNS mapping": "编辑 DNS 映射",
        "Hostname": "主机名",
        "Target / answer": "目标地址 / 解析结果",
        "Query Log": "查询记录",
        "Resolvers": "解析器",
        "Hosts": "Hosts 映射",
        "Cache": "缓存",
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
        "Demo evaluator only.\\nNo real DNS lookup or proxy routing occurs.": "仅执行匹配。\\n不会实际解析 DNS 或转发流量。",
        "Close": "关闭",
        "Evaluate": "开始测试",
        "All policies": "全部策略",
        "No remote URLs are requested or saved.": "不会访问或保存远程 URL。",
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
        "Selection and fallback states are local UI data.": "按策略选择出站节点。",
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
        "SYNTHETIC TRAFFIC": "",
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
        "The switch previews the future MITM workflow. No root certificate is generated, installed, trusted or revoked.": "开关仅 HTTPS 检查流程，不生成、安装或信任根证书。",
        "LOCAL CA: NOT INSTALLED": "本地 CA：未安装",
        "TLS SESSIONS: 0 REAL": "真实 TLS 会话：0",
        "Preview decrypt toggle": "解密开关",
        "Certificate manager": "证书管理",
        "Add domain": "添加域名",
        "Filter host patterns": "筛选域名匹配规则",
        "HOST PATTERN": "域名匹配",
        "RULE": "规则",
        "ACTION": "操作",
        "No host patterns": "暂无域名匹配规则",
        "Certificate & session": "证书与会话",
        "Trust certificate": "信任证书",
        "Revoke trust": "撤销信任",
        "CA certificate manager": "CA 证书管理",
        "NO CERTIFICATE MATERIAL AVAILABLE": "暂无证书材料",
        "Certificate preview": "证书预览",
        "Add HTTPS host pattern": "添加 HTTPS 域名规则",
        "Host pattern": "域名匹配表达式",
        "Included domains": "包含的域名",
        "Excluded domains": "排除的域名",
        "Include": "包含",
        "Exclude": "排除"
})
    function zh(value) {
        if (value === undefined || value === null) return ""
        var key = String(value)
        var labels={"Installed":"已安装","Marketplace":"扩展市场","Updates":"更新","VERSION":"版本","AUTHOR":"作者","ENABLED":"已启用","UPDATE":"更新时间","View":"查看","Details":"详情","Redirect":"重定向","Reject":"拒绝","Permissions":"权限","Planned":"待接入","Tasks":"任务","History":"历史记录","Conditions":"条件","Schedule":"定时","Interval":"周期","Daily":"每天","Weekly":"每周","On network change":"网络变化时","Destination":"目标地址","Protocol":"协议","Established":"已建立","TYPE":"类型","HTTP Response":"HTTP 响应","HTTP Request":"HTTP 请求","Trigger":"触发条件","Type":"类型","Status":"状态","Select":"手动选择","UrlTest":"延迟测试","LoadBalance":"负载均衡","DOMAIN SET":"域名集合","RULE SET":"规则集","http-request":"HTTP 请求","http-response":"HTTP 响应","Preview":"预览","Raw":"原始内容","Application":"应用程序","APPLICATION":"应用程序","RCODE":"返回码","NOERROR":"正常","BLOCKED":"已阻止","NXDOMAIN":"域名不存在","JP":"日本","HK":"香港","SG":"新加坡","US":"美国","KR":"韩国","DE":"德国","TW":"台湾","GB":"英国","AU":"澳大利亚","Healthy":"正常","Idle":"空闲","Active":"使用中","Available":"可用","Enabled":"已启用","Disabled":"已禁用","Today":"今天","Never":"从未","Current":"最新","STATUS":"状态","NODES":"节点数","SELECTED":"当前选择","FORMAT":"格式","POLICY GROUPS":"策略组","PROXY NODES":"代理节点","RULES":"规则","SOURCE":"来源","TIME":"时间","COMPONENT":"组件","MESSAGE":"信息","MATCHER":"匹配类型","PATTERN":"匹配条件","STRATEGY":"策略","PRIORITY":"优先级","Core":"内核","Rules":"规则","INFO":"信息","DEBUG":"调试","WARN":"警告","ERROR":"错误","Failover":"故障转移","DIRECT":"直连","Global":"全局","Fallback":"故障转移","Balance":"负载均衡","Automatic":"自动","Request":"请求","Response":"响应","Headers":"标头","Body":"正文","Cookies":"Cookie","Query":"查询参数","Timeline":"时间线","Copy":"复制","All sources":"全部来源","Configurations":"配置列表","Editor":"编辑器","Backups":"备份"}
        if(Object.prototype.hasOwnProperty.call(labels,key))return labels[key]
        var result=Object.prototype.hasOwnProperty.call(zhDictionary,key) ? zhDictionary[key] : key
        return result.replace(/\s*\(sample\)/g,"").replace(/\s*·\s*$/g,"")
    }
    function page(id) {
        if(id==="processes")return {id:id,title:"进程",sub:"进程流量"}
        if(id==="requestlogs")return {id:id,title:"请求日志",sub:"请求历史"}
        if(id==="featurehub") return {id:id,title:"功能模块中心",sub:"全部功能与配置草稿"}
        var feature=FeatureCatalog.find(id); if(feature)return feature
        if(id==="external") return {id:"external",title:"外部工具",sub:"尚未接入外部程序"}
        for (var i=0;i<groups.length;++i)
            for (var j=0;j<groups[i].pages.length;++j)
                if (groups[i].pages[j].id === id) return groups[i].pages[j]
        return groups[0].pages[0]
    }
    function notice(label) { toast=label+" · 尚未实现" }
}
