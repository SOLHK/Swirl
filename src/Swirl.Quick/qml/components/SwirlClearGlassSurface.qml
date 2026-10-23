import QtQuick
import SwirlQuick

Rectangle {
    id: surface
    property bool focused: false
    property bool hovered: false
    property bool pressed: false
    radius: height / 2
    antialiasing: true
    color: pressed ? Theme.pressed : hovered ? Theme.hover : Theme.buttonBase
    border.width: focused || Theme.increaseContrast ? 1 / Screen.devicePixelRatio : 0
    border.color: focused ? Theme.focusBorder : Theme.text
    Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
}
