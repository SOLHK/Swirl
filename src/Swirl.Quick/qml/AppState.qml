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
    property string toast: ""
    property bool demoLoading: false
    property bool demoError: false
    property bool demoEmpty: false
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
    function page(id) {
        for (var i=0;i<groups.length;++i)
            for (var j=0;j<groups[i].pages.length;++j)
                if (groups[i].pages[j].id === id) return groups[i].pages[j]
        return groups[0].pages[0]
    }
    function notice(label) { toast=label + " · 仅供界面演示，尚未连接内核" }
}