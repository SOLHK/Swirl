import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    readonly property real overviewHeight:Math.max(798,height)
    readonly property real unit:(overviewHeight-3*Theme.gap)/756
    function scrollToBottom() { scroll.contentItem.contentY=Math.max(0,scroll.contentItem.contentHeight-scroll.contentItem.height) }
    ScrollView {
        id:scroll; anchors.fill:parent; clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth; spacing:Theme.gap
            RowLayout {
                Layout.fillWidth:true; Layout.preferredHeight:176*page.unit; spacing:Theme.gap
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:756; Layout.fillHeight:true
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:page.width<1000 ? 18 : 23; spacing:page.width<1000 ? 14 : 18
                        RowLayout {
                            Layout.fillWidth:true; spacing:page.width<1000 ? 14 : 21
                            Rectangle {
                                width:page.width<1000 ? 58 : 74; height:width; radius:Theme.pillRadius(height); color:Theme.withAlpha(Theme.accent,0.1)
                                SwirlIcon { name:"globe"; size:44; color:Theme.accent; anchors.centerIn:parent }
                            }
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:4
                                Text { text:AppState.proxyOn ? "演示连接已开启" : "随时准备连接"; color:Theme.text; font.pixelSize:page.width<1000 ? 22 : 26; font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                                Text { text:"点击右侧开关即可连接，当前为界面演示，不会更改系统代理。"; color:Theme.muted; font.pixelSize:page.width<1000 ? 14 : 16; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                            }
                            SwirlToggle { objectName:"connectionSwitch"; large:true; implicitWidth:page.width<1000 ? 68 : 86; implicitHeight:page.width<1000 ? 38 : 46; checked:AppState.proxyOn; onToggled:AppState.setConnection(checked); Accessible.name:"演示连接开关" }
                        }
                        RowLayout {
                            Layout.fillWidth:true; spacing:24
                            Text { text:"模式"; color:Theme.muted; font.pixelSize:17; font.weight:Font.DemiBold }
                            SwirlComboBox {
                                objectName:"modeCombo"; Layout.fillWidth:true; Layout.preferredWidth:220
                                model:["规则","全局","直连"]; currentIndex:Math.max(0,model.indexOf(AppState.mode))
                                onActivated:{AppState.mode=currentText;AppState.addEvent("演示模式切换到 "+currentText,"accent")}
                                Accessible.name:"模式选择"
                            }
                            Text { text:"策略"; color:Theme.muted; font.pixelSize:17; font.weight:Font.DemiBold }
                            SwirlComboBox {
                                objectName:"policyCombo"; Layout.fillWidth:true; Layout.preferredWidth:340
                                model:["自动选择","新加坡节点","直连","拒绝"]; currentIndex:Math.max(0,model.indexOf(AppState.policy))
                                onActivated:{AppState.policy=currentText;AppState.addEvent("演示策略切换到 "+currentText,"accent")}
                                Accessible.name:"策略选择"
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:408; Layout.fillHeight:true
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:20; spacing:9
                        Text { text:"当前节点"; color:Theme.muted; font.pixelSize:17; font.weight:Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth:true; spacing:19
                            SwirlRegionBadge { region:AppState.selectedNodeRegion }
                            ColumnLayout {
                                Layout.fillWidth:true; spacing:3
                                Text { text:AppState.selectedNode; color:Theme.text; font.pixelSize:23; font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                                Text { text:AppState.selectedNodeProtocol+" · 演示线路"; color:Theme.muted; font.pixelSize:17 }
                            }
                            Button { implicitWidth:24; implicitHeight:32; background:Item{} contentItem:SwirlIcon{name:"chevron-right";size:18} onClicked:nodePicker.open(); Accessible.name:"选择演示节点" }
                        }
                        RowLayout {
                            Layout.fillWidth:true
                            Rectangle {
                                width:page.width<1000 ? 112 : 130; height:36; radius:Theme.pillRadius(height); color:Theme.withAlpha(Theme.green,0.1)
                                Text { anchors.centerIn:parent; text:AppState.selectedNodeLatency>0 ? "历史 "+AppState.selectedNodeLatency+" ms · 演示" : "尚未检测 · 演示"; color:Theme.green; font.pixelSize:page.width<1000 ? 12 : 14 }
                            }
                            Item { Layout.fillWidth:true }
                            SwirlButton { objectName:"nodePickerButton"; text:"切换节点"; iconName:"refresh"; implicitHeight:44; font.pixelSize:page.width<1000 ? 15 : 17; onClicked:nodePicker.open() }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth:true; Layout.preferredHeight:142*page.unit; spacing:Theme.gap
                SwirlMetricCard { objectName:"downloadMetric"; Layout.fillWidth:true; Layout.fillHeight:true; label:"下载速度"; value:AppState.proxyOn ? AppState.demoDown.toFixed(2)+" MB/s" : "0 KB/s"; iconName:"download" }
                SwirlMetricCard { Layout.fillWidth:true; Layout.fillHeight:true; label:"上传速度"; value:AppState.proxyOn ? AppState.demoUp.toFixed(2)+" MB/s" : "0 KB/s"; iconName:"upload"; chartColor:Theme.green }
                SwirlMetricCard { Layout.fillWidth:true; Layout.fillHeight:true; label:"活动连接"; value:String(AppState.demoConnections); iconName:"user"; chartColor:Theme.muted; bars:true }
                SwirlMetricCard { Layout.fillWidth:true; Layout.fillHeight:true; label:"总流量"; value:AppState.totalGB.toFixed(2)+" GB"; iconName:"layers"; chartColor:Theme.muted }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.preferredHeight:196*page.unit
                ColumnLayout {
                    anchors.fill:parent; anchors.leftMargin:25; anchors.rightMargin:20; anchors.topMargin:11; anchors.bottomMargin:6; spacing:15
                    RowLayout {
                        Layout.fillWidth:true; spacing:page.width<950 ? 12 : 30
                        Text { text:"流量趋势"; color:Theme.text; font.pixelSize:20; font.weight:Font.DemiBold }
                        SwirlSegmentedControl { objectName:"seriesSelector"; id:seriesSelector; accentSelection:true; implicitWidth:page.width<950 ? 210 : 295 }
                        Item { Layout.fillWidth:true }
                        SwirlSegmentedControl { objectName:"rangeSelector"; id:rangeSelector; options:["实时","1小时","6小时","24小时"]; implicitWidth:page.width<950 ? 275 : 335 }
                    }
                    SwirlTrafficChart {
                        objectName:"overviewChart"; Layout.fillWidth:true; Layout.fillHeight:true
                        series:["down","up","total"][seriesSelector.currentIndex]; rangeIndex:rangeSelector.currentIndex
                    }
                }
            }
            GridLayout {
                columns:page.width<1000 ? 1 : 3
                Layout.fillWidth:true; Layout.preferredHeight:(columns===1 ? 726 : 242)*page.unit
                rowSpacing:Theme.gap; columnSpacing:Theme.gap
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:418; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit
                    ColumnLayout {
                        anchors.fill:parent; anchors.leftMargin:25; anchors.rightMargin:22; anchors.topMargin:13; anchors.bottomMargin:13; spacing:0
                        SwirlListRow { Layout.fillWidth:true; Layout.preferredHeight:38; iconName:"clock"; title:"最近网络事件"; onClicked:AppState.navigate("logs"); contentItem:RowLayout{spacing:24;SwirlIcon{name:"clock";size:29;color:Theme.accent} Text{text:"最近网络事件";font.pixelSize:19;font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true}SwirlIcon{name:"chevron-right";size:19}} }
                        Repeater {
                            model:AppState.recentEvents
                            delegate:Item {
                                required property var modelData
                                Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:33
                                Rectangle { x:51; width:parent.width-51; height:1; color:Theme.border; opacity:0.65 }
                                RowLayout {
                                    anchors.fill:parent; spacing:27
                                    Rectangle { width:16; height:16; radius:Theme.pillRadius(height); color:modelData.tone==="success" ? Theme.green : modelData.tone==="accent" ? Theme.red : "#99A5BF" }
                                    Text { text:modelData.time; color:Theme.muted; font.pixelSize:16; Layout.preferredWidth:54 }
                                    Text { text:modelData.title; color:Theme.muted; font.pixelSize:15; Layout.fillWidth:true; elide:Text.ElideRight }
                                }
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:355; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit
                    ColumnLayout {
                        anchors.fill:parent; anchors.leftMargin:25; anchors.rightMargin:24; anchors.topMargin:13; anchors.bottomMargin:26; spacing:0
                        RowLayout {
                            Layout.fillWidth:true; Layout.preferredHeight:38; spacing:25
                            SwirlIcon { name:"bolt"; size:29; color:Theme.accent }
                            Text { text:"快捷操作"; font.pixelSize:19; font.weight:Font.DemiBold; color:Theme.text; Layout.fillWidth:true }
                            SwirlIcon { name:"chevron-right"; size:19 }
                        }
                        Repeater {
                            model:[{title:"打开系统代理",icon:"globe",kind:0},{title:"全局代理",icon:"shield",kind:1},{title:"规则模式",icon:"document",kind:2},{title:"自动切换节点",icon:"refresh",kind:3}]
                            delegate:Item {
                                required property var modelData
                                Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:38
                                Rectangle { x:51; width:parent.width-51; height:1; color:Theme.border; opacity:0.65 }
                                RowLayout {
                                    anchors.fill:parent; spacing:25
                                    SwirlIcon { name:modelData.icon; size:25 }
                                    Text { text:modelData.title; color:Theme.muted; font.pixelSize:16; Layout.fillWidth:true; elide:Text.ElideRight }
                                    SwirlToggle {
                                        checked:modelData.kind===0 ? AppState.systemProxyOn : modelData.kind===1 ? AppState.mode==="全局" : modelData.kind===2 ? AppState.mode==="规则" : AppState.autoSwitch
                                        onToggled:{
                                            if(modelData.kind===0)AppState.systemProxyOn=checked
                                            else if(modelData.kind===1)AppState.mode=checked?"全局":"规则"
                                            else if(modelData.kind===2)AppState.mode=checked?"规则":"直连"
                                            else AppState.autoSwitch=checked
                                            AppState.toast="仅切换演示选项，不会更改系统网络设置。"
                                        }
                                        Accessible.name:modelData.title+"（演示）"
                                    }
                                }
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:378; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit
                    ColumnLayout {
                        anchors.fill:parent; anchors.leftMargin:25; anchors.rightMargin:24; anchors.topMargin:13; anchors.bottomMargin:13; spacing:0
                        RowLayout {
                            Layout.fillWidth:true; Layout.preferredHeight:38; spacing:25
                            SwirlIcon { name:"grid"; size:29; color:Theme.accent }
                            Text { text:"常用工具"; font.pixelSize:19; font.weight:Font.DemiBold; color:Theme.text; Layout.fillWidth:true }
                        }
                        Repeater {
                            model:[{title:"网络检测",icon:"gauge",page:"toolbox"},{title:"HTTP 检查器",icon:"code",page:"inspector"},{title:"流量统计",icon:"bars",page:"traffic"},{title:"脚本与配置",icon:"terminal",page:"scripts"},{title:"导入配置文件",icon:"folder",page:"profiles"}]
                            delegate:SwirlListRow {
                                required property var modelData
                                objectName:modelData.page==="profiles" ? "importConfigRow" : ""
                                Layout.fillWidth:true; Layout.fillHeight:true; Layout.minimumHeight:33
                                iconName:modelData.icon; title:modelData.title; onClicked:AppState.navigate(modelData.page)
                            }
                        }
                    }
                }
            }
        }
    }
    Popup {
        id:nodePicker; objectName:"nodePicker"; anchors.centerIn:Overlay.overlay
        width:420; padding:22; modal:true; focus:true
        background:SwirlGlassPanel { material:"floating" }
        contentItem:ColumnLayout {
            spacing:12
            Text { text:"选择演示节点"; font.pixelSize:22; font.weight:Font.DemiBold; color:Theme.text }
            Text { text:"仅更改界面选择，不会建立真实网络连接。"; font.pixelSize:14; color:Theme.muted }
            Repeater {
                model:[{name:"新加坡 · 01",region:"SG",protocol:"Trojan",latency:38},{name:"香港 · 01",region:"HK",protocol:"Hysteria2",latency:52},{name:"东京 · 01",region:"JP",protocol:"Trojan",latency:66}]
                SwirlButton { required property var modelData; objectName:modelData.region==="HK" ? "hongKongNode" : ""; Layout.fillWidth:true; text:modelData.name; primary:AppState.selectedNode===modelData.name; onClicked:{AppState.selectNode(modelData);nodePicker.close()} }
            }
            SwirlButton { text:"取消"; Layout.alignment:Qt.AlignRight; onClicked:nodePicker.close() }
        }
    }
}
