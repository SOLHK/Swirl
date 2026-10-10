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
                            Text { text:"连接控制"; color:Theme.muted; font.pixelSize:11; font.letterSpacing:1.2; Layout.fillWidth:true }
                            SwirlStatusBadge { label:AppState.proxyOn?"模拟已开启":"未连接"; tone:AppState.proxyOn?"success":"neutral" }
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
                                Text { text:AppState.proxyOn?"模拟连接已开启":"随时准备连接"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                                Text { text:"当前为界面演示，不会更改 Windows 代理设置。"; color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                            }
                            SwirlToggle {
                                checked:AppState.proxyOn
                                onToggled:{
                                    AppState.proxyOn=checked
                                    AppState.notice("代理预览"+(checked?"已启用":"已关闭"))
                                }
                            }
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        RowLayout {
                            Layout.fillWidth:true
                            spacing:18
                            Text { text:"模式"; color:Theme.muted; font.pixelSize:11 }
                            SwirlComboBox {
                                model:["规则","全局","直连"]
                                currentIndex:Math.max(0,model.indexOf(AppState.mode))
                                onActivated:AppState.mode=currentText
                            }
                            Text { text:"策略"; color:Theme.muted; font.pixelSize:11 }
                            SwirlComboBox {
                                Layout.fillWidth:true
                                model:["自动选择","新加坡节点","直连","拒绝"]
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
                        Text { text:"当前节点"; color:Theme.muted; font.pixelSize:11; font.letterSpacing:1.2 }
                        Text { text:AppState.selectedNode; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                        Text { text:"Trojan · 演示线路"; color:Theme.muted; font.pixelSize:12 }
                        Item { Layout.fillHeight:true }
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlStatusBadge { label:"38 ms · 模拟"; tone:"success" }
                            Item { Layout.fillWidth:true }
                            SwirlButton { text:"切换"; iconName:"route"; onClicked:AppState.currentPage="proxies" }
                        }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true
                columns:page.width>1120?4:2
                rowSpacing:14; columnSpacing:14
                SwirlMetricCard { Layout.fillWidth:true; label:"下载速度"; value:"8.42 MB/s"; secondary:"演示数据"; iconName:"activity" }
                SwirlMetricCard { Layout.fillWidth:true; label:"上传速度"; value:"1.26 MB/s"; secondary:"演示数据"; iconName:"chart" }
                SwirlMetricCard { Layout.fillWidth:true; label:"活动连接"; value:"42"; secondary:"模拟连接"; iconName:"network" }
                SwirlMetricCard { Layout.fillWidth:true; label:"总流量"; value:"2.84 GB"; secondary:"演示会话流量"; iconName:"layers" }
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
                            Text { text:"流量趋势"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                            Text { text:"最近 60 分钟 · 模拟数据"; color:Theme.muted; font.pixelSize:11 }
                        }
                        SwirlStatusBadge { label:"● 下载"; tone:"accent" }
                        SwirlStatusBadge { label:"● 上传"; tone:"success" }
                        SwirlButton { text:"详细数据"; onClicked:AppState.currentPage="traffic" }
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
                        Text { text:"最近网络事件"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
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
                        Text { text:"快捷控制"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:"系统代理"; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true }
                            SwirlToggle { checked:AppState.systemProxyOn; onToggled:{AppState.systemProxyOn=checked;AppState.notice("系统代理")} }
                        }
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:"TUN 模式"; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true }
                            SwirlToggle { checked:AppState.tunOn; onToggled:{AppState.tunOn=checked;AppState.notice("TUN 模式")} }
                        }
                        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                        SwirlButton { Layout.fillWidth:true; text:"打开 HTTP 检查器"; iconName:"inspect"; onClicked:AppState.currentPage="inspector" }
                        SwirlButton { Layout.fillWidth:true; text:"检查 DNS"; iconName:"server"; onClicked:AppState.currentPage="dns" }
                    }
                }
            }
            Item { Layout.preferredHeight:15 }
        }
    }
}