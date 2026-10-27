pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick

// Only the final axis map is assigned. Existing family, weight, size, spacing,
// and fallback choices remain on the owner. No text/position/animation clock is
// a dependency; a changing font size still receives its correct optical size.
// Keep the scheduler outside Binding's deferred-property parser when controls
// are incubated asynchronously. The inner Binding only publishes the axis map.
QtObject {
    id: binding
    property QtObject target: null
    property bool when: true
    property string textRole: "body"
    property bool preview: false
    property bool fitWidth: false
    property real naturalWidth: 0
    property var fontWindow: target && target.Window ? target.Window.window : null
    readonly property real logicalDpi: fontWindow ? fontWindow.FontDisplayContext.logicalDpi : 96
    readonly property real devicePixelRatio: fontWindow ? fontWindow.FontDisplayContext.devicePixelRatio : 1
    property var resolvedAxes: ({})
    property bool refreshQueued: false
    // Async incubation can assign inputs before this object's methods are ready.
    // Activate publication and signal scheduling only after component completion.
    property bool initialized: false
    // Preview inputs already coalesce in Qt.callLater below. Publish that final
    // snapshot immediately, so polish does not see the previous axis tuple while
    // a second queued Binding update waits. Preserve normal text/layout timing.
    property Binding axesBinding: Binding {
        target: binding.target
        property: "font.variableAxes"
        when: binding.initialized && binding.when && binding.target !== null
        delayed: !binding.preview
        value: binding.resolvedAxes
    }

    // All QFont subproperties share fontChanged. Reading target.font directly
    // from Binding.value would create a loop when variableAxes writes it back.
    // Queue an input snapshot, then publish only a changed result. Qt.callLater
    // coalesces changes in the current event turn; it does not use a frame clock.
    function scheduleRefresh() {
        if (!initialized || !when || !target || refreshQueued)
            return
        refreshQueued = true
        Qt.callLater(refreshAxes)
    }

    function refreshAxes() {
        refreshQueued = false
        if (!initialized || !when || !target)
            return
        // Pass QFont itself. QML's pixelSize/pointSize getters both synthesize a
        // positive size; QFont retains the unit actually set by the component.
        let next = preview
            ? Theme.previewVariableAxesFor(target.font, logicalDpi, devicePixelRatio, textRole)
            : Theme.variableAxesFor(target.font, logicalDpi, devicePixelRatio, textRole)
        if (fitWidth && !preview) {
            const fit = Theme.fittedText(target.font, target.text, logicalDpi,
                devicePixelRatio, textRole, target.width, resolvedAxes.wdth)
            naturalWidth = fit.naturalWidth
            next = fit.axes
        } else {
            naturalWidth = 0
        }
        const keys = Object.keys(next)
        if (keys.length === Object.keys(resolvedAxes).length
                && keys.every(function(key) { return resolvedAxes[key] === next[key] }))
            return
        resolvedAxes = next
    }

    property Connections fontChanges: Connections {
        enabled: binding.initialized
        target: binding.initialized ? binding.target : null
        function onFontChanged() { binding.scheduleRefresh() }
    }
    property Connections layoutChanges: Connections {
        enabled: binding.initialized
        target: binding.initialized && binding.fitWidth ? binding.target : null
        function onWidthChanged() { binding.scheduleRefresh() }
        function onTextChanged() { binding.scheduleRefresh() }
    }
    property Connections configurationChanges: Connections {
        enabled: binding.initialized
        target: binding.initialized ? fontManager : null
        function onConfigurationChanged() { binding.scheduleRefresh() }
    }
    property Connections previewChanges: Connections {
        enabled: binding.initialized
        target: binding.initialized && binding.preview ? fontManager : null
        function onPreviewFamilyChanged() { binding.scheduleRefresh() }
        function onPreviewValuesChanged() { binding.scheduleRefresh() }
        function onPreviewAxesChanged() { binding.scheduleRefresh() }
        function onPreviewAutomaticChanged() { binding.scheduleRefresh() }
    }
    onTargetChanged: if (initialized) scheduleRefresh()
    onWhenChanged: if (initialized) scheduleRefresh()
    onTextRoleChanged: if (initialized) scheduleRefresh()
    onPreviewChanged: if (initialized) scheduleRefresh()
    onFitWidthChanged: if (initialized) scheduleRefresh()
    onLogicalDpiChanged: if (initialized) scheduleRefresh()
    onDevicePixelRatioChanged: if (initialized) scheduleRefresh()
    onFontWindowChanged: if (initialized && fontWindow) binding.scheduleRefresh()
    Component.onCompleted: { initialized = true; scheduleRefresh() }
    Component.onDestruction: initialized = false
}
