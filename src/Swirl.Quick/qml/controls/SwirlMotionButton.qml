import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    property bool pressMotion: true
    property bool synchronizedPressGeometry: true
    property bool presentationReady: false
    Component.onCompleted: presentationReady = true
    Component.onDestruction: presentationReady = false
    readonly property real clickLight: 0 // Compatibility for diagnostics; no pulse or overlay.
    property real motionScale:1-(1-SwirlMotion.pressScale)*pressFeedback.contact
    readonly property real motionLift:SwirlMotion.reduced ? 0 : -Theme.dp(1)*pressFeedback.hover*(1-Math.min(1,pressFeedback.contact))
    readonly property Item ownedInteractionMotion: SwirlInteractionMotion {
        id:pressFeedback
        parent:control
        hovered:control.hovered;pressed:control.pressMotion && control.down
        focused:control.visualFocus;controlEnabled:control.enabled
        pressSurfaceTarget:control.presentationReady && control.pressMotion && control.synchronizedPressGeometry?control.background:null
        pressContentTarget:control.presentationReady && control.pressMotion && control.synchronizedPressGeometry?control.contentItem:null
    }
    transform:Translate {y:control.motionLift}
    Binding { target:control.presentationReady?control.background:null; property:"scale"; value:control.motionScale; when:control.presentationReady && control.background!==null }
    Binding { target:control.presentationReady?control.contentItem:null; property:"scale"; value:control.motionScale; when:control.presentationReady && control.contentItem!==null }
    onPressed: SwirlMotion.noteTrigger(control)
}
