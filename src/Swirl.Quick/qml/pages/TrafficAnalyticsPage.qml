import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string activeTab:"Domains"
    property var topDomains:[]
    property var apps:[]
    property var nodes:[]
    readonly property var selectedRows:activeTab==="Domains"?topDomains:activeTab==="Applications"?apps:nodes
    ScrollView {
        id:scroll
        anchors.fill:parent; anchors.leftMargin:Theme.dp(23); anchors.rightMargin:Theme.dp(23); clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth; spacing:Theme.dp(15)
            RowLayout {
                Layout.fillWidth:true
                SwirlStatusBadge { label:"尚未实现"; tone:"accent" }
                Text { text:"尚未实现"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                SwirlComboBox { model:["最近 1 小时","最近 24 小时","最近 7 天","最近 30 天","自定义时段"] }
                SwirlButton { enabled:false; text:AppState.zh("Export"); onClicked:AppState.notice("导出流量报告") }
            }
            GridLayout {
                columns:page.width>1080?4:2
                Layout.fillWidth:true; columnSpacing:13; rowSpacing:13
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Download"); value:"—"; secondary:"汇总"; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Upload"); value:"—"; secondary:"汇总"; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Domains"); value:"—"; secondary:"独立域名"; iconName:"globe" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Applications"); value:"—"; secondary:"来源"; iconName:"grid" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(305)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(19); spacing:Theme.dp(11)
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:AppState.zh("传输量趋势"); color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold; Layout.fillWidth:true }
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
                    SwirlButton { enabled:false; text:modelData; quiet:page.activeTab!==modelData; onClicked:page.activeTab=modelData }
                }
                Item { Layout.fillWidth:true }
                Text { text:AppState.zh("主要流量来源"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(295); clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.selectedRows
                    columns:[{key:"name",label:AppState.zh("DESTINATION / OWNER"),w:285},{key:"connections",label:AppState.zh("REQUESTS"),w:130},
                             {key:"upload",label:AppState.zh("UPLOAD"),w:142},{key:"download",label:AppState.zh("DOWNLOAD"),w:155}]
                    onRowSelected:function(r){AppState.notice("查看流量"+r.name)}
                }
            }
            Item { Layout.preferredHeight:Theme.dp(16) }
        }
    }
}
