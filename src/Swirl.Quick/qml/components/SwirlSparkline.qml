import QtQuick
import SwirlQuick
Canvas {
        onVisibleChanged:if(visible)requestPaint();

    id:plot
    property color lineColor: Theme.accent
    property bool bars: false
    property bool active: AppState.proxyOn
    property var values: []
    onActiveChanged:requestPaint()
    onValuesChanged:requestPaint()
    onWidthChanged:requestPaint()
    onHeightChanged:requestPaint()
    Connections { target:AppState; function onMeasurementTickChanged(){if(plot.active)plot.requestPaint()} }
    onPaint: {
        var c=getContext("2d");c.reset()
        var n=values.length, base=height-Theme.dp(2)
        if(n<2)return
        if(bars) {
            var arr=values
            c.fillStyle=Theme.dark ? "#6584A4" : "#CFDDF0"
            for(var j=0;j<arr.length;j++)c.fillRect(j*width/arr.length,base-arr[j]*(height-Theme.dp(4)),width/arr.length*0.65,arr[j]*(height-Theme.dp(4)))
            return
        }
        function x(i){return i*width/(n-1)}
        function y(i){return base-values[i]*(height-Theme.dp(4))*0.85}
        function path(){c.moveTo(x(0),y(0));for(var i=1;i<n;i++){var mx=(x(i-1)+x(i))/2;c.bezierCurveTo(mx,y(i-1),mx,y(i),x(i),y(i))}}
        var grad=c.createLinearGradient(0,0,0,base);grad.addColorStop(0,Theme.withAlpha(lineColor,0.23));grad.addColorStop(1,Theme.withAlpha(lineColor,0))
        c.beginPath();path();c.lineTo(width,base);c.lineTo(0,base);c.closePath();c.fillStyle=grad;c.fill()
        c.beginPath();path();c.strokeStyle=lineColor;c.lineWidth=Theme.dp(1.8);c.stroke()
    }
}
