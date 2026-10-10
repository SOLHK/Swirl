pragma Singleton
import QtQuick
QtObject {
    property string currentPage: "overview"
    property bool sidebarCollapsed: false
    property bool proxyOn: false
    property bool systemProxyOn: false
    property bool tunOn: false
    property bool detailOpen: true
    property string mode: "Rule"
    property string policy: "Auto Select"
    property string selectedNode: "Singapore · 01"
    property string toast: ""
    property bool demoLoading: false
    property bool demoError: false
    readonly property var groups: [
      {title:"CONTROL CENTER", pages:[
        {id:"overview",title:"Overview",icon:"home",sub:"Network at a glance"},
        {id:"dashboard",title:"Dashboard",icon:"chart",sub:"Metrics and history"},
        {id:"profiles",title:"Profiles",icon:"folder",sub:"Configurations and revisions"}]},
      {title:"PROXY & ROUTING", pages:[
        {id:"proxies",title:"Proxies",icon:"globe",sub:"Endpoints and health"},
        {id:"policies",title:"Policy Groups",icon:"layers",sub:"Routing strategies"},
        {id:"subscriptions",title:"Subscriptions",icon:"refresh",sub:"Remote providers"},
        {id:"rules",title:"Rules",icon:"list",sub:"Routing decisions"},
        {id:"dns",title:"DNS",icon:"server",sub:"Resolvers, hosts and queries"}]},
      {title:"INSPECTION",pages:[
        {id:"connections",title:"Connections",icon:"activity",sub:"Network sessions"},
        {id:"inspector",title:"HTTP Inspector",icon:"inspect",sub:"Requests and responses"},
        {id:"traffic",title:"Traffic Analytics",icon:"chart",sub:"Usage and distribution"},
        {id:"tls",title:"TLS / MITM",icon:"shield",sub:"HTTPS decryption controls"}]},
      {title:"DEBUGGING",pages:[
        {id:"rewrite",title:"Rewrite",icon:"edit",sub:"HTTP transformations"},
        {id:"map",title:"Map Local / Remote",icon:"route",sub:"Response mapping"},
        {id:"breakpoint",title:"HTTP Breakpoint",icon:"pause",sub:"Intercept and modify"},
        {id:"replay",title:"HTTP Replay",icon:"play",sub:"Replay requests"}]},
      {title:"AUTOMATION",pages:[
        {id:"scripts",title:"Scripts",icon:"code",sub:"JavaScript and console"},
        {id:"modules",title:"Modules",icon:"grid",sub:"Extensions and packages"},
        {id:"automation",title:"Automation",icon:"clock",sub:"Triggers and schedules"}]},
      {title:"TOOLS",pages:[
        {id:"toolbox",title:"Toolbox",icon:"tool",sub:"Network diagnostics"},
        {id:"api",title:"Local API / CLI",icon:"terminal",sub:"Developer integration"},
        {id:"gateway",title:"Gateway & Devices",icon:"network",sub:"LAN and network interfaces"}]},
      {title:"SYSTEM",pages:[
        {id:"logs",title:"Logs",icon:"list",sub:"Events and diagnostics"},
        {id:"settings",title:"Settings",icon:"settings",sub:"Appearance and preferences"}]}
    ]
    function page(id) {
        for (var i=0;i<groups.length;++i)
            for (var j=0;j<groups[i].pages.length;++j)
                if (groups[i].pages[j].id === id) return groups[i].pages[j]
        return groups[0].pages[0]
    }
    function notice(label) { toast=label + " · UI demo only, backend not connected" }
}