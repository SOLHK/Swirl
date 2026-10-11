import QtQuick
import QtQuick.Controls
import SwirlQuick
Item {
    id:graph
    // Retain the API used by the existing analytics pages.
    property var samples: []
    property bool showUpload: false
    property bool showDownload: true
    property string series: showDownload ? "down" : "up"
    property int rangeIndex: 0
    property real reveal: 1
    readonly property real rangeMinutes: [60,60,360,1440][rangeIndex]
    readonly property real maximum: series === "total" ? 4 : 12
    property var baseHistory: [2.7,4.1,5.4,3.8,5.9,4.4,6.5,4.1,3.1,4.2,3.3,4.7,3.3,3.7,2.7,2.1,1.7,1.4,0.8,1.0,0.35,0]
    function valueAt(i) {
        if(series === "total") return 2.36+(AppState.totalGB-2.36)*i/(baseHistory.length-1)
        var v=baseHistory[i]*(series === "up" ? 0.24 : 1)
        if(i===baseHistory.length-1) return series === "up" ? AppState.demoUp : AppState.demoDown
        if(i===baseHistory.length-2 && !AppState.proxyOn) return 0
        return v*(rangeIndex>1 ? 0.8+0.2*Math.cos(i+rangeIndex) : 1)
    }
    function repaint(){plot.requestPaint()}
    function transition(){reveal=0.3;updateAnimation.restart()}
    onSeriesChanged:transition()
    onRangeIndexChanged:transition()
    onRevealChanged:repaint()
    onSamplesChanged:repaint()
    implicitHeight:130; implicitWidth:550
    NumberAnimation { id:updateAnimation; target:graph; property:"reveal"; to:1; duration:Theme.motion; easing.type:Easing.OutCubic }
    Connections { target:AppState; function onDemoTickChanged(){graph.repaint()} function onProxyOnChanged(){graph.transition()} }
    Connections { target:Theme; function onDarkChanged(){graph.repaint()} }
    Item {
        x:0; y:4; width:66; height:plot.height
        Repeater {
            model:4
            Text {
                required property int index
                width:66; height:(plot.height-1)/3
                text:graph.series==="total" ? (4-index*4/3).toFixed(1)+" GB" : index===3 ? "0" : (12-index*4)+" MB/s"
                color:Theme.muted; font.pixelSize:16; horizontalAlignment:Text.AlignRight; rightPadding:0
                y:index*(plot.height-1)/3-8
            }
        }
    }
    Canvas {
        id:plot
        x:79; y:5; width:parent.width-x-8; height:parent.height-33
        onWidthChanged:requestPaint(); onHeightChanged:requestPaint()
        onPaint: {
            var c=getContext("2d");c.reset()
            var w=width,h=height-1,n=graph.baseHistory.length
            function X(i){return i*w/(n-1)}
            function Y(i){return h-graph.valueAt(i)*h/graph.maximum*graph.reveal}
            c.strokeStyle=Theme.dark?"#405875":"#E0EBFA";c.lineWidth=1
            for(var k=0;k<4;k++){c.beginPath();c.moveTo(0,k*h/3);c.lineTo(w,k*h/3);c.stroke()}
            for(var a=0;a<5;a++){c.beginPath();c.moveTo(a*w/4,0);c.lineTo(a*w/4,h);c.stroke()}
            function curve(){c.moveTo(X(0),Y(0));for(var i=1;i<n;i++){var mid=(X(i-1)+X(i))/2;c.bezierCurveTo(mid,Y(i-1),mid,Y(i),X(i),Y(i))}}
            var color=graph.series==="up" ? Theme.green : graph.series==="total" ? Theme.muted : Theme.accent
            var gradient=c.createLinearGradient(0,0,0,h);gradient.addColorStop(0,Theme.withAlpha(color,0.35));gradient.addColorStop(1,Theme.withAlpha(color,0.06))
            c.beginPath();curve();c.lineTo(w,h);c.lineTo(0,h);c.closePath();c.fillStyle=gradient;c.fill()
            c.beginPath();curve();c.strokeStyle=color;c.lineWidth=2;c.stroke()
            if(hover.containsMouse){var ix=Math.round(hover.mouseX/w*(n-1));c.beginPath();c.moveTo(X(ix),0);c.lineTo(X(ix),h);c.strokeStyle=Theme.withAlpha(color,0.4);c.stroke();c.beginPath();c.arc(X(ix),Y(ix),3,0,Math.PI*2);c.fillStyle=color;c.fill()}
        }
        MouseArea {
            id:hover; anchors.fill:parent; hoverEnabled:true
            onPositionChanged:plot.requestPaint(); onContainsMouseChanged:plot.requestPaint()
            ToolTip.visible:containsMouse
            ToolTip.text: {
                var i=Math.max(0,Math.min(graph.baseHistory.length-1,Math.round(mouseX/width*(graph.baseHistory.length-1))))
                var when=new Date(AppState.sessionNow.getTime()-(1-i/(graph.baseHistory.length-1))*graph.rangeMinutes*60000)
                return Qt.formatDateTime(when,"MM-dd HH:mm")+" · "+graph.valueAt(i).toFixed(2)+(graph.series==="total" ? " GB" : " MB/s")+(i===graph.baseHistory.length-1 ? " · 当前演示" : " · 历史演示")
            }
        }
    }
    Row {
        x:plot.x; y:parent.height-22; width:plot.width
        Repeater {
            model:5
            Text {
                required property int index
                width:plot.width/5; font.pixelSize:14; color:Theme.muted
                horizontalAlignment:index===0?Text.AlignLeft:index===4?Text.AlignRight:Text.AlignHCenter
                text:index===4 ? "现在" : graph.rangeIndex<2 ? ["1小时前","45分钟前","30分钟前","15分钟前"][index] : (graph.rangeMinutes*(1-index/4)/60)+"小时前"
            }
        }
    }
}
