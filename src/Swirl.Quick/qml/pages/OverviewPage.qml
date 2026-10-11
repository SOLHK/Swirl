import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    readonly property real unit: 1
    function scrollToBottom() { scroll.contentItem.contentY = Math.max(0, scroll.contentItem.contentHeight - scroll.contentItem.height) }
    ScrollView {
        id: scroll; objectName: "overviewScroll"
        anchors.fill: parent; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ColumnLayout {
            width: scroll.availableWidth; spacing: Theme.gap
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 100; spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    Text { text: "总览"; color: Theme.text; font.pixelSize: 48; font.weight: Font.Bold; Accessible.role: Accessible.Heading }
                    Text { text: "实时状态、连接信息与系统设置"; color: Theme.muted; font.pixelSize: 21; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                Button {
                    id: connection; objectName: "connectionSwitch"
                    Layout.alignment: Qt.AlignTop; Layout.topMargin: 9
                    implicitWidth: page.width > 950 ? 398 : 330; implicitHeight: 48
                    hoverEnabled: true
                    background: Rectangle { radius: Theme.controlRadius; color: connection.down ? Theme.pressed : connection.hovered ? Theme.hover : Theme.surface; border.width: connection.activeFocus ? 2 : 1; border.color: connection.activeFocus ? Theme.focusBorder : Theme.border }
                    contentItem: RowLayout {
                        spacing: 12
                        Rectangle { width: 18; height: 18; radius: 9; color: AppState.proxyOn ? Theme.statusGreen : Theme.muted }
                        Text { text: AppState.proxyOn ? "演示代理运行中" : "演示代理未连接"; color: Theme.text; font.pixelSize: 17 }
                        Rectangle { width: 1; height: 24; color: Theme.border }
                        SwirlIcon { name: "clock"; size: 24; color: Theme.text }
                        Text { text: "节点延迟 " + AppState.selectedNodeLatency + " ms"; color: Theme.text; font.pixelSize: 17 }
                        SwirlIcon { name: "chevron-right"; size: 17 }
                    }
                    onClicked: AppState.setConnection(!AppState.proxyOn)
                    Accessible.name: (AppState.proxyOn ? "断开演示代理" : "连接演示代理") + "，历史节点延迟 " + AppState.selectedNodeLatency + " 毫秒"
                    ToolTip.visible: hovered
                    ToolTip.text: "连接或断开演示代理；延迟为上次演示值，不会更改系统代理。"
                }
            }
            SwirlGlassPanel {
                objectName: "speedPanel"
                Layout.fillWidth: true; Layout.preferredHeight: page.width < 760 ? 314 : 216
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 22; spacing: 15
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "实时速度"; color: Theme.text; font.pixelSize: 23; font.weight: Font.DemiBold }
                        Item { Layout.fillWidth: true }
                        Text { text: "示例数据，仅供参考"; color: Theme.muted; font.pixelSize: 15 }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    GridLayout {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        columns: page.width < 760 ? 1 : 2
                        rowSpacing: 18; columnSpacing: 28
                        Repeater {
                            model: [{label:"下载",icon:"download",up:false}, {label:"上传",icon:"upload",up:true}]
                            delegate: Item {
                                id: metric
                                required property var modelData
                                objectName: modelData.up ? "uploadMetric" : "downloadMetric"
                                property string value: AppState.proxyOn ? (modelData.up ? AppState.demoUp : AppState.demoDown).toFixed(1) + " MB/s" : "0 KB/s"
                                readonly property color tint: modelData.up ? Theme.green : Theme.speedAccent
                                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 104
                                Rectangle {
                                    id: directionIcon
                                    anchors.left: parent.left; anchors.leftMargin: 24
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 104; height: 104; radius: 52; color: Theme.withAlpha(metric.tint, 0.11)
                                    SwirlIcon { anchors.centerIn: parent; name: metric.modelData.icon; size: 58; color: metric.tint }
                                }
                                Column {
                                    anchors.left: directionIcon.right; anchors.leftMargin: 48
                                    anchors.verticalCenter: parent.verticalCenter; spacing: 2
                                    Text { text: metric.modelData.label; font.pixelSize: 20; color: Theme.text }
                                    Row {
                                        spacing: 10
                                        Text { text: metric.value.split(" ")[0]; font.family: "Segoe UI"; font.pixelSize: 62; font.weight: Font.DemiBold; color: metric.tint }
                                        Text { text: metric.value.split(" ")[1]; font.family: "Segoe UI"; font.pixelSize: 30; color: Theme.muted; anchors.verticalCenter: parent.verticalCenter }
                                    }
                                }
                                Rectangle { visible: metric.modelData.up && page.width >= 760; x: -14; y: 4; width: 1; height: parent.height - 8; color: Theme.border }
                                Accessible.name: metric.modelData.label + "速度 " + value + "，演示数据"
                            }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                objectName: "currentProxyPanel"
                Layout.fillWidth: true; Layout.preferredHeight: 180
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 10
                    Text { text: "当前代理"; color: Theme.text; font.pixelSize: 23; font.weight: Font.DemiBold }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    Button {
                        id: nodeButton; objectName: "nodePickerButton"; Layout.fillWidth: true; Layout.preferredHeight: 59
                        padding: 0; hoverEnabled: true
                        background: Rectangle { radius: Theme.controlRadius; color: nodeButton.hovered ? Theme.hover : "transparent"; border.width: nodeButton.activeFocus ? 2 : 0; border.color: Theme.focusBorder }
                        contentItem: RowLayout {
                            spacing: 28
                            Rectangle { width: 64; height: 64; radius: 32; color: Theme.raised; SwirlIcon { anchors.centerIn: parent; name: "globe"; size: 38; color: Theme.accent } }
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: 2
                                Text { text: AppState.policy + "（示例）"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold }
                                Text { text: AppState.selectedNode + " · " + AppState.selectedNodeProtocol + " · 演示线路"; color: Theme.muted; font.pixelSize: 16; Layout.fillWidth: true; elide: Text.ElideRight }
                            }
                            SwirlIcon { name: "chevron-right"; size: 22 }
                        }
                        onClicked: nodePicker.open()
                        Accessible.name: "切换演示节点，当前 " + AppState.selectedNode
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 14
                        Text { text: "模式"; color: Theme.muted; font.pixelSize: 14 }
                        SwirlComboBox { objectName: "modeCombo"; Layout.preferredWidth: 155; implicitHeight: 32; font.pixelSize: 14; model: ["规则","全局","直连"]; currentIndex: Math.max(0, model.indexOf(AppState.mode)); onActivated: { AppState.mode = currentText; AppState.addEvent("演示模式切换到 " + currentText, "accent") } Accessible.name: "模式选择" }
                        Text { text: "策略"; color: Theme.muted; font.pixelSize: 14 }
                        SwirlComboBox { objectName: "policyCombo"; Layout.preferredWidth: 205; implicitHeight: 32; font.pixelSize: 14; model: ["自动选择","新加坡节点","直连","拒绝"]; currentIndex: Math.max(0,model.indexOf(AppState.policy)); onActivated: { AppState.policy = currentText; AppState.addEvent("演示策略切换到 " + currentText, "accent") } Accessible.name: "策略选择" }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
            SwirlGlassPanel {
                objectName: "systemStatusPanel"
                Layout.fillWidth: true; Layout.preferredHeight: 304
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 0
                    Text { text: "系统状态"; color: Theme.text; font.pixelSize: 23; font.weight: Font.DemiBold; Layout.preferredHeight: 43 }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.border }
                    Repeater {
                        model: [{title:"系统代理",sub:"控制应用的网络访问方式（演示）",icon:"server",page:"settings",kind:0}, {title:"DNS",sub:"代理 DNS 解析",icon:"shield",page:"dns",kind:1}, {title:"网络连接",sub:"检测互联网连接状态（演示）",icon:"network",page:"toolbox",kind:2}]
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 20
                            SwirlIcon { name: modelData.icon; size: 32; color: Theme.text }
                            Button {
                                id: statusRow
                                Layout.fillWidth: true; Layout.fillHeight: true
                                padding: 0; hoverEnabled: true
                                background: Rectangle { radius: Theme.controlRadius; color: statusRow.hovered ? Theme.hover : "transparent"; border.width: statusRow.activeFocus ? 2 : 0; border.color: Theme.focusBorder }
                                contentItem: RowLayout {
                                    spacing: 20
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 2
                                        Text { text: modelData.title; color: Theme.text; font.pixelSize: 19; font.weight: Font.DemiBold }
                                        Text { text: modelData.sub; color: Theme.muted; font.pixelSize: 16; Layout.fillWidth: true; elide: Text.ElideRight }
                                    }
                                    Rectangle { visible: modelData.kind === 2; width: 14; height: 14; radius: 7; color: AppState.proxyOn ? Theme.statusGreen : Theme.muted }
                                    Text { text: modelData.kind === 0 ? (AppState.systemProxyOn ? "已开启" : "已关闭") : modelData.kind === 1 ? "查看设置" : (AppState.proxyOn ? "已连接" : "未连接"); color: Theme.muted; font.pixelSize: 17 }
                                    SwirlIcon { visible: modelData.kind !== 0; name: "chevron-right"; size: 20 }
                                }
                                onClicked: AppState.navigate(modelData.page)
                                Accessible.name: modelData.title + "，" + modelData.sub
                                Rectangle { visible: modelData.kind < 2; anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
                            }
                            SwirlToggle { visible: modelData.kind === 0; checked: AppState.systemProxyOn; implicitWidth: 64; implicitHeight: 36; onToggled: { AppState.systemProxyOn = checked; AppState.toast = "仅切换演示选项，不会更改系统网络设置。" } Accessible.name: "系统代理演示开关" }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.gap
                SwirlMetricCard { Layout.fillWidth: true; label: "活动连接"; value: String(AppState.demoConnections); iconName: "user"; chartColor: Theme.muted; bars: true }
                SwirlMetricCard { Layout.fillWidth: true; label: "总流量"; value: AppState.totalGB.toFixed(2) + " GB"; iconName: "layers"; chartColor: Theme.muted }
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
                    Layout.fillWidth:true; Layout.preferredWidth:418; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit; Layout.minimumWidth:0
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
                                    Text { text:modelData.title; color:Theme.muted; font.pixelSize:16; Layout.fillWidth:true; elide:Text.ElideRight }
                                }
                            }
                        }
                    }
                }
                SwirlGlassPanel {
                    Layout.fillWidth:true; Layout.preferredWidth:355; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit; Layout.minimumWidth:0
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
                                    Text { text:modelData.title; color:Theme.muted; font.pixelSize:17; Layout.fillWidth:true; elide:Text.ElideRight }
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
                    Layout.fillWidth:true; Layout.preferredWidth:378; Layout.fillHeight:true; Layout.preferredHeight:242*page.unit; Layout.minimumWidth:0
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
