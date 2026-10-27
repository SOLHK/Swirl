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
    readonly property color nativeTint:canvas
    readonly property real nativeTintOpacity: dark ? 0.92 : 0.94
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
    readonly property color glassFill: dark ? "#20364D" : "#EDF5F9"
    readonly property color glassTop: dark ? "#2A4661" : "#F6FAFC"
    readonly property color glassHoverTop: dark ? "#33536D" : "#FFFFFF"
    readonly property real sidebarShadowOpacity: dark ? 0.22 : 0.075
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
        property bool savedFollowSystemMotion: true
        property bool savedIncreaseContrast: false
        property int savedScalePercent: 100
        property bool followSystemScale: true
    }
    property bool followSystemScale: appearanceSettings.followSystemScale
    readonly property real uiScale: followSystemScale ? 1.0 : appearanceSettings.savedScalePercent / 100.0
    readonly property bool dark: mode === "Dark" || (mode === "System" && Qt.styleHints.colorScheme === Qt.Dark)
    // The light canvas runs continuously beneath content and the floating sidebar.
    readonly property color canvas: dark ? "#101D2D" : "#FBFCFD"
    readonly property color surface: dark ? "#182A40" : "#FFFFFF"
    readonly property color independentCard: dark ? "#1D3149" : "#FFFFFF"
    readonly property color primaryContainer: withAlpha(independentCard,transparency?0.90:1)
    readonly property color raised: dark ? "#20364D" : "#F3F7FA"
    // Neutral QML tint above the native window backdrop. Fall back to opacity 1.
    readonly property color sidebarBase:surface
    // Content materials are composed inside the system-owned HWND outline.
    // Light navigation shares the continuous window material without a second tint.
    readonly property real sidebarOpacity: dark ? (transparency && backdropActive ? 0.78 : 1.0) : 0.0
    readonly property real workspaceOpacity:transparency && (backdropActive || backdropTranslucent) ? (dark ? 0.88 : 0.84) : 1.0
    readonly property real settingsOpacity:dark?0.98:0.96
    readonly property real popupOpacity:transparency && backdropActive ? (dark?0.98:0.99) : 1.0
    readonly property color sidebar: withAlpha(sidebarBase, sidebarOpacity)
    readonly property color border: increaseContrast ? text : dark ? "#344B63" : "#DDE6ED"
    readonly property color glassRim: border
    readonly property color glassGlint: dark ? "#456783" : "#FFFFFF"
    readonly property color glassShadow: dark ? "#50000000" : "#18000000"
    readonly property color pillRim:border
    readonly property color pillTop: dark ? "#29435B" : "#EDF3F7"
    readonly property color pillBottom: pillTop
    readonly property color text: dark ? "#EDF5FC" : "#14283F"
    readonly property color brandOrange:"#F5A04D"
    readonly property color brandRed:"#D93962"
    readonly property color brandBlue:"#285DD3"
    readonly property color brandCyan:"#099DC2"
    readonly property color brandGreen:"#3CAA79"
    readonly property color magenta:brandRed
    readonly property color cyan:brandCyan
    readonly property color muted: dark ? "#B4C7D9" : "#53667A"
    readonly property color accent: dark ? "#55C8E6" : "#007EAA"
    readonly property color accentIndigo:brandBlue
    readonly property color speedAccent:accent
    readonly property color primaryControl:accent
    readonly property color navigationAccent:accent
    readonly property color navigationSelected:withAlpha(accent,dark?0.18:0.10)
    readonly property color navigationPressed:withAlpha(accent,dark?0.28:0.18)
    readonly property color selected: dark ? "#274861" : "#E2F0F6"
    readonly property color segmentSelected: dark ? "#2F506C" : "#FFFFFF"
    readonly property color hover: dark ? "#29445F" : "#E7F1F6"
    readonly property color pressed: dark ? "#33536D" : "#D7EAF2"
    readonly property color controlBorder: pillRim
    readonly property color focusBorder:accent
    readonly property color tableToolbar: dark ? "#20364D" : "#F0F5F8"
    readonly property color buttonBase: dark ? "#233B54" : "#EFF4F8"
    readonly property color primaryButton:accent
    readonly property color primaryButtonHover: dark ? "#7CD9EE" : "#006F98"
    readonly property color primaryButtonPressed: dark ? "#38B3D2" : "#005C82"
    readonly property color primaryButtonText: dark ? "#101D2D" : "#FFFFFF"
    readonly property color fieldSelection: dark ? "#315571" : "#D8EDF6"
    readonly property color toggleTrack: dark ? "#425D73" : "#D4E1EA"
    readonly property color controlThumb: "#FFFFFF"
    readonly property color successSurface: dark ? "#30483C" : "#EAF5EE"
    readonly property color successText: dark ? "#A6EDC6" : "#21613D"
    readonly property color warningSurface: dark ? "#4B3B2B" : "#FFF3E2"
    readonly property color warningText: dark ? "#FFE0AD" : "#805019"
    readonly property color dangerSurface: dark ? "#4A3035" : "#FBECEF"
    readonly property real disabledOpacity: 0.45
    readonly property color field: dark ? "#1B3048" : "#F2F6F9"
    readonly property color floatingSurface:surface
    readonly property color capsuleSurface: dark ? "#233B54" : "#EAF2F6"
    readonly property color green: dark ? "#75DD91" : "#30C759"
    readonly property color statusGreen: dark ? "#75DD91" : "#00B832"
    readonly property color orange: dark ? "#F5C67D" : "#FF9229"
    readonly property color red: dark ? "#FF9A93" : "#CF3029"
    // Logical point-style design sizes, independent of content zoom.
    // Qt maps these logical pixels to each screen's device pixel ratio.
    // Apple image reference normalized to the existing 672-unit shell height.
    // These are corner extents for the shared 2.5-power contour, not circle radii.
    enum ShellMetrics { WindowCornerRadius = 22, SidebarCornerRadius = 20 }
    readonly property real windowRadius: Theme.WindowCornerRadius
    readonly property real sidebarRadius: Theme.SidebarCornerRadius
    // Cards at the same hierarchy share a token, including the settings grid.
    readonly property real cardRadius: dp(14)
    readonly property real containerRadius: cardRadius
    readonly property real radius: containerRadius
    readonly property real independentCardRadius: cardRadius
    readonly property real tileRadius: dp(12)
    readonly property real tableRadius: dp(10)
    readonly property real segmentedRadius: dp(10)
    readonly property real segmentedSelectedRadius: dp(8)
    readonly property real menuRadius: dp(12)
    readonly property real popupRadius: dp(20)
    readonly property real secondaryRadius: popupRadius
    readonly property real controlRadius: dp(10)
    readonly property real buttonRadius: controlRadius
    readonly property real sidebarWidth: dp(208)
    readonly property real sidebarCollapsedWidth:dp(76)
    readonly property real shellInset:dp(12)
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
    readonly property real sidebarRowRadius:dp(12)
    readonly property real mainContainerShadowOpacity: 0.10
    readonly property real cardShadowOpacity: 0.06
    readonly property real borderWidth: dp(1)
    readonly property real shadowOpacity: 0.05
    readonly property string fontFamily: fontManager.currentFamily
    readonly property string codeFontFamily: "Cascadia Code"
    readonly property int bodyFontWeight: Font.Normal
    readonly property int pageTitleSize: fontSize(26)
    readonly property int sectionTitleSize: fontSize(18)
    readonly property int bodySize: fontSize(14)
    readonly property int captionSize: fontSize(12)
    readonly property int buttonSize: fontSize(13)
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
        if (kind === "floating") return withAlpha(floatingSurface,popupOpacity)
        if (kind === "toolbar") return canvas
        if (kind === "independent-card") return independentCard
        if (kind === "container") return primaryContainer
        return surface
    }
}
