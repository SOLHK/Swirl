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
    Row {
        x:Theme.dp(8);anchors.verticalCenter:parent.verticalCenter;spacing:Theme.dp(3)
        Repeater {
            model:["#FF5F57","#FEBC2E","#28C840"]
            SwirlMotionButton {
                required property int index
                required property string modelData
                objectName:index===0?"windowCloseButton":index===1?"windowMinimizeButton":"windowMaximizeButton"
                width:Theme.dp(24);height:width
                background:Rectangle {
                    anchors.centerIn:parent;width:Theme.dp(14);height:width;radius:width/2
                    color:bar.targetWindow.active?parent.modelData:"#B9C1C9"
                    border.width:parent.activeFocus?Theme.dp(2):0;border.color:Theme.focusBorder
                }
                contentItem:Item{}
                onClicked:{
                    if(index===0)bar.targetWindow.close()
                    else if(index===1)bar.targetWindow.showMinimized()
                    else if(bar.targetWindow.visibility===Window.Maximized)bar.targetWindow.showNormal()
                    else bar.targetWindow.showMaximized()
                }
                Accessible.name:index===0?"关闭":index===1?"最小化":"最大化或还原"
                ToolTip.visible:hovered;ToolTip.text:Accessible.name
            }
        }
    }
    Text {
        anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(200));horizontalAlignment:Text.AlignHCenter
        text:bar.targetWindow.title;color:Theme.text;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight
    }
    Shortcut { sequence:"Escape";context:Qt.WindowShortcut;enabled:!dismissals.count || !dismissals.hasPopup(bar.targetWindow);onActivated:bar.targetWindow.close() }
}
