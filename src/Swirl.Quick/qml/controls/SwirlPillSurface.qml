import QtQuick
import SwirlQuick
Rectangle {
    id: surface
    property bool selected: false
    property bool pressed: false
    property bool hovered: false
    property bool primary: false
    property bool subtleShadow: true
    radius: Theme.pillRadius(height)
    antialiasing: true
    color: primary ? (pressed ? Qt.darker(Theme.accent,1.12) : Theme.accent) :
           pressed ? Theme.pressed : selected ? Theme.selected : hovered ? Theme.hover : Theme.buttonBase
    border.width: Theme.borderWidth
    border.color: primary ? Theme.accent : Theme.controlBorder
    // Matte pills deliberately have no effect layer or white specular rim.
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
