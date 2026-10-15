import QtQuick
import SwirlQuick
Item {
    id:graph
    property bool proxyOnly:false
    readonly property var records:(engineController.telemetry.revision,engineController.telemetry.dailyTraffic(proxyOnly))
    readonly property real maximum:Math.max(1,...records.map(r=>r.value))
    function repaint(){if(visible)plot.requestPaint()}
    onRecordsChanged:repaint()
    onWidthChanged:repaint()
    onVisibleChanged:repaint()
    Connections {target:Theme;function onDarkChanged(){graph.repaint()}}
    Canvas {
        id:plot;anchors.fill:parent;anchors.bottomMargin:Theme.dp(24)
        onPaint:{const c=getContext("2d");c.reset();c.strokeStyle=Theme.border;c.lineWidth=1;for(let i=0;i<3;i++){c.beginPath();c.moveTo(0,i*height/2);c.lineTo(width,i*height/2);c.stroke()}c.fillStyle=Theme.cyan;for(let i=0;i<graph.records.length;i++){const row=graph.records[i];if(!row.sampled)continue;const bar=Math.max(1,width/48-Theme.dp(3));const value=row.value/graph.maximum*(height-Theme.dp(5));c.fillRect(i*width/48,height-value,bar,value)}}
    }
    SwirlText {anchors.left:parent.left;anchors.bottom:parent.bottom;text:"00:00";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
    SwirlText {anchors.horizontalCenter:parent.horizontalCenter;anchors.bottom:parent.bottom;text:"12:00";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
    SwirlText {anchors.right:parent.right;anchors.bottom:parent.bottom;text:"24:00";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
}
