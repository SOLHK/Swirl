pragma Singleton
import QtQuick
import QtCore
QtObject {
    property string mode: "Light"
    property bool transparency: true
    property bool backdropActive: false
    property bool windowActive:true
    // Tint the real desktop through the Qt alpha surface, including the page gutter.
    readonly property real shellOpacity:transparency && backdropActive ? (dark?0.82:0.72) : 1.0
    readonly property color shellTop:withAlpha(dark?"#292C31":windowActive?"#D7E8F3":"#E6F0F7",shellOpacity)
    readonly property color shellBottom:withAlpha(dark?"#22252B":windowActive?"#D4DEEB":"#E5EAF4",shellOpacity)
    readonly property bool effectsSupported: gpuEffectsSupported
    property bool reduceMotion: false
    property string pageBranch: "B"
    // Qt already maps QML logical pixels to each screen's DPI. Automatic mode
    // therefore uses the native 100% logical design scale; manual scaling is a
    // separate, persistent preference and never overrides Windows DPI.
    property Settings appearanceSettings: Settings {
        category: "Appearance"
        property int savedScalePercent: 100
        property bool followSystemScale: true
    }
    property bool followSystemScale: appearanceSettings.followSystemScale
    readonly property real uiScale: followSystemScale ? 1.0 : appearanceSettings.savedScalePercent / 100.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    // Opaque light surfaces separate the page from its white content cards.
    readonly property color canvas: dark ? "#24272C" : "#D9E4EC"
    readonly property color surface: dark ? "#292C31" : "#FFFFFF"
    readonly property color independentCard: withAlpha(dark ? "#FFFFFF" : "#FFFFFF", dark ? 0.35 : 0.94)
    readonly property color primaryContainer: dark ? "#292C31" : "#F5F6F8"
    readonly property color raised: dark ? "#292929" : "#F7F7F7"
    // Neutral QML tint above the native window backdrop. Fall back to opacity 1.
    readonly property color sidebarBase: dark ? "#292C31" : "#D9E4EC"
    // Native per-pixel alpha preserves the shared corner outline.
    readonly property real sidebarOpacity: shellOpacity
    readonly property color sidebar: withAlpha(sidebarBase, sidebarOpacity)
    readonly property color border: dark ? "#454545" : "#E5E5E8"
    readonly property color glassRim: border
    readonly property color glassGlint: dark ? "#4A4A4A" : "#FFFFFF"
    readonly property color glassShadow: dark ? "#50000000" : "#18000000"
    readonly property color pillRim: dark ? "#505050" : "#D9DBDE"
    readonly property color pillTop: dark ? "#333333" : "#E5E5E7"
    readonly property color pillBottom: pillTop
    readonly property color text: dark ? "#DDDDDD" : "#202327"
    readonly property color magenta: "#D92DF3"
    readonly property color cyan: "#06B5F4"
    readonly property color muted: dark ? "#8F949F" : "#A5A7AB"
    readonly property color accent: dark ? "#80B7FF" : "#007AFF"
    readonly property color accentIndigo: "#5856D6"
    readonly property color speedAccent: dark ? "#80B7FF" : "#007AFF"
    readonly property color primaryControl: dark ? "#2165AF" : "#007AFF"
    readonly property color navigationAccent: dark ? "#9AC8FF" : "#007AFF"
    readonly property color navigationSelected: withAlpha(dark ? "#FFFFFF" : "#000000", dark ? 0.12 : 0.05)
    readonly property color navigationPressed: dark ? "#636871" : "#B4BAC3"
    readonly property color selected: dark ? "#484848" : "#E3E4E7"
    readonly property color segmentSelected: dark ? "#62646B" : "#929294"
    readonly property color hover: dark ? "#3A3A3A" : "#E3E3E3"
    readonly property color pressed: dark ? "#505050" : "#D8D8D8"
    readonly property color controlBorder: pillRim
    readonly property color focusBorder: dark ? "#9AC8FF" : "#005BBF"
    readonly property color tableToolbar: dark ? "#333333" : "#ECECED"
    readonly property color buttonBase: dark ? "#333333" : "#E5E5E7"
    readonly property color field: dark ? "#353535" : "#F4F4F5"
    readonly property color capsuleSurface: dark ? "#38383C" : "#ECEDEF"
    readonly property color green: dark ? "#75DD91" : "#30C759"
    readonly property color statusGreen: dark ? "#75DD91" : "#00B832"
    readonly property color orange: dark ? "#F5C67D" : "#FF9229"
    readonly property color red: dark ? "#FF9A93" : "#CF3029"
    // Logical design units: Qt applies screen DPI; dp applies only user UI zoom.
    // Large surfaces follow the supplied ~12 pt visual reference, while nested
    // cards and controls have smaller corners. Circular controls use geometry.
    readonly property real windowRadius: dp(16)
    readonly property real containerRadius: dp(10)
    readonly property real radius: containerRadius
    readonly property real cardRadius: pageBranch === "A" ? dp(20) : dp(10)
    readonly property real independentCardRadius: dp(20)
    readonly property real tileRadius: dp(8)
    readonly property real tableRadius: dp(4)
    readonly property real segmentedRadius: dp(6)
    readonly property real segmentedSelectedRadius: dp(4)
    readonly property real popupRadius: dp(10)
    readonly property real secondaryRadius: popupRadius
    readonly property real controlRadius: dp(8)
    readonly property real buttonRadius: dp(6)
    readonly property real sidebarWidth: dp(200)
    readonly property real pageInset: dp(6)
    readonly property real space: dp(4)
    readonly property real cardPadding: dp(16)
    readonly property real subCardRadius: dp(10)
    readonly property real capsuleHeight: dp(22)
    readonly property real groupGap: dp(10)
    readonly property real gap: dp(16)
    readonly property real windowMinimumWidth: dp(914)
    readonly property real windowMinimumHeight: dp(672)
    readonly property real sidebarRowHeight: dp(38)
    readonly property real sidebarRowInset: dp(10)
    readonly property real sidebarRowRadius: dp(8)
    readonly property real mainContainerShadowOpacity: 0.10
    readonly property real cardShadowOpacity: 0.06
    readonly property real borderWidth: dp(1)
    readonly property real shadowOpacity: 0.05
    readonly property string fontFamily: "Microsoft YaHei UI"
    function dp(value) { return value === 0 ? 0 : Math.round(value * uiScale * 100) / 100 }
    function fontSize(value) { return Math.max(9, dp(value)) }
    function setScalePercent(percent) {
        appearanceSettings.followSystemScale = false
        appearanceSettings.savedScalePercent = Math.max(75, Math.min(150, Math.round(percent)))
    }
    function followSystem() { appearanceSettings.followSystemScale = true }
    function resetScale() { appearanceSettings.savedScalePercent = 100; appearanceSettings.followSystemScale = true }
    function withAlpha(color, alpha) { const value=Qt.tint(color, "transparent"); return Qt.rgba(value.r,value.g,value.b,alpha) }
    function roundedRadius(width, height) { return Math.min(controlRadius, width * 0.5, height * 0.5) }
    function pillRadius(height) { return Math.min(buttonRadius, height * 0.5) }
    readonly property int motion: SwirlMotion.duration
    function material(kind) {
        if (kind === "sidebar") return sidebar
        if (kind === "field") return field
        if (kind === "floating") return dark ? "#2B2B2B" : "#FFFFFF"
        if (kind === "toolbar") return canvas
        if (kind === "independent-card") return independentCard
        if (kind === "container") return primaryContainer
        return surface
    }
}
