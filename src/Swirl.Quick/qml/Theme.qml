pragma Singleton
import QtQuick
import QtCore
QtObject {
    property alias mode: appearanceStore.savedMode
    property alias transparency: appearanceStore.savedTransparency
    property bool backdropActive: false
    property bool backdropTranslucent: false
    property bool windowActive:true
    // Windows supplies blur and luminosity. These are only the Swirl overlay.
    readonly property color nativeTint: dark ? "#292C31" : "#F8F8F8"
    readonly property real nativeTintOpacity: dark ? 0.90 : 0.96
    // Exact contours use restrained live alpha when DWM Acrylic cannot be
    // clipped smoothly. Keep background text subdued without masking glyphs.
    readonly property real alphaTintOpacity: dark ? 0.94 : 0.95
    // Retained for the opt-in synthetic blur benchmark, never desktop sampling.
    property real glassBlurStrength: 0.85
    property int glassQuality: 1
    readonly property bool effectsSupported: gpuEffectsSupported
    property alias reduceMotion: appearanceStore.savedReduceMotion
    property alias followSystemMotion: appearanceStore.savedFollowSystemMotion
    property alias increaseContrast: appearanceStore.savedIncreaseContrast
    readonly property color interactionHover: withAlpha(dark ? "#FFFFFF" : "#000000", dark ? 0.10 : 0.045)
    readonly property color interactionPressed: withAlpha(dark ? "#FFFFFF" : "#000000", dark ? 0.16 : 0.09)
    readonly property color glassFill: dark ? "#3B3D40" : "#E4E5E7"
    readonly property color glassTop: dark ? "#45474A" : "#EFF0F1"
    readonly property color glassHoverTop: dark ? "#51565D" : "#FFFFFF"
    readonly property real sidebarShadowOpacity: dark ? 0.24 : 0.13
    readonly property color separator: increaseContrast ? text : withAlpha(dark ? "#FFFFFF" : "#18202B", dark ? 0.12 : 0.10)
    property string pageBranch: "B"
    // Qt already maps QML logical pixels to each screen's DPI. Automatic mode
    // therefore uses the native 100% logical design scale; manual scaling is a
    // separate, persistent preference and never overrides Windows DPI.
    property Settings appearanceSettings: Settings {
        id: appearanceStore
        category: "Appearance"
        property string savedMode: "System"
        property bool savedTransparency: true
        property bool savedReduceMotion: false
        property bool savedFollowSystemMotion: false
        property bool savedIncreaseContrast: false
        property int savedScalePercent: 100
        property bool followSystemScale: true
    }
    property bool followSystemScale: appearanceSettings.followSystemScale
    readonly property real uiScale: followSystemScale ? 1.0 : appearanceSettings.savedScalePercent / 100.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    // The light canvas runs continuously beneath content and the floating sidebar.
    readonly property color canvas: dark ? "#24272C" : "#F8F8F8"
    readonly property color surface: dark ? "#292C31" : "#FFFFFF"
    readonly property color independentCard: dark ? "#30343A" : "#FFFFFF"
    readonly property color primaryContainer: withAlpha(dark ? "#2A3546" : "#F2F7FD",transparency?0.78:1)
    readonly property color raised: dark ? "#292929" : "#F7F7F7"
    // Neutral QML tint above the native window backdrop. Fall back to opacity 1.
    readonly property color sidebarBase: dark ? "#292C31" : "#F8F8F8"
    // Content materials are composed inside the system-owned HWND outline.
    readonly property real sidebarOpacity: transparency && backdropActive ? (dark ? 0.78 : 0.72) : 1.0
    readonly property real workspaceOpacity:transparency && (backdropActive || backdropTranslucent) ? (dark ? 0.88 : 0.84) : 1.0
    readonly property real settingsOpacity:dark?0.98:0.96
    readonly property real popupOpacity:transparency && backdropActive ? (dark?0.98:0.99) : 1.0
    readonly property color sidebar: withAlpha(sidebarBase, sidebarOpacity)
    readonly property color border: increaseContrast ? text : dark ? "#46505C" : "#D9DEE5"
    readonly property color glassRim: border
    readonly property color glassGlint: dark ? "#4A4A4A" : "#FFFFFF"
    readonly property color glassShadow: dark ? "#50000000" : "#18000000"
    readonly property color pillRim: dark ? "#4D5C73" : "#CCD8EB"
    readonly property color pillTop: dark ? "#333333" : "#E5E5E7"
    readonly property color pillBottom: pillTop
    readonly property color text: dark ? "#F0F2F5" : "#202327"
    readonly property color magenta: "#D92DF3"
    readonly property color cyan: "#06B5F4"
    readonly property color muted: dark ? "#B8C4D4" : "#465A70"
    readonly property color accent: dark ? "#80B7FF" : "#0066CC"
    readonly property color accentIndigo: "#5856D6"
    readonly property color speedAccent: dark ? "#80B7FF" : "#007AFF"
    readonly property color primaryControl: dark ? "#2165AF" : "#0068D9"
    readonly property color navigationAccent: dark ? "#9AC8FF" : "#007AFF"
    readonly property color navigationSelected: withAlpha(dark ? "#FFFFFF" : "#000000", dark ? 0.12 : 0.05)
    readonly property color navigationPressed: dark ? "#636871" : "#B4BAC3"
    readonly property color selected: dark ? "#484848" : "#E3E4E7"
    readonly property color segmentSelected: dark ? "#64666A" : "#FFFFFF"
    readonly property color hover: dark ? "#484848" : "#E3E3E5"
    readonly property color pressed: dark ? "#555555" : "#D5D5D8"
    readonly property color controlBorder: pillRim
    readonly property color focusBorder: dark ? "#9AC8FF" : "#005BBF"
    readonly property color tableToolbar: dark ? "#333333" : "#ECECED"
    readonly property color buttonBase: navigationSelected
    readonly property color field: dark ? "#2C3A50" : "#F2F5FC"
    readonly property color capsuleSurface: dark ? "#38383C" : "#ECEDEF"
    readonly property color green: dark ? "#75DD91" : "#30C759"
    readonly property color statusGreen: dark ? "#75DD91" : "#00B832"
    readonly property color orange: dark ? "#F5C67D" : "#FF9229"
    readonly property color red: dark ? "#FF9A93" : "#CF3029"
    // Shell and floating sidebar share one contour, independent of content zoom.
    // Qt maps these logical pixels to each screen's device pixel ratio.
    readonly property real windowRadius: 16
    // Cards at the same hierarchy share a token, including the settings grid.
    readonly property real cardRadius: dp(20)
    readonly property real containerRadius: cardRadius
    readonly property real radius: containerRadius
    readonly property real independentCardRadius: cardRadius
    readonly property real tileRadius: dp(12)
    readonly property real tableRadius: dp(10)
    readonly property real segmentedRadius: dp(10)
    readonly property real segmentedSelectedRadius: dp(8)
    readonly property real popupRadius: dp(20)
    readonly property real secondaryRadius: popupRadius
    readonly property real controlRadius: dp(10)
    readonly property real buttonRadius: controlRadius
    readonly property real sidebarWidth: dp(168)
    readonly property real pageInset: dp(6)
    readonly property real space: dp(4)
    readonly property real pagePadding: dp(24)
    readonly property real sectionGap: dp(20)
    readonly property real compactGap: dp(8)
    readonly property real cardPadding: dp(20)
    readonly property real controlHeight: dp(32)
    readonly property real controlPadding: dp(12)
    readonly property real tableHeaderHeight: dp(36)
    readonly property real tableRowHeight: dp(40)
    readonly property real statusHeight: dp(26)
    readonly property real subCardRadius: dp(12)
    readonly property real capsuleHeight: dp(22)
    readonly property real groupGap: dp(10)
    readonly property real gap: dp(16)
    readonly property real windowMinimumWidth: dp(760)
    readonly property real windowMinimumHeight: dp(672)
    readonly property real windowDefaultWidth: dp(914)
    readonly property real windowDefaultHeight: dp(672)
    readonly property real sidebarRowHeight: dp(40)
    readonly property real sidebarRowInset: dp(10)
    readonly property real sidebarRowRadius: sidebarRowHeight / 2
    readonly property real mainContainerShadowOpacity: 0.10
    readonly property real cardShadowOpacity: 0.06
    readonly property real borderWidth: dp(1)
    readonly property real shadowOpacity: 0.05
    readonly property string fontFamily: fontManager.currentFamily
    readonly property int bodyFontWeight: Font.Normal
    readonly property int fontRevision: fontManager.configurationRevision
    function variableAxesFor(font, logicalDpi, dpr, role) {
        const revision = fontRevision // establish a binding dependency for same-family axis updates
        return fontManager.resolvedAxesForFont(font, logicalDpi, dpr, role)
    }
    function previewVariableAxesFor(font, logicalDpi, dpr, role) {
        const revision = fontRevision
        const family = fontManager.previewFamily
        const automatic = fontManager.previewAutomatic
        const values = fontManager.previewValues
        return fontManager.previewResolvedAxesForFont(font, logicalDpi, dpr, role)
    }
    function fittedText(font, text, logicalDpi, dpr, role, width, previousWidth) {
        return fontManager.fittedText(font, text, logicalDpi, dpr, role, width, previousWidth)
    }
    function dp(value) { return value === 0 ? 0 : Math.round(value * uiScale) }
    function fontSize(value) { return Math.max(12, Math.round(dp(value))) }
    function setScalePercent(percent) {
        appearanceSettings.followSystemScale = false
        appearanceSettings.savedScalePercent = Math.max(75, Math.min(150, Math.round(percent)))
    }
    function followSystem() { appearanceSettings.followSystemScale = true }
    function resetScale() { appearanceSettings.savedScalePercent = 100; appearanceSettings.followSystemScale = true }
    function withAlpha(color, alpha) { const value=Qt.tint(color, "transparent"); return Qt.rgba(value.r,value.g,value.b,alpha) }
    function roundedRadius(width, height) { return Math.min(controlRadius, width * 0.5, height * 0.5) }
    function pillRadius(height) { return height * 0.5 }
    readonly property int motion: SwirlMotion.duration
    function material(kind) {
        if (kind === "sidebar") return sidebar
        if (kind === "field") return field
        if (kind === "floating") return withAlpha(dark ? "#2B2B2B" : "#FFFFFF",popupOpacity)
        if (kind === "toolbar") return canvas
        if (kind === "independent-card") return independentCard
        if (kind === "container") return primaryContainer
        return surface
    }
}
