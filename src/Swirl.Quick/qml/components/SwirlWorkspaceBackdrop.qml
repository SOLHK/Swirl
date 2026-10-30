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
        duration: SwirlMotion.ms(2100)
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
            // Keep the fan near its lower-left root, outside the reading centre.
            width: Math.max(Theme.dp(420), Math.min(canvas.width * 0.72, canvas.height * 0.96))
            height: width * 0.76
            x: -width * 0.08
            y: canvas.height - height * 0.76
            SwirlWingAnimation {
                id: visual
                objectName: "apecWingVisual"
                anchors.fill: parent
                largeWing: true
                progress: canvas.progress
                opacity: Theme.dark ? 0.62 : 0.82
            }
        }
        SwirlWingAnimation {
            objectName: "workspaceWingEcho"
            width: Math.min(Theme.dp(280), canvas.width * 0.25)
            height: width * 0.76
            x: canvas.width - width * 0.72
            y: -height * 0.38
            rotation: 180
            largeWing: true
            progress: canvas.progress
            opacity: Theme.dark ? 0.22 : 0.30
        }
    }
}
