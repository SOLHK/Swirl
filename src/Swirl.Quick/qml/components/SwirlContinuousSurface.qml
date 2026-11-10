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
        // A page teardown can evaluate this binding after the inline SurfaceBorder
        // object has already been released. Read it defensively so a closed route
        // cannot emit a QML TypeError that fails the native full-motion smoke.
        property real borderWidth: surface.border ? surface.border.width : 0
        property color fillColor: surface.color
        property color rimColor: surface.border ? surface.border.color : "transparent"
        fragmentShader: "qrc:/swirl/shaders/swirl-surface.frag.qsb"
    }
    SwirlShellOutline {
        anchors.fill: parent
        visible: !Theme.effectsSupported
        radius: surface.radius
        fillColor: surface.color
        strokeWidth: surface.border ? surface.border.width : 0
        strokeColor: surface.border ? surface.border.color : "transparent"
    }
}
