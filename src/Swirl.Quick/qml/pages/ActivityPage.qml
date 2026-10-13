import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property var network: systemProvider.currentNetwork()
    readonly property var stats: engineController.telemetry
    readonly property bool available: stats.available === true
    property int period: 0
    property int scope: 0
    property int rank: 0
    readonly property real directBytes: available ? (period ? stats.monthDirect : stats.direct) : 0
    readonly property real proxyBytes: available ? (period ? stats.monthProxy : stats.proxy) : 0
    readonly property var rankings: available ? (scope ? [stats.proxyClients,stats.proxyDomains,stats.proxyPolicies] : [stats.clients,stats.domains,stats.policies])[rank] : []
    function bytes(value) {
        if(value === undefined || value < 0)return "—"
        const units=["B","KB","MB","GB"]; let i=0
        while(value>=1024 && i<3){value/=1024;i++}
        return (value>=100 || i===0 ? Math.round(value) : value.toFixed(1))+" "+units[i]
    }
    readonly property bool wide: width >= Theme.dp(700)
    readonly property real scrollOffset: scroll.contentItem ? scroll.contentItem.contentY : 0
    function scrollToBottom() { scroll.contentItem.contentY=Math.max(0,scroll.contentItem.contentHeight-scroll.contentItem.height) }
    Timer { interval:10000; repeat:true; running:true; onTriggered:page.network=systemProvider.currentNetwork() }
    Timer { interval:60000; repeat:true; triggeredOnStart:true; running:page.visible && !isolatedRun; onTriggered:if(!networkDiagnostics.busy)networkDiagnostics.start() }
    component Label: Text { color:Theme.muted; font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(12); elide:Text.ElideRight }
    component Value: Text { color:Theme.text; font.family:"Segoe UI"; font.pixelSize:Theme.fontSize(40); font.weight:Font.DemiBold; elide:Text.ElideRight }
    component Metric: Item {
        id:metric
        property string text: "—"
        implicitHeight:Theme.dp(54); implicitWidth:number.implicitWidth+unit.implicitWidth+Theme.dp(4)
        clip:true
        Value {id:number;text:metric.text.split(" ")[0]}
        Text {id:unit;text:metric.text.split(" ").slice(1).join(" ");anchors.left:number.right;anchors.leftMargin:Theme.dp(4);anchors.baseline:number.baseline;color:Theme.text;font.family:"Segoe UI";font.pixelSize:Theme.fontSize(16)}
    }
    component Segments: Item {
        id:seg; property var options: []; property int currentIndex:0
        implicitWidth:Theme.dp(178); implicitHeight:Theme.dp(26)
        Rectangle {anchors.fill:parent;radius:Theme.dp(7);color:"transparent";border.color:Theme.border}
        Row {anchors.fill:parent;anchors.margins:Theme.dp(2)
            Repeater {model:seg.options
                SwirlMotionButton {
                    required property string modelData; required property int index
                    width:parent.width/seg.options.length; height:parent.height; padding:0
                    background:Rectangle {radius:Theme.dp(4);color:seg.currentIndex===index?Theme.segmentSelected:"transparent"}
                    contentItem:Text {text:modelData.toUpperCase();color:seg.currentIndex===index?"white":Theme.muted;font.pixelSize:Theme.fontSize(13);horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter}
                    onClicked:seg.currentIndex=index
                }
            }
        }
    }
    component Card: SwirlGlassPanel {
        id: card
        property string heading
        property string actionText: ""
        property var options: []
        property alias selectedIndex:filter.currentIndex
        signal action()
        default property alias body: body.data
        cornerRadius:Theme.cardRadius
        data: Item {
            anchors.fill:parent; anchors.margins:Theme.cardPadding
            RowLayout {
                id:header; width:parent.width; height:Theme.dp(24)
                Text { text:card.heading.toUpperCase(); color:Theme.muted; font.pixelSize:Theme.fontSize(13); font.weight:Font.Normal; Layout.fillWidth:true; elide:Text.ElideRight }
                SwirlMotionButton { visible:card.actionText.length>0; text:card.actionText; font.pixelSize:Theme.fontSize(11); padding:0; implicitHeight:Theme.dp(24); leftPadding:Theme.dp(12); rightPadding:Theme.dp(12); background:Rectangle {radius:Theme.buttonRadius; color:"transparent";border.color:Theme.border} palette.buttonText:Theme.muted; onClicked:card.action() }
                Segments {id:filter;visible:card.options.length>0;options:card.options}
            }
            Item { id:body; anchors.top:header.bottom; anchors.topMargin:Theme.dp(6); anchors.left:parent.left; anchors.right:parent.right; anchors.bottom:parent.bottom }
        }
    }
    ScrollView {
        id:scroll; objectName:"activityScroll"; anchors.fill:parent; clip:true
        contentWidth:availableWidth
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ColumnLayout {
            width:scroll.availableWidth; spacing:Theme.dp(20)
            Item {
                Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(page.wide?104:160)
            Text { text:"活动"; color:Theme.text; font.pixelSize:Theme.fontSize(34); font.weight:Font.Bold; Accessible.role:Accessible.Heading }
            GridLayout {
                y:Theme.dp(52); width:parent.width; height:Theme.dp(page.wide?50:100); columns:page.wide?4:2; columnSpacing:Theme.dp(24); rowSpacing:Theme.dp(12)
                Repeater {
                    model:[{label:"当前网络",value:page.network.name},{label:"当前配置",value:engineController.processAlive?"Swirl":"—"},{label:"出站模式",value:AppState.mode},{label:"外部 IP",value:"—"}]
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; spacing:Theme.dp(4)
                        Label { text:modelData.label; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true }
                        Label { text:modelData.value; color:Theme.text; font.pixelSize:Theme.fontSize(20); Layout.fillWidth:true }
                    }
                }
            }
            }
            GridLayout {
                id:topCards
                Layout.fillWidth:true; columns:page.wide?4:2; columnSpacing:Theme.gap; rowSpacing:Theme.gap
                Card {
                    heading:"互联网延迟"; actionText:"诊断"; onAction:diagnostics.open()
                    objectName:"internetLatencyCard"; Layout.columnSpan:2; Layout.fillWidth:true; Layout.preferredWidth:page.wide?(topCards.width-Theme.gap)/2:topCards.width; Layout.minimumWidth:0; Layout.preferredHeight:Theme.dp(200)
                    ColumnLayout {
                        anchors.fill:parent; spacing:Theme.dp(5)
                        Value { Layout.preferredHeight:Theme.dp(48); text:networkDiagnostics.currentResult.latency >= 0 ? networkDiagnostics.currentResult.latency+" ms" : "—"; Layout.fillWidth:true }
                        Label { text:networkDiagnostics.currentResult.state; Layout.fillWidth:true }
                        RowLayout {
                            Layout.fillWidth:true
                            Repeater {
                                model:[{name:"路由器",value:"—"},{name:"DNS",value:networkDiagnostics.dnsResult.latency>=0?networkDiagnostics.dnsResult.latency+" ms":"—"},{name:"代理",value:networkDiagnostics.proxyResult.latency>=0?networkDiagnostics.proxyResult.latency+" ms":"—"}]
                                ColumnLayout { required property var modelData; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; Label {text:modelData.name;Layout.fillWidth:true} Label {text:modelData.value;color:Theme.text;Layout.fillWidth:true;font.pixelSize:Theme.fontSize(22)} }
                            }
                        }
                    }
                }
                Repeater {
                    model:[{name:"上传",tint:Theme.uploadColor,key:"up",history:"upHistory"},{name:"下载",tint:Theme.downloadColor,key:"down",history:"downHistory"}]
                    Card {
                        required property var modelData
                        objectName:modelData.key==="up"?"uploadMetric":"downloadMetric"; property string value:page.available&&page.stats.sampled?page.bytes(page.stats[modelData.key])+"/s":"—"
                        heading:modelData.name; Layout.fillWidth:true; Layout.preferredWidth:page.wide?(topCards.width-3*Theme.gap)/4:(topCards.width-Theme.gap)/2; Layout.minimumWidth:0; Layout.preferredHeight:Theme.dp(200)
                        ColumnLayout {
                            anchors.fill:parent
                            Metric { text:page.available && page.stats.sampled ? page.bytes(page.stats[modelData.key])+"/s" : "—"; Layout.fillWidth:true }
                            Label { text:page.available ? "" : "尚未采集" }
                            SwirlSparkline { Layout.fillWidth:true; Layout.fillHeight:true; lineColor:modelData.tint; active:page.available && page.stats.sampled; values:page.available?page.stats[modelData.history].map(function(v){return v/Math.max(1,...page.stats[modelData.history])}):[] }
                        }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth:true; columns:page.wide?2:1; uniformCellWidths:true; columnSpacing:Theme.gap; rowSpacing:Theme.gap
                ColumnLayout {
                    Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; spacing:Theme.gap
                    Card {
                        objectName:"activeConnectionCard"; heading:"活跃连接"; actionText:"详情"; onAction:AppState.navigate("connections")
                        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(200)
                        ColumnLayout {
                            anchors.fill:parent
                            Value { text:page.available?page.stats.connections.length:"—" }
                            RowLayout {
                                Layout.fillWidth:true
                                Repeater { model:[{label:"进程",value:page.available?page.stats.processes:"—"},{label:"设备",value:page.available?page.stats.devices:"—"},{label:"DHCP 设备",value:"—"}]
                                    ColumnLayout { required property var modelData; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; Value {text:modelData.value;font.pixelSize:Theme.fontSize(28);Layout.fillWidth:true} Label {text:modelData.label;Layout.fillWidth:true} }
                                }
                            }
                        }
                    }
                    Card {
                        objectName:"totalTrafficCard"; heading:"总流量"; options:["今日","本月"]; onSelectedIndexChanged:page.period=selectedIndex; Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(200)
                        ColumnLayout {
                            anchors.fill:parent; spacing:Theme.dp(5)
                            Metric {Layout.preferredHeight:Theme.dp(48);text:page.available?page.bytes(page.period?page.stats.month:page.stats.today):"—";Layout.fillWidth:true}
                            RowLayout { Layout.fillWidth:true; Column {Label {text:"直连";font.pixelSize:Theme.fontSize(11)} Value {text:page.available?page.bytes(page.directBytes):"—";font.pixelSize:Theme.fontSize(20)}} Item {Layout.fillWidth:true} Column {Label {text:"代理";font.pixelSize:Theme.fontSize(11);anchors.right:parent.right} Value {text:page.available?page.bytes(page.proxyBytes):"—";font.pixelSize:Theme.fontSize(20)}} }
                            Row {
                                Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(28);spacing:Theme.dp(4)
                                readonly property real total:page.directBytes+page.proxyBytes
                                Rectangle {width:parent.total>0?(parent.width-parent.spacing)*page.directBytes/parent.total:0;height:parent.height;radius:Theme.dp(4);color:Theme.uploadColor}
                                Rectangle {width:parent.total>0?(parent.width-parent.spacing)*page.proxyBytes/parent.total:parent.width;height:parent.height;radius:Theme.dp(4);color:parent.total>0?Theme.downloadColor:Theme.border}
                                HoverHandler {id:trafficHint}
                                ToolTip.visible:trafficHint.hovered;ToolTip.text:"仅统计 Swirl 运行时的采样；直连/代理分类及排行仅含采样捕获的连接。"
                            }
                        }
                    }
                }
                Card {
                    objectName:"trafficCard"; heading:"流量"; options:["全部","代理"]; onSelectedIndexChanged:page.scope=selectedIndex; Layout.fillWidth:true; Layout.preferredWidth:1; Layout.minimumWidth:0; Layout.preferredHeight:Theme.dp(420)
                    ColumnLayout {
                        anchors.fill:parent; spacing:Theme.dp(16)
                        Item {
                            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(112)
                            Canvas {
                                id:bars; anchors.fill:parent
                                property var values:page.available?(page.scope?page.stats.proxyHours:page.stats.hours):[]
                                onValuesChanged:requestPaint()
                                onWidthChanged:requestPaint()
                                onHeightChanged:requestPaint()
                                onPaint:{
                                    let ctx=getContext("2d");ctx.reset();let max=Math.max(1,...values)
                                    ctx.strokeStyle=Theme.border;ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(0,8);ctx.lineTo(width,8);ctx.moveTo(0,height/2);ctx.lineTo(width,height/2);ctx.stroke()
                                    ctx.fillStyle=Theme.downloadColor
                                    for(let i=0;i<values.length;i++){let h=(height-24)*values[i]/max;if(h>0)ctx.fillRect(i*width/24+4,height-18-h,Math.max(2,width/24-9),h)}
                                }
                            }
                            Label { visible:!page.available; anchors.centerIn:parent; text:"尚未采集流量数据" }
                            Row {anchors.bottom:parent.bottom;width:parent.width;Repeater {model:["0 时","6 时","12 时","18 时"];Label {required property string modelData; width:parent.width/4;text:modelData;font.pixelSize:Theme.fontSize(11)}}}
                        }
                        Segments { options:["客户端","域名","策略"]; Layout.fillWidth:true; onCurrentIndexChanged:page.rank=currentIndex }
                        Column {
                            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(10)
                            Repeater {
                                model:page.rankings
                                Item {
                                    required property var modelData; width:parent.width;height:Theme.dp(30)
                                    RowLayout {anchors.top:parent.top;width:parent.width;spacing:Theme.dp(8)
                                        SwirlIcon {name:page.rank===0?"settings":page.rank===1?"globe":"route";size:Theme.dp(20);color:Theme.accent}
                                        Label {text:modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(15);Layout.fillWidth:true}
                                        Label {text:page.bytes(modelData.bytes);color:Theme.text;font.pixelSize:Theme.fontSize(14)}
                                    }
                                    Rectangle {x:Theme.dp(28);anchors.bottom:parent.bottom;height:Theme.dp(4);radius:height/2;color:Theme.border;width:(parent.width-x)*modelData.bytes/Math.max(1,page.rankings[0].bytes)}
                                }
                            }
                            Label {visible:page.rankings.length===0;text:"暂无排行";anchors.horizontalCenter:parent.horizontalCenter}
                        }
                    }
                }
            }
        }
    }
    Popup {
        id:diagnostics; anchors.centerIn:Overlay.overlay; width:Math.min(Theme.dp(660),page.Window.window.width-Theme.dp(48)); height:Theme.dp(420); modal:true; focus:true; padding:Theme.cardPadding
        background:SwirlGlassPanel { material:"floating" }
        contentItem:ColumnLayout {
            spacing:Theme.dp(12)
            Text {text:"网络诊断";color:Theme.text;font.pixelSize:Theme.fontSize(22)}
            Label {text:"直连："+networkDiagnostics.directResult.state;Layout.fillWidth:true}
            Label {text:"当前代理："+networkDiagnostics.proxyResult.state;Layout.fillWidth:true}
            RowLayout {
                SwirlButton {text:"开始检测";enabled:!networkDiagnostics.busy;onClicked:networkDiagnostics.start()}
                SwirlButton {text:"取消";enabled:networkDiagnostics.busy;onClicked:networkDiagnostics.cancel()}
                Item {Layout.fillWidth:true}
                SwirlButton {text:"关闭";onClicked:diagnostics.close()}
            }
            ScrollView {Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                TextArea {text:networkDiagnostics.log.join("\n");readOnly:true;wrapMode:TextEdit.Wrap;font.pixelSize:Theme.fontSize(11);color:Theme.text;background:Item {}}
            }
        }
    }
}
