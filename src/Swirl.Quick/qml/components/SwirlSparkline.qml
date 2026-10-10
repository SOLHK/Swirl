import QtQuick
import SwirlQuick
Canvas {
    id:plot
    property color lineColor: Theme.accent
    property bool bars: false
    property bool active: AppState.proxyOn
    property var values: [0,0.04,0.2,0.22,0.55,0.52,0.82,0.5,0.55,0.1,0.02,0]
    onActiveChanged:requestPaint()
    onValuesChanged:requestPaint()
    onWidthChanged:requestPaint()
    onHeightChanged:requestPaint()
    Connections { target:AppState; function onDemoTickChanged(){if(plot.active)plot.requestPaint()} }
    onPaint: {
        var c=getContext("2d");c.reset()
        var n=values.length, base=height-2
        if(bars) {
            var arr=[0.1,0.18,0.27,0.43,0.35,0.52,0.68,0.45,0.32,0.77,1,0.49,0.33,0.58,active?0.28:0]
            c.fillStyle=Theme.dark ? "#6584A4" : "#CFDDF0"
            for(var j=0;j<arr.length;j++)c.fillRect(j*width/arr.length,base-arr[j]*(height-4),width/arr.length*0.65,arr[j]*(height-4))
            return
        }
        function x(i){return i*width/(n-1)}
        function y(i){var v=active&&i===n-1?0.5:values[i];return base-v*(height-4)*0.75-(active&&i>0?Math.sin(i+AppState.demoTick)*1.2:0)}
        function path(){c.moveTo(x(0),y(0));for(var i=1;i<n;i++){var mx=(x(i-1)+x(i))/2;c.bezierCurveTo(mx,y(i-1),mx,y(i),x(i),y(i))}}
        var grad=c.createLinearGradient(0,0,0,base);grad.addColorStop(0,Theme.withAlpha(lineColor,0.23));grad.addColorStop(1,Theme.withAlpha(lineColor,0))
        c.beginPath();path();c.lineTo(width,base);c.lineTo(0,base);c.closePath();c.fillStyle=grad;c.fill()
        c.beginPath();path();c.strokeStyle=lineColor;c.lineWidth=1.8;c.stroke()
    }
}
