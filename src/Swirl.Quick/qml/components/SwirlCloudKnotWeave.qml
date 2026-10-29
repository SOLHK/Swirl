pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick
import "SwirlCloudKnotPaths.js" as Knot

Item {
    id: weave
    property bool active: false
    property rect knotRect: Qt.rect(width - Theme.dp(146), (height - Theme.dp(88)) / 2, Theme.dp(128), Theme.dp(88))
    property real markSize: Theme.dp(150)
    property bool initialized: false
    readonly property bool windowVisible: !Window.window || (Window.window.visible && Window.window.visibility !== Window.Minimized)
    readonly property real markX: knotRect.x + (knotRect.width - markSize) / 2
    readonly property real markY: knotRect.y + (knotRect.height - markSize) / 2
    readonly property real pathScale: markSize / 1024 * 1.016216216
    readonly property real pathX: markX + markSize / 1024 * (136 - 117 * 1.016216216)
    readonly property real pathY: markY + markSize / 1024 * (225.43 - 263 * 1.016216216)
    readonly property real progress: {
        if (!initialized) return active ? 1 : 0
        let total = 0
        for (let i = 0; i < threads.count; ++i) {
            const thread = threads.itemAt(i) as KnotStrand
            if (thread) total += thread.amount
        }
        return total / Knot.passages.length
    }
    readonly property bool moving: {
        if (!initialized) return false
        for (let i = 0; i < threads.count; ++i) {
            const thread = threads.itemAt(i) as KnotStrand
            if (thread && thread.moving) return true
        }
        return false
    }
    signal retargetRequested()
    clip: true
    Accessible.ignored: true

    function retarget() { if (initialized) retargetRequested() }
    onActiveChanged: retarget()
    onVisibleChanged: if (!visible) retarget()
    onWindowVisibleChanged: if (!windowVisible) retarget()
    Component.onCompleted: initialized = true
    Connections { target: SwirlMotion; function onReducedChanged() { if (SwirlMotion.reduced) weave.retarget() } }

    // All five enter together. Each strand owns its current position, so
    // reversing a staggered withdrawal never remaps or jumps another strand.
    Repeater {
        id: threads
        model: Knot.passages
        delegate: KnotStrand {}
    }
    component KnotStrand: Item {
        id: strand
        required property var modelData
        property real amount: 0
        readonly property bool moving: flight.running
        readonly property real reveal: Math.max(0, Math.min(1, (amount - 0.26) / 0.74))
        readonly property real entryX: weave.pathX + modelData.start[0] * weave.pathScale
        readonly property real entryY: weave.pathY + modelData.start[1] * weave.pathScale
        readonly property string entryGuide: ["M", -Theme.dp(8), weave.height * (0.23 + modelData.index * 0.12),
            "C", weave.width * 0.32, weave.height * (0.15 + modelData.index * 0.12),
            entryX - weave.width * 0.15, entryY + Theme.dp(12), entryX, entryY].join(" ")
        objectName: "knotStrand-" + modelData.key
        width: weave.width; height: weave.height

        function retarget() {
            flight.stop()
            const destination = weave.active ? 1 : 0
            if (!weave.visible || !weave.windowVisible || SwirlMotion.reduced) {
                amount = destination
                return
            }
            if (amount === destination) return
            withdrawalDelay.duration = weave.active ? 0 : SwirlMotion.ms((4 - modelData.index) * 520)
            travel.from = amount
            travel.to = destination
            travel.duration = SwirlMotion.ms(Math.round((weave.active ? 4800 : 1100) * Math.abs(destination - amount)))
            flight.start()
        }
        Component.onCompleted: amount = weave.active ? 1 : 0
        Connections { target: weave; function onRetargetRequested() { strand.retarget() } }
        SequentialAnimation {
            id: flight
            PauseAnimation { id: withdrawalDelay }
            NumberAnimation { id: travel; target: strand; property: "amount"; easing.type: Easing.InOutSine }
        }
        SwirlSilkRope {
            objectName: "knotEntry-" + strand.modelData.key
            anchors.fill: parent
            visible: strand.amount > 0 && strand.amount < 1
            guide: strand.entryGuide
            ropeWidth: weave.pathScale * 48
            stops: strand.modelData.stops
            gradient: [weave.pathX + strand.modelData.gradient[0] * weave.pathScale,
                weave.pathY + strand.modelData.gradient[1] * weave.pathScale,
                weave.pathX + strand.modelData.gradient[2] * weave.pathScale,
                weave.pathY + strand.modelData.gradient[3] * weave.pathScale]
            trimStart: Math.max(0, Math.min(1, (strand.amount - 0.26) / 0.74))
            trimEnd: Math.min(1, strand.amount / 0.26)
        }
        Item {
            x: weave.markX; y: weave.markY; width: 1024; height: 1024
            scale: weave.markSize / 1024; transformOrigin: Item.TopLeft
            visible: strand.reveal > 0
            Item {
                x: 136; y: 225.43; scale: 1.016216216; transformOrigin: Item.TopLeft
                SwirlSilkRope {
                    objectName: "knotRope-" + strand.modelData.key
                    x: -117; y: -263; width: 1024; height: 1024
                    guide: strand.modelData.guide
                    ropeWidth: 48
                    gradient: strand.modelData.gradient
                    stops: strand.modelData.stops
                    trimEnd: strand.reveal
                }
            }
        }
    }
}
