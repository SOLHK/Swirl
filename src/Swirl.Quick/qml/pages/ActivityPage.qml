pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 required property var engineController
 required property var systemProvider
 property int period:0
 property int trafficKind:0
 property int rankingKind:0
 property bool diagnosticOpen:false
 property var network:systemProvider.currentNetwork()
 readonly property var telemetry:engineController.telemetry
 readonly property bool wide:scroll.width-2*Theme.pagePadding>=Theme.dp(620)
 readonly property bool nodeConnected:engineController.processAlive&&engineController.activeNodeId.length>0
 readonly property string activeNodeName:{if(!nodeConnected)return "尚未连接节点";const node=engineController.nodes.find(n=>n.id===engineController.activeNodeId);return node?node.name:"运行中的节点"}
 readonly property string sampleState:!engineController.processAlive?"未连接":engineController.apiHealthy?"等待采样":"采样中断"
 readonly property string proxyState:engineController.systemProxy.owned&&engineController.systemProxy.enabled?"系统代理由 Swirl 接管":engineController.systemProxy.systemEnabled?"系统代理由其他应用启用":"系统代理未启用"
 property var totals:({sampled:false,total:0})
 property var distribution:[]
 property var ranks:[]
 property bool snapshotDirty:true
 function refreshSnapshot(){
  if(!visible)return
  const range=period===0?0:3
  totals=telemetry.summary(range);distribution=telemetry.distribution(range)
  const rows=telemetry.ranking(["apps","devices","domains","nodes"][rankingKind],range,5)
  if(JSON.stringify(rows)!==JSON.stringify(ranks))ranks=rows
  snapshotDirty=false
 }
 function bytes(n,sampled){return sampled?telemetry.formatBytes(n):"—"}
 function trafficFrom(item,key){AppState.trafficPeriod=period===0?0:3;SwirlMotion.navigateFrom(item,"traffic",key)}
 function scrollToBottom(){scroll.contentY=Math.max(0,scroll.contentHeight-scroll.height)}
 onPeriodChanged:{snapshotDirty=true;refreshSnapshot()}
 onRankingKindChanged:{snapshotDirty=true;refreshSnapshot()}
 onVisibleChanged:if(visible)refreshSnapshot()
 Component.onCompleted:refreshSnapshot()
 Connections {target:page.telemetry;function onChanged(){page.snapshotDirty=true}}
 Timer {interval:250;running:page.visible&&page.snapshotDirty;repeat:true;onTriggered:page.refreshSnapshot()}
 Timer {interval:10000;running:page.visible;repeat:true;onTriggered:page.network=page.systemProvider.currentNetwork()}
 component Label:SwirlText {color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
 component Value:SwirlText {color:Theme.text;font.pixelSize:Theme.fontSize(23);font.weight:Font.DemiBold;elide:Text.ElideRight}
 component Metric:SwirlGlassPanel {
  id:metric
  property string label
  property string value
  property string hint
  property string key
  property bool cumulative:false
  readonly property Item motionTitle:metricValue
  readonly property Item motionSurface:metric
  Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredHeight:Theme.dp(132)
  function activate(){key==="activeConnections"?SwirlMotion.navigateFrom(metric,"connections",key):page.trafficFrom(metric,key)}
  SwirlMotionButton {
   anchors.fill:parent;anchors.bottomMargin:metric.cumulative?Theme.dp(48):0
   objectName:"activityMetricHit_"+metric.key
   Accessible.name:metric.label+"详情";onClicked:metric.activate()
   background:Rectangle {radius:Theme.cardRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";border.width:parent.visualFocus?1:0;border.color:Theme.focusBorder}
   contentItem:Item {}
  }
  ColumnLayout {anchors.fill:parent;anchors.margins:Theme.dp(14);spacing:Theme.dp(6)
   RowLayout {Layout.fillWidth:true;Label {text:metric.label;Layout.fillWidth:true}SwirlIconButton {implicitWidth:Theme.dp(22);implicitHeight:Theme.dp(22);iconName:"chevron-right";quiet:true;Accessible.name:metric.label+"详情";onClicked:metric.activate()}}
   Value {id:metricValue;text:metric.value;Layout.fillWidth:true}
   Label {visible:!metric.cumulative;text:metric.hint;Layout.fillWidth:true}
   SwirlSegmentedControl {visible:metric.cumulative;Layout.fillWidth:true;options:["今日","本月"];currentIndex:page.period;onActivated:index=>page.period=index}
  }
 }
 Flickable {
  id:scroll;objectName:"activityScroll"
  anchors.fill:parent;anchors.topMargin:Theme.dp(52);clip:true
  contentWidth:width;contentHeight:content.implicitHeight+Theme.pagePadding
  flickableDirection:Flickable.VerticalFlick;boundsBehavior:Flickable.StopAtBounds;pixelAligned:false
  ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout {
   id:content;x:Theme.pagePadding;width:scroll.width-2*Theme.pagePadding;spacing:Theme.sectionGap
   SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:connectionContent.implicitHeight+Theme.dp(28);cornerRadius:Theme.subCardRadius
    ColumnLayout {id:connectionContent;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.dp(14);spacing:Theme.dp(10)
     RowLayout {Layout.fillWidth:true
      Rectangle {width:Theme.dp(7);height:width;radius:width/2;color:page.nodeConnected&&page.engineController.apiHealthy?Theme.statusGreen:Theme.muted}
      SwirlText {text:page.activeNodeName;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight}
      SwirlButton {visible:!page.nodeConnected;quiet:true;text:"选择节点";implicitHeight:Theme.dp(26);onClicked:AppState.navigate("proxies")}
      Label {visible:page.nodeConnected;text:page.telemetry.sampled?"实时采样":page.sampleState}
     }
     GridLayout {Layout.fillWidth:true;columns:page.wide?4:2;columnSpacing:Theme.dp(16);rowSpacing:Theme.dp(8)
      Repeater {model:[{label:"网络",value:page.network.type||"尚未检测"},{label:"配置",value:extensionsProvider.profileName},{label:"出站",value:AppState.mode},{label:"外部 IP",value:page.telemetry.externalIp||"尚未检测"}]
       Label {required property var modelData;text:modelData.label+"  "+modelData.value;Layout.fillWidth:true;Layout.minimumWidth:0;HoverHandler{id:infoHover}ToolTip.visible:infoHover.hovered&&truncated;ToolTip.text:text;ToolTip.delay:650}
      }
     }
    }
   }
   GridLayout {Layout.fillWidth:true;columns:page.wide?4:2;columnSpacing:Theme.gap;rowSpacing:Theme.gap;uniformCellWidths:true
    Metric {objectName:"activityUpload";label:"上传速率";key:"uploadRate";value:page.bytes(page.telemetry.uploadRate,page.telemetry.sampled);hint:page.telemetry.sampled?"每秒":page.sampleState}
    Metric {objectName:"activityDownload";label:"下载速率";key:"downloadRate";value:page.bytes(page.telemetry.downloadRate,page.telemetry.sampled);hint:page.telemetry.sampled?"每秒":page.sampleState}
    Metric {objectName:"activityConnections";label:"活动连接";key:"activeConnections";value:page.telemetry.connectionsSampled?String(page.telemetry.activeConnections):"—";hint:page.telemetry.connectionsSampled?page.telemetry.activeProcesses+" 个进程":page.sampleState}
    Metric {objectName:"activityTotal";label:"累计流量";key:"totalTraffic";value:page.bytes(page.totals.total,page.totals.sampled);cumulative:true}
   }
   GridLayout {Layout.fillWidth:true;columns:page.wide?2:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
    SwirlGlassPanel {Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredWidth:7;Layout.preferredHeight:Theme.dp(240);Layout.alignment:Qt.AlignTop
     ColumnLayout {anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(10)
      RowLayout {Layout.fillWidth:true;SwirlText {text:"流量趋势";color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlSegmentedControl {Layout.preferredWidth:Theme.dp(126);options:["全部","仅代理"];currentIndex:page.trafficKind;onActivated:index=>page.trafficKind=index}}
      Label {text:"今日累计分布 · 每柱 30 分钟";Layout.fillWidth:true}
      SwirlDailyTrafficChart {Layout.fillWidth:true;Layout.fillHeight:true;proxyOnly:page.trafficKind===1}
     }
    }
    SwirlHeroCard {
     id:diagnostic;objectName:"internetDiagnosticCard";Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredWidth:5;Layout.preferredHeight:height;Layout.alignment:Qt.AlignTop
     collapsedHeight:Theme.dp(240);expandedHeight:collapsedHeight+diagnosticDetails.implicitHeight+Theme.dp(16);expanded:page.diagnosticOpen
     ColumnLayout {x:Theme.cardPadding;y:Theme.cardPadding;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(10)
      RowLayout {Layout.fillWidth:true
       SwirlText {text:"网络质量";color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold;Layout.fillWidth:true}
       SwirlIconButton {objectName:"networkDiagnosticButton";iconName:"refresh";quiet:true;enabled:page.telemetry.measurementState!=="正在测量";onClicked:page.telemetry.measureNetwork();Accessible.name:"网络诊断";ToolTip.visible:hovered;ToolTip.text:"发起网络诊断";ToolTip.delay:650}
       SwirlIconButton {objectName:"networkDiagnosticDetails";iconName:page.diagnosticOpen?"chevron-left":"chevron-right";quiet:true;onClicked:page.diagnosticOpen=!page.diagnosticOpen;Accessible.name:page.diagnosticOpen?"收起检测详情":"查看检测详情"}
      }
      Label {text:"互联网延迟";Layout.fillWidth:true}
      Value {text:page.telemetry.latencies.internet||"尚未检测";Layout.fillWidth:true}
      Label {text:page.telemetry.measurementState||"尚未检测";Layout.fillWidth:true}
      RowLayout {Layout.fillWidth:true;spacing:Theme.dp(8)
       Repeater {model:[{label:"路由",value:page.telemetry.latencies.router||"—"},{label:"DNS",value:page.telemetry.latencies.dns||"—"},{label:"代理",value:page.nodeConnected?(page.telemetry.latencies.proxy||"—"):"未连接"}]
        ColumnLayout {required property var modelData;Layout.fillWidth:true;Layout.minimumWidth:0;Label{text:modelData.label}SwirlText {text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}}
       }
      }
     }
     ColumnLayout {id:diagnosticDetails;x:Theme.cardPadding;y:diagnostic.collapsedHeight;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(10);visible:diagnostic.reveal>0;enabled:diagnostic.expanded
      SwirlText {text:page.telemetry.internetDiagnostic.advice||"点击刷新，发起真实的 HTTPS 请求。";color:Theme.text;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12)}
      Label {text:"引擎："+(page.engineController.processAlive?"运行中":"未运行")+" · 接口："+(page.engineController.apiHealthy?"正常":"未就绪")+" · 端口："+(page.engineController.activeProxyPort||"未开放");Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:"出站："+(page.telemetry.internetDiagnostic.route||"尚未检测")+" · 节点："+page.activeNodeName;Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:page.proxyState;Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:page.telemetry.internetDiagnostic.http!==undefined?"HTTP "+page.telemetry.internetDiagnostic.http+" · 错误码 "+page.telemetry.internetDiagnostic.networkError+" · "+page.telemetry.internetDiagnostic.elapsedMs+" ms":"尚无 HTTPS 检测结果";Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
     }
    }
   }
   SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:rankingContent.implicitHeight+2*Theme.cardPadding
    ColumnLayout {id:rankingContent;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
     RowLayout {Layout.fillWidth:true;SwirlText {text:"流量来源";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {text:"查看全部";quiet:true;onClicked:{AppState.trafficPeriod=page.period===0?0:3;AppState.navigate(page.rankingKind===0?"processes":page.rankingKind===1?"gateway":"traffic")}}}
     SwirlSegmentedControl {Layout.preferredWidth:Math.min(parent.width,Theme.dp(360));options:["进程","设备","域名","策略"];currentIndex:page.rankingKind;onActivated:index=>page.rankingKind=index}
     Repeater {model:page.ranks
      SwirlMotionButton {id:rank;readonly property Item motionTitle:rankName;readonly property Item motionSurface:background;required property var modelData;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(32);padding:Theme.dp(4);hoverEnabled:true
       background:Rectangle {color:rank.down?Theme.pressed:rank.hovered?Theme.hover:"transparent";radius:Theme.controlRadius}
       contentItem:RowLayout {SwirlText {id:rankName;Layout.fillWidth:true;text:rank.modelData.name;color:Theme.text;elide:Text.ElideRight;font.pixelSize:Theme.fontSize(13)}Label {text:rank.modelData.value}}
       onClicked:{AppState.trafficPeriod=page.period===0?0:3;if(page.rankingKind===0){AppState.trafficSelectedProcess=modelData.name;SwirlMotion.navigateFrom(rank,"processes","processName")}else if(page.rankingKind===1){AppState.trafficSelectedDevice=modelData.name;SwirlMotion.navigateFrom(rank,"gateway","deviceName")}else AppState.navigate("traffic")}
      }
     }
     Label {visible:page.ranks.length===0;text:"尚未采集排行数据";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(56)}
     Label {text:"仅统计经过 Swirl 的流量 · "+(page.period===0?"今日":"本月")+" · DHCP 租用设备 "+gatewayProvider.devices.filter(r=>r.status==="租用中").length;Layout.fillWidth:true}
     Label {text:"直连 "+(page.distribution[1]?page.distribution[1].value:"—")+" · 代理 "+(page.distribution[0]?page.distribution[0].value:"—")+(page.totals.sampled&&!page.telemetry.sampled?" · 历史累计":"");Layout.fillWidth:true}
    }
   }
  }
 }
}
