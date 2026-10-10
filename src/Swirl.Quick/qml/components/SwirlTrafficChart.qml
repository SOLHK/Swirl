import QtQuick
import QtQuick.Layouts
import SwirlQuick
Item {
    id:graph
    property var samples:demoProvider.traffic()
    property bool showUpload:true
    property bool showDownload:true
    implicitHeight:242
    implicitWidth:550
    onSamplesChanged:plot.requestPaint()
    Connections {
        target:Theme
        function onDarkChanged(){plot.requestPaint()}
        function onAccentChanged(){plot.requestPaint()}
    }
    Canvas {
        id:plot
        anchors.fill:parent
        anchors.leftMargin:2
        anchors.topMargin:7
        anchors.bottomMargin:26
        renderTarget:Canvas.Image
        onWidthChanged:requestPaint()
        onHeightChanged:requestPaint()
        onPaint:{
            var c=getContext("2d")
            c.reset()
            if(!graph.samples || graph.samples.length<2) return
            var w=width, h=height, base=h-8, top=8
            var max=180, n=graph.samples.length
            function X(i){return 4+i*(w-8)/(n-1)}
            function Y(v){return base-v*(base-top)/max}
            for(var k=0;k<5;k++){
                var gy=top+k*(base-top)/4
                c.beginPath();c.moveTo(0,gy);c.lineTo(w,gy)
                c.strokeStyle=Theme.dark?"#354155":"#E7ECF4";c.lineWidth=1;c.stroke()
            }
            function draw(key,rgb){
                var grad=c.createLinearGradient(0,top,0,base)
                grad.addColorStop(0,Theme.dark?rgb[0]:rgb[1]);grad.addColorStop(1,"transparent")
                c.beginPath()
                c.moveTo(X(0),base)
                for(var i=0;i<n;i++) c.lineTo(X(i),Y(graph.samples[i][key]))
                c.lineTo(X(n-1),base);c.closePath()
                c.fillStyle=grad;c.fill()
                c.beginPath()
                for(var j=0;j<n;j++){
                    if(j===0)c.moveTo(X(j),Y(graph.samples[j][key]))
                    else c.lineTo(X(j),Y(graph.samples[j][key]))
                }
                c.lineWidth=2.15
                c.strokeStyle=key==="down"?Theme.accent:Theme.green
                c.stroke()
            }
            if(graph.showDownload)draw("down",["rgba(149,185,255,0.22)","rgba(66,118,231,0.14)"])
            if(graph.showUpload)draw("up",["rgba(108,212,179,0.13)","rgba(22,135,102,0.08)"])
        }
    }
    RowLayout {
        anchors.left:parent.left; anchors.right:parent.right
        anchors.bottom:parent.bottom
        spacing:0
        Repeater {
            model:["60m ago","45m","30m","15m","Now"]
            Text {
                text:modelData
                color:Theme.muted
                font.pixelSize:10
                Layout.fillWidth:true
                horizontalAlignment:index===0?Text.AlignLeft:index===4?Text.AlignRight:Text.AlignHCenter
            }
        }
    }
}