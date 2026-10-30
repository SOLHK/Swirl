import QtQuick
import SwirlQuick

SwirlContinuousSurface {
    id: surface
    property bool hovered: false
    property bool pressed: false
    property bool focused: false
    property real cornerRadius: Theme.cardRadius
    radius: Math.min(cornerRadius, width / 2, height / 2)
    color: Theme.dark ? Theme.independentCard : "#FFFFFF"
    // Ordinary cards have no rim. Explicit accessibility focus stays visible.
    border.width: focused ? Theme.dp(1.5) : Theme.increaseContrast ? Theme.dp(2) : 0
    border.color: focused ? Theme.focusBorder : Theme.text

    ShaderEffect {
        x: -padding; y: -padding; z: -1
        width: surface.width + 2 * padding; height: surface.height + 2 * padding
        visible: Theme.effectsSupported && !Theme.increaseContrast
        property real padding: Theme.dp(24)
        property vector2d surfaceSize: Qt.vector2d(surface.width, surface.height)
        property real cornerRadius: surface.radius
        property vector2d shadowOffset: Qt.vector2d(0, Theme.dp(surface.pressed ? 2 : 3))
        property real softness: Theme.dp(surface.pressed ? 5 : 8)
        property color shadowColor: Theme.withAlpha("#000000",
            (Theme.dark ? 0.16 : 0.065) * (surface.pressed ? 0.65 : surface.hovered ? 1.12 : 1))
        fragmentShader: "qrc:/swirl/shaders/card-shadow.frag.qsb"
        Behavior on softness { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.hoverDuration } }
        Behavior on shadowColor { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
}
