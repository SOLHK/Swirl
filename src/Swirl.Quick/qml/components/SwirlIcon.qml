import QtQuick
import SwirlQuick
Item {
    id:root
    property string name:"home"
    property int size:20
    property color color:Theme.muted
    implicitWidth:size; implicitHeight:size
    width:size; height:size
    onNameChanged:canvas.requestPaint()
    onColorChanged:canvas.requestPaint()
    Canvas {
        id:canvas
        anchors.fill:parent
        antialiasing:true
        onPaint:{
            var c=getContext("2d")
            c.reset()
            c.scale(width/24,height/24)
            c.strokeStyle=root.color
            c.fillStyle=root.color
            c.lineWidth=1.8
            c.lineCap="round"
            c.lineJoin="round"
            function line(a,b,d,e){c.beginPath();c.moveTo(a,b);c.lineTo(d,e);c.stroke()}
            function box(x,y,w,h,r){c.beginPath();c.moveTo(x+r,y);c.lineTo(x+w-r,y);c.lineTo(x+w,y+r);c.lineTo(x+w,y+h-r);c.lineTo(x+w-r,y+h);c.lineTo(x+r,y+h);c.lineTo(x,y+h-r);c.lineTo(x,y+r);c.closePath();c.stroke()}
            function circle(x,y,r){c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.stroke()}
            var n=root.name
            if(n==="search"){circle(10.5,10.5,6);line(15,15,21,21)}
            else if(n==="home"){c.beginPath();c.moveTo(3,11);c.lineTo(12,4);c.lineTo(21,11);c.stroke();line(6,10,6,20);line(6,20,18,20);line(18,20,18,10)}
            else if(n==="chart"){line(3,21,3,4);line(3,21,22,21);c.beginPath();c.moveTo(5,16);c.lineTo(10,11);c.lineTo(14,13);c.lineTo(21,5);c.stroke()}
            else if(n==="activity"){c.beginPath();c.moveTo(2,13);c.lineTo(6,13);c.lineTo(9,5);c.lineTo(14,20);c.lineTo(17,11);c.lineTo(22,11);c.stroke()}
            else if(n==="folder"){c.beginPath();c.moveTo(3,7);c.lineTo(10,7);c.lineTo(12,9);c.lineTo(21,9);c.lineTo(21,20);c.lineTo(3,20);c.closePath();c.stroke()}
            else if(n==="globe"){circle(12,12,9);line(3,12,21,12);c.beginPath();c.ellipse(12,12,4,9,0,0,Math.PI*2);c.stroke()}
            else if(n==="list"){for(var j=0;j<3;j++){line(8,6+j*6,21,6+j*6);circle(4,6+j*6,1)}}
            else if(n==="pause"){box(4,4,16,16,3);line(10,8,10,16);line(14,8,14,16)}
            else if(n==="play"){circle(12,12,9);c.beginPath();c.moveTo(10,8);c.lineTo(16,12);c.lineTo(10,16);c.closePath();c.stroke()}
            else if(n==="layers"){line(3,8,12,3);line(12,3,21,8);line(21,8,12,13);line(12,13,3,8);line(3,13,12,18);line(12,18,21,13);line(3,18,12,23);line(12,23,21,18)}
            else if(n==="grid"){for(var a=0;a<2;a++)for(var b=0;b<2;b++)box(4+9*a,4+9*b,7,7,1)}
            else if(n==="code"){line(9,6,3,12);line(3,12,9,18);line(15,6,21,12);line(21,12,15,18);line(14,4,10,20)}
            else if(n==="shield"){c.beginPath();c.moveTo(12,2);c.lineTo(21,6);c.lineTo(20,15);c.lineTo(12,22);c.lineTo(4,15);c.lineTo(3,6);c.closePath();c.stroke()}
            else if(n==="settings"){circle(12,12,4);circle(12,12,9);line(12,1,12,4);line(12,20,12,23);line(1,12,4,12);line(20,12,23,12)}
            else if(n==="server"){box(3,4,18,7,2);box(3,14,18,7,2);circle(7,7.5,1);circle(7,17.5,1)}
            else if(n==="inspect"){box(3,4,18,16,3);line(7,9,17,9);line(7,13,13,13);circle(18,18,4)}
            else if(n==="refresh"){c.beginPath();c.arc(12,12,8,-1.4,2.4);c.stroke();line(7,19,4,17);line(4,17,4,21);line(19,5,21,8)}
            else if(n==="clock"){circle(12,12,9);line(12,7,12,12);line(12,12,17,15)}
            else if(n==="terminal"){box(2,4,20,16,2);line(6,9,10,12);line(10,12,6,15);line(12,16,18,16)}
            else if(n==="edit"){box(3,4,18,16,2);line(7,17,16,8);line(13,6,17,10)}
            else if(n==="network"){circle(12,4,2);circle(5,19,2);circle(19,19,2);line(12,6,5,17);line(12,6,19,17);line(7,19,17,19)}
            else if(n==="route"){circle(5,5,2);circle(19,19,2);c.beginPath();c.moveTo(5,8);c.bezierCurveTo(21,6,2,18,19,17);c.stroke()}
            else if(n==="tool"){line(4,20,14,10);circle(17,7,5);line(15,4,20,9)}
            else {box(4,4,16,16,3)}
        }
    }
}