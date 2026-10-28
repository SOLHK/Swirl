import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    property bool pressMotion: true
    readonly property real clickLight: 0 // Compatibility for diagnostics; no pulse or overlay.
    property real motionScale:1-(1-SwirlMotion.pressScale)*pressFeedback.contact
    readonly property real motionLift:SwirlMotion.reduced ? 0 : -Theme.dp(1)*pressFeedback.hover*(1-Math.min(1,pressFeedback.contact))
    SwirlInteractionMotion {id:pressFeedback;hovered:control.hovered;pressed:control.pressMotion && control.down;focused:control.visualFocus;controlEnabled:control.enabled}
    transform:Translate {y:control.motionLift}
    Binding { target:control.background; property:"scale"; value:control.motionScale; when:control.background!==null }
    Binding { target:control.contentItem; property:"scale"; value:control.motionScale; when:control.contentItem!==null }
    onPressed: SwirlMotion.noteTrigger(control)
}
