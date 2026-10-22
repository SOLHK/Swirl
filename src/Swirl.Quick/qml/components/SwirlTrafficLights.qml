pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../controls"
Item {
    id: lights
    required property var targetWindow
    implicitWidth:Theme.dp(78);implicitHeight:Theme.dp(24)
    HoverHandler {id:groupHover}
    Row {
        anchors.fill:parent;spacing:Theme.dp(3)
        Repeater {
            model:["#FF5F57","#FEBC2E","#28C840"]
            SwirlMotionButton {
                id:lamp;required property int index;required property string modelData
                width:Theme.dp(24);height:width;hoverEnabled:true
                objectName:index===0?"windowCloseButton":index===1?"windowMinimizeButton":"windowMaximizeButton"
                background:Rectangle {anchors.centerIn:parent;width:Theme.dp(14);height:width;radius:width/2;color:lamp.modelData;border.width:lamp.visualFocus?Theme.dp(1):0;border.color:Theme.text}
                contentItem:Item {
                    SwirlText {anchors.centerIn:parent;visible:groupHover.hovered && lamp.index<2;text:lamp.index===0?"×":"−";font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(11);font.weight:Font.Bold;color:lamp.index===0?"#6B1510":"#6A4B00"}
                    Canvas {
                        id:glyph;anchors.centerIn:parent;width:Theme.dp(12);height:width;visible:groupHover.hovered && lamp.index===2
                        onVisibleChanged:if(visible)requestPaint()
                        Connections {target:lights.targetWindow;function onVisibilityChanged(){glyph.requestPaint()}}
                        onPaint:{const c=getContext("2d");c.reset();c.scale(width/12,height/12);c.strokeStyle="#07551A";c.lineWidth=1.15;c.lineCap="round";const inward=lights.targetWindow.visibility===Window.FullScreen;c.beginPath();if(inward){c.moveTo(2.5,2.5);c.lineTo(5,5);c.moveTo(2,5);c.lineTo(5,5);c.lineTo(5,2);c.moveTo(9.5,9.5);c.lineTo(7,7);c.moveTo(10,7);c.lineTo(7,7);c.lineTo(7,10)}else{c.moveTo(5,5);c.lineTo(2.5,2.5);c.lineTo(2.5,5);c.moveTo(2.5,2.5);c.lineTo(5,2.5);c.moveTo(7,7);c.lineTo(9.5,9.5);c.lineTo(7,9.5);c.moveTo(9.5,9.5);c.lineTo(9.5,7)}c.stroke()}
                    }
                }
                onClicked:{if(index===0)lights.targetWindow.close();else if(index===1)lights.targetWindow.showMinimized();else if(lights.targetWindow.visibility===Window.FullScreen)lights.targetWindow.showNormal();else lights.targetWindow.showFullScreen()}
                Accessible.name:index===0?"关闭":index===1?"最小化":lights.targetWindow.visibility===Window.FullScreen?"退出全屏":"进入全屏"
                SwirlToolTip {parent:lamp;visible:lamp.hovered && !previewCaptureMode;delay:650;text:lamp.Accessible.name}
            }
        }
    }
}
