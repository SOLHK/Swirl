import QtQuick
import QtQuick.Controls
import SwirlQuick
Item {
    id:graph
    // Retain the API used by the existing analytics pages.
    property var points: (engineController.telemetry.revision,engineController.telemetry.historyPoints(series,[60,60,300,3600][rangeIndex]))
    property var samples: points.map(function(p){return p.value})
    readonly property real endTime: (engineController.telemetry.revision,Date.now())
    readonly property real startTime: endTime-rangeMinutes*60000
    property bool showUpload: false
    property bool showDownload: true
    property string series: showDownload ? "down" : "up"
    property int rangeIndex: 0
    property real reveal: 1
    readonly property real rangeMinutes: [1,1,5,60][rangeIndex]
    readonly property real maximum: Math.max(1,Math.max.apply(null,samples))
    readonly property var baseHistory: samples
    function valueAt(i) { return baseHistory[i] || 0 }
    function nearestIndex(fraction){if(!points.length)return -1;var target=startTime+fraction*(endTime-startTime),best=-1,distance=3000;for(var i=0;i<points.length;i++){var delta=Math.abs(points[i].time-target);if(delta<distance){distance=delta;best=i}}return best}
    function repaint(){if(visible && Window.window && Window.window.visibility!==Window.Minimized)plot.requestPaint()}
    function transition(){if(!visible || SwirlMotion.reduced){updateAnimation.stop();reveal=1;return}reveal=0.3;updateAnimation.restart()}
    onVisibleChanged:if(visible)repaint();else updateAnimation.stop()
    onSeriesChanged:transition()
    onRangeIndexChanged:transition()
    onRevealChanged:repaint()
    onSamplesChanged:repaint()
    implicitHeight:Theme.dp(130); implicitWidth:Theme.dp(550)
    NumberAnimation { id:updateAnimation; target:graph; property:"reveal"; to:1; duration:Theme.motion; easing.type:Easing.OutCubic }
    Connections { target:AppState; function onMeasurementTickChanged(){graph.repaint()} function onProxyOnChanged(){graph.transition()} }
    Connections { target:Theme; function onDarkChanged(){graph.repaint()} }
    Item {
        x:Theme.dp(0); y:Theme.dp(4); width:Theme.dp(66); height:plot.height
        Repeater {
            model:4
            Text {
                required property int index
                width:Theme.dp(66); height:(plot.height-Theme.dp(1))/3
                text:engineController.telemetry.formatBytes(graph.maximum*(1-index/3))+"/s"
                color:Theme.muted; font.pixelSize:Theme.fontSize(16); horizontalAlignment:Text.AlignRight; rightPadding:Theme.dp(0)
                y:index*(plot.height-Theme.dp(1))/3-Theme.dp(8)
            }
        }
    }
    Canvas {
        onVisibleChanged:if(visible)requestPaint();

        id:plot
        x:Theme.dp(79); y:Theme.dp(5); width:parent.width-x-Theme.dp(8); height:parent.height-Theme.dp(33)
        onWidthChanged:requestPaint(); onHeightChanged:requestPaint()
        onPaint: {
            var c=getContext("2d");c.reset()
            var w=width,h=height-Theme.dp(1),n=graph.baseHistory.length
            function X(i){return points.length===n?Math.max(0,Math.min(w,(points[i].time-graph.startTime)*w/(graph.endTime-graph.startTime))):i*w/(n-1)}
            var points=graph.points
            function Y(i){return h-graph.valueAt(i)*h/graph.maximum*graph.reveal}
            c.strokeStyle=Theme.dark?"#405875":"#E0EBFA";c.lineWidth=Theme.dp(1)
            for(var k=0;k<4;k++){c.beginPath();c.moveTo(0,k*h/3);c.lineTo(w,k*h/3);c.stroke()}
            for(var a=0;a<5;a++){c.beginPath();c.moveTo(a*w/4,0);c.lineTo(a*w/4,h);c.stroke()}
            if(n<2)return
            function curve(first,last){c.moveTo(X(first),Y(first));for(var i=first+1;i<=last;i++){var mid=(X(i-1)+X(i))/2;c.bezierCurveTo(mid,Y(i-1),mid,Y(i),X(i),Y(i))}}
            var color=graph.series==="up" ? Theme.green : graph.series==="total" ? Theme.muted : Theme.accent
            var gradient=c.createLinearGradient(0,0,0,h);gradient.addColorStop(0,Theme.withAlpha(color,0.35));gradient.addColorStop(1,Theme.withAlpha(color,0.06))
            for(var first=0;first<n;){var last=first;while(last+1<n&&(points.length!==n||points[last+1].time-points[last].time<=6000))last++;
                c.beginPath();curve(first,last);c.lineTo(X(last),h);c.lineTo(X(first),h);c.closePath();c.fillStyle=gradient;c.fill()
                c.beginPath();curve(first,last);c.strokeStyle=color;c.lineWidth=Theme.dp(2);c.stroke();first=last+1
            }
            var ix=graph.nearestIndex(hover.mouseX/w)
            if(hover.containsMouse&&ix>=0){c.beginPath();c.moveTo(X(ix),0);c.lineTo(X(ix),h);c.strokeStyle=Theme.withAlpha(color,0.4);c.stroke();c.beginPath();c.arc(X(ix),Y(ix),Theme.dp(3),0,Math.PI*2);c.fillStyle=color;c.fill()}
        }
        MouseArea {
            id:hover; anchors.fill:parent; hoverEnabled:true
            onPositionChanged:plot.requestPaint(); onContainsMouseChanged:plot.requestPaint()
            ToolTip.visible:containsMouse&&!previewCaptureMode&&graph.nearestIndex(mouseX/width)>=0
            ToolTip.text: {
                if(graph.nearestIndex(mouseX/width)<0)return ""
                var i=Math.max(0,graph.nearestIndex(mouseX/width))
                var when=new Date(graph.points.length===graph.baseHistory.length?graph.points[i].time:graph.startTime+i/(graph.baseHistory.length-1)*(graph.endTime-graph.startTime))
                return Qt.formatDateTime(when,"MM-dd HH:mm")+" · "+engineController.telemetry.formatBytes(graph.valueAt(i))+"/s"+(i===graph.baseHistory.length-1 ? " · 当前" : " · 历史")
            }
        }
    }
    Row {
        x:plot.x; y:parent.height-Theme.dp(22); width:plot.width
        Repeater {
            model:5
            Text {
                required property int index
                width:plot.width/5; font.pixelSize:Theme.fontSize(14); color:Theme.muted
                horizontalAlignment:index===0?Text.AlignLeft:index===4?Text.AlignRight:Text.AlignHCenter
                text:index===4 ? "现在" : graph.rangeIndex===0 ? ["1分钟前","45秒前","30秒前","15秒前"][index] : (graph.rangeMinutes*(1-index/4))+"分钟前"
            }
        }
    }
}
