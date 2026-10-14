pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;required property var systemProvider
 property int period:0;property int trafficKind:0;property int rankingKind:0
 property var network:systemProvider.currentNetwork()
 readonly property var telemetry:engineController.telemetry
 readonly property var totals:(telemetry.revision,telemetry.summary(period===0?0:3))
 readonly property var distribution:(telemetry.revision,telemetry.distribution(period===0?0:3))
 readonly property var ranks:{telemetry.revision;const range=period===0?0:3;return rankingKind===0?telemetry.ranking("apps",range,8).concat(telemetry.ranking("devices",range,8)).sort((a,b)=>b.total-a.total).slice(0,8):telemetry.ranking(["apps","domains","nodes"][rankingKind],range,8)}
 readonly property var daily:(telemetry.revision,telemetry.dailyTraffic(trafficKind===1))
 readonly property real dailyMaximum:Math.max(1,...daily.map(r=>r.value))
 function bytes(n,sampled){return sampled?telemetry.formatBytes(n):"—"}
 Timer {interval:10000;running:true;repeat:true;onTriggered:page.network=page.systemProvider.currentNetwork()}
 component Label:Text {color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 component Value:Row {id:value;property string text;readonly property var parts:text.split(/\s+/);spacing:Theme.dp(3)
  Text{text:value.parts[0];color:Theme.text;font.pixelSize:Theme.fontSize(32);font.weight:Font.DemiBold}
  Text{text:value.parts.slice(1).join(" ");color:Theme.text;font.pixelSize:Theme.fontSize(12);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(6)}
 }
 component Card:SwirlGlassPanel {cornerRadius:Theme.independentCardRadius}
 Flickable {
  anchors.fill:parent;contentWidth:Theme.dp(698);contentHeight:Theme.dp(620);clip:true;boundsBehavior:Flickable.StopAtBounds
  Text {x:Theme.dp(4);y:Theme.dp(6);text:"活动";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
  Repeater {model:[{label:"网络",value:page.network.type||"未检测"},{label:"配置",value:extensionsProvider.profileName},{label:"出站模式",value:AppState.mode},{label:"外部 IP",value:page.telemetry.externalIp||"…"}]
   Column {required property var modelData;required property int index;x:Theme.dp(4+index*176);y:Theme.dp(49);spacing:Theme.dp(3)
    Label{text:modelData.label}
    Text {text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
   }
  }
  Card {x:Theme.dp(4);y:Theme.dp(103);width:Theme.dp(336);height:Theme.dp(160)
   Label{x:Theme.dp(16);y:Theme.dp(16);text:"INTERNET 延迟"}
   SwirlIconButton{quiet:true;x:Theme.dp(94);y:Theme.dp(12);width:Theme.dp(24);height:width;iconName:"refresh";onClicked:page.telemetry.measureNetwork();Accessible.name:"刷新延迟"}
   SwirlButton{x:Theme.dp(226);y:Theme.dp(12);width:Theme.dp(100);text:"网络诊断";outlined:true;enabled:page.telemetry.measurementState!=="正在测量";onClicked:page.telemetry.measureNetwork()}
   Value{x:Theme.dp(16);y:Theme.dp(34);text:page.telemetry.latencies.internet||"—"}
   Repeater{model:2;Rectangle{required property int index;x:Theme.dp(112+index*112);y:Theme.dp(105);width:Theme.dp(1);height:Theme.dp(40);color:Theme.border}}
   Row {x:Theme.dp(16);y:Theme.dp(106);spacing:Theme.dp(16)
    Repeater {model:[{label:"路由",value:page.telemetry.latencies.router||"—"},{label:"DNS",value:page.telemetry.latencies.dns||"—"},{label:"代理",value:page.engineController.activeNodeId.length?(page.telemetry.latencies.proxy||"—"):"不适用"}]
     Column {required property var modelData;required property int index;width:Theme.dp(96);spacing:Theme.dp(5);Label{text:modelData.label}Text{text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}}
    }
   }
  }
  Repeater {model:["上传","下载"]
   Card {required property string modelData;required property int index;x:Theme.dp(356+index*176);y:Theme.dp(103);width:Theme.dp(160);height:Theme.dp(160);clip:true
    Label{x:Theme.dp(16);y:Theme.dp(16);text:modelData}
    Value{x:Theme.dp(16);y:Theme.dp(34);text:page.bytes(index===0?page.telemetry.uploadRate:page.telemetry.downloadRate,page.telemetry.sampled)+(page.telemetry.sampled?"/s":"")}
    Label{anchors.right:parent.right;anchors.rightMargin:Theme.dp(8);y:Theme.dp(22);text:page.telemetry.sampled?page.bytes(Math.max(page.telemetry.uploadRate,page.telemetry.downloadRate),true)+"/s":"—";opacity:0.4}
    Label{anchors.right:parent.right;anchors.rightMargin:Theme.dp(8);y:Theme.dp(81);text:page.telemetry.sampled?page.bytes(Math.max(page.telemetry.uploadRate,page.telemetry.downloadRate)/2,true)+"/s":"—";opacity:0.4}
    Rectangle{anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(20);width:parent.width;height:Theme.dp(2);color:index===0?Theme.accentIndigo:Theme.cyan}
   }
  }
  Card{x:Theme.dp(4);y:Theme.dp(279);width:Theme.dp(336);height:Theme.dp(160)
   Label{x:Theme.dp(16);y:Theme.dp(16);text:"活动连接"}
   Value{x:Theme.dp(16);y:Theme.dp(34);text:page.telemetry.connectionsSampled?String(page.telemetry.activeConnections):"—"}
   Rectangle{x:Theme.dp(305);y:Theme.dp(19);width:Theme.dp(12);height:width;radius:width/2;color:page.engineController.apiHealthy?Theme.green:Theme.muted}
   Repeater{model:2;Rectangle{required property int index;x:Theme.dp(112+index*112);y:Theme.dp(104);width:Theme.dp(1);height:Theme.dp(40);color:Theme.border}}
   Row{x:Theme.dp(16);y:Theme.dp(104);spacing:Theme.dp(16)
    Repeater{model:[{label:"进程",value:page.telemetry.connectionsSampled?String(page.telemetry.activeProcesses):"—"},{label:"设备",value:page.telemetry.connectionsSampled?String(new Set(page.telemetry.connections.filter(r=>r.status==="活动"&&r.sourceIp&&r.sourceIp!=="127.0.0.1"&&r.sourceIp!=="::1").map(r=>r.sourceIp)).size):"—"},{label:"DHCP 设备",value:String(gatewayProvider.devices.filter(r=>r.status==="租用中").length)}]
     Column{required property var modelData;required property int index;width:Theme.dp(96);Text{text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(24);font.weight:Font.DemiBold}Label{text:modelData.label}}
    }
   }
  }
  Card{x:Theme.dp(4);y:Theme.dp(455);width:Theme.dp(336);height:Theme.dp(160)
   Label{x:Theme.dp(16);y:Theme.dp(16);text:"总计"}
   SwirlSegmentedControl{x:Theme.dp(186);y:Theme.dp(14);width:Theme.dp(136);options:["今日","本月"];currentIndex:page.period;onActivated:index=>page.period=index}
   Value{x:Theme.dp(16);y:Theme.dp(34);text:page.bytes(page.totals.total,page.totals.sampled)}
   Column{x:Theme.dp(16);y:Theme.dp(87);Label{text:"DIRECT"}Text{text:page.distribution[1]?page.distribution[1].value:"—";color:Theme.text;font.pixelSize:Theme.fontSize(16)}}
   Column{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(87);Label{text:"代理"}Text{text:page.distribution[0]?page.distribution[0].value:"—";color:Theme.text;font.pixelSize:Theme.fontSize(16)}}
   Rectangle{x:Theme.dp(16);y:Theme.dp(122);width:Theme.dp(304);height:Theme.dp(22);radius:Theme.dp(4);color:Theme.field
    Rectangle{height:parent.height;width:page.totals.total>0?parent.width*(page.distribution[1].bytes/page.totals.total):0;radius:parent.radius;color:Theme.accentIndigo}
   }
  }
  Card{x:Theme.dp(356);y:Theme.dp(279);width:Theme.dp(336);height:Theme.dp(336)
   Label{x:Theme.dp(16);y:Theme.dp(16);text:"流量"}
   SwirlSegmentedControl{x:Theme.dp(186);y:Theme.dp(14);width:Theme.dp(136);options:["全部","仅代理"];currentIndex:page.trafficKind;onActivated:index=>page.trafficKind=index}
   Canvas{id:dailyPlot;x:Theme.dp(16);y:Theme.dp(46);width:Theme.dp(304);height:Theme.dp(66)
    onWidthChanged:requestPaint();onHeightChanged:requestPaint();onVisibleChanged:if(visible)requestPaint()
    Connections{target:page;function onDailyChanged(){dailyPlot.requestPaint()}function onDailyMaximumChanged(){dailyPlot.requestPaint()}}
    Connections{target:Theme;function onDarkChanged(){dailyPlot.requestPaint()}}
    onPaint:{const c=getContext("2d");c.reset();c.strokeStyle=Theme.border;c.lineWidth=Theme.dp(1);c.setLineDash([Theme.dp(1),Theme.dp(4)]);for(let i=0;i<3;i++){c.beginPath();c.moveTo(0,i*height/2);c.lineTo(width,i*height/2);c.stroke()}c.setLineDash([]);c.fillStyle=Theme.cyan;for(let i=0;i<page.daily.length;i++){const row=page.daily[i];if(!row.sampled)continue;c.beginPath();c.arc(i*(width-Theme.dp(5))/47+Theme.dp(2),height-Theme.dp(3)-row.value*(height-Theme.dp(6))/page.dailyMaximum,Theme.dp(2.5),0,Math.PI*2);c.fill()}}
   }
   Label{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(48);text:page.telemetry.formatBytes(page.dailyMaximum===1?0:page.dailyMaximum);opacity:0.4}
   Label{x:Theme.dp(16);y:Theme.dp(118);text:"12AM                 6AM                 12PM                 6PM";opacity:0.6}
   SwirlSegmentedControl{x:Theme.dp(16);y:Theme.dp(138);width:Theme.dp(304);options:["进程与设备","域名","策略"];currentIndex:page.rankingKind;onActivated:index=>page.rankingKind=index}
   Column{x:Theme.dp(16);y:Theme.dp(172);width:Theme.dp(304);spacing:Theme.dp(8)
    Repeater{model:page.ranks;RowLayout{required property var modelData;required property int index;width:parent.width;Text{text:modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;elide:Text.ElideRight}Label{text:modelData.value}}}
   }
  }
 }
}
