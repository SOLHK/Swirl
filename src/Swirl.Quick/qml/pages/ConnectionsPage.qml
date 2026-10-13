import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property var selected:null
    property var visibleRows:{
        var q=search.text.toLowerCase()
        var s=sort.currentText
        var state=status.currentText
        var rows=engineController.connections.filter(function(r){
            return (r.host+" "+r.process+" "+r.ip+" "+r.policy).toLowerCase().indexOf(q)>=0 &&
                   (state==="全部状态"||r.status===state)
        })
        rows.sort(function(a,b){
            var key=s==="域名"?"host":s==="延迟"?"latency":s==="下载"?"down":"process"
            return String(a[key]).localeCompare(String(b[key]),undefined,{numeric:true})
        })
        return rows
    }
    ColumnLayout {
        anchors.fill:parent
        anchors.leftMargin:Theme.dp(23); anchors.rightMargin:Theme.dp(23); anchors.bottomMargin:Theme.dp(14)
        spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(10)
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("搜索域名、IP、进程或策略") }
            SwirlComboBox { id:status; model:["全部状态","活动","已结束"] }
            SwirlComboBox { id:sort; model:["域名","延迟","下载","进程"] }
            SwirlButton { enabled:false; text:AppState.zh("导出"); iconName:"folder"; onClicked:AppState.notice("导出连接记录") }
            SwirlButton { enabled:false; text:AppState.zh("Clear"); onClicked:{selected=null;AppState.notice("清空连接记录")} }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(8)
            SwirlStatusBadge { label:visibleRows.length+" 条记录"; tone:"accent" }
            Text { text:AppState.zh("Click a row to examine a connection"); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { text:AppState.detailOpen?"隐藏详情":"显示详情"; quiet:false; onClicked:AppState.detailOpen=!AppState.detailOpen }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.visibleRows
                    selectedId:page.selected?page.selected.id:""
                    columns:[
                        {key:"host",label:AppState.zh("HOST"),w:220},{key:"ip",label:AppState.zh("IP ADDRESS"),w:125},
                        {key:"process",label:AppState.zh("PROCESS"),w:115},{key:"protocol",label:AppState.zh("PROTO"),w:80},
                        {key:"policy",label:AppState.zh("POLICY"),w:119},{key:"up",label:AppState.zh("UPLOAD"),w:89},
                        {key:"down",label:AppState.zh("DOWNLOAD"),w:100},{key:"latency",label:AppState.zh("LATENCY"),w:95},
                        {key:"time",label:AppState.zh("SINCE"),w:88},{key:"status",label:AppState.zh("状态"),w:88}
                    ]
                    onRowSelected:function(record){page.selected=record}
                }
                SwirlEmptyState {
                    visible:page.visibleRows.length===0
                    anchors.centerIn:parent
                    headline:AppState.zh("没有匹配的连接")
                    detail:AppState.zh("Adjust the search or status filter")
                }
            }
            SwirlGlassPanel {
                visible:AppState.detailOpen
                Layout.preferredWidth:Theme.dp(290); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(15)
                    Text { text:AppState.zh("Connection details"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selected?page.selected.status.toUpperCase():"尚未选择"; tone:page.selected?"success":"neutral" }
                    Repeater {
                        model:[
                            ["Host",page.selected?page.selected.host:"—"],
                            ["Destination",page.selected?page.selected.ip:"—"],
                            ["Application",page.selected?page.selected.process:"—"],
                            ["Protocol",page.selected?page.selected.protocol:"—"],
                            ["匹配策略",page.selected?page.selected.policy:"—"],
                            ["匹配规则",page.selected?page.selected.rule:"—"],
                            ["Upload",page.selected?page.selected.up:"—"],
                            ["Download",page.selected?page.selected.down:"—"],
                            ["Latency",page.selected?page.selected.latency:"—"],
                            ["Established",page.selected?page.selected.time:"—"]
                        ]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); elide:Text.ElideRight; Layout.fillWidth:true }
                        }
                    }

                        }
                    }

                    SwirlButton {
                        enabled:page.selected && page.selected.status==="活动" && engineController.apiHealthy; Layout.fillWidth:true; text:AppState.zh("Terminate connection"); danger:true
                        onClicked:engineController.closeConnection(page.selected.id)
                    }

                }
            }
        }
    }
}
