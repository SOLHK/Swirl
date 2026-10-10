pragma Singleton
import QtQuick
QtObject {
    property string mode: "Light"
    property bool transparency: true
    property bool reduceMotion: false
    property real uiScale: 1.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    readonly property color canvas: dark ? "#111B2B" : "#E3F1FF"
    readonly property color surface: dark ? "#26334A" : "#F6FAFE"
    readonly property color raised: dark ? "#2F4057" : "#FAFCFF"
    readonly property color sidebar: dark ? "#B71C293E" : "#DDEDFB"
    readonly property color border: dark ? "#53677F" : "#E2ECF7"
    readonly property color glassRim: dark ? "#69B5D0F2" : "#DFFFFFFF"
    readonly property color glassGlint: dark ? "#A3DAE8FF" : "#F8FFFFFF"
    readonly property color glassShadow: dark ? "#7A020814" : "#2D567391"
    readonly property color text: dark ? "#F5F8FE" : "#101820"
    readonly property color muted: dark ? "#AEBFD1" : "#3E537F"
    readonly property color accent: dark ? "#9AC6FF" : "#0785FF"
    readonly property color selected: dark ? "#79466A9A" : "#CBE5FD"
    readonly property color hover: dark ? "#4A66829F" : "#8FE6F1FF"
    readonly property color field: dark ? "#9F17263B" : "#BFEAF2FC"
    readonly property color green: dark ? "#6AD9B3" : "#00B92F"
    readonly property color orange: dark ? "#F7C783" : "#B47A35"
    readonly property color red: dark ? "#FB9AA2" : "#FF554C"
    readonly property real windowRadius: 24
    readonly property real cardRadius: 20
    readonly property real secondaryRadius: 18
    readonly property real controlRadius: 12
    readonly property real sidebarWidth: 243
    readonly property real gap: 14
    readonly property real borderWidth: 1
    readonly property real shadowOpacity: 0.08
    readonly property string fontFamily: "Microsoft YaHei UI"
    function withAlpha(color, alpha) { return Qt.rgba(color.r, color.g, color.b, alpha) }
    function pillRadius(height) { return height * 0.5 }
    readonly property int motion: reduceMotion ? 0 : 210
    function material(kind) {
        if (dark) return kind === "sidebar" ? "#24364E" : kind === "field" ? "#2B405B" : "#293B53"
        if (kind === "sidebar") return "#DDEDFB"
        if (kind === "field") return "#F0F6FD"
        if (kind === "floating") return "#FAFCFF"
        if (kind === "toolbar") return "#F3F8FE"
        return "#F6FAFE"
    }
}
