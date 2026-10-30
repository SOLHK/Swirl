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
    required property Item frontLayer
    required property Item knotTarget
    required property Item cardViewport
    property Item proxyAnchor: null
    property Item sidebarAnchor: null
    property var wingScene: null
    property bool active: false
    property bool presentationActive: true
    property bool wide: true
    property real gap: Theme.dp(16)
    property real progress: 0
    property real release: 1
    property bool initialized: false
    property rect knotRect: Qt.rect(0, 0, 0, 0)
    property rect viewportRect: Qt.rect(0, 0, 0, 0)
    property var routes: ({})
    readonly property bool windowVisible: !Window.window || (Window.window.visible && Window.window.visibility !== Window.Minimized)
    readonly property bool moving: flight.running || withdrawal.running
    // Fit the visible cloud, not the old 1024px asset's transparent margins.
    // These coordinates never depend on animation progress.
    readonly property real pathScale: Math.min(knotRect.width * 0.86 / 718, knotRect.height * 0.76 / 548)
    readonly property real pathX: knotRect.x + knotRect.width / 2 - 487 * pathScale
    readonly property real pathY: knotRect.y + knotRect.height / 2 - 544 * pathScale
    readonly property real strokeWidth: 32 * pathScale
    readonly property real flightWidth: 25 * pathScale
    readonly property var cardItems: [connectionItem, transferItem, sourcesItem]
    Accessible.ignored: true

    function rectFor(item) {
        const p = item.mapToItem(behindCards, 0, 0);
        return Qt.rect(p.x,p.y,item.width,item.height);
    }
    function updateGeometry() {
        if (!initialized) return;
        knotRect = rectFor(knotTarget);
        viewportRect = rectFor(cardViewport);
        const cards = {connection:rectFor(connectionItem), traffic:rectFor(transferItem), sources:rectFor(sourcesItem)};
        const title = transferItem.titleItem;
        const titleOrigin = title.mapToItem(behindCards, title.leftPadding, title.topPadding);
        const scene = {
            proxy: proxyAnchor ? rectFor(proxyAnchor) : Qt.rect(cards.connection.x,0,Theme.dp(130),Theme.dp(30)),
            sidebar: sidebarAnchor ? rectFor(sidebarAnchor) : Qt.rect(0,0,Math.max(0,cards.connection.x-gap),behindCards.height),
            viewport: viewportRect,
            trafficTitle: Qt.rect(titleOrigin.x, titleOrigin.y, Math.min(title.contentWidth, title.width), title.contentHeight),
            leftWing: wingScene ? wingScene.ribbonWaypoints(behindCards) : [Qt.point(0,height*0.5),Qt.point(gap,height*0.6),Qt.point(gap*2,height*0.5),Qt.point(gap,height*0.4)],
            rightWing: wingScene ? wingScene.ribbonWaypoints(behindCards, "right") : [Qt.point(width-gap,0),Qt.point(width-gap*2,gap),Qt.point(width-gap*3,gap),Qt.point(width-gap*4,gap)]
        };
        const next = {};
        for (let i=0;i<Knot.passages.length;++i) {
            const passage=Knot.passages[i];
            next[passage.card]=Knot.route(passage,cards,knotRect,Knot.point(pathX,pathY),pathScale,wide,gap,scene);
        }
        routes=next;
    }
    function settleHidden() {
        flight.stop(); withdrawal.stop();
        progress=active?1:0; release=active?0:1;
    }
    function retarget() {
        if (!initialized) return;
        flight.stop(); withdrawal.stop();
        if (!visible || !windowVisible || !presentationActive) { settleHidden(); return; }
        if (SwirlMotion.reduced) {
            settleHidden();
            return;
        }
        if (active) {
            withdrawal.to=0; withdrawal.duration=180; withdrawal.start();
            if (progress<1) { flight.from=progress; flight.to=1; flight.duration=Math.max(1,SwirlMotion.ms(4800*(1-progress))); flight.start(); }
        } else {
            // Freeze route position and locally release each visible strand.
            // Turning off never races backwards through the whole scene.
            withdrawal.to=1; withdrawal.duration=180; withdrawal.start();
        }
    }
    onActiveChanged: retarget()
    onVisibleChanged: if (!visible && initialized) settleHidden()
    onPresentationActiveChanged: {
        if (!initialized) return;
        // Preserve the partial drawing while the overview fades into a detail.
        // A completed exit settles below; reversing an exit resumes in place.
        if (presentationActive) retarget();
        else { flight.stop(); withdrawal.stop(); }
    }
    onOpacityChanged: if (opacity === 0 && initialized) settleHidden()
    onWindowVisibleChanged: if (!windowVisible && initialized) settleHidden()
    onWidthChanged: Qt.callLater(updateGeometry)
    onHeightChanged: Qt.callLater(updateGeometry)
    onWideChanged: Qt.callLater(updateGeometry)
    Component.onCompleted: { initialized=true; settleHidden(); Qt.callLater(updateGeometry); }
    Connections { target: SwirlMotion; function onReducedChanged() { if (SwirlMotion.reduced) weave.retarget(); } }
    Connections { target: Theme; function onUiScaleChanged() { Qt.callLater(weave.updateGeometry); } }
    Connections {
        target: weave.transferItem.titleItem
        function onContentWidthChanged() { Qt.callLater(weave.updateGeometry); }
        function onContentHeightChanged() { Qt.callLater(weave.updateGeometry); }
        function onXChanged() { Qt.callLater(weave.updateGeometry); }
        function onYChanged() { Qt.callLater(weave.updateGeometry); }
    }
    Connections { target: weave.behindCards; function onWidthChanged() { Qt.callLater(weave.updateGeometry); } function onHeightChanged() { Qt.callLater(weave.updateGeometry); } }
    Connections {
        target: weave.knotTarget
        function onXChanged() { Qt.callLater(weave.updateGeometry); }
        function onYChanged() { Qt.callLater(weave.updateGeometry); }
        function onWidthChanged() { Qt.callLater(weave.updateGeometry); }
        function onHeightChanged() { Qt.callLater(weave.updateGeometry); }
    }
    Repeater {
        model: weave.cardItems
        delegate: Item {
            id: observer
            required property var modelData
            Connections {
                target: observer.modelData
                function onWidthChanged() { Qt.callLater(weave.updateGeometry); }
                function onHeightChanged() { Qt.callLater(weave.updateGeometry); }
                function onParentChanged() { Qt.callLater(weave.updateGeometry); }
                function onLiftChanged() { Qt.callLater(weave.updateGeometry); }
            }
            Connections {
                target: observer.modelData.parent
                function onXChanged() { Qt.callLater(weave.updateGeometry); }
                function onYChanged() { Qt.callLater(weave.updateGeometry); }
            }
        }
    }
    NumberAnimation {
        id: flight; target: weave; property: "progress"; easing.type: Easing.Linear
        paused: running && (!weave.presentationActive || !weave.windowVisible)
    }
    NumberAnimation {
        id: withdrawal; target: weave; property: "release"; easing.type: Easing.InOutSine
        paused: running && (!weave.presentationActive || !weave.windowVisible)
        onFinished: if (!weave.active && weave.release===1) weave.progress=0
    }
    Item {
        id: backView; parent: weave.behindCards
        width: parent.width; height: parent.height
        visible: weave.visible && weave.release<1
        opacity: weave.opacity*(1-weave.release)
    }
    Item {
        id: frontView; parent: weave.frontLayer
        x: weave.viewportRect.x; y: weave.viewportRect.y
        width: weave.viewportRect.width; height: weave.viewportRect.height
        clip: true
        visible: backView.visible; opacity: backView.opacity
    }
    Item {
        id: knotView; parent: frontView
        x: weave.knotRect.x - weave.viewportRect.x; y: weave.knotRect.y - weave.viewportRect.y
        width: weave.knotRect.width; height: weave.knotRect.height
        clip: true
    }
    Repeater {
        model: Knot.passages
        delegate: Item {
            id: strand
            required property var modelData
            readonly property var route: weave.routes[modelData.card] || null
            readonly property real head: route ? Knot.head(weave.progress,modelData.card,route) : 0
            readonly property real baseTail: route ? Knot.tail(weave.progress,modelData.card,route,head) : 0
            readonly property real tail: baseTail+(head-baseTail)*weave.release*0.75
            readonly property color ink: Theme.increaseContrast?Theme.text:modelData.ink
            readonly property rect aperture: route ? Qt.rect(route.aperture.x,route.aperture.y,route.aperture.width,route.aperture.height) : Qt.rect(0,0,0,0)
            RibbonStroke {
                objectName: "knotFlight-" + strand.modelData.card
                parent: backView; width: parent.width; height: parent.height
                guide: strand.route?strand.route.guide:""; ink: strand.ink; ribbonWidth: weave.flightWidth
                trimStart: strand.tail; trimEnd: strand.route ? Math.min(strand.head, strand.route.join) : 0
                broadening: 0.18
                settlement: 0.65
            }
            Item {
                parent: frontView
                x: strand.aperture.x - weave.viewportRect.x; y: strand.aperture.y - weave.viewportRect.y
                width: strand.aperture.width; height: strand.aperture.height
                visible: width > 0 && height > 0
                clip: true
                RibbonStroke {
                    objectName: "knotTitleOrbit-" + strand.modelData.key
                    x: -strand.aperture.x; y: -strand.aperture.y
                    width: backView.width; height: backView.height
                    guide: strand.route?strand.route.guide:""; ink: strand.ink; ribbonWidth: weave.flightWidth
                    trimStart: strand.tail; trimEnd: strand.route ? Math.min(strand.head, strand.route.join) : 0
                    broadening: 0.18; settlement: 0.65
                }
            }
            RibbonStroke {
                objectName: "knotRope-" + strand.modelData.key
                parent: knotView
                x: -weave.knotRect.x; y: -weave.knotRect.y
                width: frontView.width; height: frontView.height
                guide: strand.route?strand.route.guide:""; ink: strand.ink
                ribbonWidth: weave.strokeWidth
                trimStart: strand.tail; trimEnd: strand.head
                settlement: 1
            }
        }
    }
    Repeater {
        parent: knotView
        model: Knot.crossings
        delegate: Item {
            id: crossing
            required property var modelData
            readonly property var passage: Knot.passages[modelData.passage]
            readonly property var route: weave.routes[passage.card] || null
            readonly property real head: route?Knot.head(weave.progress,passage.card,route):0
            readonly property real baseTail: route?Knot.tail(weave.progress,passage.card,route,head):0
            readonly property real start: route?Math.max(route.join+modelData.start*(1-route.join),baseTail+(head-baseTail)*weave.release*0.75):0
            readonly property real end: route?Math.min(route.join+modelData.end*(1-route.join),head):0
            x: -weave.knotRect.x; y: -weave.knotRect.y
            width: frontView.width; height: frontView.height; visible:end>start
            RibbonStroke { anchors.fill:parent; guide:crossing.route?crossing.route.guide:""; ribbonWidth:weave.strokeWidth * 1.5; ink:Theme.independentCard; trimStart:crossing.start; trimEnd:crossing.end; settlement:1 }
            RibbonStroke { anchors.fill:parent; guide:crossing.route?crossing.route.guide:""; ribbonWidth:weave.strokeWidth; ink:Theme.increaseContrast?Theme.text:crossing.passage.ink; trimStart:crossing.start; trimEnd:crossing.end; settlement:1 }
        }
    }
}
