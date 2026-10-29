pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick

QtObject {
    id: motion
    readonly property bool active: engineController.systemProxy.owned && engineController.systemProxy.enabled && engineController.processAlive
    property bool windowVisible: true
    property real progress: 0
    property bool initialized: false
    readonly property bool moving: unfold.running
    readonly property int expandDuration: 1600
    readonly property int collapseDuration: 1000
    property alias animation: unfold
    Behavior on progress {
        enabled: motion.initialized && motion.windowVisible && !SwirlMotion.reduced
        SmoothedAnimation {
            id: unfold
            velocity: 1000 / Math.max(1, SwirlMotion.ms(motion.active ? motion.expandDuration : motion.collapseDuration))
            maximumEasingTime: 100
            reversingMode: SmoothedAnimation.Eased
        }
    }
    function update() {
        if (!initialized) return
        // Behavior retargets the animation from its current value and velocity.
        progress = active ? 1 : 0
    }
    onActiveChanged: update()
    onWindowVisibleChanged: update()
    property Connections motionPolicyConnection: Connections {
        target: SwirlMotion
        function onReducedChanged() { motion.update() }
    }
    Component.onCompleted: { initialized = true; update() }
}
