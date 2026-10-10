import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
TextField {
    id:control
    implicitHeight:38
    implicitWidth:225
    leftPadding:37
    rightPadding:12
    placeholderText:"Search"
    placeholderTextColor:Theme.muted
    color:Theme.text
    selectedTextColor:"white"
    selectionColor:Theme.accent
    font.family:"Segoe UI"
    font.pixelSize:13
    background:Rectangle {
        radius:10
        color:Theme.field
        border.color:control.activeFocus?Theme.accent:Theme.border
    }
    SwirlIcon {
        anchors.left:parent.left; anchors.leftMargin:12
        anchors.verticalCenter:parent.verticalCenter
        name:"search"; size:17; color:Theme.muted
    }
}