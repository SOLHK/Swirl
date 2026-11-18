import QtQuick
import SwirlQuick

SwirlContinuousSurface {
    id: surface
    property bool hovered: false
    property bool pressed: false
    property bool focused: false
    property bool floating: false
    property real cornerRadius: Theme.cardRadius
    radius: Math.min(cornerRadius, width / 2, height / 2)
    color: Theme.dark ? Theme.independentCard : "#FFFFFF"
    // Ordinary cards never acquire an outline from pointer or keyboard focus.
    border.width: Theme.increaseContrast ? Theme.dp(2) : floating ? Theme.borderWidth : 0
    border.color: Theme.increaseContrast ? Theme.text : Theme.border

    ShaderEffect {
        x: -padding; y: -padding; z: -1
        width: surface.width + 2 * padding; height: surface.height + 2 * padding
        visible: Theme.effectsSupported && !Theme.increaseContrast
        // Cover the complete finite blur kernel; a two-sigma texture ended
        // while the shadow was still visible and exposed its rectangular edge.
        property real padding: Math.ceil(4 * softness + Math.abs(shadowOffset.y))
        property vector2d surfaceSize: Qt.vector2d(surface.width, surface.height)
        property real cornerRadius: surface.radius
        property vector2d shadowOffset: Qt.vector2d(0, Theme.dp(surface.floating ? 4 : surface.pressed ? 2 : 3))
        property real softness: Theme.dp(surface.floating ? 12 : surface.pressed ? 5 : 8)
        property real floatingShadow: surface.floating ? 1 : 0
        property color shadowColor: Theme.withAlpha("#000000",
            (surface.floating ? (Theme.dark ? 0.38 : 0.14) : Theme.dark ? 0.16 : 0.065) * (surface.pressed ? 0.65 : (surface.hovered || surface.focused) ? 1.12 : 1))
        fragmentShader: "qrc:/swirl/shaders/card-shadow.frag.qsb"
        Behavior on softness { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.hoverDuration } }
        Behavior on shadowColor { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
}
