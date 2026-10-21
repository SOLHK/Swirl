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
 property bool diagnosticOpen:false
 property bool previewMeasured:false
 property var network:systemProvider.currentNetwork()
 readonly property var telemetry:engineController.telemetry
 readonly property var shownLatencies:previewMeasured?({internet:"347 ms",router:"2 ms",dns:"6 ms",proxy:"400 ms"}):telemetry.latencies
 readonly property var shownInternetDiagnostic:previewMeasured?({success:true,route:"代理",advice:"HTTPS 请求完成，当前策略可用。",http:204,networkError:0,elapsedMs:347}):telemetry.internetDiagnostic
 readonly property var shownProxyDiagnostic:previewMeasured?({detail:"通过当前代理入口单独测量 HTTPS 往返。",http:204,networkError:0}):telemetry.proxyDiagnostic
 readonly property string shownMeasurementState:previewMeasured?"测量完成":telemetry.measurementState
 readonly property bool paired:scroll.width-2*Theme.pagePadding>=Theme.dp(460)
 readonly property bool wide:scroll.width-2*Theme.pagePadding>=Theme.dp(620)
 readonly property real activityCardRadius:Theme.dp(30)
 readonly property real activityTileHeight:Theme.dp(164)
 readonly property bool nodeConnected:engineController.processAlive&&engineController.activeNodeId.length>0
 readonly property string activeNodeName:{if(!nodeConnected)return "尚未连接节点";const node=engineController.nodes.find(n=>n.id===engineController.activeNodeId);return node?node.name:"运行中的节点"}
 readonly property string sampleState:!engineController.processAlive?"未连接":engineController.apiHealthy?"等待采样":"采样中断"
 readonly property string proxyState:engineController.systemProxy.owned&&engineController.systemProxy.enabled?"系统代理由 Swirl 接管":engineController.systemProxy.systemEnabled?"系统代理由其他应用启用":"系统代理未启用"
 property var totals:({sampled:false,total:0})
 property var ranks:[]
 property bool snapshotDirty:true
 function refreshSnapshot(){
  if(!visible)return
  totals=telemetry.summary(0)
  const rows=telemetry.ranking("apps",0,1)
  if(JSON.stringify(rows)!==JSON.stringify(ranks))ranks=rows
  snapshotDirty=false
 }
 function bytes(n,sampled){return sampled?telemetry.formatBytes(n):"—"}
 function trafficFrom(item,key){AppState.trafficPeriod=0;SwirlMotion.navigateFrom(item,"traffic",key)}
 function openSources(){AppState.trafficPeriod=0;AppState.navigate("processes")}
 function scrollToBottom(){scroll.contentY=Math.max(0,scroll.contentHeight-scroll.height)}
 function preparePreviewState(state){if(previewCaptureMode&&(state==="activity-measured"||state==="activity-measured-expanded")){previewMeasured=true;diagnosticOpen=state==="activity-measured-expanded"}}
 onVisibleChanged:if(visible)refreshSnapshot()
 Component.onCompleted:refreshSnapshot()
 Connections {target:page.telemetry;function onChanged(){page.snapshotDirty=true}}
 Timer {interval:250;running:page.visible&&page.snapshotDirty;repeat:true;onTriggered:page.refreshSnapshot()}
 Timer {interval:10000;running:page.visible;repeat:true;onTriggered:page.network=page.systemProvider.currentNetwork()}
 component Label:SwirlText {textRole:"auxiliary";color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
 component Value:SwirlText {textRole:"data";color:Theme.text;font.pixelSize:Theme.fontSize(23);font.weight:Font.DemiBold;elide:Text.ElideRight}
 component Metric:SwirlGlassPanel {
  id:metric
  property string label
  property string value
  property string hint
  property string key
  property string iconName
  property color iconColor:Theme.accent
  property bool primary:false
  readonly property Item motionTitle:metricValue
  readonly property Item motionSurface:metric
  Layout.fillWidth:true;Layout.fillHeight:false;Layout.minimumWidth:0;Layout.preferredHeight:page.activityTileHeight;cornerRadius:page.activityCardRadius
  function activate(){key==="activeConnections"?SwirlMotion.navigateFrom(metric,"connections",key):page.trafficFrom(metric,key)}
  SwirlMotionButton {
    anchors.fill:parent
   objectName:"activityMetricHit_"+metric.key
   Accessible.name:metric.label+"详情";onClicked:metric.activate()
   background:Rectangle {radius:page.activityCardRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";border.width:parent.visualFocus?1:0;border.color:Theme.focusBorder}
   contentItem:Item {}
  }
  ColumnLayout {anchors.fill:parent;anchors.margins:Theme.dp(12);spacing:Theme.dp(4)
   RowLayout {Layout.fillWidth:true;SwirlText {text:metric.label;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlIconButton {implicitWidth:Theme.dp(22);implicitHeight:Theme.dp(22);iconName:"chevron-right";quiet:true;Accessible.name:metric.label+"详情";onClicked:metric.activate()}}
   Item {Layout.fillWidth:true;Layout.fillHeight:true
    ColumnLayout {anchors.centerIn:parent;width:parent.width;spacing:Theme.dp(2)
     SwirlIcon {name:metric.iconName;size:Theme.dp(48);color:metric.iconColor;Layout.alignment:Qt.AlignHCenter;Accessible.ignored:true}
     Value {id:metricValue;text:metric.value;font.pixelSize:Theme.fontSize(metric.primary?29:28);Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter}
    }
   }
    Label {text:metric.hint;Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter}
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
   SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:connectionContent.implicitHeight+Theme.dp(28);cornerRadius:page.activityCardRadius
    ColumnLayout {id:connectionContent;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.dp(14);spacing:Theme.dp(10)
     RowLayout {Layout.fillWidth:true
      Rectangle {width:Theme.dp(7);height:width;radius:width/2;color:page.nodeConnected&&page.engineController.apiHealthy?Theme.statusGreen:Theme.muted}
      SwirlText {text:page.activeNodeName;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight}
      SwirlButton {visible:!page.nodeConnected;quiet:true;text:"选择节点";implicitHeight:Theme.dp(26);onClicked:AppState.navigate("proxies")}
      Label {visible:page.nodeConnected;text:page.telemetry.sampled?"实时采样":page.sampleState}
     }
     GridLayout {Layout.fillWidth:true;columns:page.wide?4:2;columnSpacing:Theme.dp(16);rowSpacing:Theme.dp(8)
      Repeater {model:[{label:"网络",value:page.network.type||"尚未检测"},{label:"配置",value:extensionsProvider.profileName},{label:"出站",value:AppState.mode},{label:"外部 IP",value:page.telemetry.externalIp||"尚未检测"}]
       Label {id:infoLabel;required property var modelData;text:modelData.label+"  "+modelData.value;Layout.fillWidth:true;Layout.minimumWidth:0;HoverHandler{id:infoHover}SwirlToolTip {parent:infoLabel;visible:infoHover.hovered&&infoLabel.truncated;text:infoLabel.text;delay:650}}
      }
     }
    }
   }
   GridLayout {Layout.fillWidth:true;columns:page.wide?3:page.paired?2:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap;uniformCellWidths:true
    Metric {objectName:"activityUpload";label:"上传速率";key:"uploadRate";iconName:"upload";iconColor:Theme.cyan;primary:true;value:page.bytes(page.telemetry.uploadRate,page.telemetry.sampled);hint:page.telemetry.sampled?"每秒":page.sampleState}
    Metric {objectName:"activityDownload";label:"下载速率";key:"downloadRate";iconName:"download";iconColor:Theme.speedAccent;primary:true;value:page.bytes(page.telemetry.downloadRate,page.telemetry.sampled);hint:page.telemetry.sampled?"每秒":page.sampleState}
    Metric {objectName:"activityConnections";label:"活动连接";key:"activeConnections";iconName:"link";iconColor:Theme.green;value:page.telemetry.connectionsSampled?String(page.telemetry.activeConnections):"—";hint:page.telemetry.connectionsSampled?page.telemetry.activeProcesses+" 个进程":page.sampleState}
     Metric {objectName:"activityTotal";label:"累计流量";key:"totalTraffic";iconName:"chart";iconColor:Theme.accentIndigo;value:page.bytes(page.totals.total,page.totals.sampled);hint:"今日"}
     SwirlGlassPanel {id:trend;Layout.fillWidth:true;Layout.fillHeight:false;Layout.minimumWidth:0;Layout.preferredHeight:page.activityTileHeight;Layout.alignment:Qt.AlignTop;cornerRadius:page.activityCardRadius
      SwirlMotionButton {objectName:"activityTrendHit";anchors.fill:parent;onClicked:page.trafficFrom(trend,"trend");Accessible.name:"查看流量趋势"
       background:Rectangle {radius:page.activityCardRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";border.width:parent.visualFocus?1:0;border.color:Theme.focusBorder}
       contentItem:Item {}
      }
      ColumnLayout {anchors.fill:parent;anchors.margins:Theme.dp(12);spacing:Theme.dp(6)
       RowLayout {Layout.fillWidth:true;SwirlText {text:"流量趋势";color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlIconButton {implicitWidth:Theme.dp(22);implicitHeight:Theme.dp(22);iconName:"chevron-right";quiet:true;Accessible.name:"查看流量趋势";onClicked:page.trafficFrom(trend,"trend")}}
       Item {id:trendViewport;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;readonly property bool hasSamples:trendChart.records.some(r=>r.sampled)
        SwirlDailyTrafficChart {id:trendChart;x:0;y:-Theme.dp(20);width:parent.width;height:parent.height+Theme.dp(44);proxyOnly:false;opacity:trendViewport.hasSamples?1:0}
        ColumnLayout {anchors.centerIn:parent;visible:!trendViewport.hasSamples;spacing:Theme.dp(2)
         SwirlIcon {name:"chart";size:Theme.dp(48);color:Theme.cyan;Layout.alignment:Qt.AlignHCenter;Accessible.ignored:true}
         Label {text:"暂无走势";Layout.alignment:Qt.AlignHCenter}
        }
       }
      }
     }
    SwirlHeroCard {
     id:diagnostic;objectName:"internetDiagnosticCard";Layout.fillWidth:true;Layout.fillHeight:false;Layout.minimumWidth:0;Layout.preferredHeight:height;Layout.alignment:Qt.AlignTop;cornerRadius:page.activityCardRadius
     collapsedHeight:page.activityTileHeight;expandedHeight:collapsedHeight+diagnosticDetails.implicitHeight+Theme.dp(16);expanded:page.diagnosticOpen
      SwirlMotionButton {objectName:"activityQualityHit";x:0;y:0;width:parent.width;height:diagnostic.collapsedHeight;onClicked:page.diagnosticOpen=!page.diagnosticOpen;Accessible.name:page.diagnosticOpen?"收起网络质量详情":"查看网络质量详情"
       background:Rectangle {radius:page.activityCardRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";border.width:parent.visualFocus?1:0;border.color:Theme.focusBorder}
       contentItem:Item {}
      }
      ColumnLayout {x:Theme.dp(12);y:Theme.dp(12);width:parent.width-2*Theme.dp(12);height:diagnostic.collapsedHeight-Theme.dp(24);spacing:Theme.dp(4)
      RowLayout {Layout.fillWidth:true
        SwirlText {text:"网络质量";color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true}
       SwirlIconButton {objectName:"networkDiagnosticDetails";iconName:page.diagnosticOpen?"chevron-left":"chevron-right";quiet:true;onClicked:page.diagnosticOpen=!page.diagnosticOpen;Accessible.name:page.diagnosticOpen?"收起检测详情":"查看检测详情"}
      }
       Item {Layout.fillWidth:true;Layout.fillHeight:true
        ColumnLayout {anchors.centerIn:parent;width:parent.width;spacing:Theme.dp(2)
         Value {text:page.shownLatencies.internet||"—";font.pixelSize:Theme.fontSize(29);Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter}
         Label {text:"HTTPS 请求耗时";Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter}
        }
       }
       Label {text:page.shownMeasurementState||"尚未检测";Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter}
      }
      ColumnLayout {id:diagnosticDetails;x:Theme.cardPadding;y:diagnostic.collapsedHeight;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(10);visible:diagnostic.reveal>0;enabled:diagnostic.expanded
       RowLayout {Layout.fillWidth:true
        Label {text:"分别测量的结果";Layout.fillWidth:true}
        SwirlIconButton {id:networkDiagnosticButton;objectName:"networkDiagnosticButton";iconName:"refresh";quiet:true;enabled:page.telemetry.measurementState!=="正在测量";onClicked:page.telemetry.measureNetwork();Accessible.name:"重新测量网络质量";SwirlToolTip {parent:networkDiagnosticButton;visible:networkDiagnosticButton.hovered;text:"重新测量";delay:650}}
       }
       RowLayout {Layout.fillWidth:true;spacing:Theme.dp(8)
       Repeater {model:[{label:"路由",value:page.shownLatencies.router||"—"},{label:"DNS",value:page.shownLatencies.dns||"—"},{label:"代理",value:page.nodeConnected||page.previewMeasured?(page.shownLatencies.proxy||"—"):"未连接"}]
        ColumnLayout {required property var modelData;Layout.fillWidth:true;Layout.minimumWidth:0;Label{text:modelData.label}SwirlText {text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}}
       }
      }
       Label {text:"HTTPS 请求包含连接、TLS 和响应；各项分别采样，不能相加";Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      SwirlText {text:page.shownInternetDiagnostic.advice||"点击刷新，发起真实的 HTTPS 请求。";color:Theme.text;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12)}
      Label {text:"引擎："+(page.engineController.processAlive?"运行中":"未运行")+" · 接口："+(page.engineController.apiHealthy?"正常":"未就绪")+" · 端口："+(page.engineController.activeProxyPort||"未开放");Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:"出站："+(page.shownInternetDiagnostic.route||"尚未检测")+" · 节点："+page.activeNodeName;Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:page.proxyState;Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:page.shownInternetDiagnostic.http!==undefined?"HTTP "+page.shownInternetDiagnostic.http+" · 错误码 "+page.shownInternetDiagnostic.networkError+" · "+page.shownInternetDiagnostic.elapsedMs+" ms":"尚无 HTTPS 检测结果";Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
      Label {text:"代理："+(page.shownLatencies.proxy||"尚未测量")+" · "+(page.shownProxyDiagnostic.detail||"通过当前代理入口单独测量 HTTPS 往返。")+(page.shownProxyDiagnostic.networkError!==undefined?" · HTTP "+page.shownProxyDiagnostic.http+" · 错误码 "+page.shownProxyDiagnostic.networkError:"");Layout.fillWidth:true;wrapMode:Text.Wrap;elide:Text.ElideNone}
     }
    }
   }
    SwirlGlassPanel {Layout.fillWidth:true;Layout.fillHeight:false;Layout.minimumWidth:0;Layout.preferredHeight:Theme.dp(88);Layout.alignment:Qt.AlignTop;cornerRadius:page.activityCardRadius
     SwirlMotionButton {objectName:"activitySourcesHit";anchors.fill:parent;onClicked:page.openSources();Accessible.name:"查看流量来源"
      background:Rectangle {radius:page.activityCardRadius;color:parent.down?Theme.selected:parent.hovered?Theme.hover:"transparent";border.width:parent.visualFocus?1:0;border.color:Theme.focusBorder}
      contentItem:Item {}
     }
     ColumnLayout {anchors.fill:parent;anchors.margins:Theme.dp(14);spacing:Theme.dp(8)
      RowLayout {Layout.fillWidth:true;SwirlText {text:"流量来源";color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {text:"查看全部";quiet:true;onClicked:page.openSources()}}
      RowLayout {Layout.fillWidth:true;spacing:Theme.dp(10)
       SwirlText {text:page.ranks.length?page.ranks[0].name:"尚未采集来源";color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight;Layout.fillWidth:true}
       Label {visible:page.ranks.length>0;text:page.ranks.length?page.ranks[0].value:""}
      }
     }
    }
  }
 }
}
