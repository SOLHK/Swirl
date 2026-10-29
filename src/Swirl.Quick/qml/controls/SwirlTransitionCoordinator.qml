import QtQuick
import SwirlQuick
Item {
    id: coordinator
    // One reversible clock. Business state changes before animation starts;
    // interruption continues from the currently displayed geometry.
    property real progress: 0
    property real destination: 0
    property int duration: SwirlMotion.expandDuration
    property bool retargeting:false
    readonly property bool moving: retargeting || travel.running
    property int generation:0
    property int token: 0
    Component.onCompleted: {token=SwirlTransitionRegistry.allocate();if(moving)SwirlTransitionRegistry.setActive(token,true)}
    function moveTo(value) {
        // Retargeting is one continuous operation. Do not briefly publish
        // "finished" while stopping the old direction: a native window could
        // otherwise close itself before the reverse clock has even started.
        ++generation
        retargeting=true
        travel.stop()
        destination = Math.max(0, Math.min(1, value))
        if (SwirlMotion.reduced || Math.abs(destination-progress)<0.001) {
            progress = destination
            retargeting=false
            return
        }
        travel.from = progress
        travel.to = destination
        travel.duration = Math.max(1, Math.round(duration*Math.abs(destination-progress)))
        travel.start()
        retargeting=false
    }
    function stop() {retargeting=true;travel.stop();retargeting=false}
    function finish() { retargeting=true;travel.stop();progress=destination;retargeting=false }
    onMovingChanged: SwirlTransitionRegistry.setActive(token, moving)
    Component.onDestruction: SwirlTransitionRegistry.setActive(token, false)
    Connections { target: SwirlMotion; function onReducedChanged() { if (SwirlMotion.reduced) coordinator.finish() } }
    NumberAnimation { id: travel; target: coordinator; property: "progress"; easing.type: SwirlMotion.standardEasing }
}
