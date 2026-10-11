import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string chosen:"自动选择"
    property var groups:[
        {id:"g1",name:"自动选择",type:"延迟测试",current:"新加坡 · 01",health:"Healthy"},
        {id:"g2",name:"Global",type:"手动选择",current:"香港 · 01",health:"Healthy"},
        {id:"g3",name:"Fallback",type:"Failover",current:"东京 · 01",health:"Healthy"},
        {id:"g4",name:"Balance",type:"负载均衡",current:"轮询",health:"Healthy"},
        {id:"g5",name:"办公 Wi-Fi",type:"SSID",current:"DIRECT",health:"Idle"}
    ]
    readonly property var active:groups.find(function(g){return g.name===page.chosen})||groups[0]
    readonly property var showing:groups.filter(function(g){return (g.name+" "+g.type).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("STRATEGY PREVIEW"); tone:"accent" }
            Text { text:AppState.zh("Selection and fallback states are local UI data."); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Test policies"); onClicked:AppState.notice("策略组延迟测试") }
            SwirlButton { text:AppState.zh("Add group"); primary:true; onClicked:addDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:120
            RowLayout {
                anchors.fill:parent; anchors.margins:19; spacing:19
                SwirlIcon { name:"layers"; size:36; color:Theme.accent }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:AppState.zh("Selected strategy"); color:Theme.muted; font.pixelSize:11 }
                    Text { text:page.chosen; color:Theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
                    Text { text:AppState.zh("策略组类型：")+page.active.type+"  ·  当前演示节点："+page.active.current; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlButton { text:AppState.zh("Apply selection"); primary:true; onClicked:{AppState.policy=page.chosen;AppState.notice("已选择策略组")} }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:11
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Filter groups") }
            SwirlComboBox { model:["All types","手动选择","延迟测试","Failover","负载均衡","SSID"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.showing
                    selectedId:page.active.id
                    columns:[{key:"name",label:AppState.zh("POLICY GROUP"),w:193},{key:"type",label:AppState.zh("GROUP TYPE"),w:163},
                             {key:"current",label:AppState.zh("ACTIVE ROUTE"),w:195},{key:"health",label:AppState.zh("状态"),w:100}]
                    onRowSelected:function(r){page.chosen=r.name}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:309; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:AppState.zh("Routing relationship"); color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.active.type.toUpperCase(); tone:"accent" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.preferredHeight:68; radius:11
                        color:Theme.selected; border.color:Theme.border
                        Text { anchors.centerIn:parent; text:page.active.name; color:Theme.accent; font.pixelSize:15; font.weight:Font.DemiBold }
                    }
                    Text { text:AppState.zh("↓   resolves to"); color:Theme.muted; Layout.alignment:Qt.AlignHCenter; font.pixelSize:11 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.preferredHeight:68; radius:11
                        color:Theme.field; border.color:Theme.border
                        RowLayout {
                            anchors.centerIn:parent; spacing:7
                            SwirlIcon { name:"globe"; size:18; color:Theme.green }
                            Text { text:page.active.current; color:Theme.text; font.pixelSize:14 }
                        }
                    }
                    Text {
                        text:page.active.type==="负载均衡"?"在可用的模拟节点间轮询":
                             page.active.type==="Failover"?"故障后切换下一条可用线路":
                             page.active.type==="SSID"?"按照当前网络名称选择路由":
                             page.active.type==="延迟测试"?"选择模拟延迟最低的节点":"手动选择节点"
                        color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:AppState.zh("Choose endpoint"); onClicked:AppState.currentPage="proxies" }
                    SwirlButton { text:AppState.zh("View details"); onClicked:AppState.notice("策略关系详情") }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"创建策略组"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:AppState.zh("Group name"); color:Theme.text }
            SwirlTextField { id:groupName; Layout.fillWidth:true; placeholderText:AppState.zh("My policy group") }
            SwirlComboBox { id:groupType; Layout.fillWidth:true; model:["手动选择","延迟测试","Failover","负载均衡","SSID"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("取消"); onClicked:addDialog.close() }
                SwirlButton {
                    text:AppState.zh("Add demo"); primary:true; enabled:groupName.text.trim().length>0
                    onClicked:{
                        page.groups=page.groups.concat([{id:"g"+Date.now(),name:groupName.text.trim(),
                            type:groupType.currentText,current:"DIRECT",health:"Idle"}])
                        page.chosen=groupName.text.trim()
                        groupName.text="";addDialog.close()
                    }
                }
            }
        }
    }
}