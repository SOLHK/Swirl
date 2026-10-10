import QtQuick
import QtQuick.Controls
import SwirlQuick
Switch {
    id:control
    implicitWidth:48; implicitHeight:30
    hoverEnabled:true
    indicator:Rectangle {
        implicitWidth:46; implicitHeight:26
        x:0; y:(control.height-height)/2; radius:13
        color:control.checked?Theme.accent:Theme.border
        Behavior on color { ColorAnimation { duration:Theme.motion } }
        Rectangle {
            y:3; x:control.checked?23:3
            width:20; height:20; radius:10
            color:control.checked&&Theme.dark?"#13263D":"white"
            Behavior on x { NumberAnimation { duration:Theme.motion; easing.type:Easing.OutCubic } }
        }
    }
    contentItem:Item {}
}