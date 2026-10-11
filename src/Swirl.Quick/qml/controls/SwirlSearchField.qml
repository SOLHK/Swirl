import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
TextField {
    id: control
    implicitHeight: 42
    implicitWidth: 225
    leftPadding: 39
    rightPadding: control.objectName === "pageSearch" && control.width > 130 ? 64 : 15
    placeholderText: "搜索"
    placeholderTextColor: Theme.muted
    color: Theme.text
    selectedTextColor: "white"
    selectionColor: Theme.accent
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 16
    background: SwirlPillSurface {
        hovered:control.activeFocus
        radius: Theme.controlRadius
        gradient: null
        subtleShadow: false
        antialiasing: true
        color: control.activeFocus ? Theme.hover : Theme.material("field")
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    Text { visible:control.objectName === "pageSearch" && control.width > 130; anchors.right:parent.right; anchors.rightMargin:12; anchors.verticalCenter:parent.verticalCenter; text:"Ctrl+K"; color:Theme.muted; font.pixelSize:11 }
    SwirlIcon {
        anchors.left: parent.left; anchors.leftMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size: 22; color: control.activeFocus ? Theme.focusBorder : Theme.text
    }
}
