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
            // Fit the whole shoulder and first long tips inside the glass/sidebar
            // corridor. The remaining feathers continue into the bottom margin.
            // Avoid scaling the entire master until only middle bands are visible.
            readonly property real corridor: canvas.glassSurface ? canvas.glassBounds.x + canvas.glassBounds.width : Theme.sidebarWidth
            width: Math.min(canvas.width * 0.48, canvas.height * 0.62,
                Math.max(Theme.dp(235), corridor * 1.65))
            height: width * 780 / 760
            x: -Theme.dp(12)
            y: canvas.height - height - Theme.dp(8)
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
            width: Math.min(Theme.dp(185), canvas.width * 0.20)
            height: width * 780 / 760
            x: canvas.width - width + Theme.dp(12)
            y: -height * 0.52
            rotation: 166
            largeWing: true
            progress: canvas.progress
            opacity: Theme.dark ? 0.75 : 0.70
        }
    }
}
