import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string chosen: ""
    property var groups:[]
    readonly property var active:groups.find(function(g){return g.name===page.chosen})||({id:"",name:"未配置",type:"尚未实现",current:"—",health:"未检测"})
    readonly property var showing:groups.filter(function(g){return (g.name+" "+g.type).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"尚未实现"; tone:"accent" }
            Text { text:"策略组尚未实现。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("Test policies"); onClicked:AppState.notice("策略组延迟测试") }
            SwirlButton { enabled:false; text:AppState.zh("Add group"); primary:true; onClicked:addDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(120)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(19); spacing:Theme.dp(19)
                SwirlIcon { name:"layers"; size:Theme.dp(36); color:Theme.accent }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(6)
                    Text { text:AppState.zh("Selected strategy"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    Text { text:page.chosen; color:Theme.text; font.pixelSize:Theme.fontSize(22); font.weight:Font.DemiBold }
                    Text { text:AppState.zh("策略组类型：")+page.active.type+"  ·  当前节点："+page.active.current; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                SwirlButton { enabled:false; text:AppState.zh("Apply selection"); primary:true; onClicked:AppState.notice("尚未实现") }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(11)
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Filter groups") }
            SwirlComboBox { model:["All types","手动选择","延迟测试","Failover","负载均衡","SSID"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.showing
                    selectedId:page.active.id
                    columns:[{key:"name",label:AppState.zh("POLICY GROUP"),w:193},{key:"type",label:AppState.zh("GROUP TYPE"),w:163},
                             {key:"current",label:AppState.zh("ACTIVE ROUTE"),w:195},{key:"health",label:AppState.zh("状态"),w:100}]
                    onRowSelected:function(r){page.chosen=r.name}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(309); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(14)
                    Text { text:AppState.zh("Routing relationship"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.active.type.toUpperCase(); tone:"accent" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(68); radius:Theme.roundedRadius(width,height)
                        color:Theme.selected; border.color:Theme.border
                        Text { anchors.centerIn:parent; text:page.active.name; color:Theme.accent; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold }
                    }
                    Text { text:AppState.zh("↓ 当前使用"); color:Theme.muted; Layout.alignment:Qt.AlignHCenter; font.pixelSize:Theme.fontSize(11) }
                    Rectangle {
                        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(68); radius:Theme.roundedRadius(width,height)
                        color:Theme.field; border.color:Theme.border
                        RowLayout {
                            anchors.centerIn:parent; spacing:Theme.dp(7)
                            SwirlIcon { name:"globe"; size:Theme.dp(18); color:Theme.green }
                            Text { text:page.active.current; color:Theme.text; font.pixelSize:Theme.fontSize(14) }
                        }
                    }
                    Text {
                        text:page.active.type==="负载均衡"?"在可用的节点间轮询":
                             page.active.type==="Failover"?"故障后切换下一条可用线路":
                             page.active.type==="SSID"?"按照当前网络名称选择路由":
                             page.active.type==="延迟测试"?"选择延迟最低的节点":"手动选择节点"
                        color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("Choose endpoint"); onClicked:AppState.currentPage="proxies" }
                    SwirlButton { enabled:false; text:AppState.zh("View details"); onClicked:AppState.notice("策略关系详情") }

                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"创建策略组"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:AppState.zh("Group name"); color:Theme.text }
            SwirlTextField { id:groupName; Layout.fillWidth:true; placeholderText:AppState.zh("My policy group") }
            SwirlComboBox { id:groupType; Layout.fillWidth:true; model:["手动选择","延迟测试","Failover","负载均衡","SSID"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("取消"); onClicked:addDialog.close() }
                SwirlButton { enabled:false;
                    text:"尚未实现"; primary:true;
                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
