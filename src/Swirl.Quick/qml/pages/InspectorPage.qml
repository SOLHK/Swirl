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
        return (systemProvider.revision,systemProvider.requests()).filter(function(r){
            return (r.host+r.path+r.method).toLowerCase().indexOf(q)>=0 &&
                   (method==="全部方法"||r.method===method)
        })
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(13)
        RowLayout {
            Layout.fillWidth:true
            SwirlText { text:"此页为请求调试；查看真实会话请进入抓包。"; color:Theme.muted; font.pixelSize:Theme.fontSize(14); Layout.fillWidth:true }
            SwirlButton { text:"打开真实抓包"; iconName:"capture"; font.pixelSize:Theme.fontSize(15); onClicked:AppState.navigate("capture") }
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
            SwirlStatusBadge { label:"研发中"; tone:"accent" }
            SwirlText { text:displayRows.length+" 条本地"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Record"); iconName:"play"; onClicked:AppState.notice("抓包记录") }
            SwirlButton { text:AppState.zh("Clear"); onClicked:{selected=null;AppState.notice("清空抓包")} }
        }
        SplitView {
            Layout.fillWidth:true; Layout.fillHeight:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:Theme.dp(7); color:Theme.canvas; Rectangle { width:Theme.dp(2); height:Theme.dp(45); radius:Theme.roundedRadius(width,height); color:Theme.border; anchors.centerIn:parent } }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:Theme.dp(320)
                clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
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
                SplitView.preferredWidth:Theme.dp(440); SplitView.minimumWidth:Theme.dp(325)
                record:page.selected
            }
        }
        SwirlGlassPanel {
            visible:page.waterfallOpen
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(159)
            ColumnLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(12); spacing:Theme.dp(6)
                RowLayout {
                    Layout.fillWidth:true
                    SwirlText { text:AppState.zh("耗时明细尚未采集"); color:Theme.text; font.pixelSize:Theme.fontSize(13); font.weight:Font.DemiBold; Layout.fillWidth:true }
                    SwirlText { text:AppState.zh("0           100           200           300 ms"); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                }
                ListView { pixelAligned: true;
                    add: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";from:0;to:1;duration:SwirlMotion.duration} }
                    remove: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} }
                    move: Transition {enabled:!SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:!SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
                    Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:Theme.dp(3)
                    model:[]
                    delegate:RowLayout {
                        width:Math.floor(ListView.view.width); height:Theme.dp(20); spacing:Theme.dp(10)
                        SwirlText {
                            Layout.preferredWidth:Theme.dp(180)
                            text:modelData.method+" "+modelData.path
                            font.pixelSize:Theme.fontSize(10); color:Theme.muted; elide:Text.ElideRight
                        }
                        Item {
                            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(17)
                            Rectangle {
                                x:Math.round(parent.width*Number(modelData.waterfall)/100)
                                width:Math.round(Math.max(Theme.dp(6),Math.min(parent.width-x,parent.width*Number.parseInt(modelData.duration)/640)))
                                height:Theme.dp(12); radius:Theme.roundedRadius(width,height)
                                color:page.selected&&page.selected.id===modelData.id?Theme.green:Theme.accent
                                opacity:0.8
                            }
                        }
                        SwirlText { text:modelData.duration; Layout.preferredWidth:Theme.dp(54); font.pixelSize:Theme.fontSize(10); color:Theme.muted }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlButton {
                text:page.waterfallOpen?"隐藏瀑布图":"显示瀑布图"
                iconName:"chart"; quiet:false; onClicked:page.waterfallOpen=!page.waterfallOpen
            }
            SwirlText { text:"研发中"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Replay"); onClicked:AppState.currentPage="replay" }
            SwirlButton { text:AppState.zh("Breakpoint"); onClicked:AppState.currentPage="breakpoint" }
        }
    }
}
