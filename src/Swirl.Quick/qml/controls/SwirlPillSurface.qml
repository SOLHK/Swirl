import QtQuick
import QtQuick.Effects
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
           pressed ? Theme.selected : selected ? Theme.selected : hovered ? Theme.raised : Theme.material("floating")
    border.width: Theme.borderWidth
    border.color: primary ? "#308EFF" : "#CAFFFFFF"
    layer.enabled: subtleShadow
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: Qt.rgba(0.18,0.32,0.5,Theme.shadowOpacity)
        shadowBlur: 0.35
        shadowVerticalOffset: 2
    }
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
