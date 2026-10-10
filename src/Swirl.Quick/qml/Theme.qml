pragma Singleton
import QtQuick
QtObject {
    property string mode: "System"
    property bool transparency: true
    property bool reduceMotion: false
    property real uiScale: 1.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    readonly property color canvas: dark ? "#111B2B" : "#EEF3F9"
    readonly property color surface: dark ? "#26334A" : "#F5F9FF"
    readonly property color raised: dark ? "#2F4057" : "#FFFFFF"
    readonly property color sidebar: dark ? "#B71C293E" : "#BFE6F0FC"
    readonly property color border: dark ? "#53677F" : "#B7C7D9"
    readonly property color glassRim: dark ? "#69B5D0F2" : "#DFFFFFFF"
    readonly property color glassGlint: dark ? "#A3DAE8FF" : "#F8FFFFFF"
    readonly property color glassShadow: dark ? "#7A020814" : "#2D567391"
    readonly property color text: dark ? "#F5F8FE" : "#203049"
    readonly property color muted: dark ? "#AEBFD1" : "#65768D"
    readonly property color accent: dark ? "#9AC6FF" : "#376FE4"
    readonly property color selected: dark ? "#79466A9A" : "#A9D6E6FF"
    readonly property color hover: dark ? "#4A66829F" : "#8FE6F1FF"
    readonly property color field: dark ? "#9F17263B" : "#BFEAF2FC"
    readonly property color green: dark ? "#6AD9B3" : "#128C6B"
    readonly property color orange: dark ? "#F7C783" : "#B47A35"
    readonly property color red: dark ? "#FB9AA2" : "#D45460"
    readonly property int motion: reduceMotion ? 0 : 210
    function material(kind) {
        if (!transparency) {
            if (kind === "sidebar") return surface
            if (kind === "floating") return raised
            if (kind === "field") return field
            return surface
        }
        if (kind === "sidebar") return dark ? "#BD1A293F" : "#B8F3F8FF"
        if (kind === "floating") return dark ? "#E42C3F59" : "#E9FFFFFF"
        if (kind === "toolbar") return dark ? "#C8253751" : "#CFF9FCFF"
        if (kind === "secondary") return dark ? "#AD293951" : "#B7F3F8FF"
        if (kind === "field") return field
        return dark ? "#C21D2B40" : "#C8FFFFFF"
    }
}
