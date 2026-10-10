import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
Button {
    id: control
    property bool primary:false
    property bool quiet:false
    property bool danger:false
    property string iconName:""
    implicitWidth: Math.max(78, contents.implicitWidth+26)
    implicitHeight:38
    hoverEnabled:true
    font.family:"Segoe UI"
    font.pixelSize:13
    background:Rectangle {
        radius:11
        border.width:control.primary || control.quiet ? 0 : 1
        border.color:Theme.border
        color:control.down ? Theme.selected :
              control.primary ? Theme.accent :
              control.hovered ? Theme.hover :
              control.quiet ? "transparent" : Theme.raised
        Behavior on color { ColorAnimation { duration:Theme.motion } }
    }
    contentItem:RowLayout {
        id:contents
        spacing:7
        SwirlIcon {
            visible:control.iconName!==""
            name:control.iconName; size:16
            color:control.primary?(Theme.dark?"#13263D":"white"):Theme.text
        }
        Text {
            text:control.text
            font:control.font
            font.weight:control.primary?Font.DemiBold:Font.Medium
            color:control.primary?(Theme.dark?"#13263D":"white"):control.danger?Theme.red:Theme.text
            Layout.alignment:Qt.AlignVCenter
        }
    }
}