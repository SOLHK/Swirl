pragma Singleton
import QtQuick
QtObject {
    property string mode: "Light"
    property bool transparency: true
    property bool reduceMotion: false
    property real uiScale: 1.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    // Opaque light surfaces separate the page from its white content cards.
    readonly property color canvas: dark ? "#1E1E1E" : "#F8F8FA"
    readonly property color surface: dark ? canvas : "#FFFFFF"
    readonly property color raised: dark ? "#292929" : "#F7F7F7"
    // Keep light mode independent of the wallpaper and Windows backdrop.
    // Retain the existing optional translucent material in dark mode.
    readonly property color sidebarBase: dark ? "#292929" : "#F1F1F4"
    readonly property real sidebarOpacity: dark && transparency ? 0.94 : 1.0
    readonly property color sidebar: withAlpha(sidebarBase, sidebarOpacity)
    readonly property color border: dark ? "#454545" : "#E8E8ED"
    readonly property color glassRim: border
    readonly property color glassGlint: dark ? "#4A4A4A" : "#FFFFFF"
    readonly property color glassShadow: dark ? "#50000000" : "#18000000"
    readonly property color pillRim: dark ? "#505050" : "#D9DBDE"
    readonly property color pillTop: dark ? "#333333" : "#F7F7F7"
    readonly property color pillBottom: pillTop
    readonly property color text: dark ? "#F5F5F5" : "#171717"
    readonly property color muted: dark ? "#BFC3CB" : "#586174"
    readonly property color accent: dark ? "#80B7FF" : "#0069D9"
    readonly property color speedAccent: dark ? "#80B7FF" : "#007AFF"
    readonly property color primaryControl: dark ? "#2165AF" : "#005BBF"
    readonly property color navigationAccent: dark ? "#9AC8FF" : "#005BBF"
    readonly property color selected: dark ? "#484848" : "#DADADA"
    readonly property color hover: dark ? "#3A3A3A" : "#E3E3E3"
    readonly property color pressed: dark ? "#505050" : "#D8D8D8"
    readonly property color controlBorder: pillRim
    readonly property color focusBorder: dark ? "#9AC8FF" : "#005BBF"
    readonly property color buttonBase: dark ? "#333333" : "#F7F7F7"
    readonly property color field: dark ? "#353535" : "#F6F6F6"
    readonly property color green: dark ? "#75DD91" : "#00852A"
    readonly property color statusGreen: dark ? "#75DD91" : "#00B832"
    readonly property color orange: dark ? "#F5C67D" : "#976217"
    readonly property color red: dark ? "#FF9A93" : "#CF3029"
    readonly property real windowRadius: 18
    readonly property real cardRadius: 12
    readonly property real secondaryRadius: 10
    readonly property real controlRadius: 10
    readonly property real sidebarWidth: 286
    readonly property real gap: 24
    readonly property real borderWidth: 1
    readonly property real shadowOpacity: 0.05
    readonly property string fontFamily: "Microsoft YaHei UI"
    function withAlpha(color, alpha) { return Qt.rgba(color.r, color.g, color.b, alpha) }
    function pillRadius(height) { return height * 0.5 }
    readonly property int motion: reduceMotion ? 0 : 180
    function material(kind) {
        if (kind === "sidebar") return sidebar
        if (kind === "field") return field
        if (kind === "floating") return dark ? "#2B2B2B" : "#FFFFFF"
        if (kind === "toolbar") return canvas
        return surface
    }
}
