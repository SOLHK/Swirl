import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property var selected:null
    property bool waterfallOpen:true
    property var displayRows:{
        var q=search.text.toLowerCase()
        var method=methodFilter.currentText
        return demoProvider.requests().filter(function(r){
            return (r.host+r.path+r.method).toLowerCase().indexOf(q)>=0 &&
                   (method==="All methods"||r.method===method)
        })
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:13
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Search URL, path, or request method" }
            SwirlComboBox { id:methodFilter; model:["All methods","GET","POST","PUT","DELETE"] }
            SwirlButton { text:"Import HAR"; iconName:"folder"; onClicked:AppState.notice("HAR import") }
            SwirlButton { text:"Export HAR"; onClicked:AppState.notice("HAR export") }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"HTTP CAPTURE DEMO"; tone:"accent" }
            Text { text:displayRows.length+" local fixtures"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Record"; iconName:"play"; onClicked:AppState.notice("Capture recording") }
            SwirlButton { text:"Clear"; onClicked:{selected=null;AppState.notice("Clear capture")} }
        }
        SplitView {
            Layout.fillWidth:true; Layout.fillHeight:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:7; color:Theme.canvas; Rectangle { width:2; height:45; radius:1; color:Theme.border; anchors.centerIn:parent } }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:320
                clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.displayRows
                    selectedId:page.selected?page.selected.id:""
                    columns:[
                        {key:"method",label:"METHOD",w:83},{key:"status",label:"STATUS",w:78},
                        {key:"host",label:"HOST",w:174},{key:"path",label:"PATH / QUERY",w:260},
                        {key:"version",label:"HTTP",w:94},{key:"duration",label:"TIME",w:92},
                        {key:"size",label:"SIZE",w:78}
                    ]
                    onRowSelected:function(r){page.selected=r}
                }
            }
            SwirlInspectorPanel {
                SplitView.preferredWidth:440; SplitView.minimumWidth:325
                record:page.selected
            }
        }
        SwirlGlassPanel {
            visible:page.waterfallOpen
            Layout.fillWidth:true; Layout.preferredHeight:159
            ColumnLayout {
                anchors.fill:parent; anchors.margins:12; spacing:6
                RowLayout {
                    Layout.fillWidth:true
                    Text { text:"Request waterfall"; color:Theme.text; font.pixelSize:13; font.weight:Font.DemiBold; Layout.fillWidth:true }
                    Text { text:"0           100           200           300 ms"; color:Theme.muted; font.pixelSize:10 }
                }
                ListView {
                    Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:3
                    model:page.displayRows.slice(0,5)
                    delegate:RowLayout {
                        width:ListView.view.width; height:20; spacing:10
                        Text {
                            Layout.preferredWidth:180
                            text:modelData.method+" "+modelData.path
                            font.pixelSize:10; color:Theme.muted; elide:Text.ElideRight
                        }
                        Item {
                            Layout.fillWidth:true; height:17
                            Rectangle {
                                x:parent.width*Number(modelData.waterfall)/100
                                width:Math.max(6,Math.min(parent.width-x,parent.width*Number.parseInt(modelData.duration)/640))
                                height:12; radius:3
                                color:page.selected&&page.selected.id===modelData.id?Theme.green:Theme.accent
                                opacity:0.8
                            }
                        }
                        Text { text:modelData.duration; Layout.preferredWidth:54; font.pixelSize:10; color:Theme.muted }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlButton {
                text:page.waterfallOpen?"Hide waterfall":"Show waterfall"
                iconName:"chart"; quiet:true; onClicked:page.waterfallOpen=!page.waterfallOpen
            }
            Text { text:"Synthetic timing breakdown · select a request for full details"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
            SwirlButton { text:"Replay"; onClicked:AppState.currentPage="replay" }
            SwirlButton { text:"Breakpoint"; onClicked:AppState.currentPage="breakpoint" }
        }
    }
}