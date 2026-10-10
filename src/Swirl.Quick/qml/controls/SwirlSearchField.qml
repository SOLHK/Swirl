import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
TextField {
    id: control
    implicitHeight: 39
    implicitWidth: 225
    leftPadding: 39
    rightPadding: 15
    placeholderText: "搜索"
    placeholderTextColor: Theme.muted
    color: Theme.text
    selectedTextColor: "white"
    selectionColor: Theme.accent
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 12
    background: Rectangle {
        radius: 14
        antialiasing: true
        color: control.activeFocus ? Theme.material("floating") : Theme.material("field")
        border.width: control.activeFocus ? 1.5 : 1
        border.color: control.activeFocus ? Theme.accent : Theme.glassRim
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    SwirlIcon {
        anchors.left: parent.left; anchors.leftMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size: 17; color: control.activeFocus ? Theme.accent : Theme.muted
    }
}
