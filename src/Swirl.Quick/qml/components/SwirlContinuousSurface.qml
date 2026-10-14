import QtQuick
import SwirlQuick
Item {
    id: surface
    property color color: "transparent"
    property real radius: Theme.containerRadius
    property alias border: fallback.border
    property bool antialiasing: true
    Rectangle { id:fallback; anchors.fill:parent; color:surface.color; radius:surface.radius; border.width:0; antialiasing:surface.antialiasing; visible:!Theme.effectsSupported }
    ShaderEffect {
        anchors.fill:parent; visible:Theme.effectsSupported
        property vector2d surfaceSize: Qt.vector2d(width,height)
        property real cornerRadius: surface.radius
        property real borderWidth: fallback.border.width
        property color fillColor: surface.color
        property color rimColor: fallback.border.color
        fragmentShader: "qrc:/swirl/shaders/swirl-surface.frag.qsb"
    }
}
