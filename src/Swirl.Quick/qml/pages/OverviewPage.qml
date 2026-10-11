import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    readonly property bool wide: width >= 1000
    readonly property bool medium: width >= 820
    property var network: demoProvider.currentNetwork()
    property bool showDetails: false
    readonly property real scrollOffset: scroll.contentItem ? scroll.contentItem.contentY : 0
    property int speedRange: 0
    readonly property var apps: [
        {name:"Edge",mark:"E",color:"#0078D4",value:"428.6 MB",percent:"34.5%"},
        {name:"微信",mark:"微",color:"#00A547",value:"298.4 MB",percent:"24.0%"},
        {name:"Steam",mark:"S",color:"#25476B",value:"128.9 MB",percent:"10.4%"},
        {name:"GitHub Desktop",mark:"G",color:"#8328B6",value:"74.6 MB",percent:"6.0%"},
        {name:"其他应用",mark:"···",color:"#6D7480",value:"312.1 MB",percent:"25.1%"}]
    readonly property var domains: [
        {name:"youtube.com",mark:"▶",color:"#EA1717",value:"320.4 MB",percent:"25.8%"},
        {name:"google.com",mark:"G",color:"#4285F4",value:"298.1 MB",percent:"24.0%"},
        {name:"github.com",mark:"G",color:"#17181B",value:"128.9 MB",percent:"10.4%"},
        {name:"openai.com",mark:"O",color:"#17181B",value:"96.3 MB",percent:"7.8%"},
        {name:"其他域名",mark:"···",color:"#6D7480",value:"398.9 MB",percent:"32.0%"}]
    function periodValue(value, index) {
        return index===0 ? value : (parseFloat(value)*(index===1?0.78:4.6)).toFixed(1)+" MB"
    }
    function scrollToBottom() { scroll.contentItem.contentY=Math.max(0,scroll.contentItem.contentHeight-scroll.contentItem.height) }
    Timer { interval:10000; repeat:true; running:true; onTriggered:page.network=demoProvider.currentNetwork() }
    component Glyph: Rectangle {
        property string icon: "globe"
        property color tint: Theme.accent
        implicitWidth: 48; implicitHeight: 48
        width:48; height:48; radius:width/2
        color:Theme.withAlpha(tint,0.08)
        SwirlIcon { anchors.centerIn:parent; name:parent.icon; size:28; color:parent.tint }
    }
    component Card: SwirlGlassPanel {
        id: card
        property string heading: ""
        property string actionText: ""
        property var filters: []
        property alias filterIndex: filter.currentIndex
        default property alias body: bodyItem.data
        signal action()
        data: [Item {
            anchors.fill:parent; anchors.margins:Theme.cardPadding
            RowLayout {
                id:cardHeader; width:parent.width; height:24; spacing:8
                Text { text:card.heading; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                SwirlComboBox { id:filter; visible:card.filters.length>0; model:card.filters; implicitWidth:card.heading==="实时速度"?138:88; implicitHeight:28; font.pixelSize:13; leftPadding:8; rightPadding:22; Accessible.name:card.heading+"时间范围" }
                Button { visible:card.actionText.length>0; text:card.actionText; padding:0; implicitHeight:24; font.pixelSize:13; palette.buttonText:Theme.muted; background:Rectangle{radius:Theme.roundedRadius(width,height);color:parent.hovered?Theme.hover:"transparent"} onClicked:card.action(); Accessible.name:card.heading+" "+text }
            }
            Item { id:bodyItem; anchors.top:cardHeader.bottom; anchors.topMargin:10; anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom }
        }]
    }
    component Ranking: Card {
        id:ranking
        property var rows: []
        property string destination: "traffic"
        filters:["今日","昨日","本周"]
        Column {
            anchors.fill:parent; spacing:0
            Repeater {
                model:ranking.rows
                Button {
                    required property var modelData
                    width:parent.width; height:parent.height/5; padding:0; hoverEnabled:true
                    background:Rectangle { radius:Theme.roundedRadius(width,height); color:parent.hovered?Theme.hover:"transparent" }
                    contentItem:RowLayout {
                        spacing:10
                        Rectangle { width:23;height:23;radius:width/2;color:modelData.color
                            Text { anchors.centerIn:parent;text:modelData.mark;color:"white";font.pixelSize:13;font.weight:Font.Bold }
                        }
                        Text { text:modelData.name;color:Theme.text;font.pixelSize:14;Layout.fillWidth:true;elide:Text.ElideRight }
                        Text { text:page.periodValue(modelData.value,ranking.filterIndex);color:Theme.muted;font.family:"Segoe UI";font.pixelSize:13;Layout.preferredWidth:74;horizontalAlignment:Text.AlignRight }
                        Text { text:modelData.percent;color:Theme.muted;font.family:"Segoe UI";font.pixelSize:13;Layout.preferredWidth:42;horizontalAlignment:Text.AlignRight }
                        SwirlIcon { name:"chevron-right";size:14 }
                    }
                    onClicked:AppState.navigate("traffic")
                    Accessible.name:modelData.name+"，演示流量 "+modelData.value+"，"+modelData.percent
                    Rectangle { anchors.bottom:parent.bottom; x:33; width:parent.width-33;height:1;color:Theme.border;opacity:0.55 }
                }
            }
        }
    }
    ScrollView {
        id:scroll; objectName:"overviewScroll"; anchors.fill:parent;clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth;spacing:Theme.gap
            RowLayout {
                Layout.fillWidth:true;Layout.preferredHeight:66
                ColumnLayout {
                    Layout.fillWidth:true;spacing:1
                    Text { text:"总览";color:Theme.text;font.pixelSize:38;font.weight:Font.Bold;Accessible.role:Accessible.Heading }
                    Text { text:"实时状态、连接信息与系统设置";color:Theme.muted;font.pixelSize:17;Layout.fillWidth:true;elide:Text.ElideRight }
                }
                Text { text:"界面演示";color:Theme.orange;font.pixelSize:12 }
                SwirlButton { objectName:"connectionSwitch";text:AppState.proxyOn?"断开演示":"连接演示";implicitHeight:32;implicitWidth:100;font.pixelSize:13;onClicked:AppState.setConnection(!AppState.proxyOn);Accessible.name:text+"，不会更改系统代理" }
            }
            GridLayout {
                Layout.fillWidth:true;columns:page.wide?6:3;columnSpacing:8;rowSpacing:Theme.gap
                Repeater {
                    model:[
                        {label:"当前网络",value:page.network.type,sub:page.network.name,icon:"wifi",route:"toolbox",tint:Theme.accent},
                        {label:"当前配置",value:"Default.conf",sub:"3 条规则 · 演示",icon:"document",route:"profiles",tint:Theme.accent},
                        {label:"出站模式",value:AppState.mode,sub:"根据策略组分流 · 演示",icon:"code",route:"rules",tint:Theme.green},
                        {label:"活跃连接",value:String(AppState.demoConnections),sub:"条连接 · 演示",icon:"link",route:"connections",tint:Theme.accent},
                        {label:"活跃进程",value:AppState.proxyOn?"6":"0",sub:"个进程 · 演示",icon:"settings",route:"processes",tint:Theme.accent},
                        {label:"今日流量",value:AppState.proxyOn?AppState.totalGB.toFixed(2)+" GB":"0 B",sub:"流量统计 · 演示",icon:"clock",route:"traffic",tint:Theme.accent}]
                    Button {
                        required property var modelData
                        Layout.fillWidth:true;Layout.preferredHeight:90;Layout.minimumWidth:0;hoverEnabled:true;padding:10
                        background:SwirlGlassPanel { color:parent.hovered?Theme.raised:Theme.surface }
                        contentItem:RowLayout {
                            spacing:9
                            Glyph { icon:modelData.icon;tint:modelData.tint;implicitWidth:40;implicitHeight:40;width:40;height:40 }
                            ColumnLayout {
                                Layout.fillWidth:true;spacing:2
                                Text { text:modelData.label;color:Theme.muted;font.pixelSize:13;Layout.fillWidth:true;elide:Text.ElideRight }
                                Text { text:modelData.value;color:Theme.text;font.family:"Segoe UI";font.pixelSize:18;font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight }
                                Text { text:modelData.sub;color:Theme.muted;font.pixelSize:11;Layout.fillWidth:true;elide:Text.ElideRight }
                            }
                        }
                        onClicked:AppState.navigate(modelData.route)
                        Accessible.name:modelData.label+" "+modelData.value+" "+modelData.sub
                        ToolTip.visible:hovered;ToolTip.text:modelData.label+"："+modelData.value+" · "+modelData.sub
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true;columns:page.wide?2:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
                Card {
                    heading:"网络延迟";actionText:"演示 · 详情 ›";onAction:AppState.navigate("toolbox")
                    Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.preferredHeight:158
                    RowLayout {
                        anchors.fill:parent;spacing:8
                        Repeater {
                            model:[{label:"互联网延迟",value:28,icon:"globe",tint:Theme.accent},{label:"路由器延迟",value:4,icon:"router",tint:Theme.green},{label:"DNS 延迟",value:12,icon:"network",tint:Theme.accent},{label:"代理延迟",value:AppState.selectedNodeLatency,icon:"bolt",tint:Theme.orange}]
                            Item {
                                required property var modelData
                                Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumWidth:0
                                RowLayout {
                                    width:parent.width;spacing:6
                                    Glyph { icon:modelData.icon;tint:modelData.tint;implicitWidth:40;implicitHeight:40;width:40;height:40 }
                                    ColumnLayout {
                                        spacing:4;Layout.fillWidth:true
                                        Text { text:modelData.label;color:Theme.muted;font.pixelSize:12;Layout.fillWidth:true;elide:Text.ElideRight }
                                        Text { text:modelData.value+" ms";color:Theme.text;font.family:"Segoe UI";font.pixelSize:22;font.weight:Font.DemiBold }
                                    }
                                }
                                Rectangle { x:42;y:62;width:50;height:26;radius:Theme.roundedRadius(width,height);color:Theme.withAlpha(Theme.green,0.10)
                                    Text { anchors.centerIn:parent;text:"示例";color:Theme.green;font.pixelSize:12 }
                                }
                            }
                        }
                    }
                }
                Card {
                    heading:"实时速度";filters:["最近 1 分钟","最近 5 分钟","最近 1 小时"]
                    objectName:"speedPanel";Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.preferredHeight:158
                    onFilterIndexChanged:page.speedRange=filterIndex
                    RowLayout {
                        anchors.fill:parent;spacing:20
                        Repeater {
                            model:[{label:"下载速度",up:false,icon:"download",tint:Theme.accent},{label:"上传速度",up:true,icon:"upload",tint:Theme.green}]
                            Item {
                                id:metric;required property var modelData
                                objectName:modelData.up?"uploadMetric":"downloadMetric"
                                property string value:AppState.proxyOn?(modelData.up?AppState.demoUp:AppState.demoDown).toFixed(1)+" MB/s":"0 KB/s"
                                Layout.fillWidth:true;Layout.fillHeight:true
                                RowLayout {
                                    width:parent.width;spacing:10
                                    Glyph { icon:modelData.icon;tint:modelData.tint;implicitWidth:44;implicitHeight:44;width:44;height:44 }
                                    Column {
                                        Layout.fillWidth:true;spacing:2
                                        Text { text:metric.modelData.label;color:Theme.muted;font.pixelSize:12 }
                                        Text { text:metric.value;color:Theme.text;font.family:"Segoe UI";font.pixelSize:24;font.weight:Font.DemiBold }
                                    }
                                }
                                Text { x:0;y:55;text:AppState.proxyOn?"演示":"未连接";font.pixelSize:11;color:Theme.muted }
                                SwirlSparkline { x:44;y:54;width:parent.width-44;height:42;lineColor:metric.modelData.tint;active:AppState.proxyOn;values:AppState.proxyOn?(page.speedRange===0?[0.18,0.65,0.25,0.56,0.3,0.85,0.52,0.73]:page.speedRange===1?[0.2,0.4,0.65,0.6,0.8,0.6,0.4,0.9]:[0.5,0.3,0.6,0.25,0.85,0.5,0.35,0.6]):[0,0,0,0,0,0,0,0] }
                                Accessible.name:metric.modelData.label+" "+value+"，演示数据"
                            }
                        }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true;columns:page.wide?3:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
                Card {
                    id:distribution;heading:"流量分布";filters:["今日","昨日","本周"];Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.preferredHeight:198
                    ColumnLayout {
                        anchors.fill:parent;spacing:5
                        Rectangle {
                            Layout.fillWidth:true;Layout.preferredHeight:22;radius:Theme.roundedRadius(width,height);color:Theme.raised;clip:true
                            Canvas { anchors.fill:parent; onPaint:{ var ctx=getContext("2d");ctx.reset();var r=height/2;ctx.beginPath();ctx.moveTo(r,0);ctx.lineTo(width-r,0);ctx.arc(width-r,r,r,-Math.PI/2,Math.PI/2);ctx.lineTo(r,height);ctx.arc(r,r,r,Math.PI/2,Math.PI*1.5);ctx.closePath();ctx.clip();ctx.fillStyle=Theme.accent;ctx.fillRect(0,0,width*0.682,height);ctx.fillStyle=Theme.statusGreen;ctx.fillRect(width*0.682,0,width*0.241,height);ctx.fillStyle="#FFA326";ctx.fillRect(width*0.923,0,width*0.047,height) } }
                        }
                        Repeater {
                            model:[{name:"代理流量",percent:"68.2%",value:"845.6 MB",tint:Theme.accent},{name:"直连流量",percent:"24.1%",value:"298.4 MB",tint:Theme.statusGreen},{name:"阻止流量",percent:"4.7%",value:"58.1 MB",tint:"#FFA326"},{name:"其他流量",percent:"3.0%",value:"37.9 MB",tint:Theme.muted}]
                            RowLayout {
                                required property var modelData
                                Layout.fillWidth:true;Layout.fillHeight:true;spacing:10
                                Rectangle { width:12;height:12;radius:width/2;color:modelData.tint }
                                Text { text:modelData.name;color:Theme.text;font.pixelSize:14;Layout.fillWidth:true }
                                Text { text:modelData.percent;color:Theme.text;font.family:"Segoe UI";font.pixelSize:14;Layout.preferredWidth:46;horizontalAlignment:Text.AlignRight }
                                Text { text:page.periodValue(modelData.value,distribution.filterIndex);color:Theme.muted;font.family:"Segoe UI";font.pixelSize:13;Layout.preferredWidth:86;horizontalAlignment:Text.AlignRight }
                            }
                        }
                    }
                }
                Ranking { heading:"应用流量排行";rows:page.apps;Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.preferredHeight:198 }
                Ranking { heading:"域名流量排行";rows:page.domains;Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.preferredHeight:198 }
            }
            GridLayout {
                Layout.fillWidth:true;columns:page.medium?3:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
                ColumnLayout {
                    Layout.columnSpan:page.medium?2:1;Layout.fillWidth:true;Layout.preferredWidth:2;Layout.minimumWidth:0;spacing:Theme.gap
                    Card {
                        heading:"当前代理";actionText:AppState.connectionState;onAction:AppState.toast="Qt 代理核心尚未接入；当前界面仅演示。"
                        objectName:"currentProxyPanel";Layout.fillWidth:true;Layout.preferredHeight:146
                        ColumnLayout {
                            anchors.fill:parent;spacing:6
                            Button {
                                id:nodeButton;objectName:"nodePickerButton";Layout.fillWidth:true;Layout.preferredHeight:54;padding:0;hoverEnabled:true
                                background:Rectangle { radius:Theme.roundedRadius(width,height);color:parent.hovered?Theme.hover:"transparent";border.width:parent.activeFocus?2:0;border.color:Theme.focusBorder }
                                contentItem:RowLayout {
                                    spacing:12;Glyph { icon:"globe" }
                                    ColumnLayout {
                                        Layout.fillWidth:true;spacing:2
                                        Text { text:AppState.policy+"（示例）";color:Theme.text;font.pixelSize:18;font.weight:Font.DemiBold }
                                        Text { text:AppState.selectedNode+" · "+AppState.selectedNodeProtocol+" · 演示数据";color:Theme.muted;font.pixelSize:13;Layout.fillWidth:true;elide:Text.ElideRight }
                                    }
                                    SwirlIcon { name:"chevron-right";size:18 }
                                }
                                onClicked:nodePicker.open();Accessible.name:"切换演示节点，当前 "+AppState.selectedNode
                            }
                            RowLayout {
                                Layout.fillWidth:true;spacing:8
                                Text { text:"模式";color:Theme.muted;font.pixelSize:13 }
                                SwirlComboBox { objectName:"modeCombo";Layout.fillWidth:true;Layout.minimumWidth:0;implicitHeight:32;font.pixelSize:13;model:["规则","全局","直连"];currentIndex:Math.max(0,model.indexOf(AppState.mode));onActivated:AppState.mode=currentText;Accessible.name:"模式选择" }
                                Text { text:"策略";color:Theme.muted;font.pixelSize:13 }
                                SwirlComboBox { objectName:"policyCombo";Layout.fillWidth:true;Layout.minimumWidth:0;implicitHeight:32;font.pixelSize:13;model:["自动选择","新加坡节点","直连","拒绝"];currentIndex:Math.max(0,model.indexOf(AppState.policy));onActivated:AppState.policy=currentText;Accessible.name:"策略选择" }
                                SwirlButton { text:AppState.selectedNode;Layout.fillWidth:true;Layout.minimumWidth:0;implicitHeight:32;font.pixelSize:13;onClicked:nodePicker.open();Accessible.name:"当前节点 "+text }
                            }
                        }
                    }
                    Card {
                        heading:"最近连接";actionText:"演示 · 查看更多 ›";onAction:AppState.navigate("connections");Layout.fillWidth:true;Layout.preferredHeight:164
                        Column {
                            anchors.fill:parent;spacing:0
                            Rectangle {
                                width:parent.width;height:24;radius:Theme.roundedRadius(width,height);color:Theme.raised
                                Row {
                                    anchors.fill:parent;anchors.leftMargin:8
                                    Repeater { model:[{name:"时间",ratio:0.11},{name:"目标地址",ratio:0.25},{name:"类型",ratio:0.08},{name:"进程",ratio:0.18},{name:"代理节点",ratio:0.17},{name:"延迟",ratio:0.10},{name:"流量",ratio:0.11}]
                                        Text { required property var modelData;width:(parent.width-8)*modelData.ratio;height:24;text:modelData.name;color:Theme.muted;font.pixelSize:11;verticalAlignment:Text.AlignVCenter }
                                    }
                                }
                            }
                            Repeater {
                                model:demoProvider.connections().slice(0,3)
                                Button {
                                    required property var modelData;width:parent.width;height:(parent.height-24)/3;padding:0
                                    background:Rectangle { color:parent.hovered?Theme.hover:"transparent";radius:Theme.roundedRadius(width,height) }
                                    contentItem:Row {
                                        leftPadding:8
                                        Repeater { model:[{value:modelData.time,ratio:0.11},{value:modelData.host,ratio:0.25},{value:"代理",ratio:0.08},{value:modelData.process,ratio:0.18},{value:AppState.selectedNode,ratio:0.17},{value:modelData.latency,ratio:0.10},{value:modelData.down,ratio:0.11}]
                                            Text { required property var modelData;width:(parent.width-8)*modelData.ratio;height:parent.height;text:modelData.value;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:12;verticalAlignment:Text.AlignVCenter;elide:Text.ElideRight }
                                        }
                                    }
                                    onClicked:AppState.navigate("connections")
                                }
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;spacing:Theme.gap
                    Card {
                        objectName:"systemStatusPanel";heading:"系统状态";actionText:"演示";onAction:AppState.toast="这里的开关仅演示，不会修改 Windows 设置。";Layout.fillWidth:true;Layout.preferredHeight:172
                        ColumnLayout {
                            anchors.fill:parent;spacing:0
                            Repeater {
                                model:[{title:"系统代理",sub:"系统流量转发（演示）",icon:"layers",kind:0},{title:"增强模式（TUN）",sub:"网络接管（演示）",icon:"layers",kind:1},{title:"DNS",sub:"使用 DNS 解析",icon:"shield",kind:2}]
                                RowLayout {
                                    required property var modelData;Layout.fillWidth:true;Layout.fillHeight:true;spacing:12
                                    SwirlIcon { name:modelData.icon;size:22;color:Theme.text }
                                    ColumnLayout {
                                        Layout.fillWidth:true;spacing:0
                                        Text { text:modelData.title;color:Theme.text;font.pixelSize:14;font.weight:Font.DemiBold }
                                        Text { text:modelData.sub;color:Theme.muted;font.pixelSize:11;Layout.fillWidth:true;elide:Text.ElideRight }
                                    }
                                    SwirlToggle {
                                        objectName:modelData.kind===0?"systemProxyToggle":"tunToggle";visible:modelData.kind<2;implicitWidth:46;implicitHeight:26
                                        checked:modelData.kind===0?AppState.systemProxyOn:AppState.tunOn
                                        onToggled:{ if(checked&&!AppState.proxyOn)AppState.setConnection(true);if(modelData.kind===0)AppState.systemProxyOn=checked;else AppState.tunOn=checked;AppState.toast="仅切换演示状态，不会更改系统代理或 TUN。" }
                                        Accessible.name:modelData.title+"演示开关"
                                    }
                                    SwirlButton { visible:modelData.kind===2;text:"查看设置";implicitHeight:28;implicitWidth:84;font.pixelSize:12;onClicked:AppState.navigate("dns") }
                                }
                            }
                        }
                    }
                    Card {
                        heading:"快捷操作";Layout.fillWidth:true;Layout.preferredHeight:126
                        GridLayout {
                            anchors.fill:parent;columns:2;rowSpacing:6;columnSpacing:6
                            Repeater {
                                model:[{title:"测试代理延迟",icon:"gauge",route:"toolbox"},{title:"网络检测",icon:"activity",route:"toolbox"},{title:"导入订阅",icon:"document",route:"subscriptions"},{title:"打开设置",icon:"settings",route:"settings"}]
                                SwirlButton {
                                    required property var modelData;objectName:modelData.route==="subscriptions"?"importConfigRow":""
                                    Layout.fillWidth:true;Layout.minimumWidth:0;Layout.fillHeight:true;implicitHeight:34;implicitWidth:100;text:modelData.title;iconName:modelData.icon;font.pixelSize:13
                                    onClicked:AppState.navigate(modelData.route)
                                }
                            }
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth:true;spacing:8
                Text { text:"代理、延迟、流量及排名为演示数据；真实 HTTP 抓包可在工具中单独启动。";color:Theme.muted;font.pixelSize:12;Layout.fillWidth:true;wrapMode:Text.Wrap }
                SwirlButton { text:page.showDetails?"收起趋势":"更多趋势";implicitHeight:28;implicitWidth:76;font.pixelSize:12;onClicked:page.showDetails=!page.showDetails }
                SwirlButton { text:"全部工具";implicitHeight:28;implicitWidth:76;font.pixelSize:12;onClicked:AppState.navigate("featurehub") }
            }
            Card {
                visible:page.showDetails;heading:"流量趋势 · 演示历史";Layout.fillWidth:true;Layout.preferredHeight:240
                ColumnLayout {
                    anchors.fill:parent;spacing:12
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlSegmentedControl { id:seriesSelector;objectName:"seriesSelector";implicitWidth:210;accentSelection:true }
                        Item { Layout.fillWidth:true }
                        SwirlSegmentedControl { id:rangeSelector;objectName:"rangeSelector";options:["实时","1小时","6小时","24小时"];implicitWidth:275 }
                    }
                    SwirlTrafficChart { objectName:"overviewChart";Layout.fillWidth:true;Layout.fillHeight:true;series:["down","up","total"][seriesSelector.currentIndex];rangeIndex:rangeSelector.currentIndex }
                }
            }
        }
    }
    Popup {
        id:nodePicker;objectName:"nodePicker";anchors.centerIn:Overlay.overlay;width:420;padding:22;modal:true;focus:true
        background:SwirlGlassPanel { material:"floating" }
        contentItem:ColumnLayout {
            spacing:12
            Text { text:"选择演示节点";font.pixelSize:22;font.weight:Font.DemiBold;color:Theme.text }
            Text { text:"仅更改界面选择，不会建立真实网络连接。";font.pixelSize:14;color:Theme.muted }
            Repeater {
                model:[{name:"新加坡 · 01",region:"SG",protocol:"Trojan",latency:38},{name:"香港 · 01",region:"HK",protocol:"Hysteria2",latency:52},{name:"东京 · 01",region:"JP",protocol:"Trojan",latency:66}]
                SwirlButton { required property var modelData;objectName:modelData.region==="HK"?"hongKongNode":"";Layout.fillWidth:true;text:modelData.name;primary:AppState.selectedNode===modelData.name;onClicked:{AppState.selectNode(modelData);nodePicker.close()} }
            }
            SwirlButton { text:"取消";Layout.alignment:Qt.AlignRight;onClicked:nodePicker.close() }
        }
    }
}
