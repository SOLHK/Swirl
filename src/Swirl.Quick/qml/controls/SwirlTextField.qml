import QtQuick
import QtQuick.Controls
import SwirlQuick
TextField {
    id: control
    implicitHeight:Theme.dp(39)
    leftPadding:Theme.dp(15); rightPadding:Theme.dp(15)
    color: Theme.text
    selectionColor: Theme.accent
    selectedTextColor: "white"
    placeholderTextColor: Theme.muted
    font.family: "Microsoft YaHei UI"
    font.pixelSize:Theme.fontSize(12)
    background: Rectangle {
        radius: Theme.controlRadius
        antialiasing: true
        color: control.activeFocus ? Theme.hover : Theme.material("field")
        border.width: Theme.dp(control.activeFocus ? 1.5 : 1)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
}
