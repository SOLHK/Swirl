import QtQuick
import SwirlQuick
Item {
    id: surface
    property real radius: Theme.containerRadius
    property color color: "transparent"
    component SurfaceBorder: QtObject {
        property real width: 0
        property color color: "transparent"
    }
    readonly property SurfaceBorder border: SurfaceBorder {}
    // Paint only the background: child text never enters a scaled texture.
    ShaderEffect {
        anchors.fill: parent
        visible: Theme.effectsSupported
        property vector2d surfaceSize: Qt.vector2d(width, height)
        property real cornerRadius: surface.radius
        property real borderWidth: surface.border.width
        property color fillColor: surface.color
        property color rimColor: surface.border.color
        fragmentShader: "qrc:/swirl/shaders/swirl-surface.frag.qsb"
    }
    SwirlShellOutline {
        anchors.fill: parent
        visible: !Theme.effectsSupported
        radius: surface.radius
        fillColor: surface.color
        strokeWidth: surface.border.width
        strokeColor: surface.border.color
    }
}
