import QtQuick
import QtQuick.Effects
import SwirlQuick

Rectangle {
    id: glass
    property bool focused: false
    property bool hovered: false
    property bool pressed: false
    property bool elevated: true
    property color topColor: Theme.glassTop
    property color baseColor: Theme.glassFill
    property real shadowBlur: Theme.dp(8)
    property real shadowOpacity: Theme.dark ? 0.16 : 0.055
    property vector2d shadowOffset: Qt.vector2d(0, Theme.dp(2))
    property bool glassEnabled: Theme.transparency && !Theme.increaseContrast
    radius: Theme.controlRadius
    antialiasing: true
    color: pressed ? Theme.interactionPressed : hovered ? Theme.interactionHover : baseColor
    border.width: focused || Theme.increaseContrast ? 1 / Screen.devicePixelRatio : 0
    border.color: focused ? Theme.focusBorder : Theme.text
    gradient: glassEnabled && !pressed ? glassGradient : null
    Gradient {
        id: glassGradient
        GradientStop { position: 0; color: glass.hovered ? Theme.glassHoverTop : glass.topColor; Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } } }
        GradientStop { position: 1; color: glass.hovered ? Theme.interactionHover : glass.baseColor; Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } } }
    }
    Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
    RectangularShadow {
        anchors.fill: parent; z: -1
        visible: glass.elevated && Theme.effectsSupported && !Theme.increaseContrast
        radius: glass.radius; blur: glass.shadowBlur
        offset: glass.shadowOffset
        color: Theme.withAlpha("#000000", glass.shadowOpacity)
    }
}
