import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 readonly property var telemetry:engineController.telemetry
 property int period:0
 property string kind:"domains"
 readonly property var totals:(telemetry.revision,telemetry.summary(period))
 ScrollView { id:scroll;anchors.fill:parent;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout { width:scroll.availableWidth;spacing:Theme.gap
   RowLayout { Layout.fillWidth:true
    Text { text:"流量分析";font.pixelSize:Theme.fontSize(30);font.weight:Font.DemiBold;color:Theme.text;Layout.fillWidth:true }
    SwirlComboBox { model:["今日","昨日","本周"];onActivated:page.period=currentIndex }
   }
   Text { text:"仅统计经过 Swirl 的流量；排行基于已采集连接，短于采样间隔的连接可能无法归属。历史保留 32 天。";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap }
   GridLayout { Layout.fillWidth:true;columns:page.width>Theme.dp(800)?4:2;columnSpacing:Theme.gap;rowSpacing:Theme.gap
    SwirlMetricCard { Layout.fillWidth:true;label:"下载";value:totals.sampled?telemetry.formatBytes(totals.down):"未采集";iconName:"download" }
    SwirlMetricCard { Layout.fillWidth:true;label:"上传";value:totals.sampled?telemetry.formatBytes(totals.up):"未采集";iconName:"upload" }
    SwirlMetricCard { Layout.fillWidth:true;label:"域名";value:totals.sampled?String(totals.domains):"未采集";iconName:"globe" }
    SwirlMetricCard { Layout.fillWidth:true;label:"来源";value:totals.sampled?String(totals.apps):"未采集";iconName:"sliders" }
   }
   SwirlGlassPanel { Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(245)
    ColumnLayout { anchors.fill:parent;anchors.margins:Theme.cardPadding
     Text { text:"实时传输速率 · 最近 1 小时";color:Theme.text;font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold }
     SwirlTrafficChart { Layout.fillWidth:true;Layout.fillHeight:true;rangeIndex:3 }
    }
   }
   RowLayout { Layout.fillWidth:true
    Repeater { model:[{name:"域名",key:"domains"},{name:"应用",key:"apps"},{name:"出口",key:"nodes"}];SwirlButton { required property var modelData;text:modelData.name;primary:page.kind===modelData.key;onClicked:page.kind=modelData.key } }
   }
   SwirlGlassPanel { Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(350)
    SwirlDataTable { anchors.fill:parent;rows:(telemetry.revision,telemetry.ranking(page.kind,page.period,100));columns:[{key:"name",label:"名称",w:300},{key:"connections",label:"连接次数",w:120},{key:"upload",label:"上传",w:130},{key:"download",label:"下载",w:130},{key:"value",label:"总流量",w:130}] }
   }
   Text { text:telemetry.storageError;visible:text.length>0;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap }
  }
 }
}
