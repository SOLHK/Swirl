import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    property bool pressMotion: true
    readonly property real clickLight: 0 // Compatibility for diagnostics; no pulse or overlay.
    property real motionScale: pressMotion && enabled && down ? SwirlMotion.pressScale : 1
    Behavior on motionScale {
        enabled: !SwirlMotion.reduced
        NumberAnimation { duration:control.down?SwirlMotion.pressDuration:SwirlMotion.releaseDuration; easing.type:SwirlMotion.standardEasing }
    }
    Binding { target:control.background; property:"scale"; value:control.motionScale; when:control.background!==null }
    onPressed: SwirlMotion.noteTrigger(control)
}
