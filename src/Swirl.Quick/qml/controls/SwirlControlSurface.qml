import QtQuick
import SwirlQuick

Rectangle {
    id: surface
    property bool hovered: false
    property bool pressed: false
    property bool focused: false
    property bool controlEnabled: true
    property bool primary: false
    property bool quiet: false
    property bool selected: false
    property bool outlined: false
    property bool field: false
    property bool invalid: false
    radius: Theme.controlRadius
    antialiasing: true
    opacity: controlEnabled ? 1 : Theme.disabledOpacity
    color: primary ? (pressed ? Theme.primaryButtonPressed : hovered ? Theme.primaryButtonHover : Theme.primaryButton)
         : field ? (hovered && !focused ? Theme.buttonBase : Theme.field) : pressed ? Theme.pressed : hovered ? Theme.hover
         : selected ? Theme.segmentSelected : quiet ? "transparent" : Theme.buttonBase
    border.width: outlined || field || Theme.increaseContrast ? Theme.borderWidth : 0
    border.color: invalid ? Theme.red : Theme.increaseContrast ? Theme.text : Theme.controlBorder
    Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -Theme.dp(2)
        visible: surface.focused && surface.controlEnabled
        color: "transparent"
        radius: surface.radius + Theme.dp(2)
        border.width: Theme.dp(2)
        border.color: surface.invalid ? Theme.red : Theme.focusBorder
    }
}
