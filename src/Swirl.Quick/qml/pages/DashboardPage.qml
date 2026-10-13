import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:true
    property string range:"今日"
    property int period:0
    property var sessions: engineController.telemetry.connections
    readonly property var totals:(engineController.telemetry.revision,engineController.telemetry.summary(period))
    property var sampleRows: (engineController.telemetry.revision,engineController.telemetry.ranking("domains",period,20))
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.leftMargin:Theme.dp(23); anchors.rightMargin:Theme.dp(23)
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: scroll.availableWidth
            spacing:Theme.dp(15)
            RowLayout {
                Layout.fillWidth:true
                Text { text:AppState.zh("Activity and throughput"); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                SwirlSegmentedControl {
                    Layout.preferredWidth:Theme.dp(365)
                    options:["今日","昨日","本周"]
                    onActivated: function(index, value) {
                        page.period=index;page.range=["今日","昨日","本周"][index]
                    }
                }
                SwirlButton { enabled:false; text:AppState.zh("导出报告"); iconName:"folder"; onClicked:AppState.notice("导出仪表盘") }
            }
            GridLayout {
                Layout.fillWidth:true
                columns:page.width>1080?4:2
                columnSpacing:13; rowSpacing:13
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Total Download"); value:totals.sampled?engineController.telemetry.formatBytes(totals.down):"未采集"; secondary:""+page.range; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Total Upload"); value:totals.sampled?engineController.telemetry.formatBytes(totals.up):"未采集"; secondary:""+page.range; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Avg. Latency"); value:"—"; secondary:"节点"; iconName:"clock" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Connections"); value:engineController.telemetry.connectionsSampled?String(engineController.telemetry.activeConnections):"未采集"; secondary:"未采集"; iconName:"network" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(304)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(13)
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text { text:AppState.zh("网络吞吐量"); font.pixelSize:Theme.fontSize(17); color:Theme.text; font.weight:Font.DemiBold }
                            Text { text:"真实速率 · 最近 1 分钟"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                        }
                        SwirlStatusBadge { label:AppState.zh("● DOWNLOAD"); tone:"accent" }
                        SwirlStatusBadge { label:AppState.zh("● UPLOAD"); tone:"success" }
                    }
                    SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
                }
            }
            RowLayout {
                Layout.fillWidth:true; spacing:Theme.dp(14)
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(337)
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:Theme.dp(17); spacing:Theme.dp(11)
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:AppState.zh("Top destinations"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold; Layout.fillWidth:true }
                            SwirlButton { text:AppState.zh("查看连接记录"); quiet:false; onClicked:AppState.currentPage="connections" }
                        }
                        SwirlDataTable {
                            Layout.fillWidth:true; Layout.fillHeight:true
                            rows:page.sampleRows
                            columns:[{key:"name",label:AppState.zh("DOMAIN"),w:230},{key:"connections",label:AppState.zh("REQUESTS"),w:88},
                                     {key:"download",label:AppState.zh("DOWNLOAD"),w:95},{key:"policy",label:AppState.zh("POLICY"),w:125}]
                            onRowSelected:function(r){AppState.notice("查看目标"+r.name)}
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.preferredWidth:Theme.dp(290); Layout.preferredHeight:Theme.dp(337)
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(15)
                        Text { text:AppState.zh("流量分布"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                        Repeater {
                            model:(engineController.telemetry.revision,engineController.telemetry.distribution(page.period))
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:Theme.dp(6)
                                RowLayout {
                                    Layout.fillWidth:true
                                    Text { text:modelData.name; color:Theme.text; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
                                    Text { text:modelData.percent; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                                }
                                Rectangle {
                                    Layout.fillWidth:true; height:Theme.dp(7); radius:Theme.roundedRadius(width,height); color:Theme.field
                                    Rectangle {
                                        width:parent.width*(parseFloat(modelData.percent)||0)/100; height:parent.height; radius:Theme.roundedRadius(width,height)
                                        color:modelData.tint
                                        Behavior on width { NumberAnimation { duration:Theme.motion } }
                                    }
                                }
                            }
                        }
                        Item { Layout.fillHeight:true }
                        Text { text:"未采集的短连接计入其他流量；阻止请求按次数显示"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    }
                }
            }
            Item { Layout.preferredHeight:Theme.dp(15) }
        }
    }
}
