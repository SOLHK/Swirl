pragma Singleton
import QtQuick
QtObject {
    property string mode: "System"
    property bool transparency: true
    property bool reduceMotion: false
    property real uiScale: 1.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    readonly property color canvas: dark ? "#111821" : "#F4F6FA"
    readonly property color surface: dark ? "#1C2634" : "#FFFFFF"
    readonly property color raised: dark ? "#253449" : "#FFFFFF"
    readonly property color sidebar: dark ? "#E0151F2C" : "#F2FAFCFF"
    readonly property color border: dark ? "#35445A" : "#DFE6F0"
    readonly property color text: dark ? "#F4F7FC" : "#182638"
    readonly property color muted: dark ? "#A0AEC1" : "#687A91"
    readonly property color accent: dark ? "#95B9FF" : "#4276E7"
    readonly property color selected: dark ? "#294363" : "#E7EFFE"
    readonly property color hover: dark ? "#2A394D" : "#EDF2F9"
    readonly property color field: dark ? "#162231" : "#F6F8FC"
    readonly property color green: dark ? "#6CD4B3" : "#168766"
    readonly property color orange: dark ? "#F6C57D" : "#B8792F"
    readonly property color red: dark ? "#F599A2" : "#D35561"
    readonly property int motion: reduceMotion ? 0 : 180
    function material(kind) {
        if (kind === "sidebar" && transparency) return sidebar
        if (kind === "floating") return raised
        return surface
    }
}