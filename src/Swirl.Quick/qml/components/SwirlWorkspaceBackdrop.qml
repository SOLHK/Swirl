pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: canvas
    property var targetWindow: Window.window
    property Item glassSurface: null
    property bool glassSampled: false
    property bool homeVisible: true
    readonly property Item decorationSource: decoration
    readonly property bool splitDecoration: glassSampled && Theme.effectsSupported
    readonly property rect glassBounds: {
        if (!glassSurface) return Qt.rect(0, 0, 0, 0)
        glassSurface.x; glassSurface.y; glassSurface.width; glassSurface.height
        const origin = glassSurface.mapToItem(canvas, 0, 0)
        return Qt.rect(origin.x, origin.y, glassSurface.width, glassSurface.height)
    }
    readonly property bool presenting: homeVisible && visible && Theme.transparency && !Theme.increaseContrast
        && (!targetWindow || (targetWindow.visible && targetWindow.visibility !== Window.Minimized))
    readonly property bool entering: entrance.running
    property bool entranceConsumed: false
    property bool initialized: false

    function present() {
        if (!initialized) return
        entrance.stop()
        visual.opacity = presenting ? Theme.wingOpacity : 0
        visual.scale = 1
        visual.rotation = 0
        visual.y = 0
        if (presenting && !entranceConsumed) {
            entranceConsumed = true
            if (!SwirlMotion.reduced) entrance.start()
        }
    }
    onPresentingChanged: present()
    Component.onCompleted: { initialized = true; present() }
    Connections {
        target: SwirlMotion
        function onReducedChanged() { if (SwirlMotion.reduced) canvas.present() }
    }
    Connections {
        target: Theme
        function onDarkChanged() { canvas.present() }
    }

    SwirlGlassMaterial { anchors.fill: parent; targetWindow: canvas.targetWindow }
    Item {
        id: decoration
        objectName: "workspaceWingDecoration"
        anchors.fill: parent
        Accessible.ignored: true
        Item {
            id: footprint
            objectName: "apecWingFootprint"
            // A single right-facing fan enters from beyond the lower-left edge.
            // Its fixed artboard is uniformly scaled; the window crops the root.
            width: Math.max(canvas.width * 1.08, canvas.height * 1.52)
            height: width * 0.625
            x: canvas.width - width - Theme.dp(20)
            y: canvas.height - height + Theme.dp(40)
            Item {
                id: visual
                objectName: "apecWingVisual"
                width: footprint.width; height: footprint.height
                transformOrigin: Item.BottomLeft
                opacity: 0
                Shape {
                    objectName: "apecFlatWingPaths"
                    width: 1600; height: 1000
                    scale: footprint.width / 1600
                    transformOrigin: Item.TopLeft
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: 0; strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: 160; y1: 960; x2: 1560; y2: 30
                            GradientStop { position: 0; color: Theme.withAlpha(Theme.wingGold, 0.42) }
                            GradientStop { position: 0.16; color: Theme.withAlpha(Theme.wingCoral, 0.65) }
                            GradientStop { position: 0.33; color: Theme.wingRose }
                            GradientStop { position: 0.55; color: Theme.wingCyan }
                            GradientStop { position: 0.79; color: Theme.withAlpha(Theme.wingTeal, 0.74) }
                            GradientStop { position: 1; color: Theme.withAlpha(Theme.wingGreen, 0.48) }
                        }
                        PathSvg { path: "M -70 830 C 35 957 205 955 415 868 C 798 709 1202 359 1570 20 C 1246 388 825 745 433 915 C 206 1000 10 1002 -70 830 Z
M 280 925 C 653 771 1093 505 1460 205 C 1125 544 684 827 300 960 Z
M 408 942 C 692 835 1061 656 1365 425 C 1118 698 736 904 439 970 Z
M 510 954 C 751 871 1007 751 1235 650 C 1038 795 782 942 520 980 Z
M 600 980 C 800 918 1004 844 1140 795 C 1020 895 842 965 610 1000 Z" }
                    }
                }
            }
        }
    }
    ShaderEffectSource {
        id: wingTexture
        sourceItem: canvas.splitDecoration ? decoration : null
        hideSource: canvas.splitDecoration; visible: false
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
    ParallelAnimation {
        id: entrance
        OpacityAnimator { target: visual; from: 0; to: Theme.wingOpacity; duration: SwirlMotion.ms(620); easing.type: Easing.OutCubic }
        ScaleAnimator { target: visual; from: 0.92; to: 1; duration: SwirlMotion.ms(900); easing.type: Easing.OutCubic }
        RotationAnimator { target: visual; from: 4; to: 0; duration: SwirlMotion.ms(900); easing.type: Easing.OutCubic }
        YAnimator { target: visual; from: Theme.dp(14); to: 0; duration: SwirlMotion.ms(900); easing.type: Easing.OutCubic }
    }
}
