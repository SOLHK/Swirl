import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 readonly property Item motionTitle:heading.titleItem
 readonly property var rankingRows:visible?(telemetry.revision,telemetry.ranking(kind,period,100)):[]
 readonly property var telemetry:engineController.telemetry
 property int period:AppState.trafficPeriod
 readonly property var motionSurfaces:({totalTraffic:totalSurface,uploadRate:uploadSurface,downloadRate:downloadSurface})
 readonly property var heroTargets:({totalTraffic:totalTraffic,uploadRate:uploadRate,downloadRate:downloadRate})
 Connections {target:AppState;function onTrafficPeriodChanged(){page.period=AppState.trafficPeriod}}
 property string kind:"domains"
 readonly property var totals:visible?(telemetry.revision,telemetry.summary(period)):({})
 ScrollView {id:scroll;anchors.fill:parent;anchors.margins:Theme.pagePadding;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout {width:scroll.availableWidth;spacing:Theme.sectionGap
   SwirlPageHeader {id:heading;Layout.fillWidth:true;title:qsTr("流量分析");description:qsTr("仅统计经过 Swirl 的流量。排行来自已采集连接，短连接可能无法归属。");metadata:qsTr("历史保留 32 天；期间累计与实时速率分别显示。")
    SwirlButton {text:qsTr("返回");visible:SwirlMotion.returnShared&&SwirlMotion.returnShared.route===AppState.currentPage;onClicked:SwirlMotion.returnToHub(totalTraffic)}
    SwirlComboBox {model:["今日","昨日","本周","本月"];currentIndex:page.period;onActivated:page.period=currentIndex;Accessible.name:qsTr("统计期间")}
   }
   GridLayout {Layout.fillWidth:true;columns:width<Theme.dp(650)?1:3;columnSpacing:Theme.dp(28);rowSpacing:Theme.dp(16)
    Item {id:totalSurface;property color color:Theme.material("content");Layout.fillWidth:true;implicitHeight:totalColumn.implicitHeight+Theme.dp(12)
     ColumnLayout {id:totalColumn;anchors.left:parent.left;anchors.right:parent.right;spacing:Theme.dp(8);SwirlText {text:qsTr("期间累计流量");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}SwirlText {id:totalTraffic;textRole:"data";text:page.totals.sampled?page.telemetry.formatBytes(page.totals.total):"—";color:Theme.text;font.pixelSize:Theme.fontSize(32);font.weight:Font.DemiBold;Layout.fillWidth:true}}
    }
    Item {id:uploadSurface;property color color:Theme.material("content");Layout.fillWidth:true;implicitHeight:uploadColumn.implicitHeight+Theme.dp(12)
     ColumnLayout {id:uploadColumn;anchors.left:parent.left;anchors.right:parent.right;spacing:Theme.dp(8);SwirlText {text:qsTr("实时上传 / 秒");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}SwirlText {id:uploadRate;textRole:"data";text:page.telemetry.sampled?page.telemetry.formatBytes(page.telemetry.uploadRate):"—";color:Theme.text;font.pixelSize:Theme.fontSize(27);font.weight:Font.DemiBold;Layout.fillWidth:true}}
    }
    Item {id:downloadSurface;property color color:Theme.material("content");Layout.fillWidth:true;implicitHeight:downloadColumn.implicitHeight+Theme.dp(12)
     ColumnLayout {id:downloadColumn;anchors.left:parent.left;anchors.right:parent.right;spacing:Theme.dp(8);SwirlText {text:qsTr("实时下载 / 秒");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}SwirlText {id:downloadRate;textRole:"data";text:page.telemetry.sampled?page.telemetry.formatBytes(page.telemetry.downloadRate):"—";color:Theme.text;font.pixelSize:Theme.fontSize(27);font.weight:Font.DemiBold;Layout.fillWidth:true}}
    }
   }
   Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
   GridLayout {Layout.fillWidth:true;columns:width<Theme.dp(520)?2:4;columnSpacing:Theme.dp(20);rowSpacing:Theme.dp(16)
    Repeater {model:[{label:qsTr("期间下载"),value:page.totals.sampled?page.telemetry.formatBytes(page.totals.down):"—"},{label:qsTr("期间上传"),value:page.totals.sampled?page.telemetry.formatBytes(page.totals.up):"—"},{label:qsTr("域名"),value:page.totals.sampled?String(page.totals.domains):"—"},{label:qsTr("应用来源"),value:page.totals.sampled?String(page.totals.apps):"—"}]
     ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:Theme.dp(6);SwirlText {text:modelData.label;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}SwirlText {text:modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(17);font.weight:Font.Medium}}
    }
   }
   SwirlSectionTitle {Layout.fillWidth:true;Layout.topMargin:Theme.dp(8);title:qsTr("实时传输速率");description:qsTr("最近 1 小时，来自实际采样。")}
   SwirlTrafficChart {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(220);rangeIndex:3}
   SwirlSectionTitle {Layout.fillWidth:true;Layout.topMargin:Theme.dp(8);title:qsTr("流量排行");description:qsTr("所选期间内已归属的连接，最多显示前 100 项。")}
Item { id:rankingTabs; Layout.fillWidth:true; Layout.preferredHeight:Theme.controlHeight
    readonly property int selectedIndex:["domains","apps","nodes"].indexOf(page.kind)
    SwirlArcMotion {id:rankingSelection;targetX:rankingTabs.selectedIndex*Theme.dp(100);targetY:0;bend:Theme.dp(4);motionEnabled:page.visible}
    Rectangle {x:rankingSelection.position.x;y:rankingSelection.position.y;width:Theme.dp(96);height:rankingTabs.height;radius:Theme.controlRadius;color:Theme.withAlpha(Theme.accent,0.1)}
    Row {spacing:Theme.dp(4)
     Repeater {model:[{name:"域名",key:"domains"},{name:"应用",key:"apps"},{name:"出口",key:"nodes"}];SwirlButton {required property var modelData;width:Theme.dp(96);text:modelData.name;quiet:true;onClicked:page.kind=modelData.key}}
    }
   }
   Item {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(340)
    SwirlDataTable {objectName:"trafficRankingTable";anchors.fill:parent;rows:page.rankingRows;incrementalRows:true;animateRowChanges:false;minimal:true;columns:[{key:"name",label:qsTr("名称"),w:300},{key:"connections",label:qsTr("连接次数"),w:120},{key:"upload",label:qsTr("上传"),w:130},{key:"download",label:qsTr("下载"),w:130},{key:"value",label:qsTr("总流量"),w:130}]}
    SwirlEmptyState {visible:page.rankingRows.length===0;anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(24));headline:qsTr("尚无可归属流量");detail:qsTr("此期间采集到的域名、应用或出口流量会显示在这里。")}
   }
   SwirlText {text:page.telemetry.storageError;visible:text.length>0;color:Theme.red;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12)}
   Item {Layout.preferredHeight:Theme.dp(16)}
  }
 }
}
