import QtQuick
import QtQuick.Controls
import SwirlQuick
TextField {
    id: control
    implicitHeight: 39
    leftPadding: 15; rightPadding: 15
    color: Theme.text
    selectionColor: Theme.accent
    selectedTextColor: "white"
    placeholderTextColor: Theme.muted
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 12
    background: Rectangle {
        radius: Theme.controlRadius
        antialiasing: true
        color: control.activeFocus ? Theme.hover : Theme.material("field")
        border.width: control.activeFocus ? 1.5 : 1
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
}
