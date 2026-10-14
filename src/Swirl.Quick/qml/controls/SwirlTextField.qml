import QtQuick
import QtQuick.Controls
import SwirlQuick
TextField {
    id: control
    implicitHeight:Theme.dp(26)
    leftPadding:Theme.dp(8); rightPadding:Theme.dp(8)
    color: Theme.text
    selectionColor: Theme.accent
    selectedTextColor: "white"
    placeholderTextColor: Theme.muted
    font.family: "Microsoft YaHei UI"
    font.pixelSize:Theme.fontSize(12)
    background: Rectangle {
        radius: Theme.controlRadius
        antialiasing: true
        color:Theme.dark?Theme.field:Theme.surface
        border.width: Theme.dp(control.activeFocus ? 3 : 1)
        border.color: control.activeFocus ? (Theme.dark?Theme.focusBorder:"#80ABFF") : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.width {NumberAnimation{duration:SwirlMotion.hoverDuration}}
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
}
