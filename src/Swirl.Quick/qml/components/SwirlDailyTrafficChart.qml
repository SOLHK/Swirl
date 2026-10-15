import QtQuick
import SwirlQuick
Item {
 id:graph
 property bool proxyOnly:false
 property var records:[]
 property bool dirty:true
 readonly property real maximum:Math.max(1,...records.map(r=>r.value))
 function refresh(){if(!visible)return;const now=Date.now();const next=engineController.telemetry.dailyTraffic(proxyOnly).filter(r=>r.time<=now);if(JSON.stringify(next)!==JSON.stringify(records))records=next;dirty=false;repaint()}
 function repaint(){if(visible && Window.window && Window.window.visibility!==Window.Minimized)plot.requestPaint()}
 onProxyOnlyChanged:{dirty=true;refresh()}
 onRecordsChanged:repaint()
 onVisibleChanged:if(visible)refresh()
 Component.onCompleted:refresh()
 Connections {target:engineController.telemetry;function onChanged(){graph.dirty=true}}
 Timer {interval:500;running:graph.visible&&graph.dirty;repeat:true;onTriggered:graph.refresh()}
 Connections {target:Theme;function onDarkChanged(){graph.repaint()}}
 Canvas {
  id:plot;anchors.fill:parent;anchors.topMargin:Theme.dp(20);anchors.bottomMargin:Theme.dp(24)
  onWidthChanged:graph.repaint();onHeightChanged:graph.repaint()
  onPaint:{const c=getContext("2d");c.reset();c.strokeStyle=Theme.border;c.lineWidth=1;for(let i=0;i<3;i++){c.beginPath();c.moveTo(0,i*height/2);c.lineTo(width,i*height/2);c.stroke()}const n=Math.max(1,graph.records.length);c.fillStyle=Theme.cyan;for(let i=0;i<n;i++){const row=graph.records[i];if(!row || !row.sampled)continue;const bar=Math.max(1,width/n-Theme.dp(3));const value=row.value/graph.maximum*(height-Theme.dp(5));c.fillRect(i*width/n,height-value,bar,value)}}
 }
 SwirlText {anchors.top:parent.top;anchors.right:parent.right;text:graph.records.some(r=>r.sampled)?engineController.telemetry.formatBytes(graph.maximum)+" / 30 分钟":"单位：B / 30 分钟";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
 SwirlText {anchors.centerIn:plot;visible:!graph.records.some(r=>r.sampled);text:"尚未采集今日流量";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
 SwirlText {anchors.left:parent.left;anchors.bottom:parent.bottom;text:"00:00";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
 SwirlText {anchors.right:parent.right;anchors.bottom:parent.bottom;text:graph.records.length?Qt.formatDateTime(new Date(graph.records[graph.records.length-1].time),"HH:mm"):"现在";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
}
