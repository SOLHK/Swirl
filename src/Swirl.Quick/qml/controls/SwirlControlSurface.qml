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
    readonly property bool transientFill: quiet && !primary && !field && !selected && !outlined
    radius: field ? Theme.controlRadius : Theme.pillRadius(height)
    antialiasing: true
    opacity: controlEnabled ? 1 : Theme.disabledOpacity
    color: transientFill ? Theme.withAlpha(
            Qt.tint(Theme.hover, Theme.withAlpha(Theme.pressed, Math.max(0, Math.min(1, feedback.contact)))),
            controlEnabled ? Math.max(hovered ? feedback.hover : 0, pressed ? feedback.contact : 0) : 0)
         : primary ? (controlEnabled && pressed ? Theme.primaryButtonPressed : controlEnabled && hovered ? Theme.primaryButtonHover : Theme.primaryButton)
         : field ? (controlEnabled && hovered && !focused ? Theme.buttonBase : Theme.field) : controlEnabled && pressed ? Theme.pressed : controlEnabled && hovered ? Theme.hover
         : selected || outlined ? Theme.segmentSelected : Theme.buttonBase
    border.width: field || Theme.increaseContrast ? Theme.borderWidth : 0
    border.color: invalid ? Theme.red : Theme.increaseContrast ? Theme.text : Theme.controlBorder
    // Quiet fills share the existing interaction clock. Gating its alpha by
    // pointer state clears a departed row without a second fading color tween.
    Behavior on color {
        enabled: !SwirlMotion.reduced && !surface.transientFill
        ColorAnimation { duration: SwirlMotion.hoverDuration }
    }
    SwirlInteractionMotion {id:feedback;hovered:surface.hovered;pressed:surface.pressed;focused:surface.focused;controlEnabled:surface.controlEnabled}
    Rectangle {
        objectName:"controlFocusFill"
        anchors.fill:parent
        radius:surface.radius
        border.width:0
        color:Theme.withAlpha(surface.primary ? Theme.primaryButtonText : Theme.text,0.08)
        opacity:feedback.focusAmount
        visible:opacity>0
        Accessible.ignored:true
    }
}
