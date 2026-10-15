import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../controls"

Item {
    id:bar
    required property var targetWindow
    implicitHeight:Theme.dp(40)
    MouseArea {
        anchors.fill:parent
        property point pressPosition
        property bool moving:false
        onPressed:mouse=>{pressPosition=Qt.point(mouse.x,mouse.y);moving=false}
        onPositionChanged:mouse=>{
            if(pressed&&!moving&&Math.hypot(mouse.x-pressPosition.x,mouse.y-pressPosition.y)>Qt.styleHints.startDragDistance){moving=true;bar.targetWindow.startSystemMove()}
        }
        onDoubleClicked:bar.targetWindow.visibility===Window.Maximized?bar.targetWindow.showNormal():bar.targetWindow.showMaximized()
    }
    SwirlTrafficLights{x:Theme.dp(8);anchors.verticalCenter:parent.verticalCenter;targetWindow:bar.targetWindow}
    SwirlText {
        anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(200));horizontalAlignment:Text.AlignHCenter
        text:bar.targetWindow.title;color:Theme.text;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight
    }
}
