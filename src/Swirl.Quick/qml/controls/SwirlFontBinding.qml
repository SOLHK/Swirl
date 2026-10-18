import QtQuick
import SwirlQuick

// Only the final axis map is assigned. Existing family, weight, size, spacing,
// and fallback choices remain on the owner. No text/position/animation clock is
// a dependency; a changing font size still receives its correct optical size.
Binding {
    id: binding
    property string textRole: "body"
    property bool preview: false
    property var fontWindow: target ? target.Window.window : null
    readonly property real logicalDpi: fontWindow ? fontWindow.FontDisplayContext.logicalDpi : 96
    readonly property real devicePixelRatio: fontWindow ? fontWindow.FontDisplayContext.devicePixelRatio : 1
    property var resolvedAxes: ({})
    property bool refreshQueued: false
    property: "font.variableAxes"
    delayed: true
    value: resolvedAxes

    // All QFont subproperties share fontChanged. Reading target.font directly
    // from Binding.value would create a loop when variableAxes writes it back.
    // Queue an input snapshot, then publish only a changed result. Qt.callLater
    // coalesces changes in the current event turn; it does not use a frame clock.
    function scheduleRefresh() {
        if (!when || !target || refreshQueued)
            return
        refreshQueued = true
        Qt.callLater(refreshAxes)
    }

    function refreshAxes() {
        refreshQueued = false
        if (!when || !target)
            return
        // Pass QFont itself. QML's pixelSize/pointSize getters both synthesize a
        // positive size; QFont retains the unit actually set by the component.
        const next = preview
            ? Theme.previewVariableAxesFor(target.font, logicalDpi, devicePixelRatio, textRole)
            : Theme.variableAxesFor(target.font, logicalDpi, devicePixelRatio, textRole)
        const keys = Object.keys(next)
        if (keys.length === Object.keys(resolvedAxes).length
                && keys.every(function(key) { return resolvedAxes[key] === next[key] }))
            return
        resolvedAxes = next
    }

    property Connections fontChanges: Connections {
        target: binding.target
        function onFontChanged() { binding.scheduleRefresh() }
    }
    property Connections configurationChanges: Connections {
        target: fontManager
        function onConfigurationChanged() { binding.scheduleRefresh() }
    }
    property Connections previewChanges: Connections {
        target: binding.preview ? fontManager : null
        function onPreviewFamilyChanged() { binding.scheduleRefresh() }
        function onPreviewValuesChanged() { binding.scheduleRefresh() }
        function onPreviewAxesChanged() { binding.scheduleRefresh() }
        function onPreviewAutomaticChanged() { binding.scheduleRefresh() }
    }
    onTargetChanged: scheduleRefresh()
    onWhenChanged: scheduleRefresh()
    onTextRoleChanged: scheduleRefresh()
    onPreviewChanged: scheduleRefresh()
    onLogicalDpiChanged: scheduleRefresh()
    onDevicePixelRatioChanged: scheduleRefresh()
    onFontWindowChanged: scheduleRefresh()
    Component.onCompleted: scheduleRefresh()
}
