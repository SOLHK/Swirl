import QtQuick
import SwirlQuick

Rectangle {
    id: glass
    readonly property bool glassEnabled: Theme.transparency && (backdrop.blurActive || backdrop.active || backdrop.translucent)
    property bool focused: false
    property bool hovered: false
    property bool pressed: false
    radius: Theme.dp(14)
    antialiasing: true
    color: pressed ? Theme.withAlpha(Theme.dark ? "#FFFFFF" : "#000000", Theme.dark ? 0.16 : 0.08)
        : hovered ? Theme.withAlpha(Theme.dark ? "#FFFFFF" : "#000000", Theme.dark ? 0.09 : 0.035)
        : glassEnabled ? Theme.withAlpha("#FFFFFF", Theme.dark ? 0.05 : 0.04)
        : Theme.dark ? "#333B46" : "#FBFBFB"
    border.width: Theme.dp(1)
    border.color: focused ? Theme.focusBorder
        : Theme.dark ? Theme.withAlpha("#FFFFFF", 0.18) : Theme.withAlpha("#777777", 0.12)
    Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }

    Rectangle {
        x: glass.width
        y: glass.radius
        width: Theme.dp(10)
        height: Math.max(0, glass.height - 2 * glass.radius)
        visible: Theme.effectsSupported && height > 0
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.withAlpha("#000000", Theme.dark ? 0.12 : 0.065) }
            GradientStop { position: 1; color: "transparent" }
        }
    }
    Rectangle {
        x: glass.radius
        y: glass.height
        width: Math.max(0, glass.width - 2 * glass.radius)
        height: Theme.dp(6)
        visible: Theme.effectsSupported && width > 0
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: Theme.withAlpha("#000000", Theme.dark ? 0.09 : 0.045) }
            GradientStop { position: 1; color: "transparent" }
        }
    }
}
