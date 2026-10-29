import QtQuick
import SwirlQuick

Item {
    id: glass
    property Item backdropSource: null
    property real cornerRadius: Theme.sidebarRadius
    property real interaction: 0
    property point lightPoint: Qt.point(0.18, 0.15)
    // The original scene stays visible beneath this pane. No capture, fill,
    // blur or refracted copy may change the wing's interior pixels.
    readonly property bool sampled: false
    readonly property bool captureLive: false
    readonly property int shaderStatus: material.status
    readonly property string shaderLog: material.log

    ShaderEffect {
        id: material
        objectName: "sidebarLiquidShader"
        anchors.fill: parent
        visible: Theme.effectsSupported && !Theme.increaseContrast
        property vector2d surfaceSize: Qt.vector2d(width, height)
        property real cornerRadius: glass.cornerRadius
        property real pixelWidth: 1 / Screen.devicePixelRatio
        property real interaction: glass.interaction
        property vector2d lightPoint: Qt.vector2d(glass.lightPoint.x, glass.lightPoint.y)
        property color highlightColor: Theme.glassHighlight
        property color reflectionColor: Theme.glassReflection
        property real darkAppearance: Theme.dark ? 1 : 0
        fragmentShader: "qrc:/swirl/shaders/sidebar-liquid.frag.qsb"
    }
    SwirlShellOutline {
        anchors.fill: parent
        visible: !Theme.effectsSupported || Theme.increaseContrast
        radius: glass.cornerRadius
        fillColor: "transparent"
        strokeColor: Theme.increaseContrast ? Theme.text : Theme.withAlpha(Theme.border, Theme.dark ? 0.06 : 0.45)
    }
    Accessible.ignored: true
}
