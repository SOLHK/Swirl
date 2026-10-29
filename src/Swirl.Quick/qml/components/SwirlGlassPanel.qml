import QtQuick
import SwirlQuick
SwirlContinuousSurface {
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
    radius: floating ? Math.min(cornerRadius, width / 2, height / 2)
        : Math.min(cornerRadius, Math.max(Theme.dp(16), Math.min(width, height) * 0.22), width / 2, height / 2)
    readonly property color surfaceColor: independentCard ? (pressed || interactive && focused ? Theme.cardPressed : interactive && hovered ? Theme.cardHover : selected ? Theme.selected : Theme.independentCard) : Theme.material(material)
    color: surfaceHidden ? Theme.withAlpha(surfaceColor,0) : surfaceColor
    border.width: surfaceHidden ? 0 : Theme.increaseContrast ? Theme.dp(2) : independentCard ? 1 / Screen.devicePixelRatio : 0
    border.color:Theme.increaseContrast ? Theme.text : Theme.border
    // The same continuous contour casts an exterior-only, background shadow.
    ShaderEffect {
        x: -padding; y: -padding; z: -1
        width: panel.width + 2 * padding; height: panel.height + 2 * padding
        visible: !panel.surfaceHidden && panel.independentCard && Theme.effectsSupported
        property real padding: Theme.dp(16)
        property vector2d surfaceSize: Qt.vector2d(panel.width, panel.height)
        property real cornerRadius: panel.radius
        property vector2d shadowOffset: Qt.vector2d(0, Theme.dp(3))
        property real softness: Theme.dp(6)
        property color shadowColor: Theme.withAlpha(Theme.shadowColor, panel.pressed ? Theme.cardShadowOpacity * 0.55 : panel.interactive && panel.hovered ? Theme.cardShadowOpacity + 0.025 : Theme.cardShadowOpacity)
        fragmentShader: "qrc:/swirl/shaders/sidebar-shadow.frag.qsb"
        Behavior on shadowColor { ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }

}
