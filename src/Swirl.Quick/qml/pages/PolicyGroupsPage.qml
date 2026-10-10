import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string chosen:"Auto Select"
    property var groups:[
        {id:"g1",name:"Auto Select",type:"Latency Test",current:"Singapore · 01",health:"Healthy"},
        {id:"g2",name:"Global",type:"Manual Select",current:"Hong Kong · 01",health:"Healthy"},
        {id:"g3",name:"Fallback",type:"Failover",current:"Tokyo · 01",health:"Healthy"},
        {id:"g4",name:"Balance",type:"Load Balance",current:"Round Robin",health:"Healthy"},
        {id:"g5",name:"Office Wi-Fi",type:"SSID",current:"DIRECT",health:"Idle"}
    ]
    readonly property var active:groups.find(function(g){return g.name===page.chosen})||groups[0]
    readonly property var showing:groups.filter(function(g){return (g.name+" "+g.type).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"STRATEGY PREVIEW"; tone:"accent" }
            Text { text:"Selection and fallback states are local UI data."; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Test policies"; onClicked:AppState.notice("Policy group latency test") }
            SwirlButton { text:"Add group"; primary:true; onClicked:addDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:120
            RowLayout {
                anchors.fill:parent; anchors.margins:19; spacing:19
                SwirlIcon { name:"layers"; size:36; color:Theme.accent }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:"Selected strategy"; color:Theme.muted; font.pixelSize:11 }
                    Text { text:page.chosen; color:Theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
                    Text { text:"Group type: "+page.active.type+"  ·  Active preview node: "+page.active.current; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlButton { text:"Apply selection"; primary:true; onClicked:{AppState.policy=page.chosen;AppState.notice("Selected policy group")} }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:11
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Filter groups" }
            SwirlComboBox { model:["All types","Manual Select","Latency Test","Failover","Load Balance","SSID"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.showing
                    selectedId:page.active.id
                    columns:[{key:"name",label:"POLICY GROUP",w:193},{key:"type",label:"GROUP TYPE",w:163},
                             {key:"current",label:"ACTIVE ROUTE",w:195},{key:"health",label:"STATE",w:100}]
                    onRowSelected:function(r){page.chosen=r.name}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:309; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:"Routing relationship"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.active.type.toUpperCase(); tone:"accent" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.preferredHeight:68; radius:11
                        color:Theme.selected; border.color:Theme.border
                        Text { anchors.centerIn:parent; text:page.active.name; color:Theme.accent; font.pixelSize:15; font.weight:Font.DemiBold }
                    }
                    Text { text:"↓   resolves to"; color:Theme.muted; Layout.alignment:Qt.AlignHCenter; font.pixelSize:11 }
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
                        text:page.active.type==="Load Balance"?"Round robin among healthy sample nodes":
                             page.active.type==="Failover"?"Use next healthy route after failure":
                             page.active.type==="SSID"?"Route based on currently matched network name":
                             page.active.type==="Latency Test"?"Choose lowest synthetic latency endpoint":"Manual node selection"
                        color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Choose endpoint"; onClicked:AppState.currentPage="proxies" }
                    SwirlButton { text:"View details"; onClicked:AppState.notice("Policy relationship details") }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"Create policy group"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Group name"; color:Theme.text }
            SwirlTextField { id:groupName; Layout.fillWidth:true; placeholderText:"My policy group" }
            SwirlComboBox { id:groupType; Layout.fillWidth:true; model:["Manual Select","Latency Test","Failover","Load Balance","SSID"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"Add demo"; primary:true; enabled:groupName.text.trim().length>0
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