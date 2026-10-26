import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    property bool pressMotion: true
    readonly property real clickLight: 0 // Compatibility for diagnostics; no pulse or overlay.
    property real motionScale:1-(1-SwirlMotion.pressScale)*pressFeedback.contact
    SwirlInteractionMotion {id:pressFeedback;pressed:control.pressMotion && control.down;controlEnabled:control.enabled}
    Binding { target:control.background; property:"scale"; value:control.motionScale; when:control.background!==null }
    onPressed: SwirlMotion.noteTrigger(control)
}
