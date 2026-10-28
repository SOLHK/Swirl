import QtQuick
import SwirlQuick

Rectangle {
    id: surface
    property bool hovered: false
    property bool pressed: false
    property bool focused: false
    property bool controlEnabled: true
    property bool primary: false
    property bool quiet: false
    property bool selected: false
    property bool outlined: false
    property bool field: false
    property bool invalid: false
    readonly property real hoverProgress:feedback.hover
    readonly property real contactProgress:feedback.contact
    readonly property bool moving:feedback.moving
    radius: field ? Theme.controlRadius : Theme.pillRadius(height)
    antialiasing: true
    opacity: controlEnabled ? 1 : Theme.disabledOpacity
    color: primary ? (controlEnabled && pressed ? Theme.primaryButtonPressed : controlEnabled && hovered ? Theme.primaryButtonHover : Theme.primaryButton)
         : field ? (controlEnabled && hovered && !focused ? Theme.buttonBase : Theme.field) : controlEnabled && pressed ? Theme.pressed : controlEnabled && hovered ? Theme.hover
         : selected ? Theme.segmentSelected : quiet ? "transparent" : Theme.buttonBase
    border.width: outlined || field || Theme.increaseContrast ? Theme.borderWidth : 0
    border.color: invalid ? Theme.red : Theme.increaseContrast ? Theme.text : Theme.controlBorder
    Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    SwirlInteractionMotion {id:feedback;hovered:surface.hovered;pressed:surface.pressed;focused:surface.focused;controlEnabled:surface.controlEnabled}
    Rectangle {
        objectName:"controlInteractionRim"
        anchors.fill:parent
        radius:surface.radius
        color:"transparent"
        border.width:1/Screen.devicePixelRatio
        border.color:surface.primary ? Theme.withAlpha(Theme.primaryButtonText,0.5) : Theme.withAlpha(Theme.text,0.16)
        opacity:Theme.increaseContrast ? 0 : feedback.hover*(1-0.45*Math.min(1,feedback.contact))
        visible:opacity>0
        transform:Scale {origin.x:surface.width/2;xScale:0.72+0.28*feedback.hover}
        Accessible.ignored:true
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -Theme.dp(2)
        visible:opacity>0
        opacity:feedback.focusAmount
        color: "transparent"
        radius: surface.radius + Theme.dp(2)
        border.width: Theme.dp(2)
        border.color: surface.invalid ? Theme.red : Theme.focusBorder
    }
}
