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
    gradient:Gradient {
        GradientStop { position:0; color:Theme.dark ? panel.color : Qt.lighter(panel.color,1.009) }
        GradientStop { position:1; color:panel.color }
    }
    border.width: Theme.borderWidth
    border.color: selected ? Theme.accent : "#50FFFFFF"
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
