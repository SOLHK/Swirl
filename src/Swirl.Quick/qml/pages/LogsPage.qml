import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property var selected:null
    property bool followTail:true
    property var records:demoProvider.logs()
    readonly property var displayLogs:records.filter(function(r){
        return (r.message+" "+r.source+" "+r.level).toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
               (level.currentText==="全部级别"||r.level===level.currentText)
    }).map(function(r,i){return {id:"log-"+i,time:r.time,level:r.level,source:r.source,message:r.message}})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:13
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"模拟日志流"; tone:"accent" }
            Text { text:displayLogs.length+" 条记录 · 数据仅供预览"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Export"; iconName:"folder"; onClicked:AppState.notice("导出日志记录") }
            SwirlButton { text:"Clear"; danger:true; onClicked:{page.records=[];page.selected=null} }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"搜索消息、级别或组件" }
            SwirlComboBox { id:level; model:["全部级别","INFO","DEBUG","WARN","ERROR"] }
            Text { text:"跟随最新日志"; color:Theme.muted; font.pixelSize:12 }
            SwirlToggle { checked:page.followTail; onToggled:page.followTail=checked }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.displayLogs
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"time",label:"TIME",w:108},{key:"level",label:"LEVEL",w:84},
                             {key:"source",label:"SOURCE",w:104},{key:"message",label:"MESSAGE",w:570}]
                    onRowSelected:function(r){page.selected=r}
                }
                SwirlEmptyState {
                    visible:page.displayLogs.length===0; anchors.centerIn:parent
                    headline:"没有日志记录"
                    detail:"请调整筛选条件或恢复演示数据"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:289; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:12
                    Text { text:"事件详情"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selected?page.selected.level:"未选择"; tone:page.selected&&page.selected.level==="ERROR"?"warning":"neutral" }
                    Repeater {
                        model:[["TIME",page.selected?page.selected.time:"—"],["COMPONENT",page.selected?page.selected.source:"—"],
                               ["MESSAGE",page.selected?page.selected.message:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:4
                            Text { text:modelData[0]; font.pixelSize:10; color:Theme.muted }
                            Text { text:modelData[1]; font.pixelSize:12; color:Theme.text; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:"诊断事件"; color:Theme.muted; font.pixelSize:10 }
                    Text {
                        Layout.fillWidth:true
                        text:"这里的事件由模拟数据生成，不会读取系统、Mihomo 或 Windows 日志。"
                        color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"恢复演示日志"; onClicked:page.records=demoProvider.logs() }
                }
            }
        }
    }
}