import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string section:"Appearance"
    property var sections:["General","Appearance","Proxy","TUN","DNS","Ports","System Integration","Startup","Notifications","Data Management","Privacy & Security","Keyboard Shortcuts","About Swirl"]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            Text { text:AppState.zh("Personalize how Swirl looks and behaves"); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlStatusBadge { label:AppState.zh("LOCAL UI PREFERENCES"); tone:"accent" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.preferredWidth:229; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:12; spacing:8
                    Text { text:AppState.zh("PREFERENCES"); color:Theme.muted; font.pixelSize:11; leftPadding:8; topPadding:6 }
                    ListView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        model:page.sections; clip:true; spacing:3
                        delegate:Rectangle {
                            width:ListView.view.width; height:36; radius:9
                            color:page.section===modelData?Theme.selected:hover.containsMouse?Theme.hover:"transparent"
                            Text {
                                anchors.fill:parent; anchors.leftMargin:11
                                text:modelData; color:Theme.text; font.pixelSize:12
                                verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight
                            }
                            MouseArea { id:hover; anchors.fill:parent; hoverEnabled:true; onClicked:page.section=modelData }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ScrollView {
                    id:options
                    anchors.fill:parent; anchors.margins:24
                    clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                        width:options.availableWidth; spacing:17
                        Text { text:page.section; color:Theme.text; font.pixelSize:23; font.weight:Font.DemiBold }
                        Text {
                            text:page.section==="Appearance"?"System-aware colors, translucency, motion and interface sizing.":"Configuration preview. No operating system setting will be modified."
                            color:Theme.muted; wrapMode:Text.WordWrap; Layout.fillWidth:true; font.pixelSize:12
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        ColumnLayout {
                            visible:page.section==="Appearance"; spacing:21; Layout.fillWidth:true
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Color theme"); color:Theme.text; font.pixelSize:14; font.weight:Font.DemiBold }
                                    Text { text:AppState.zh("Choose light, dark or follow Windows"); color:Theme.muted; font.pixelSize:11 }
                                }
                                SwirlComboBox {
                                    model:["System","Light","Dark"]
                                    currentIndex:model.indexOf(Theme.mode)
                                    onActivated:Theme.mode=currentText
                                }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Windows backdrop material"); color:Theme.text; font.pixelSize:14 }
                                    Text { text:AppState.zh("Uses DWM on supported Windows 11 systems"); color:Theme.muted; font.pixelSize:11 }
                                }
                                SwirlToggle { checked:Theme.transparency; onToggled:Theme.transparency=checked }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Reduce motion"); color:Theme.text; font.pixelSize:14 }
                                    Text { text:AppState.zh("Disable most transition animations"); color:Theme.muted; font.pixelSize:11 }
                                }
                                SwirlToggle { checked:Theme.reduceMotion; onToggled:Theme.reduceMotion=checked }
                            }
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Interface scale"); color:Theme.text; font.pixelSize:14 }
                                    Text { text:Math.round(Theme.uiScale*100)+"%"; color:Theme.muted; font.pixelSize:11 }
                                }
                                Slider {
                                    Layout.preferredWidth:200
                                    from:0.9; to:1.25; stepSize:0.05
                                    value:Theme.uiScale
                                    onMoved:Theme.uiScale=value
                                }
                            }
                            SwirlStatusBadge { label:AppState.zh("CHANGES ARE LOCAL TO THIS UI PREVIEW"); tone:"accent" }
                        }
                        ColumnLayout {
                            visible:page.section!=="Appearance"; Layout.fillWidth:true; spacing:17
                            Repeater {
                                model:page.section==="Proxy"?["System proxy","Default strategy","Process bypass","Proxy authentication"]:
                                      page.section==="DNS"?["Resolver selection","Encrypted DNS","IPv6","Fake-IP handling"]:
                                      page.section==="TUN"?["TUN entry point","Interface selection","Route exclusions","Gateway DNS"]:
                                      page.section==="Ports"?["HTTP port","SOCKS port","API port","Port conflict alerts"]:
                                      page.section==="Privacy & Security"?["Sensitive data redaction","Local encryption","Certificate trust","Diagnostic consent"]:
                                      page.section==="About Swirl"?["Version","Build information","Third-party components","Project links"]:
                                      ["Enable feature","Default behavior","Advanced options","Diagnostics"]
                                RowLayout {
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        Text { text:modelData; color:Theme.text; font.pixelSize:14 }
                                        Text { text:AppState.zh("Preview configuration, not applied"); color:Theme.muted; font.pixelSize:11 }
                                    }
                                    SwirlToggle { onToggled:AppState.notice(modelData) }
                                }
                            }
                            Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                            SwirlButton { text:AppState.zh("Open advanced options"); onClicked:AppState.notice(page.section+" options") }
                        }
                        Item { Layout.preferredHeight:25 }
                    }
                }
            }
        }
    }
}