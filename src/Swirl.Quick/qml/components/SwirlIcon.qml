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
            else if(n==="home"){c.beginPath();c.moveTo(3,11);c.lineTo(12,4);c.lineTo(21,11);c.stroke();line(6,10,6,20);line(6,20,18,20);line(18,20,18,10);line(10,20,10,14);line(10,14,14,14);line(14,14,14,20)}
            else if(n==="chart"){line(3,21,3,4);line(3,21,22,21);c.beginPath();c.moveTo(5,16);c.lineTo(10,11);c.lineTo(14,13);c.lineTo(21,5);c.stroke()}
            else if(n==="activity"){c.beginPath();c.moveTo(2,13);c.lineTo(6,13);c.lineTo(9,5);c.lineTo(14,20);c.lineTo(17,11);c.lineTo(22,11);c.stroke()}
            else if(n==="folder"){c.beginPath();c.moveTo(3,7);c.lineTo(10,7);c.lineTo(12,9);c.lineTo(21,9);c.lineTo(21,20);c.lineTo(3,20);c.closePath();c.stroke()}
            else if(n==="globe"){circle(12,12,9);line(3,12,21,12);line(5,7,19,7);line(5,17,19,17);c.beginPath();c.ellipse(7.5,3,9,18);c.stroke()}
            else if(n==="list"){for(var j=0;j<3;j++){line(8,6+j*6,21,6+j*6);circle(4,6+j*6,1)}}
            else if(n==="pause"){box(4,4,16,16,3);line(10,8,10,16);line(14,8,14,16)}
            else if(n==="play"){circle(12,12,9);c.beginPath();c.moveTo(10,8);c.lineTo(16,12);c.lineTo(10,16);c.closePath();c.stroke()}
            else if(n==="layers"){line(3,8,12,3);line(12,3,21,8);line(21,8,12,13);line(12,13,3,8);line(3,13,12,18);line(12,18,21,13);line(3,18,12,23);line(12,23,21,18)}
            else if(n==="grid"){for(var a=0;a<2;a++)for(var b=0;b<2;b++)box(4+9*a,4+9*b,7,7,1)}
            else if(n==="code"){line(9,6,3,12);line(3,12,9,18);line(15,6,21,12);line(21,12,15,18);line(14,4,10,20)}
            else if(n==="shield"){c.beginPath();c.moveTo(12,2);c.lineTo(21,6);c.lineTo(20,15);c.lineTo(12,22);c.lineTo(4,15);c.lineTo(3,6);c.closePath();c.stroke()}
            else if(n==="settings"){circle(12,12,3);c.beginPath();for(var g=0;g<32;g++){var ga=g*Math.PI/16;var gr=g%4===0||g%4===3?9:7;var gx=12+gr*Math.cos(ga),gy=12+gr*Math.sin(ga);if(g===0)c.moveTo(gx,gy);else c.lineTo(gx,gy)}c.closePath();c.stroke()}
            else if(n==="server"){box(3,4,18,7,2);box(3,14,18,7,2);circle(7,7.5,1);circle(7,17.5,1)}
            else if(n==="inspect"){box(3,4,18,16,3);line(7,9,17,9);line(7,13,13,13);circle(18,18,4)}
            else if(n==="refresh"){c.beginPath();c.arc(12,12,8,3.5,5.95);c.stroke();c.beginPath();c.arc(12,12,8,0.35,2.8);c.stroke();line(20,4,20,9);line(20,9,15,9);line(4,20,4,15);line(4,15,9,15)}
            else if(n==="clock"){circle(12,12,9);line(12,7,12,12);line(12,12,17,15)}
            else if(n==="terminal"){box(2,4,20,16,2);line(6,9,10,12);line(10,12,6,15);line(12,16,18,16)}
            else if(n==="edit"){box(3,4,18,16,2);line(7,17,16,8);line(13,6,17,10)}
            else if(n==="network"){circle(12,4,2);circle(5,19,2);circle(19,19,2);line(12,6,5,17);line(12,6,19,17);line(7,19,17,19)}
            else if(n==="route"){circle(5,5,2);circle(19,19,2);c.beginPath();c.moveTo(5,8);c.bezierCurveTo(21,6,2,18,19,17);c.stroke()}
            else if(n==="tool"){line(4,20,14,10);circle(17,7,5);line(15,4,20,9)}
            else if(n==="plus"){line(12,3,12,21);line(3,12,21,12)}
            else if(n==="capture"){box(2,4,20,16,3);line(4,12,8,12);line(8,12,10,8);line(10,8,13,17);line(13,17,16,10);line(16,10,20,10)}
            else if(n==="chevron-right"){line(9,6,15,12);line(15,12,9,18)}
            else if(n==="chevron-left"){line(15,6,9,12);line(9,12,15,18)}
            else if(n==="download" || n==="upload"){line(12,3,12,17);var flip=n==="upload";line(6,flip?9:11,12,flip?3:17);line(12,flip?3:17,18,flip?9:11);if(!flip)line(6,21,18,21)}
            else if(n==="user"){circle(12,7,4);c.beginPath();c.moveTo(3,21);c.lineTo(3,18);c.bezierCurveTo(3,11,21,11,21,18);c.lineTo(21,21);c.closePath();c.stroke()}
            else if(n==="pin"){c.beginPath();c.moveTo(12,22);c.bezierCurveTo(0,10,4,2,12,2);c.bezierCurveTo(20,2,24,10,12,22);c.stroke();circle(12,9,3)}
            else if(n==="document" || n==="file"){c.beginPath();c.moveTo(5,2);c.lineTo(14,2);c.lineTo(20,8);c.lineTo(20,22);c.lineTo(5,22);c.closePath();c.stroke();line(14,2,14,8);line(14,8,20,8);if(n==="document"){line(8,13,16,13);line(8,17,16,17)}}
            else if(n==="gauge"){c.beginPath();c.arc(12,13,9,Math.PI,2*Math.PI);c.lineTo(21,20);c.lineTo(3,20);c.closePath();c.stroke();line(12,16,17,10);for(var t=0;t<4;t++){var an=Math.PI+t*Math.PI/3;line(12+6*Math.cos(an),13+6*Math.sin(an),12+7.5*Math.cos(an),13+7.5*Math.sin(an))}}
            else if(n==="bars"){line(3,21,22,21);box(5,11,3,8,1);box(11,4,3,15,1);box(17,8,3,11,1)}
            else if(n==="bolt"){c.beginPath();c.moveTo(14,1);c.lineTo(4,14);c.lineTo(11,14);c.lineTo(9,23);c.lineTo(21,9);c.lineTo(13,9);c.closePath();c.stroke()}
            else {box(4,4,16,16,3)}
        }
    }
}
