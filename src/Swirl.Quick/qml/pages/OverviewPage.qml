import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    ScrollView {
        id:scroll
        anchors.fill:parent
        anchors.leftMargin:24; anchors.rightMargin:24
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        clip:true
        ColumnLayout {
            width:scroll.availableWidth
            spacing:18
            RowLayout {
                Layout.fillWidth:true
                spacing:15
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredHeight:205
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:21; spacing:10
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:"CONNECTION CONTROL"; color:Theme.muted; font.pixelSize:11; font.letterSpacing:1.2; Layout.fillWidth:true }
                            SwirlStatusBadge { label:AppState.proxyOn?"SIMULATED ON":"DISCONNECTED"; tone:AppState.proxyOn?"success":"neutral" }
                        }
                        RowLayout {
                            Layout.fillWidth:true
                            spacing:15
                            Rectangle {
                                width:52; height:52; radius:16
                                color:Theme.selected
                                SwirlIcon { name:"globe"; size:27; color:Theme.accent; anchors.centerIn:parent }
                            }
                            ColumnLayout {
                                Layout.fillWidth:true
                                Text { text:AppState.proxyOn?"Demo connection enabled":"Ready when you are"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                                Text { text:"This control does not modify your Windows proxy."; color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                            }
                            SwirlToggle {
                                checked:AppState.proxyOn
                                onToggled:{
                                    AppState.proxyOn=checked
                                    AppState.notice("Proxy preview "+(checked?"enabled":"disabled"))
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        RowLayout {
                            Layout.fillWidth:true
                            spacing:18
                            Text { text:"MODE"; color:Theme.muted; font.pixelSize:11 }
                            SwirlComboBox {
                                model:["Rule","Global","Direct"]
                                currentIndex:Math.max(0,model.indexOf(AppState.mode))
                                onActivated:AppState.mode=currentText
                            }
                            Text { text:"POLICY"; color:Theme.muted; font.pixelSize:11 }
                            SwirlComboBox {
                                Layout.fillWidth:true
                                model:["Auto Select","Global / SG","DIRECT","REJECT"]
                                onActivated:AppState.policy=currentText
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.preferredWidth:Math.max(270,page.width*0.27)
                    Layout.preferredHeight:205
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:21; spacing:11
                        Text { text:"ACTIVE ENDPOINT"; color:Theme.muted; font.pixelSize:11; font.letterSpacing:1.2 }
                        Text { text:AppState.selectedNode; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                        Text { text:"Trojan · Demo route"; color:Theme.muted; font.pixelSize:12 }
                        Item { Layout.fillHeight:true }
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlStatusBadge { label:"38 ms · sample"; tone:"success" }
                            Item { Layout.fillWidth:true }
                            SwirlButton { text:"Change"; iconName:"route"; onClicked:AppState.currentPage="proxies" }
                        }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true
                columns:page.width>1120?4:2
                rowSpacing:14; columnSpacing:14
                SwirlMetricCard { Layout.fillWidth:true; label:"Download"; value:"8.42 MB/s"; secondary:"Illustrative snapshot"; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Upload"; value:"1.26 MB/s"; secondary:"Illustrative snapshot"; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Active sessions"; value:"42"; secondary:"Synthetic connections"; iconName:"network" }
                SwirlMetricCard { Layout.fillWidth:true; label:"Total traffic"; value:"2.84 GB"; secondary:"Demo session volume"; iconName:"layers" }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true
                Layout.preferredHeight:314
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:20
                    spacing:9
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:3
                            Text { text:"Traffic overview"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                            Text { text:"Last 60 minutes · representative sample"; color:Theme.muted; font.pixelSize:11 }
                        }
                        SwirlStatusBadge { label:"● Download"; tone:"accent" }
                        SwirlStatusBadge { label:"● Upload"; tone:"success" }
                        SwirlButton { text:"Details"; onClicked:AppState.currentPage="traffic" }
                    }
                    SwirlTrafficChart { Layout.fillWidth:true; Layout.fillHeight:true; samples:demoProvider.traffic() }
                }
            }
            RowLayout {
                Layout.fillWidth:true; spacing:16
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredHeight:295
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:18; spacing:12
                        Text { text:"Recent network events"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                        Repeater {
                            model:demoProvider.events()
                            RowLayout {
                                Layout.fillWidth:true; spacing:11
                                Text { text:modelData.time; color:Theme.muted; font.pixelSize:11; Layout.preferredWidth:57 }
                                ColumnLayout {
                                    Layout.fillWidth:true; spacing:2
                                    Text { text:modelData.title; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight; Layout.fillWidth:true }
                                    Text { text:modelData.detail; color:Theme.muted; font.pixelSize:11 }
                                }
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.preferredWidth:310; Layout.preferredHeight:295
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:18; spacing:13
                        Text { text:"Quick controls"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:"System Proxy"; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true }
                            SwirlToggle { checked:AppState.systemProxyOn; onToggled:{AppState.systemProxyOn=checked;AppState.notice("System proxy setting")} }
                        }
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:"TUN mode"; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true }
                            SwirlToggle { checked:AppState.tunOn; onToggled:{AppState.tunOn=checked;AppState.notice("TUN mode setting")} }
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        SwirlButton { Layout.fillWidth:true; text:"Open HTTP Inspector"; iconName:"inspect"; onClicked:AppState.currentPage="inspector" }
                        SwirlButton { Layout.fillWidth:true; text:"Check DNS"; iconName:"server"; onClicked:AppState.currentPage="dns" }
                    }
                }
            }
            Item { Layout.preferredHeight:15 }
        }
    }
}