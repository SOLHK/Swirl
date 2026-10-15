import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string tab:"Tasks"
    property var selected:null
    property var jobs:[]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"研发中"; tone:"warning" }
            SwirlText { text:"计划任务服务研发中；触发条件与动作尚未执行。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { development:true; enabled:false; text:"新建自动化"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Tasks","History","Conditions"]
                SwirlButton { development:true; enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { development:true; enabled:false; text:"全部运行"; iconName:"play"; onClicked:AppState.notice("运行自动化任务") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Tasks"
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.jobs; selectedId:page.selected?page.selected.id:""
                    columns:[{key:"name",label:"任务",w:225},{key:"trigger",label:"触发条件",w:155},
                             {key:"action",label:"操作",w:155},{key:"state",label:"状态",w:96},
                             {key:"last",label:"上次运行",w:96}]
                    onRowSelected:function(r){page.selected=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Tasks"
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(16)
                    SwirlText { text:page.tab==="History"?"任务执行历史":"可用触发条件"; color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    Repeater {
                        model:[]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"clock"; size:Theme.dp(17); color:Theme.muted }
                            SwirlText { text:modelData; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(310); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(17); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(14)
                    SwirlText { text:"自动化编辑器"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlText { text:page.selected?page.selected.name:"选择任务"; color:Theme.accent; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    SwirlText { text:"触发类型"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlComboBox { Layout.fillWidth:true; model:["Schedule","网络变化","HTTP 事件","DNS 事件","错误事件"] }
                    SwirlText { text:"定时 / 事件筛选"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"0 8 * * *" }
                    SwirlText { text:"操作"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlComboBox { Layout.fillWidth:true; model:["刷新配置","选择代理","记录日志","运行脚本","Notify"] }
                    Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlText { text:"启用任务"; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                        SwirlToggle { enabled:false;checked:false; onToggled:AppState.notice("自动化启用开关") }
                    }

                        }
                    }

                    SwirlButton { development:true; enabled:false; text:"检查规则"; onClicked:AppState.notice("检查自动化") }
                    SwirlButton { development:true; enabled:false; text:"保存预览"; primary:true; onClicked:AppState.notice("保存自动化预览") }

                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"创建自动化"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            SwirlText { text:"任务名称"; color:Theme.text }
            SwirlTextField { id:taskName; Layout.fillWidth:true; placeholderText:"新建自动化" }
            SwirlText { text:"触发类型"; color:Theme.text }
            SwirlComboBox { id:triggerInput; Layout.fillWidth:true; model:["Scheduled","网络变化","HTTP 事件","错误事件"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { development:true; enabled:false; text:"取消"; onClicked:newDialog.close() }
                SwirlButton { development:true; enabled:false;
                    text:"创建"; primary:true;
                    onClicked:AppState.notice("研发中")
                }
            }
        }
    }
}
