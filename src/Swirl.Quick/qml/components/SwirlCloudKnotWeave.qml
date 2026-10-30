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
    required property Item behindCards
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

    function reveal(passage) {
        const route = routes[passage.card];
        if (!route) return 0;
        return Math.max(0, (Knot.head(progress, passage.card, route.join) - route.join) / (1 - route.join));
    }
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
            next[passage.card] = Knot.route(passage, cards, knotRect, Knot.point(pathX, pathY), pathScale, wide, gap);
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
        // Departure, arrival and winding have separate per-strand cues on one clock.
        flight.duration = SwirlMotion.ms(Math.max(1, Math.round((active ? 1900 : 1100) * Math.abs(destination - progress))))
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
        delegate: Item {
            id: strand
            required property var modelData
            readonly property var route: weave.routes[modelData.card] || null
            readonly property real head: route ? Knot.head(weave.progress, modelData.card, route.join) : 0
            readonly property real tail: route ? Knot.tail(weave.progress, modelData.card, route, head) : 0
            readonly property color ink: Theme.increaseContrast ? Theme.text : modelData.ink
            readonly property rect aperture: route ? Qt.rect(route.aperture.x, route.aperture.y, route.aperture.width, route.aperture.height) : Qt.rect(0,0,0,0)
            width: weave.width; height: weave.height
            // A single continuous guide contains both approach and knot. Three
            // views expose it behind cards, at its launch, and inside the emblem.
            SwirlSilkRope {
                objectName: "knotFlight-" + strand.modelData.card
                parent: weave.behindCards
                width: weave.width; height: weave.height
                guide: strand.route ? strand.route.guide : ""
                flatInk: strand.ink; ropeWidth: weave.pathScale * 36
                trimStart: strand.tail; trimEnd: strand.head
            }
            Item {
                x: strand.aperture.x; y: strand.aperture.y
                width: strand.aperture.width; height: strand.aperture.height
                clip: true
                // The local strand is already exposed by the emblem view.
                visible: strand.modelData.card !== "connection"
                SwirlSilkRope {
                    x: -parent.x; y: -parent.y; width: weave.width; height: weave.height
                    guide: strand.route ? strand.route.guide : ""
                    flatInk: strand.ink; ropeWidth: weave.pathScale * 36
                    trimStart: strand.tail; trimEnd: strand.head
                }
            }
            Item {
                x: weave.knotRect.x; y: weave.knotRect.y
                width: weave.knotRect.width; height: weave.knotRect.height
                clip: true
                SwirlSilkRope {
                    objectName: "knotRope-" + strand.modelData.key
                    x: -parent.x; y: -parent.y; width: weave.width; height: weave.height
                    guide: strand.route ? strand.route.guide : ""
                    flatInk: strand.ink; ropeWidth: weave.pathScale * 36
                    trimStart: strand.tail; trimEnd: strand.head
                }
            }
        }
    }
    Item {
        x: weave.pathX; y: weave.pathY
        width: 1024; height: 1024
        scale: weave.pathScale; transformOrigin: Item.TopLeft
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
                    guide: crossing.passage.guide; ropeWidth: 48
                    flatInk: Theme.independentCard
                    trimStart: crossing.modelData.start; trimEnd: crossing.revealed
                }
                SwirlSilkRope {
                    anchors.fill: parent
                    guide: crossing.passage.guide; ropeWidth: 36
                    flatInk: Theme.increaseContrast ? Theme.text : crossing.passage.ink
                    trimStart: crossing.modelData.start; trimEnd: crossing.revealed
                }
            }
        }
    }
}
