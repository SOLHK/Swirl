pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick
import "../controls"

Item {
    id: canvas
    property var targetWindow: Window.window
    property Item glassSurface: null
    property bool glassSampled: false
    readonly property Item decorationSource: decoration
    readonly property bool splitDecoration: glassSampled && Theme.effectsSupported
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
        duration: SwirlMotion.ms(2600)
        paused: entrance.running && !canvas.presenting
    }

    SwirlGlassMaterial { anchors.fill: parent; targetWindow: canvas.targetWindow }
    Item {
        id: decoration
        objectName: "workspaceWingDecoration"
        anchors.fill: parent
        visible: canvas.presenting
        Accessible.ignored: true
        Item {
            id: footprint
            objectName: "apecWingFootprint"
            // A single right-facing fan enters from beyond the lower-left edge.
            // Its fixed artboard is uniformly scaled; the window crops the root.
            width: Math.max(canvas.width * 1.08, canvas.height * 1.52)
            height: width * 0.625
            x: canvas.width - width - Theme.dp(20)
            y: canvas.height - height + Theme.dp(8)
            SwirlWingAnimation {
                id: visual
                objectName: "apecWingVisual"
                anchors.fill: parent
                largeWing: true
                progress: canvas.progress
                opacity: Theme.wingOpacity
            }
        }
    }
    ShaderEffectSource {
        id: wingTexture
        sourceItem: canvas.splitDecoration ? decoration : null
        hideSource: canvas.splitDecoration
        visible: false
        live: canvas.presenting && decoration.visible
        smooth: true
        textureSize: Qt.size(Math.max(1, Math.ceil(canvas.width * Screen.devicePixelRatio)),
                             Math.max(1, Math.ceil(canvas.height * Screen.devicePixelRatio)))
    }
    ShaderEffect {
        anchors.fill: parent
        visible: canvas.splitDecoration && canvas.presenting && decoration.visible
        property var source: wingTexture
        property vector2d surfaceSize: Qt.vector2d(width, height)
        property vector4d glassRect: Qt.vector4d(canvas.glassBounds.x, canvas.glassBounds.y, canvas.glassBounds.width, canvas.glassBounds.height)
        property real cornerRadius: Theme.sidebarRadius
        property real glassActive: 1
        fragmentShader: "qrc:/swirl/shaders/workspace-wing.frag.qsb"
    }
}
