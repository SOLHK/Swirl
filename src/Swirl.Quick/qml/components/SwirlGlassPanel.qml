import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    id:panel
    property string material: "content"
    property bool selected: false
    property bool surfaceHidden:false
    property bool interactive:false
    HoverHandler{id:cardHover;enabled:panel.interactive}
    Behavior on border.color{ColorAnimation{duration:SwirlMotion.hoverDuration}}
    property real cornerRadius: floating ? Theme.popupRadius : Theme.cardRadius
    property bool independentCard: !floating
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    color: surfaceHidden ? "transparent" : independentCard ? Theme.independentCard : Theme.material(material)
    border.width: surfaceHidden || independentCard ? 0 : Theme.borderWidth
    border.color: selected ? Theme.focusBorder : interactive && cardHover.hovered?Theme.withAlpha(Theme.focusBorder,0.35):Theme.border
    // Analytic background-only shadow: no offscreen capture of child text.
    RectangularShadow {
        anchors.fill: parent; z: -1
        visible: !panel.surfaceHidden && panel.independentCard && Theme.effectsSupported
        radius: panel.radius; blur: Theme.dp(10); offset: Qt.vector2d(0,Theme.dp(2))
        color: Theme.withAlpha("#000000",Theme.cardShadowOpacity)
    }

}
