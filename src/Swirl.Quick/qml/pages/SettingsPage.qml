import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string section:"外观"
    property var sections:["常规","外观","代理","TUN","DNS","端口","系统集成","启动","通知","数据管理","隐私与安全","快捷键","关于 Swirl"]
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
                                text:AppState.zh(modelData); color:Theme.text; font.pixelSize:12
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
                        Text { text:AppState.zh(page.section); color:Theme.text; font.pixelSize:23; font.weight:Font.DemiBold }
                        Text {
                            text:page.section==="外观"?"跟随系统的色彩、玻璃材质、动画与界面缩放。":"当前仅供预览，不会修改操作系统设置。"
                            color:Theme.muted; wrapMode:Text.WordWrap; Layout.fillWidth:true; font.pixelSize:12
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        ColumnLayout {
                            visible:page.section==="外观"; spacing:21; Layout.fillWidth:true
                            RowLayout {
                                Layout.fillWidth:true
                                ColumnLayout {
                                    Layout.fillWidth:true
                                    Text { text:AppState.zh("Color theme"); color:Theme.text; font.pixelSize:14; font.weight:Font.DemiBold }
                                    Text { text:AppState.zh("Choose light, dark or follow Windows"); color:Theme.muted; font.pixelSize:11 }
                                }
                                SwirlComboBox {
                                    model:["跟随系统","浅色","深色"]
                                    currentIndex:["System","Light","Dark"].indexOf(Theme.mode)
                                    onActivated:Theme.mode=["System","Light","Dark"][currentIndex]
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
                                    id: scaleSlider
                                    Layout.preferredWidth:200
                                    from:0.9; to:1.25; stepSize:0.05
                                    value:Theme.uiScale
                                    onMoved:Theme.uiScale=value
                                    background: Rectangle {
                                        x: scaleSlider.leftPadding
                                        y: scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2
                                        width: scaleSlider.availableWidth
                                        height: 7
                                        radius: 4
                                        color: Theme.material("field")
                                        border.width: 1
                                        border.color: Theme.glassRim
                                        Rectangle {
                                            height: parent.height
                                            radius: 4
                                            width: scaleSlider.visualPosition * parent.width
                                            color: Theme.accent
                                        }
                                    }
                                    handle: Rectangle {
                                        x: scaleSlider.leftPadding + scaleSlider.visualPosition * (scaleSlider.availableWidth - width)
                                        y: scaleSlider.topPadding + scaleSlider.availableHeight / 2 - height / 2
                                        implicitWidth: 20; implicitHeight: 20
                                        radius: 10
                                        color: "#FBFDFF"
                                        border.width: 1
                                        border.color: Theme.glassRim
                                    }
                                }
                            }
                            SwirlStatusBadge { label:AppState.zh("CHANGES ARE LOCAL TO THIS UI PREVIEW"); tone:"accent" }
                        }
                        ColumnLayout {
                            visible:page.section!=="外观"; Layout.fillWidth:true; spacing:17
                            Repeater {
                                model:page.section==="代理"?["系统代理","默认策略","进程绕过","代理身份验证"]:
                                      page.section==="DNS"?["解析器选择","加密 DNS","IPv6","虚拟 IP 处理"]:
                                      page.section==="TUN"?["TUN 入口","网卡选择","路由排除","网关 DNS"]:
                                      page.section==="端口"?["HTTP 端口","SOCKS 端口","API 端口","端口冲突提醒"]:
                                      page.section==="隐私与安全"?["敏感数据脱敏","本地加密","证书信任","诊断授权"]:
                                      page.section==="关于 Swirl"?["版本","构建信息","第三方组件","项目链接"]:
                                      ["启用功能","默认行为","高级选项","诊断"]
                                RowLayout {
                                    Layout.fillWidth:true
                                    ColumnLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh(modelData); color:Theme.text; font.pixelSize:14 }
                                        Text { text:AppState.zh("Preview configuration, not applied"); color:Theme.muted; font.pixelSize:11 }
                                    }
                                    SwirlToggle { onToggled:AppState.notice(modelData) }
                                }
                            }
                            Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                            SwirlButton { text:AppState.zh("Open advanced options"); onClicked:AppState.notice(page.section+"选项") }
                        }
                        Item { Layout.preferredHeight:25 }
                    }
                }
            }
        }
    }
}