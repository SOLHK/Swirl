import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string activeTab:"Domains"
    property var topDomains:[
        {id:"d1",name:"api.github.com",connections:"1,240",upload:"62 MB",download:"389 MB"},
        {id:"d2",name:"cdn.jsdelivr.net",connections:"986",upload:"34 MB",download:"270 MB"},
        {id:"d3",name:"www.microsoft.com",connections:"641",upload:"12 MB",download:"98 MB"},
        {id:"d4",name:"example.test",connections:"318",upload:"4 MB",download:"43 MB"}
    ]
    property var apps:[
        {id:"a1",name:"Browser",connections:"1,874",upload:"180 MB",download:"840 MB"},
        {id:"a2",name:"Code",connections:"492",upload:"84 MB",download:"420 MB"},
        {id:"a3",name:"Terminal",connections:"215",upload:"38 MB",download:"176 MB"}
    ]
    property var nodes:[
        {id:"n1",name:"新加坡 · 01",connections:"1,280",upload:"98 MB",download:"510 MB"},
        {id:"n2",name:"香港 · 01",connections:"837",upload:"40 MB",download:"279 MB"},
        {id:"n3",name:"东京 · 02",connections:"243",upload:"21 MB",download:"122 MB"}
    ]
    readonly property var selectedRows:activeTab==="Domains"?topDomains:activeTab==="Applications"?apps:nodes
    ScrollView {
        id:scroll
        anchors.fill:parent; anchors.leftMargin:23; anchors.rightMargin:23; clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth; spacing:15
            RowLayout {
                Layout.fillWidth:true
                SwirlStatusBadge { label:AppState.zh("SYNTHETIC TRAFFIC"); tone:"accent" }
                Text { text:AppState.zh("Aggregates are fixtures, not system counters"); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
                SwirlComboBox { model:["最近 1 小时","最近 24 小时","最近 7 天","最近 30 天","自定义时段"] }
                SwirlButton { text:AppState.zh("Export"); onClicked:AppState.notice("导出流量报告") }
            }
            GridLayout {
                columns:page.width>1080?4:2
                Layout.fillWidth:true; columnSpacing:13; rowSpacing:13
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Download"); value:"1.48 GB"; secondary:"模拟汇总"; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Upload"); value:"304 MB"; secondary:"模拟汇总"; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Domains"); value:"128"; secondary:"模拟独立域名"; iconName:"globe" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Applications"); value:"12"; secondary:"模拟流量来源"; iconName:"grid" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:305
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:19; spacing:11
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:AppState.zh("传输量趋势"); color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SwirlStatusBadge { label:AppState.zh("● DOWN"); tone:"accent" }
                        SwirlStatusBadge { label:AppState.zh("● UP"); tone:"success" }
                    }
                    SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
                }
            }
            RowLayout {
                Layout.fillWidth:true
                Repeater {
                    model:["Domains","Applications","Nodes"]
                    SwirlButton { text:modelData; quiet:page.activeTab!==modelData; onClicked:page.activeTab=modelData }
                }
                Item { Layout.fillWidth:true }
                Text { text:AppState.zh("主要流量来源"); color:Theme.muted; font.pixelSize:11 }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:295; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.selectedRows
                    columns:[{key:"name",label:AppState.zh("DESTINATION / OWNER"),w:285},{key:"connections",label:AppState.zh("REQUESTS"),w:130},
                             {key:"upload",label:AppState.zh("UPLOAD"),w:142},{key:"download",label:AppState.zh("DOWNLOAD"),w:155}]
                    onRowSelected:function(r){AppState.notice("查看流量"+r.name)}
                }
            }
            Item { Layout.preferredHeight:16 }
        }
    }
}