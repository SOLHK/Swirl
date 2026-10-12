import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    // Transform the paint nodes, keeping layout and mouse/keyboard hit areas fixed.
    property real motionScale: down ? SwirlMotion.pressScale : 1
    Behavior on motionScale {
        enabled: !SwirlMotion.reduced
        SwirlSpring {}
    }
    Binding { target:control.background; property:"scale"; value:control.motionScale; when:control.background!==null }
    Binding { target:control.contentItem; property:"scale"; value:control.motionScale; when:control.contentItem!==null }
    onPressed: SwirlMotion.noteTrigger(control)
}
