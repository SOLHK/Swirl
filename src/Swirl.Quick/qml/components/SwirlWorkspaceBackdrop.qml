pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick
import "../controls"

Item {
    id: canvas
    property var targetWindow: Window.window
    property var composition: backdrop
    property Item glassSurface: null
    property bool glassSampled: false
    property real ribbonProgress: 0
    property real ribbonStrength: 1
    readonly property Item mainWingItem: visual
    function mapWingPoint(target, x, y) { return visual.mapMasterPoint(target, x, y) }
    function ribbonWaypoints(target) {
        return [visual.routePoint(target, "root"), visual.routePoint(target, "shoulder"),
            visual.routePoint(target, "tip"), visual.routePoint(target, "gap")]
    }
    readonly property Item decorationSource: decoration
    // Kept for callers which inspect the material, but the clear sidebar never
    // replaces any part of the original vector scene with a captured texture.
    readonly property bool splitDecoration: false
    readonly property rect glassBounds: {
        if (!glassSurface) return Qt.rect(0, 0, 0, 0)
        glassSurface.x; glassSurface.y; glassSurface.width; glassSurface.height
        const origin = glassSurface.mapToItem(canvas, 0, 0)
        return Qt.rect(origin.x, origin.y, glassSurface.width, glassSurface.height)
    }
    readonly property bool presenting: visible && !Theme.increaseContrast
        && (!targetWindow || (targetWindow.visible && targetWindow.visibility !== Window.Minimized))
    readonly property bool entering: entrance.running
    property bool entranceConsumed: false
    property bool firstFramePresented: false
    property real progress: 0

    function startEntrance() {
        if (!presenting || entranceConsumed) return
        entranceConsumed = true
        if (SwirlMotion.reduced) progress = 1
        else entrance.start()
    }
    onPresentingChanged: {
        if (presenting && firstFramePresented && !entranceConsumed) visibleDelay.restart()
    }
    Connections {
        target: canvas.targetWindow
        enabled: !canvas.entranceConsumed
        function onFrameSwapped() {
            if (!canvas.presenting || canvas.firstFramePresented) return
            canvas.firstFramePresented = true
            visibleDelay.start()
        }
    }
    Connections {
        target: SwirlMotion
        function onReducedChanged() {
            if (SwirlMotion.reduced && canvas.entranceConsumed) {
                entrance.stop()
                canvas.progress = 1
            }
        }
    }
    Timer {
        id: visibleDelay
        interval: 120
        onTriggered: canvas.startEntrance()
    }
    NumberAnimation {
        id: entrance
        target: canvas
        property: "progress"
        from: 0
        to: 1
        duration: SwirlMotion.ms(1240)
        paused: entrance.running && !canvas.presenting
    }

    SwirlGlassMaterial { anchors.fill: parent; targetWindow: canvas.targetWindow; composition: canvas.composition }
    Item {
        id: decoration
        objectName: "workspaceWingDecoration"
        anchors.fill: parent
        visible: canvas.presenting
        Accessible.ignored: true
        Item {
            id: footprint
            objectName: "apecWingFootprint"
            // The rising outer shoulders remain visible through the clear sidebar;
            // the curved spine continues beneath the lower card row.
            readonly property real corridor: canvas.glassSurface ? canvas.glassBounds.x + canvas.glassBounds.width : Theme.sidebarWidth
            width: Math.min(canvas.width * 0.40, canvas.height * 0.65,
                Math.max(Theme.dp(280), corridor * 1.48))
            height: width * 580 / 880
            x: -Theme.dp(8)
            y: canvas.height - height + Theme.dp(4)
            SwirlWingAnimation {
                id: visual
                objectName: "apecWingVisual"
                anchors.fill: parent
                largeWing: true
                progress: canvas.progress
                ribbonProgress: canvas.presenting ? canvas.ribbonProgress : 0
                ribbonStrength: canvas.ribbonStrength
                opacity: 1
            }
        }
        SwirlWingAnimation {
            objectName: "workspaceWingEcho"
            width: Math.min(Theme.dp(260), canvas.width * 0.27)
            height: width * 130 / 540
            x: canvas.width - width + Theme.dp(2)
            y: 0
            largeWing: true
            echoWing: true
            progress: canvas.progress
            opacity: Theme.dark ? 0.62 : 0.56
        }
    }
}
