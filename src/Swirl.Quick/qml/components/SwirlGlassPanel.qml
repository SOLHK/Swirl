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
    Behavior on color{
        id:fillMotion
        // Shared-surface handoff owns visibility. Only animate ordinary
        // opaque feedback; hiding/restoring cannot start another alpha clock.
        enabled:panel.interactive && !SwirlMotion.reduced && !panel.surfaceHidden &&
                fillMotion.targetValue!==undefined && Math.abs(panel.color.a-fillMotion.targetValue.a)<0.0001
        ColorAnimation{duration:SwirlMotion.hoverDuration}
    }
    Behavior on border.color{enabled:panel.interactive && !SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.hoverDuration}}
    property real cornerRadius: floating ? Theme.popupRadius : Theme.cardRadius
    property bool independentCard: !floating
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    readonly property color surfaceColor: independentCard ? (pressed || interactive && focused ? Theme.cardPressed : interactive && hovered ? Theme.cardHover : selected ? Theme.selected : Theme.independentCard) : Theme.material(material)
    color: surfaceHidden ? Theme.withAlpha(surfaceColor,0) : surfaceColor
    border.width: surfaceHidden ? 0 : Theme.increaseContrast ? Theme.dp(2) : independentCard ? 1 / Screen.devicePixelRatio : 0
    border.color:Theme.increaseContrast ? Theme.text : Theme.border
    // Analytic background-only shadow: no offscreen capture of child text.
    RectangularShadow {
        anchors.fill: parent; z: -1
        visible: !panel.surfaceHidden && panel.independentCard && Theme.effectsSupported
        radius: panel.radius; blur: Theme.dp(10); offset: Qt.vector2d(0,Theme.dp(2))
        color: Theme.withAlpha(Theme.shadowColor,panel.pressed ? Theme.cardShadowOpacity * 0.55 : panel.interactive && panel.hovered ? Theme.cardShadowOpacity + 0.025 : Theme.cardShadowOpacity)
        Behavior on color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }

}
