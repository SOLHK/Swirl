pragma Singleton
import QtQuick
QtObject {
    property string mode: "System"
    property bool transparency: true
    property bool reduceMotion: false
    property real uiScale: 1.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    readonly property color canvas: dark ? "#101622" : "#F3F6FA"
    readonly property color surface: dark ? "#1B2635" : "#FBFCFE"
    readonly property color raised: dark ? "#263648" : "#FFFFFF"
    readonly property color sidebar: dark ? "#E5182636" : "#ECEDF3FA"
    readonly property color border: dark ? "#405166" : "#DCE4EC"
    readonly property color text: dark ? "#F5F8FB" : "#1C2938"
    readonly property color muted: dark ? "#AFBDCD" : "#66798B"
    readonly property color accent: dark ? "#98BEFF" : "#3874E6"
    readonly property color selected: dark ? "#30455D" : "#E3EDFF"
    readonly property color hover: dark ? "#2D4056" : "#EAF0F8"
    readonly property color field: dark ? "#172331" : "#F5F8FB"
    readonly property color green: dark ? "#6CD4B3" : "#168766"
    readonly property color orange: dark ? "#F6C57D" : "#B8792F"
    readonly property color red: dark ? "#F599A2" : "#D35561"
    readonly property int motion: reduceMotion ? 0 : 180
    function material(kind) {
        if (kind === "sidebar") return transparency ? sidebar : surface
        if (kind === "floating") return transparency ? (dark ? "#EC263955" : "#F8FFFFFF") : raised
        return transparency ? (dark ? "#EE1A2A3C" : "#EDFFFFFF") : surface
    }
}