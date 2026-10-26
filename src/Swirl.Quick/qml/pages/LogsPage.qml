import QtQuick
import QtQuick.Dialogs
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    readonly property Item motionTitle:heading.titleItem
    readonly property bool compact:width<Theme.dp(620)
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
        anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.dp(16)
        SwirlPageHeader {id:heading;Layout.fillWidth:true;title:qsTr("日志");description:qsTr("应用内可观测事件与诊断信息。");metadata:qsTr("%1 条诊断事件").arg(page.displayLogs.length)
            SwirlButton {text:qsTr("导出诊断报告");iconName:"folder";onClicked:diagnosticFile.open()}
            SwirlButton {text:qsTr("标记已读");quiet:true;enabled:diagnostics.eventCount>0;onClicked:diagnostics.acknowledge()}
            SwirlButton {text:qsTr("清空");danger:true;quiet:true;onClicked:{systemProvider.clearLogs();page.selected=null}}
        }
        GridLayout {Layout.fillWidth:true;columns:width<Theme.dp(620)?1:2;columnSpacing:Theme.dp(16);rowSpacing:Theme.compactGap
            SwirlSearchField {id:search;Layout.fillWidth:true;placeholderText:qsTr("搜索消息、级别或组件")}
            RowLayout {spacing:Theme.dp(12);SwirlComboBox {id:level;model:["全部级别","INFO","DEBUG","WARN","ERROR"];Accessible.name:qsTr("日志级别")} SwirlText {text:qsTr("跟随最新日志");color:Theme.muted;font.pixelSize:Theme.fontSize(12)} SwirlToggle {checked:page.followTail;onToggled:page.followTail=checked;Accessible.name:qsTr("跟随最新日志")}}
        }
        GridLayout {Layout.fillWidth:true;Layout.fillHeight:true;columns:page.compact?1:2;columnSpacing:Theme.sectionGap;rowSpacing:Theme.sectionGap
            Item {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(100)
                SwirlDataTable {id:logTable;objectName:"logTable";anchors.fill:parent;rows:page.displayLogs;incrementalRows:true;followTail:page.followTail;animateRowChanges:false;selectedId:page.selected?page.selected.id:"";minimal:true;columns:[{key:"time",label:qsTr("时间"),w:108},{key:"level",label:qsTr("级别"),w:84},{key:"source",label:qsTr("来源"),w:104},{key:"message",label:qsTr("信息"),w:570}];onRowSelected:function(r){page.selected=r;logDetail.present(logTable.selectedItem)}}
                SwirlEmptyState {visible:page.displayLogs.length===0;anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(24));headline:qsTr("没有匹配的日志");detail:page.records.length?qsTr("调整搜索或级别筛选。"):qsTr("暂无真实引擎事件。")}
            }
            SwirlLinkedDetail {id:logDetail;animationLayer:page;sourceViewport:logTable;detailOpen:page.selected!==null;visible:!page.compact||page.selected!==null||moving;Layout.preferredWidth:page.compact?1:Theme.dp(300);Layout.fillWidth:page.compact;Layout.fillHeight:!page.compact;Layout.preferredHeight:page.compact?Theme.dp(180):-1
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
                            SwirlText { text:String(modelData[1]); textFormat:Text.PlainText; font.pixelSize:Theme.fontSize(12); color:Theme.text; Layout.fillWidth:true; wrapMode:Text.WordWrap }
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
