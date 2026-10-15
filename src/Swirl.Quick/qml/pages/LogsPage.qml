import QtQuick
import QtQuick.Dialogs
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property var selected:null
 property bool detailHasSelection:selected!==null
 onDetailHasSelectionChanged:{if(visible)detailClock.moveTo(detailHasSelection?1:0);else{detailClock.destination=detailHasSelection?1:0;detailClock.finish()}}
 SwirlTransitionCoordinator {id:detailClock;duration:SwirlMotion.dialogDuration}
    property bool followTail:true
    property var records:visible?(systemProvider.revision,systemProvider.logs()):[]
    readonly property var displayLogs:records.filter(function(r){
        return (r.message+" "+r.source+" "+r.level).toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
               (level.currentText==="全部级别"||r.level===level.currentText)
    }).map(function(r){return {id:r.id||[r.time,r.correlation,r.source,r.code].join("/"),time:r.time,level:r.level,source:r.source,message:r.message}}).reverse()
    FileDialog { id:diagnosticFile;title:"导出诊断报告";fileMode:FileDialog.SaveFile;nameFilters:["诊断 ZIP (*.zip)"];defaultSuffix:"zip";onAccepted:{diagnostics.exportReport(selectedFile,systemProvider.diagnosticSnapshot());AppState.toast=diagnostics.exportMessage} }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(13)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"日志记录"; tone:"accent" }
            SwirlText { text:displayLogs.length+" 条诊断事件"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { text:"导出诊断报告"; iconName:"folder"; onClicked:diagnosticFile.open() }
            SwirlButton { text:"标记已读";enabled:diagnostics.eventCount>0;onClicked:diagnostics.acknowledge() }
            SwirlButton { text:"清空"; danger:true; onClicked:{systemProvider.clearLogs();page.selected=null} }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索消息、级别或组件" }
            SwirlComboBox { id:level; model:["全部级别","INFO","DEBUG","WARN","ERROR"] }
            SwirlText { text:"跟随最新日志"; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
            SwirlToggle { checked:page.followTail; onToggled:page.followTail=checked }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.displayLogs;incrementalRows:true;followTail:page.followTail;animateRowChanges:false
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"time",label:"时间",w:108},{key:"level",label:"级别",w:84},
                             {key:"source",label:"来源",w:104},{key:"message",label:"信息",w:570}]
                    onRowSelected:function(r){page.selected=r}
                }
                SwirlEmptyState {
                    visible:page.displayLogs.length===0; anchors.centerIn:parent
                    headline:"没有日志记录"
                    detail:"暂无真实引擎事件"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(289); Layout.fillHeight:true
                transform:Translate{x:SwirlMotion.reduced?0:Theme.dp(16)*(1-detailClock.progress)}
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(12)
                    SwirlText { text:"事件详情"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selected?page.selected.level:"未选择"; tone:page.selected&&page.selected.level==="ERROR"?"warning":"neutral" }
                    Repeater {
                        model:[["TIME",page.selected?page.selected.time:"—"],["COMPONENT",page.selected?page.selected.source:"—"],
                               ["MESSAGE",page.selected?page.selected.message:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(4)
                            SwirlText { text:AppState.zh(modelData[0]); font.pixelSize:Theme.fontSize(10); color:Theme.muted }
                            SwirlText { text:AppState.zh(modelData[1]); font.pixelSize:Theme.fontSize(12); color:Theme.text; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                    SwirlText { text:"诊断事件"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlText {
                        Layout.fillWidth:true
                        text:"记录 Swirl 可观测的活动与诊断事件。日志已脱敏并限制大小；诊断 ZIP 保存在本机，不会自动上传。"
                        color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.WordWrap
                    }

                        }
                    }

                    SwirlButton { text:"恢复日志"; onClicked:page.records=Qt.binding(()=>page.visible?(systemProvider.revision,systemProvider.logs()):[]) }

                }
            }
        }
    }
}
