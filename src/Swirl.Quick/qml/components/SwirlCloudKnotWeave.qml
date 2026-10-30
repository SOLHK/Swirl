pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick
import "SwirlCloudKnotPaths.js" as Knot

Item {
    id: weave
    required property Item connectionItem
    required property Item transferItem
    required property Item sourcesItem
    required property Item diagnosticItem
    required property Item connectionsItem
    required property Item knotTarget
    property bool active: false
    property bool presentationActive: true
    property bool wide: true
    property real gap: Theme.dp(16)
    property real markSize: Theme.dp(100)
    property real progress: 0
    property bool initialized: false
    property rect knotRect: Qt.rect(0, 0, 0, 0)
    property var routes: ({})
    readonly property bool windowVisible: !Window.window || (Window.window.visible && Window.window.visibility !== Window.Minimized)
    readonly property bool moving: flight.running
    readonly property real markX: knotRect.x + (knotRect.width - markSize) / 2
    readonly property real markY: knotRect.y + (knotRect.height - markSize) / 2
    readonly property real pathScale: markSize / 1024 * 1.016216216
    readonly property real pathX: markX + markSize / 1024 * (136 - 117 * 1.016216216)
    readonly property real pathY: markY + markSize / 1024 * (225.43 - 263 * 1.016216216)
    readonly property var cardItems: [connectionItem, transferItem, sourcesItem, diagnosticItem, connectionsItem]
    Accessible.ignored: true
    // This item deliberately has no input handlers or card-sized clip.

    function phase(start, end) {
        const t = Math.max(0, Math.min(1, (progress - start) / (end - start)))
        return t * t * (3 - 2 * t)
    }
    function reveal(passage) { return phase(0.27 + passage.order * 0.013, 0.94 + passage.order * 0.013) }
    function rectFor(item) {
        const p = item.mapToItem(weave, 0, 0)
        return Qt.rect(p.x, p.y, item.width, item.height)
    }
    function updateGeometry() {
        if (!initialized) return
        knotRect = rectFor(knotTarget)
        const cards = { connection: rectFor(connectionItem), traffic: rectFor(transferItem),
            sources: rectFor(sourcesItem), diagnostics: rectFor(diagnosticItem), connections: rectFor(connectionsItem) }
        const next = {}
        for (let i = 0; i < Knot.passages.length; ++i) {
            const passage = Knot.passages[i]
            const end = Knot.point(pathX + passage.start[0] * pathScale, pathY + passage.start[1] * pathScale)
            const approach = Knot.point(end.x - passage.tangent[0] * pathScale, end.y - passage.tangent[1] * pathScale)
            next[passage.card] = Knot.route(passage.card, cards, knotRect, end, approach, wide, passage.order, gap)
        }
        routes = next
    }
    function retarget() {
        if (!initialized) return
        flight.stop()
        const destination = active ? 1 : 0
        if (!visible || !windowVisible || !presentationActive || SwirlMotion.reduced) {
            progress = destination
            return
        }
        if (progress === destination) return
        flight.from = progress
        flight.to = destination
        // 4.1s vs the previous 4.8s; most time remains with the actual weave.
        flight.duration = SwirlMotion.ms(Math.max(1, Math.round((active ? 4100 : 1450) * Math.abs(destination - progress))))
        flight.start()
    }
    onActiveChanged: retarget()
    onVisibleChanged: if (!visible) retarget()
    onWidthChanged: Qt.callLater(updateGeometry)
    onHeightChanged: Qt.callLater(updateGeometry)
    onWideChanged: Qt.callLater(updateGeometry)
    onMarkSizeChanged: Qt.callLater(updateGeometry)
    Component.onCompleted: { initialized = true; progress = active ? 1 : 0; Qt.callLater(updateGeometry) }
    Connections { target: SwirlMotion; function onReducedChanged() { if (SwirlMotion.reduced) weave.retarget() } }
    Connections { target: Theme; function onUiScaleChanged() { Qt.callLater(weave.updateGeometry) } }
    Connections {
        target: weave.knotTarget
        function onXChanged() { Qt.callLater(weave.updateGeometry) }
        function onYChanged() { Qt.callLater(weave.updateGeometry) }
        function onWidthChanged() { Qt.callLater(weave.updateGeometry) }
        function onHeightChanged() { Qt.callLater(weave.updateGeometry) }
    }
    Repeater {
        model: weave.cardItems
        delegate: Item {
            id: observer
            required property var modelData
            Connections {
                target: observer.modelData
                function onWidthChanged() { Qt.callLater(weave.updateGeometry) }
                function onHeightChanged() { Qt.callLater(weave.updateGeometry) }
                function onParentChanged() { Qt.callLater(weave.updateGeometry) }
                function onLiftChanged() { Qt.callLater(weave.updateGeometry) }
            }
            Connections {
                target: observer.modelData.parent
                function onXChanged() { Qt.callLater(weave.updateGeometry) }
                function onYChanged() { Qt.callLater(weave.updateGeometry) }
            }
        }
    }
    NumberAnimation {
        id: flight
        target: weave; property: "progress"
        easing.type: Easing.Linear
        // Retain the exact position during a detail visit; never replay on return.
        paused: running && (!weave.presentationActive || !weave.windowVisible)
    }
    Repeater {
        model: Knot.passages
        delegate: SwirlKnotLead {
            id: lead
            required property var modelData
            objectName: "knotEntry-" + modelData.key
            width: weave.width; height: weave.height
            route: weave.routes[modelData.card] || null
            ink: Theme.increaseContrast ? Theme.text : modelData.stops[0].light
            tip: ink
            ropeWidth: weave.pathScale * 36
            amount: weave.phase(modelData.order * 0.013, 0.27 + modelData.order * 0.013)
            withdrawal: weave.phase(0.57 + modelData.order * 0.013, 0.90 + modelData.order * 0.013)
            bend: Theme.dp(1.2) * Math.sin(Math.PI * amount) * (modelData.order % 2 ? 1 : -1)
        }
    }
    Item {
        x: weave.pathX; y: weave.pathY
        width: 1024; height: 1024
        scale: weave.pathScale; transformOrigin: Item.TopLeft
        Repeater {
            model: Knot.passages
            delegate: SwirlSilkRope {
                required property var modelData
                objectName: "knotRope-" + modelData.key
                width: 1024; height: 1024
                guide: modelData.guide
                ropeWidth: 48
                gradient: modelData.gradient; stops: modelData.stops
                trimEnd: weave.reveal(modelData)
            }
        }
        Repeater {
            model: Knot.crossings
            delegate: Item {
                id: crossing
                required property var modelData
                readonly property var passage: Knot.passages[modelData.passage]
                readonly property real revealed: Math.min(modelData.end, weave.reveal(passage))
                width: 1024; height: 1024
                visible: revealed > modelData.start
                // A local surface-coloured clearance exposes the underpass, then
                // the same growing strand is redrawn above it. No image swap.
                SwirlSilkRope {
                    anchors.fill: parent
                    guide: crossing.passage.guide; ropeWidth: 62
                    flatInk: Theme.independentCard
                    trimStart: crossing.modelData.start; trimEnd: crossing.revealed
                }
                SwirlSilkRope {
                    anchors.fill: parent
                    guide: crossing.passage.guide; ropeWidth: 48
                    gradient: crossing.passage.gradient; stops: crossing.passage.stops
                    trimStart: crossing.modelData.start; trimEnd: crossing.revealed
                }
            }
        }
    }
}
