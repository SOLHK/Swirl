import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string range: "最近 1 小时"
    property var sessions: demoProvider.connections()
    property var sampleRows: [
        {name:"api.github.com",requests:"1,240",download:"389 MB",policy:"自动选择"},
        {name:"cdn.jsdelivr.net",requests:"986",download:"270 MB",policy:"直连"},
        {name:"developer.apple.com",requests:"824",download:"116 MB",policy:"全局 · 新加坡"},
        {name:"www.microsoft.com",requests:"641",download:"98 MB",policy:"自动选择"},
        {name:"fonts.gstatic.com",requests:"318",download:"42 MB",policy:"直连"}
    ]
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.leftMargin: 23; anchors.rightMargin: 23
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 15
            RowLayout {
                Layout.fillWidth:true
                Text { text:AppState.zh("Activity and throughput"); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
                SwirlSegmentedControl {
                    Layout.preferredWidth: 365
                    options: ["1 小时", "24 小时", "7 天", "30 天"]
                    onActivated: function(index, value) {
                        page.range = ["最近 1 小时","最近 24 小时","最近 7 天","最近 30 天"][index]
                    }
                }
                SwirlButton { text:AppState.zh("导出报告"); iconName:"folder"; onClicked:AppState.notice("导出仪表盘") }
            }
            GridLayout {
                Layout.fillWidth:true
                columns:page.width>1080?4:2
                columnSpacing:13; rowSpacing:13
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Total Download"); value:"1.48 GB"; secondary:"模拟"+page.range; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Total Upload"); value:"304 MB"; secondary:"模拟"+page.range; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Avg. Latency"); value:"58 ms"; secondary:"模拟节点"; iconName:"clock" }
                SwirlMetricCard { Layout.fillWidth:true; label:AppState.zh("Connections"); value:"54"; secondary:"42 个活动连接 · 演示"; iconName:"network" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:304
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:20; spacing:13
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text { text:AppState.zh("网络吞吐量"); font.pixelSize:17; color:Theme.text; font.weight:Font.DemiBold }
                            Text { text:AppState.zh("Download and upload · local representative series"); color:Theme.muted; font.pixelSize:11 }
                        }
                        SwirlStatusBadge { label:AppState.zh("● DOWNLOAD"); tone:"accent" }
                        SwirlStatusBadge { label:AppState.zh("● UPLOAD"); tone:"success" }
                    }
                    SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true }
                }
            }
            RowLayout {
                Layout.fillWidth:true; spacing:14
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredHeight:337
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:17; spacing:11
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:AppState.zh("Top destinations"); color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold; Layout.fillWidth:true }
                            SwirlButton { text:AppState.zh("查看连接记录"); quiet:true; onClicked:AppState.currentPage="connections" }
                        }
                        SwirlDataTable {
                            Layout.fillWidth:true; Layout.fillHeight:true
                            rows:page.sampleRows
                            columns:[{key:"name",label:AppState.zh("DOMAIN"),w:230},{key:"requests",label:AppState.zh("REQUESTS"),w:88},
                                     {key:"download",label:AppState.zh("DOWNLOAD"),w:95},{key:"policy",label:AppState.zh("POLICY"),w:125}]
                            onRowSelected:function(r){AppState.notice("查看目标"+r.name)}
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.preferredWidth:290; Layout.preferredHeight:337
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:18; spacing:15
                        Text { text:AppState.zh("流量分布"); color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                        Repeater {
                            model:[{name:"HTTP/2",share:.47,color:Theme.accent},
                                   {name:"HTTP/3",share:.29,color:Theme.green},
                                   {name:"TCP",share:.17,color:Theme.orange},
                                   {name:"其他",share:.07,color:Theme.muted}]
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:6
                                RowLayout {
                                    Layout.fillWidth:true
                                    Text { text:modelData.name; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                                    Text { text:Math.round(modelData.share*100)+"%"; color:Theme.muted; font.pixelSize:12 }
                                }
                                Rectangle {
                                    Layout.fillWidth:true; height:7; radius:4; color:Theme.field
                                    Rectangle {
                                        width:parent.width*modelData.share; height:parent.height; radius:4
                                        color:modelData.color
                                        Behavior on width { NumberAnimation { duration:Theme.motion } }
                                    }
                                }
                            }
                        }
                        Item { Layout.fillHeight:true }
                        Text { text:AppState.zh("Protocol percentages are illustrative."); color:Theme.muted; font.pixelSize:10 }
                    }
                }
            }
            Item { Layout.preferredHeight:15 }
        }
    }
}