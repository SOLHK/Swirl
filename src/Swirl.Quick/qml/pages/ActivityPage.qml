pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;required property var systemProvider
 property int period:0;property int trafficKind:0;property int rankingKind:0;property bool diagnosticOpen:false
 property var network:systemProvider.currentNetwork()
 readonly property var telemetry:engineController.telemetry
 readonly property var totals:(telemetry.revision,telemetry.summary(period===0?0:3))
 readonly property var distribution:(telemetry.revision,telemetry.distribution(period===0?0:3))
 readonly property var ranks:{telemetry.revision;const range=period===0?0:3;return rankingKind===0?telemetry.ranking("apps",range,8).concat(telemetry.ranking("devices",range,8)).sort((a,b)=>b.total-a.total).slice(0,5):telemetry.ranking(["apps","domains","nodes"][rankingKind],range,5)}
 function bytes(n,sampled){return sampled?telemetry.formatBytes(n):"—"}
 function trafficFrom(item,key){AppState.trafficPeriod=period===0?0:3;SwirlMotion.navigateFrom(item,"traffic",key)}
 Timer {interval:10000;running:page.visible;repeat:true;onTriggered:page.network=page.systemProvider.currentNetwork()}
 component Label:SwirlText {renderType:Text.NativeRendering;color:Theme.muted;font.pixelSize:Theme.fontSize(12);font.family:Theme.fontFamily}
 component Value:SwirlText {renderType:Text.NativeRendering;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(28);font.weight:Font.DemiBold;elide:Text.ElideRight;textFormat:Text.PlainText}
 component Card:SwirlGlassPanel {cornerRadius:Theme.independentCardRadius}
 ScrollView {
  id:scroll;anchors.fill:parent;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout {
   width:Math.min(scroll.availableWidth,Theme.dp(1050));spacing:Theme.dp(14)
   SwirlText {renderType:Text.NativeRendering;text:"活动";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.topMargin:Theme.dp(4)}
   GridLayout {Layout.fillWidth:true;Layout.topMargin:Theme.dp(4);Layout.bottomMargin:Theme.dp(6);columns:4;columnSpacing:Theme.dp(16)
    Repeater {model:[{label:"网络",value:page.network.type||"未检测"},{label:"配置",value:extensionsProvider.profileName},{label:"出站模式",value:AppState.mode},{label:"外部 IP",value:page.telemetry.externalIp||"未检测"}]
     ColumnLayout {required property var modelData;Layout.fillWidth:true;Layout.minimumWidth:0;spacing:Theme.dp(4)
      Label {text:modelData.label}
      SwirlText {renderType:Text.NativeRendering;text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.Medium;Layout.fillWidth:true;elide:Text.ElideRight}
     }
    }
   }
   RowLayout {Layout.fillWidth:true;spacing:Theme.dp(14)
    SwirlHeroCard {
     id:diagnostic;objectName:"internetDiagnosticCard";Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(300);Layout.preferredWidth:Theme.dp(480);Layout.preferredHeight:height;Layout.alignment:Qt.AlignTop
     collapsedHeight:Theme.dp(184);expandedHeight:collapsedHeight+diagnosticDetails.implicitHeight+Theme.dp(16)
     expanded:page.diagnosticOpen;cornerRadius:Theme.independentCardRadius
     ColumnLayout {x:Theme.cardPadding;y:Theme.cardPadding;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(8)
      RowLayout {Layout.fillWidth:true;spacing:Theme.dp(6)
       Label {text:"互联网延迟";Layout.fillWidth:true}
       SwirlIconButton {objectName:"networkDiagnosticButton";iconName:"refresh";quiet:true;enabled:page.telemetry.measurementState!=="正在测量";onClicked:page.telemetry.measureNetwork();Accessible.name:"网络诊断";ToolTip.visible:hovered;ToolTip.text:"发起网络诊断";ToolTip.delay:650}
       SwirlIconButton {objectName:"networkDiagnosticDetails";iconName:page.diagnosticOpen?"chevron-left":"chevron-right";quiet:true;onClicked:page.diagnosticOpen=!page.diagnosticOpen;Accessible.name:page.diagnosticOpen?"收起检测详情":"查看检测详情"}
      }
      Value {text:page.telemetry.latencies.internet||"尚未检测";Layout.fillWidth:true;font.pixelSize:Theme.fontSize(25)}
      RowLayout {Layout.fillWidth:true;spacing:Theme.dp(12)
       Repeater {model:[{label:"路由",value:page.telemetry.latencies.router||"—"},{label:"DNS",value:page.telemetry.latencies.dns||"—"},{label:"代理",value:page.engineController.activeNodeId.length?(page.telemetry.latencies.proxy||"—"):"未连接"}]
        ColumnLayout {required property var modelData;Layout.fillWidth:true;Layout.minimumWidth:0;spacing:Theme.dp(3);Label {text:modelData.label}SwirlText {renderType:Text.NativeRendering;text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;elide:Text.ElideRight}}
       }
      }
      ColumnLayout {id:diagnosticDetails;Layout.fillWidth:true;spacing:Theme.dp(9);opacity:Math.max(0,Math.min(1,(diagnostic.reveal-0.2)/0.65));enabled:diagnostic.expanded
       Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
       SwirlText {renderType:Text.NativeRendering;text:page.telemetry.internetDiagnostic.advice||"点击刷新，发起真实的 HTTPS 请求。";color:Theme.text;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12)}
       Label {text:"引擎："+(page.engineController.processAlive?"运行中":"未运行")+" · 接口："+(page.engineController.apiHealthy?"正常":"未就绪")+" · 端口："+(page.engineController.activeProxyPort||"未开放");Layout.fillWidth:true;wrapMode:Text.Wrap}
       Label {text:"出站："+(page.telemetry.internetDiagnostic.route||"未检测")+" · 节点："+page.engineController.selectedNodeName;Layout.fillWidth:true;wrapMode:Text.Wrap}
       Label {text:"系统代理："+(page.engineController.systemProxy.owned?"Swirl 已接管":page.engineController.systemProxy.systemEnabled?"由其他应用启用":"未启用");Layout.fillWidth:true;wrapMode:Text.Wrap}
       Label {text:page.telemetry.internetDiagnostic.http!==undefined?"HTTP "+page.telemetry.internetDiagnostic.http+" · 错误码 "+page.telemetry.internetDiagnostic.networkError+" · "+page.telemetry.internetDiagnostic.elapsedMs+" ms":"尚无 HTTPS 检测结果";Layout.fillWidth:true;wrapMode:Text.Wrap}
      }
     }
    }
    ColumnLayout {Layout.fillWidth:true;Layout.preferredWidth:Theme.dp(280);Layout.minimumWidth:Theme.dp(216);Layout.alignment:Qt.AlignTop;spacing:Theme.dp(12)
     Repeater {model:["上传","下载"]
     Card {required property string modelData;required property int index;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(86)
      ColumnLayout {anchors.fill:parent;anchors.margins:Theme.dp(16);spacing:Theme.dp(4)
       RowLayout {Layout.fillWidth:true;Label {text:modelData+(page.telemetry.sampled?" / 秒":" · 等待采样");Layout.fillWidth:true}SwirlIcon {name:index===0?"upload":"download";color:index===0?Theme.accentIndigo:Theme.cyan;size:Theme.dp(15)}}
       RowLayout {Layout.fillWidth:true;Value {id:rate;Layout.fillWidth:true;text:page.bytes(index===0?page.telemetry.uploadRate:page.telemetry.downloadRate,page.telemetry.sampled);font.pixelSize:Theme.fontSize(22)}SwirlIconButton {iconName:"chevron-right";quiet:true;onClicked:page.trafficFrom(rate,index===0?"uploadRate":"downloadRate");Accessible.name:modelData+"流量分析"}}
      }
     }
    }
    }
   }
   RowLayout {Layout.fillWidth:true;spacing:Theme.dp(14);Layout.alignment:Qt.AlignTop;layoutDirection:Qt.RightToLeft
    ColumnLayout {Layout.fillWidth:true;Layout.preferredWidth:Theme.dp(280);Layout.minimumWidth:Theme.dp(216);spacing:Theme.dp(14)
     Card {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(152)
      ColumnLayout {anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(8)
       RowLayout {Layout.fillWidth:true;Label {text:"活动连接";Layout.fillWidth:true}SwirlIconButton {iconName:"chevron-right";quiet:true;onClicked:SwirlMotion.navigateFrom(connectionValue,"connections","activeConnections");Accessible.name:"连接记录"}}
       RowLayout {Layout.fillWidth:true;Value {id:connectionValue;text:page.telemetry.connectionsSampled?String(page.telemetry.activeConnections):"—";Layout.fillWidth:true}Label {text:page.telemetry.connectionsSampled?page.telemetry.activeProcesses+" 个进程":"等待采样"}}
       Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
       Label {text:"DHCP 设备  "+gatewayProvider.devices.filter(r=>r.status==="租用中").length;Layout.fillWidth:true}
       Item {Layout.fillHeight:true}
      }
     }
     Card {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(174)
      ColumnLayout {anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(8)
       RowLayout {Layout.fillWidth:true;Label {text:"总流量";Layout.fillWidth:true}SwirlSegmentedControl {Layout.preferredWidth:Theme.dp(116);options:["今日","本月"];currentIndex:page.period;onActivated:index=>page.period=index}}
       RowLayout {Layout.fillWidth:true;Value {id:totalValue;Layout.fillWidth:true;text:page.bytes(page.totals.total,page.totals.sampled)}SwirlIconButton {iconName:"chevron-right";quiet:true;onClicked:page.trafficFrom(totalValue,"totalTraffic");Accessible.name:"详细流量统计"}}
       RowLayout {Layout.fillWidth:true;Label {text:"直连 "+(page.distribution[1]?page.distribution[1].value:"—");Layout.fillWidth:true}Label {text:"代理 "+(page.distribution[0]?page.distribution[0].value:"—")}}
       Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(5);radius:height/2;color:Theme.field
        Rectangle {height:parent.height;radius:height/2;color:Theme.accentIndigo;width:page.totals.total>0?parent.width*Math.max(0,Math.min(1,(page.distribution[1]?page.distribution[1].bytes:0)/page.totals.total)):0}
       }
      }
     }
    }
    Card {Layout.fillWidth:true;Layout.preferredWidth:Theme.dp(480);Layout.minimumWidth:Theme.dp(300);Layout.preferredHeight:Theme.dp(340)
     ColumnLayout {anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(10)
      RowLayout {Layout.fillWidth:true;Label {text:"流量趋势";Layout.fillWidth:true}SwirlSegmentedControl {Layout.preferredWidth:Theme.dp(126);options:["全部","仅代理"];currentIndex:page.trafficKind;onActivated:index=>page.trafficKind=index}}
      SwirlDailyTrafficChart {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(96);proxyOnly:page.trafficKind===1}
      SwirlSegmentedControl {Layout.fillWidth:true;options:["进程与设备","域名","策略"];currentIndex:page.rankingKind;onActivated:index=>page.rankingKind=index}
      ColumnLayout {Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(2)
       Repeater {model:page.ranks
        SwirlMotionButton {id:rank;required property var modelData;Layout.fillWidth:true;implicitHeight:Theme.dp(24);padding:Theme.dp(3);enabled:page.rankingKind===0
         background:Rectangle {color:rank.hovered?Theme.hover:"transparent";radius:Theme.controlRadius}
         contentItem:RowLayout {SwirlText {renderType:Text.NativeRendering;id:rankName;Layout.fillWidth:true;text:rank.modelData.name;color:Theme.text;elide:Text.ElideRight;font.pixelSize:Theme.fontSize(12)}Label {text:rank.modelData.value}}
         onClicked:{AppState.trafficPeriod=page.period===0?0:3;AppState.trafficSelectedProcess=modelData.name;SwirlMotion.navigateFrom(rankName,"processes","processName")}
        }
       }
       Label {visible:page.ranks.length===0;text:"尚未采集排行数据";Layout.fillWidth:true;Layout.alignment:Qt.AlignTop}
       Item {Layout.fillHeight:true}
      }
     }
    }
   }
   Item {Layout.preferredHeight:Theme.dp(12)}
  }
 }
}
