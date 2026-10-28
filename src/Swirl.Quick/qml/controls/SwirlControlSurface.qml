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
         : selected || outlined ? Theme.segmentSelected : quiet ? "transparent" : Theme.buttonBase
    border.width: field || Theme.increaseContrast ? Theme.borderWidth : 0
    border.color: invalid ? Theme.red : Theme.increaseContrast ? Theme.text : Theme.controlBorder
    Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
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
