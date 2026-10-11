import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"Tasks"
    property var selected:null
    property var jobs:[
        {id:"auto1",name:"刷新配置",trigger:"Daily · 08:00",action:"配置刷新",state:"Enabled",last:"Never"},
        {id:"auto2",name:"Wi-Fi 路由选择",trigger:"网络变化",action:"切换策略",state:"Enabled",last:"Never"},
        {id:"auto3",name:"错误日志摘要",trigger:"错误事件",action:"生成报告",state:"Disabled",last:"Never"}
    ]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"计划任务未连接"; tone:"warning" }
            Text { text:"触发条件、定时表达式及操作均为模拟数据"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"新建自动化"; primary:true; onClicked:newDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Tasks","History","Conditions"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"全部运行（演示）"; iconName:"play"; onClicked:AppState.notice("运行自动化任务") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Tasks"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.jobs; selectedId:page.selected?page.selected.id:""
                    columns:[{key:"name",label:"任务",w:225},{key:"trigger",label:"触发条件",w:155},
                             {key:"action",label:"操作",w:155},{key:"state",label:"状态",w:96},
                             {key:"last",label:"上次运行",w:96}]
                    onRowSelected:function(r){page.selected=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Tasks"
                    anchors.fill:parent; anchors.margins:18; spacing:16
                    Text { text:page.tab==="History"?"任务执行历史":"可用触发条件"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="History"?["预览中尚无任务执行记录",
                            "示例：08:00 · 刷新配置 · 未执行（无后端）"]:
                            ["定时 / Cron","Wi-Fi 名称变化","网络连接或断开","DNS 查询失败",
                             "HTTP 响应条件","策略延迟阈值"]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"clock"; size:17; color:Theme.muted }
                            Text { text:modelData; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:310; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:14
                    Text { text:"自动化编辑器"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.selected?page.selected.name:"选择任务"; color:Theme.accent; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                    Text { text:"触发类型"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { Layout.fillWidth:true; model:["Schedule","网络变化","HTTP 事件","DNS 事件","错误事件"] }
                    Text { text:"定时 / 事件筛选"; color:Theme.muted; font.pixelSize:10 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"0 8 * * *" }
                    Text { text:"操作"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { Layout.fillWidth:true; model:["刷新配置","选择代理","记录日志","运行脚本","Notify"] }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"启用任务"; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                        SwirlToggle { onToggled:AppState.notice("自动化启用开关") }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"检查演示规则"; onClicked:AppState.notice("检查自动化") }
                    SwirlButton { text:"保存预览"; primary:true; onClicked:AppState.notice("保存自动化预览") }
                }
            }
        }
    }
    SwirlDialog {
        id:newDialog; title:"创建自动化"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"任务名称"; color:Theme.text }
            SwirlTextField { id:taskName; Layout.fillWidth:true; placeholderText:"新建自动化" }
            Text { text:"触发类型"; color:Theme.text }
            SwirlComboBox { id:triggerInput; Layout.fillWidth:true; model:["Scheduled","网络变化","HTTP 事件","错误事件"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"取消"; onClicked:newDialog.close() }
                SwirlButton {
                    text:"创建演示"; primary:true; enabled:taskName.text.trim().length>0
                    onClicked:{
                        page.jobs=page.jobs.concat([{id:"auto"+Date.now(),name:taskName.text.trim(),
                            trigger:triggerInput.currentText,action:"空操作预览",state:"Disabled",last:"Never"}])
                        taskName.text="";newDialog.close()
                    }
                }
            }
        }
    }
}