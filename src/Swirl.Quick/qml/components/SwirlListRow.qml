import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
SwirlMotionButton {
    id:row
    property string iconName:""
    property string title:""
    property bool arrow:true
    implicitHeight:Theme.dp(36)
    padding:Theme.dp(0); hoverEnabled:true
    background:Rectangle {
        color:row.down ? Theme.selected : row.hovered ? Theme.hover : "transparent"
        radius:Theme.controlRadius
        Rectangle { width:parent.width-Theme.dp(52); x:Theme.dp(52); height:Theme.dp(1); color:Theme.border; opacity:0.65 }

 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
    contentItem:RowLayout {
        spacing:Theme.dp(24)
        SwirlIcon { name:row.iconName; size:Theme.dp(25) }
        SwirlText { text:row.title; color:Theme.muted; font.pixelSize:Theme.fontSize(17); Layout.fillWidth:true; elide:Text.ElideRight }
        SwirlIcon { visible:row.arrow; name:"chevron-right"; size:Theme.dp(17) }
    }
    Accessible.name:title
}
