import QtQuick
import SwirlQuick
Rectangle {
    id: panel
    property string material: "content"
    property bool selected: false
    property int cornerRadius: 22
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    color: Theme.material(material)
    border.width: 1
    border.color: selected ? Theme.accent : Theme.glassRim
    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.dark ? "#DB40516D" : "#F5FFFFFF" }
        GradientStop { position: 0.16; color: Theme.material(panel.material) }
        GradientStop { position: 1.0; color: Theme.dark ? "#BA152437" : "#BDE7F1FD" }
    }
    // Gentle specular rim and reflected edge, without a solid white card.
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: panel.cornerRadius
        anchors.rightMargin: panel.cornerRadius
        anchors.topMargin: 1
        height: 1
        radius: 1
        color: Theme.glassGlint
        opacity: Theme.transparency ? 0.82 : 0.3
    }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: panel.cornerRadius
        anchors.rightMargin: panel.cornerRadius
        anchors.bottomMargin: 1
        height: 1
        radius: 1
        color: Theme.dark ? "#235E7896" : "#88C0D1E8"
        opacity: 0.6
    }
    Behavior on color { ColorAnimation { duration: Theme.motion } }
    Behavior on border.color { ColorAnimation { duration: Theme.motion } }
}
