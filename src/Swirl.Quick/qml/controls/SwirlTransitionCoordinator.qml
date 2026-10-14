import QtQuick
import SwirlQuick
Item {
    id: coordinator
    // One reversible clock. Business state changes before animation starts;
    // interruption continues from the currently displayed geometry.
    property real progress: 0
    property real destination: 0
    property int duration: SwirlMotion.expandDuration
    readonly property bool moving: travel.running
    property int token: 0
    Component.onCompleted: {token=SwirlTransitionRegistry.allocate();if(moving)SwirlTransitionRegistry.setActive(token,true)}
    function moveTo(value) {
        travel.stop()
        destination = Math.max(0, Math.min(1, value))
        if (SwirlMotion.reduced || Math.abs(destination-progress)<0.001) {
            progress = destination
            return
        }
        travel.from = progress
        travel.to = destination
        travel.duration = Math.max(1, Math.round(duration*Math.abs(destination-progress)))
        travel.start()
    }
    function finish() { travel.stop(); progress = destination }
    onMovingChanged: SwirlTransitionRegistry.setActive(token, moving)
    Component.onDestruction: SwirlTransitionRegistry.setActive(token, false)
    Connections { target: SwirlMotion; function onReducedChanged() { if (SwirlMotion.reduced) coordinator.finish() } }
    NumberAnimation { id: travel; target: coordinator; property: "progress"; easing.type: Easing.OutCubic }
}
