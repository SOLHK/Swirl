import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property var selected:null
    property var viewRows:{
        var needle=search.text.toLowerCase()
        var country=region.currentText
        var list=demoProvider.nodes().filter(function(n){
            return n.name.toLowerCase().indexOf(needle)>=0 &&
                   (country==="All regions"||n.region===country)
        })
        list.sort(function(a,b){
            return sort.currentText==="Latency"?a.latency-b.latency:a.name.localeCompare(b.name)
        })
        return list
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:24; spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:110
            RowLayout {
                anchors.fill:parent; anchors.margins:20; spacing:18
                ColumnLayout {
                    Layout.fillWidth:true
                    Text { text:"Active proxy strategy"; color:Theme.muted; font.pixelSize:11 }
                    Text { text:AppState.policy; color:Theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
                    Text { text:"Selected endpoint: "+AppState.selectedNode; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlStatusBadge { label:"TEST NODES"; tone:"accent" }
                SwirlButton { text:"Test all"; iconName:"activity"; onClicked:AppState.notice("Latency test") }
                SwirlButton { text:"Add node"; primary:true; onClicked:addDialog.open() }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:9
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Find a node or region" }
            SwirlComboBox { id:region; model:["All regions","HK","SG","JP","US","KR","DE","TW","GB","AU"] }
            SwirlComboBox { id:sort; model:["Name","Latency"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.viewRows
                    selectedId:page.selected?page.selected.name:""
                    columns:[
                        {key:"name",label:"PROXY ENDPOINT",w:240},
                        {key:"region",label:"REGION",w:93},
                        {key:"protocol",label:"PROTOCOL",w:122},
                        {key:"latency",label:"LATENCY (ms)",w:115},
                        {key:"status",label:"HEALTH",w:132}
                    ]
                    onRowSelected:function(r){page.selected=r;AppState.selectedNode=r.name}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:280; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:19; spacing:16
                    Text { text:"Endpoint inspector"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlIcon { name:"globe"; size:45; color:Theme.accent; Layout.alignment:Qt.AlignHCenter }
                    Text {
                        Layout.fillWidth:true
                        text:page.selected?page.selected.name:AppState.selectedNode
                        color:Theme.text; font.pixelSize:19; font.weight:Font.DemiBold
                        horizontalAlignment:Text.AlignHCenter; wrapMode:Text.WordWrap
                    }
                    Text { text:"Synthetic node · No connection established"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; wrapMode:Text.WordWrap; horizontalAlignment:Text.AlignHCenter }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:"Protocol    "+(page.selected?page.selected.protocol:"Trojan"); color:Theme.muted }
                    Text { text:"Latency       "+(page.selected?page.selected.latency:"38")+" ms (demo)"; color:Theme.muted }
                    Text { text:"Strategy      "+AppState.policy; color:Theme.muted }
                    Item { Layout.fillHeight:true }
                    SwirlButton { Layout.fillWidth:true; text:"Select in demo"; primary:true; onClicked:AppState.notice("Select endpoint") }
                    SwirlButton { Layout.fillWidth:true; text:"Edit endpoint"; onClicked:addDialog.open() }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog
        title:"Add proxy endpoint"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Endpoint label"; color:Theme.muted }
            SwirlTextField { id:nodeName; Layout.fillWidth:true; placeholderText:"e.g. Singapore · 03" }
            Text { text:nodeName.text.trim().length===0?"Please enter a label":"UI-only preview: no configuration will be saved"; color:nodeName.text.trim().length===0?Theme.orange:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"Save demo"; primary:true; enabled:nodeName.text.trim().length>0
                    onClicked:{AppState.selectedNode=nodeName.text.trim();addDialog.close();AppState.notice("Save endpoint")}
                }
            }
        }
    }
}