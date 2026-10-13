import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id: page
    readonly property bool medium: width >= Theme.dp(700)
    property var network: systemProvider.currentNetwork()
    readonly property real scrollOffset: scroll.contentItem ? scroll.contentItem.contentY : 0
    function scrollToBottom() { scroll.contentItem.contentY=Math.max(0,scroll.contentItem.contentHeight-scroll.contentItem.height) }
    Timer { interval:10000; repeat:true; running:true; onTriggered:page.network=systemProvider.currentNetwork() }
    component Glyph: Rectangle {
        property string icon: "globe"
        property color tint: Theme.accent
        implicitWidth:Theme.dp(48); implicitHeight:Theme.dp(48)
        width:Theme.dp(48); height:Theme.dp(48); radius:width/2
        color:Theme.withAlpha(tint,0.08)
        SwirlIcon { anchors.centerIn:parent; name:parent.icon; size:Theme.dp(28); color:parent.tint }
    }
    component Card: SwirlGlassPanel {
        cornerRadius:Theme.cardRadius
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
                id:cardHeader; width:parent.width; height:Theme.dp(24); spacing:Theme.dp(8)
                Text { text:card.heading; color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold; Layout.fillWidth:true; elide:Text.ElideRight }
                SwirlComboBox { id:filter; visible:card.filters.length>0; model:card.filters; implicitWidth:Theme.dp(card.heading==="实时速度"?138:88); implicitHeight:Theme.dp(28); font.pixelSize:Theme.fontSize(13); leftPadding:Theme.dp(8); rightPadding:Theme.dp(22); Accessible.name:card.heading+"时间范围" }
                SwirlMotionButton { visible:card.actionText.length>0; text:card.actionText; padding:Theme.dp(0); implicitHeight:Theme.dp(24); font.pixelSize:Theme.fontSize(13); palette.buttonText:Theme.muted; background:Rectangle{radius:Theme.roundedRadius(width,height);color:parent.hovered?Theme.hover:"transparent"
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 } onClicked:card.action(); Accessible.name:card.heading+" "+text }
            }
            Item { id:bodyItem; anchors.top:cardHeader.bottom; anchors.topMargin:Theme.dp(10); anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom }
        }]
    }
    ScrollView {
        id:scroll; objectName:"overviewScroll"; anchors.fill:parent;clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth;spacing:Theme.gap
            RowLayout {
                Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(66)
                ColumnLayout {
                    Layout.fillWidth:true;spacing:Theme.dp(1)
                    Text { text:"总览";color:Theme.text;font.pixelSize:Theme.fontSize(38);font.weight:Font.Bold;Accessible.role:Accessible.Heading }
                    Text { text:"真实引擎与节点状态 · 未采集的数据不显示数值";color:Theme.muted;font.pixelSize:Theme.fontSize(17);Layout.fillWidth:true;elide:Text.ElideRight }
                }
            }
            GridLayout {
                objectName:"statusCardsGrid"
                Layout.fillWidth:true
                readonly property int fittingColumns:Math.max(1,Math.min(6,Math.floor((width+Theme.dp(8))/(Theme.dp(145)+Theme.dp(8)))))
                // Six is the intended reference row. When that no longer fits
                // at a useful card width, use balanced thirds instead of a
                // five-plus-one orphan row.
                columns:Math.min(3,fittingColumns)
                columnSpacing:Theme.dp(8);rowSpacing:Theme.gap
                Repeater {
                    model:[
                        {label:"当前网络",value:page.network.type,sub:page.network.name,icon:"wifi",route:"toolbox",tint:Theme.accent},
                        {label:"当前配置",value:engineController.processAlive?"Swirl 运行配置":"未运行",sub:"本机代理配置",icon:"document",route:"profiles",tint:Theme.accent},
                        {label:"出站模式",value:AppState.mode,sub:"单一选中节点",icon:"code",route:"rules",tint:Theme.green}]
                    SwirlMotionButton {
                        required property var modelData
                        Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(90);Layout.minimumWidth:Theme.dp(0);hoverEnabled:true;padding:Theme.dp(10)
                        background:SwirlGlassPanel { cornerRadius:Theme.cardRadius; color:parent.hovered?Theme.raised:Theme.surface
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
                        contentItem:RowLayout {
                            spacing:Theme.dp(9)
                            Glyph { icon:modelData.icon;tint:modelData.tint;implicitWidth:Theme.dp(40);implicitHeight:Theme.dp(40);width:Theme.dp(40);height:Theme.dp(40) }
                            ColumnLayout {
                                Layout.fillWidth:true;spacing:Theme.dp(2)
                                Text { text:modelData.label;color:Theme.muted;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;elide:Text.ElideRight }
                                Text { text:modelData.value;color:Theme.text;font.family:"Segoe UI";font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight }
                                Text { text:modelData.sub;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;elide:Text.ElideRight }
                            }
                        }
                        onClicked:AppState.navigate(modelData.route)
                        Accessible.name:modelData.label+" "+modelData.value+" "+modelData.sub
                        ToolTip.visible:hovered&&!previewCaptureMode;ToolTip.text:modelData.label+"："+modelData.value+" · "+modelData.sub
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true;columns:page.medium?3:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
                ColumnLayout {
                    Layout.columnSpan:page.medium?2:1;Layout.fillWidth:true;Layout.alignment:Qt.AlignTop;Layout.preferredWidth:Theme.dp(2);Layout.minimumWidth:Theme.dp(0);spacing:Theme.gap
                    Card {
                        heading:"当前代理";actionText:AppState.connectionState;onAction:AppState.navigate("proxies")
                        objectName:"currentProxyPanel";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(172)
                        ColumnLayout {
                            anchors.fill:parent;spacing:Theme.dp(6)
                            SwirlMotionButton {
                                id:nodeButton;objectName:"nodePickerButton";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(54);padding:Theme.dp(0);hoverEnabled:true
                                background:Rectangle { radius:Theme.roundedRadius(width,height);color:parent.hovered?Theme.hover:"transparent";border.width:parent.activeFocus?2:0;border.color:Theme.focusBorder
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
                                contentItem:RowLayout {
                                    spacing:Theme.dp(12);Glyph { icon:"globe" }
                                    ColumnLayout {
                                        Layout.fillWidth:true;spacing:Theme.dp(2)
                                        Text { text:AppState.policy+"";color:Theme.text;font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold }
                                        Text { text:AppState.selectedNode+" · "+AppState.selectedNodeProtocol+"";color:Theme.muted;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;elide:Text.ElideRight }
                                    }
                                    SwirlIcon { name:"chevron-right";size:Theme.dp(18) }
                                }
                                onClicked:nodePicker.open();Accessible.name:"切换节点，当前 "+AppState.selectedNode
                            }
                            RowLayout {
                                Layout.fillWidth:true;spacing:Theme.dp(8)
                                Text { text:"模式";color:Theme.muted;font.pixelSize:Theme.fontSize(13) }
                                SwirlComboBox { objectName:"modeCombo";Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(0);implicitHeight:Theme.dp(32);font.pixelSize:Theme.fontSize(13);enabled:false;model:["固定节点","直连"];currentIndex:Math.max(0,model.indexOf(AppState.mode));onActivated:AppState.mode=currentText;Accessible.name:"模式选择" }
                                Text { text:"策略";color:Theme.muted;font.pixelSize:Theme.fontSize(13) }
                                SwirlComboBox { objectName:"policyCombo";Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(0);implicitHeight:Theme.dp(32);font.pixelSize:Theme.fontSize(13);enabled:false;model:["固定节点"];currentIndex:Math.max(0,model.indexOf(AppState.policy));onActivated:AppState.policy=currentText;Accessible.name:"策略选择" }
                                SwirlButton { text:AppState.selectedNode;Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(0);implicitHeight:Theme.dp(32);font.pixelSize:Theme.fontSize(13);onClicked:nodePicker.open();Accessible.name:"当前节点 "+text }
                            }
                        }
                    }
                    Card {
                        heading:"最近连接";actionText:"查看更多 ›";onAction:AppState.navigate("connections");Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(164)
                        Column {
                            anchors.fill:parent;spacing:Theme.dp(0)
                            Rectangle {
                                width:parent.width;height:Theme.dp(24);radius:Theme.roundedRadius(width,height);color:Theme.raised
                                Row {
                                    anchors.fill:parent;anchors.leftMargin:Theme.dp(8)
                                    Repeater { model:[{name:"时间",ratio:0.11},{name:"目标地址",ratio:0.25},{name:"类型",ratio:0.08},{name:"进程",ratio:0.18},{name:"代理节点",ratio:0.17},{name:"延迟",ratio:0.10},{name:"流量",ratio:0.11}]
                                        Text { required property var modelData;width:(parent.width-Theme.dp(8))*modelData.ratio;height:Theme.dp(24);text:modelData.name;color:Theme.muted;font.pixelSize:Theme.fontSize(11);verticalAlignment:Text.AlignVCenter }
                                    }
                                }
                            }
                            Repeater {
                                model:systemProvider.connections().slice(0,3)
                                SwirlMotionButton {
                                    required property var modelData;width:parent.width;height:(parent.height-Theme.dp(24))/3;padding:Theme.dp(0)
                                    background:Rectangle { color:parent.hovered?Theme.hover:"transparent";radius:Theme.roundedRadius(width,height)
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
                                    contentItem:Row {
                                        leftPadding:Theme.dp(8)
                                        Repeater { model:[{value:modelData.time,ratio:0.11},{value:modelData.host,ratio:0.25},{value:"代理",ratio:0.08},{value:modelData.process,ratio:0.18},{value:AppState.selectedNode,ratio:0.17},{value:modelData.latency,ratio:0.10},{value:modelData.down,ratio:0.11}]
                                            Text { required property var modelData;width:(parent.width-Theme.dp(8))*modelData.ratio;height:parent.height;text:modelData.value;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12);verticalAlignment:Text.AlignVCenter;elide:Text.ElideRight }
                                        }
                                    }
                                    onClicked:AppState.navigate("connections")
                                }
                            }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth:true;Layout.alignment:Qt.AlignTop;Layout.preferredWidth:Theme.dp(1);Layout.minimumWidth:Theme.dp(0);spacing:Theme.gap
                    Card {
                        objectName:"systemStatusPanel";heading:"系统状态";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(172)
                        ColumnLayout {
                            anchors.fill:parent;spacing:Theme.dp(0)
                            Repeater {
                                model:[{title:"系统代理",sub:"系统流量转发",icon:"layers",kind:0},{title:"增强模式（TUN）",sub:"网络接管",icon:"layers",kind:1},{title:"DNS",sub:"使用 DNS 解析",icon:"shield",kind:2}]
                                RowLayout {
                                    required property var modelData;Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(12)
                                    SwirlIcon { name:modelData.icon;size:Theme.dp(22);color:Theme.text }
                                    ColumnLayout {
                                        Layout.fillWidth:true;spacing:Theme.dp(0)
                                        Text { text:modelData.title;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold }
                                        Text { text:modelData.sub;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;elide:Text.ElideRight }
                                    }
                                    SwirlToggle {
                                        objectName:modelData.kind===0?"systemProxyToggle":"tunToggle";visible:modelData.kind<2;implicitWidth:Theme.dp(46);implicitHeight:Theme.dp(26)
                                        checked:modelData.kind===0?AppState.systemProxyOn:AppState.tunOn
                                        enabled:false
                                        Accessible.name:modelData.title+"开关"
                                    }
                                    SwirlButton { visible:modelData.kind===2;text:"查看设置";implicitHeight:Theme.dp(28);implicitWidth:Theme.dp(84);font.pixelSize:Theme.fontSize(12);onClicked:AppState.navigate("dns") }
                                }
                            }
                        }
                    }
                    Card {
                        heading:"快捷操作";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(164)
                        GridLayout {
                            anchors.fill:parent;columns:2;rowSpacing:Theme.dp(6);columnSpacing:Theme.dp(6)
                            Repeater {
                                model:[{title:"测试代理延迟",icon:"gauge",route:"toolbox"},{title:"网络检测",icon:"activity",route:"toolbox"},{title:"导入订阅",icon:"document",route:"subscriptions"},{title:"打开设置",icon:"settings",route:"settings"}]
                                SwirlButton {
                                    required property var modelData;objectName:modelData.route==="subscriptions"?"importConfigRow":""
                                    Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(0);Layout.fillHeight:true;implicitHeight:Theme.dp(34);implicitWidth:Theme.dp(100);text:modelData.title;iconName:modelData.icon;font.pixelSize:Theme.fontSize(13)
                                    onClicked:AppState.navigate(modelData.route)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    Popup {
        id:nodePicker;objectName:"nodePicker";anchors.centerIn:Overlay.overlay;width:Theme.dp(420);padding:Theme.dp(22);modal:true;focus:true
        background:SwirlGlassPanel { material:"floating"; cornerRadius:Theme.popupRadius }
        contentItem:ColumnLayout {
            spacing:Theme.dp(12)
            Text { text:"选择节点";font.pixelSize:Theme.fontSize(22);font.weight:Font.DemiBold;color:Theme.text }
            Text { text:"选择要使用的代理节点";font.pixelSize:Theme.fontSize(14);color:Theme.muted }
            Repeater {
                model:engineController.nodes
                SwirlButton { required property var modelData;objectName:"savedNodeChoice";Layout.fillWidth:true;text:modelData.name;primary:AppState.selectedNode===modelData.name;onClicked:{engineController.chooseNode(modelData.id);nodePicker.close()} }
            }
            SwirlButton { text:"取消";Layout.alignment:Qt.AlignRight;onClicked:nodePicker.close() }
        }
    }
}
