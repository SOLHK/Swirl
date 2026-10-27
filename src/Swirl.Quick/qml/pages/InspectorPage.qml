import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property var selected:null
    readonly property bool compact:workspace.width<Theme.dp(680)
    property bool waterfallOpen:true
    property bool componentReady:false
    SwirlTransitionCoordinator{id:waterfallMotion;progress:1;destination:1}
    onWaterfallOpenChanged:if(componentReady)waterfallMotion.moveTo(waterfallOpen?1:0)
    Component.onCompleted:componentReady=true
    Connections{target:page.componentReady?page:null;function onVisibleChanged(){if(!page.visible)waterfallMotion.finish()}}
    property var displayRows:{
        var q=search.text.toLowerCase()
        var method=methodFilter.currentText
        return (systemProvider.revision,systemProvider.requests()).filter(function(r){
            return (r.host+r.path+r.method).toLowerCase().indexOf(q)>=0 &&
                   (method==="全部方法"||r.method===method)
        })
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.pagePadding; spacing:Theme.sectionGap
        SwirlPageHeader{Layout.fillWidth:true;title:qsTr("请求检查器");description:qsTr("查看本地调试记录；真实 HTTP 会话请进入抓包面板。")
            SwirlButton{text:qsTr("打开真实抓包");iconName:"capture";primary:true;onClicked:AppState.navigate("capture")}
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; Layout.minimumWidth:0; placeholderText:AppState.zh("Search URL, path, or request method") }
            SwirlComboBox { id:methodFilter; Layout.preferredWidth:Theme.dp(140); model:["全部方法","GET","POST","PUT","DELETE"] }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"研发中"; tone:"accent" }
            SwirlText { text:displayRows.length+" 条本地"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { development:true;enabled:false;text:AppState.zh("Record"); iconName:"play"; onClicked:AppState.notice("抓包记录") }
            SwirlButton { objectName:"inspectorClearSelection";text:qsTr("取消选择");enabled:page.selected!==null;onClicked:page.selected=null }
        }
        SplitView {
            id:workspace;objectName:"inspectorWorkspace"
            Layout.fillWidth:true; Layout.fillHeight:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:Theme.dp(7); color:Theme.canvas; Rectangle { width:Theme.dp(2); height:Theme.dp(45); radius:Theme.roundedRadius(width,height); color:Theme.border; anchors.centerIn:parent } }
            SwirlGlassPanel {
                objectName:"inspectorListSurface"
                visible:!page.compact||page.selected===null
                SplitView.fillWidth:true; SplitView.minimumWidth:page.compact?0:Theme.dp(320)
                clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.displayRows;fillEmptyRows:false
                    selectedId:page.selected?page.selected.id:""
                    columns:[
                        {key:"method",label:AppState.zh("METHOD"),w:83},{key:"status",label:AppState.zh("STATUS"),w:78},
                        {key:"host",label:AppState.zh("HOST"),w:174},{key:"path",label:AppState.zh("PATH / QUERY"),w:260},
                        {key:"version",label:AppState.zh("HTTP"),w:94},{key:"duration",label:AppState.zh("时间"),w:92},
                        {key:"size",label:AppState.zh("SIZE"),w:78}
                    ]
                    onRowSelected:function(r){page.selected=r}
                }
                SwirlEmptyState { anchors.centerIn:parent; width:Math.max(0,parent.width-Theme.dp(28)); visible:page.displayRows.length===0; headline:qsTr("暂无本地请求"); detail:qsTr("通过抓包面板查看真实会话，或调整现有筛选。") }
            }
            SwirlInspectorPanel {
                objectName:"inspectorDetails"
                visible:page.selected!==null
                SplitView.fillWidth:page.compact
                SplitView.preferredWidth:page.compact?workspace.width:Theme.dp(440); SplitView.minimumWidth:page.compact?0:Theme.dp(325)
                record:page.selected
            }
        }
        SwirlGlassPanel {
            visible:page.waterfallOpen||waterfallMotion.moving
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(96)*waterfallMotion.progress;clip:true
            ColumnLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(12); spacing:Theme.dp(6)
                transform:Translate{y:-SwirlMotion.pageArc*(1-waterfallMotion.progress)}
                RowLayout {
                    Layout.fillWidth:true
                    SwirlText { text:AppState.zh("耗时明细尚未采集"); color:Theme.text; font.pixelSize:Theme.fontSize(13); font.weight:Font.DemiBold; Layout.fillWidth:true }
                }
                SwirlText{Layout.fillWidth:true;Layout.fillHeight:true;wrapMode:Text.Wrap;text:qsTr("当前请求来源未提供连接、TLS 与传输阶段的独立耗时。");color:Theme.muted;font.pixelSize:Theme.captionSize}

            }
        }
        Flow {
            Layout.fillWidth:true;Layout.preferredHeight:implicitHeight;spacing:Theme.dp(8)
            SwirlButton {
                text:page.waterfallOpen?"隐藏瀑布图":"显示瀑布图"
                iconName:"chart"; quiet:false; onClicked:page.waterfallOpen=!page.waterfallOpen
            }
            SwirlButton { text:AppState.zh("Replay"); onClicked:AppState.currentPage="replay" }
            SwirlButton { text:AppState.zh("Breakpoint"); onClicked:AppState.currentPage="breakpoint" }
            SwirlButton { development:true;enabled:false;text:AppState.zh("Import HAR"); iconName:"folder"; onClicked:AppState.notice("HAR import") }
            SwirlButton { development:true;enabled:false;text:AppState.zh("Export HAR"); onClicked:AppState.notice("HAR export") }
        }
    }
}
