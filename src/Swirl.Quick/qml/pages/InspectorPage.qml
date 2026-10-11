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
                   (method==="全部方法"||r.method===method)
        })
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:13
        RowLayout {
            Layout.fillWidth:true
            Text { text:"此页为请求调试演示；查看真实会话请进入抓包。"; color:Theme.muted; font.pixelSize:14; Layout.fillWidth:true }
            SwirlButton { text:"打开真实抓包"; iconName:"capture"; font.pixelSize:15; onClicked:AppState.navigate("capture") }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search URL, path, or request method") }
            SwirlComboBox { id:methodFilter; model:["全部方法","GET","POST","PUT","DELETE"] }
            SwirlButton { text:AppState.zh("Import HAR"); iconName:"folder"; onClicked:AppState.notice("HAR import") }
            SwirlButton { text:AppState.zh("Export HAR"); onClicked:AppState.notice("HAR export") }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("HTTP CAPTURE DEMO"); tone:"accent" }
            Text { text:displayRows.length+" 条本地示例"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Record"); iconName:"play"; onClicked:AppState.notice("抓包记录") }
            SwirlButton { text:AppState.zh("Clear"); onClicked:{selected=null;AppState.notice("清空抓包")} }
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
                        {key:"method",label:AppState.zh("METHOD"),w:83},{key:"status",label:AppState.zh("STATUS"),w:78},
                        {key:"host",label:AppState.zh("HOST"),w:174},{key:"path",label:AppState.zh("PATH / QUERY"),w:260},
                        {key:"version",label:AppState.zh("HTTP"),w:94},{key:"duration",label:AppState.zh("时间"),w:92},
                        {key:"size",label:AppState.zh("SIZE"),w:78}
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
                    Text { text:AppState.zh("Request waterfall"); color:Theme.text; font.pixelSize:13; font.weight:Font.DemiBold; Layout.fillWidth:true }
                    Text { text:AppState.zh("0           100           200           300 ms"); color:Theme.muted; font.pixelSize:10 }
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
                text:page.waterfallOpen?"隐藏瀑布图":"显示瀑布图"
                iconName:"chart"; quiet:true; onClicked:page.waterfallOpen=!page.waterfallOpen
            }
            Text { text:AppState.zh("Synthetic timing breakdown · select a request for full details"); color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Replay"); onClicked:AppState.currentPage="replay" }
            SwirlButton { text:AppState.zh("Breakpoint"); onClicked:AppState.currentPage="breakpoint" }
        }
    }
}
