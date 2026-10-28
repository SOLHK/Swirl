import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    id:panel
    property string material: "content"
    property bool selected: false
    property bool surfaceHidden:false
    property bool interactive:false
    property bool hovered:cardHover.hovered
    property bool pressed:false
    property bool focused:false
    HoverHandler{id:cardHover;enabled:panel.interactive}
    Behavior on color{enabled:!SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.hoverDuration}}
    Behavior on border.color{enabled:!SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.hoverDuration}}
    property real cornerRadius: floating ? Theme.popupRadius : Theme.cardRadius
    property bool independentCard: !floating
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    color: surfaceHidden ? "transparent" : independentCard ? (pressed ? Theme.cardPressed : interactive && hovered ? Theme.cardHover : Theme.independentCard) : Theme.material(material)
    border.width: surfaceHidden ? 0 : focused || Theme.increaseContrast ? Theme.dp(2) : independentCard || selected ? 1 / Screen.devicePixelRatio : 0
    border.color: selected || focused ? Theme.focusBorder : interactive && (hovered || pressed) ? Theme.cardHoverBorder : Theme.border
    // Analytic background-only shadow: no offscreen capture of child text.
    RectangularShadow {
        anchors.fill: parent; z: -1
        visible: !panel.surfaceHidden && panel.independentCard && Theme.effectsSupported
        radius: panel.radius; blur: Theme.dp(10); offset: Qt.vector2d(0,Theme.dp(2))
        color: Theme.withAlpha(Theme.shadowColor,panel.pressed ? Theme.cardShadowOpacity * 0.55 : panel.interactive && panel.hovered ? Theme.cardShadowOpacity + 0.025 : Theme.cardShadowOpacity)
        Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }

}
