import QtQuick
import SwirlQuick
Rectangle {
    id:panel
    property string material: "content"
    property bool selected: false
    property real cornerRadius: Theme.cardRadius
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    color: Theme.material(material)
    border.width: Theme.borderWidth
    border.color: selected ? Theme.focusBorder : Theme.border
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
