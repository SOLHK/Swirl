import QtQuick
import SwirlQuick
Rectangle {
    id:badge
    property string region:"SG"
    width:Theme.dp(68); height:Theme.dp(58); radius:Theme.secondaryRadius; color:Theme.raised
    Rectangle {
        x:Theme.dp(5); y:Theme.dp(8); width:parent.width-Theme.dp(10); height:Theme.dp(28); radius:Theme.roundedRadius(width,height); color:badge.region==="SG" ? "#EF2742" : "#E5EFFB"
        Text { visible:badge.region!=="SG"; anchors.centerIn:parent; text:badge.region; color:Theme.muted; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
        Canvas {
        onVisibleChanged:if(visible)requestPaint();

            anchors.fill:parent; visible:badge.region==="SG"
            onPaint:{var c=getContext("2d");c.reset();c.fillStyle="white";c.beginPath();c.arc(16,14,9,0,Math.PI*2);c.fill();c.fillStyle="#EF2742";c.beginPath();c.arc(20,12,8,0,Math.PI*2);c.fill();c.fillStyle="white";for(var i=0;i<5;i++){var a=-Math.PI/2+i*Math.PI*2/5;c.beginPath();c.arc(23+5*Math.cos(a),14+5*Math.sin(a),1,0,Math.PI*2);c.fill()}}
        }
    }
}
