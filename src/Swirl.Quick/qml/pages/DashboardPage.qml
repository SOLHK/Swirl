import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string range: "Last hour"
    property var sessions: demoProvider.connections()
    property var sampleRows: [
        {name:"api.github.com",requests:"1,240",download:"389 MB",policy:"Auto Select"},
        {name:"cdn.jsdelivr.net",requests:"986",download:"270 MB",policy:"DIRECT"},
        {name:"developer.apple.com",requests:"824",download:"116 MB",policy:"Global / SG"},
        {name:"www.microsoft.com",requests:"641",download:"98 MB",policy:"Auto Select"},
        {name:"fonts.gstatic.com",requests:"318",download:"42 MB",policy:"DIRECT"}
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
                Text { text:"Activity and throughput"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
                SwirlComboBox {
                    model:["Last hour","24 hours","7 days","30 days"]
                    onActivated:page.range=currentText
                }
                SwirlButton { text:"Export report"; iconName:"folder"; onClicked:AppState.notice("Export dashboard") }
            }
            GridLayout {
                Layout.fillWidth:true
                columns:page.width>1080?4:2
                columnSpacing:13; rowSpacing:13
                SwirlMetricCard { Layout.fillWidth:true; label:"Total Download"; value:"1.48 GB"; secondary:"Synthetic "+page.range; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Total Upload"; value:"304 MB"; secondary:"Synthetic "+page.range; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Avg. Latency"; value:"58 ms"; secondary:"Synthetic endpoints"; iconName:"clock" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Connections"; value:"54"; secondary:"42 active · demo"; iconName:"network" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:304
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:20; spacing:13
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text { text:"Network throughput"; font.pixelSize:17; color:Theme.text; font.weight:Font.DemiBold }
                            Text { text:"Download and upload · local representative series"; color:Theme.muted; font.pixelSize:11 }
                        }
                        SwirlStatusBadge { label:"● DOWNLOAD"; tone:"accent" }
                        SwirlStatusBadge { label:"● UPLOAD"; tone:"success" }
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
                            Text { text:"Top destinations"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold; Layout.fillWidth:true }
                            SwirlButton { text:"Open connections"; quiet:true; onClicked:AppState.currentPage="connections" }
                        }
                        SwirlDataTable {
                            Layout.fillWidth:true; Layout.fillHeight:true
                            rows:page.sampleRows
                            columns:[{key:"name",label:"DOMAIN",w:230},{key:"requests",label:"REQUESTS",w:88},
                                     {key:"download",label:"DOWNLOAD",w:95},{key:"policy",label:"POLICY",w:125}]
                            onRowSelected:function(r){AppState.notice("Inspect destination "+r.name)}
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.preferredWidth:290; Layout.preferredHeight:337
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:18; spacing:15
                        Text { text:"Traffic distribution"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                        Repeater {
                            model:[{name:"HTTP/2",share:.47,color:Theme.accent},
                                   {name:"HTTP/3",share:.29,color:Theme.green},
                                   {name:"TCP",share:.17,color:Theme.orange},
                                   {name:"Other",share:.07,color:Theme.muted}]
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
                        Text { text:"Protocol percentages are illustrative."; color:Theme.muted; font.pixelSize:10 }
                    }
                }
            }
            Item { Layout.preferredHeight:15 }
        }
    }
}