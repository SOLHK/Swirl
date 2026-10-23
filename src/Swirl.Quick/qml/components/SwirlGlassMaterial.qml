import QtQuick
import SwirlQuick
// Common top-level surface. The HWND contour clips background and content
// together, using either Swirl's exact region or the system corner preset.
// No wallpaper image, desktop capture, QML blur or whole-window texture mask.
Rectangle {
    id: surface
    required property var targetWindow
    property var composition: backdrop
    property real sidebarGlassWidth: 0
    readonly property bool nativeMaterial: composition.active && Theme.transparency
    readonly property real cornerRadius: composition.nativeCorners ? 0 : Theme.windowRadius
    readonly property real tintOpacity: composition.blurActive && Theme.transparency ? (Theme.dark?0.80:0.82) : nativeMaterial ? Theme.nativeTintOpacity : composition.translucent && Theme.transparency ? Theme.alphaTintOpacity : 1
    readonly property real sidebarTintOpacity: sidebarGlassWidth>0 && Theme.transparency ? tintOpacity*(composition.blurActive || nativeMaterial ? 0.48 : composition.translucent ? 0.68 : 1) : tintOpacity
    anchors.fill: parent
    color: Theme.withAlpha(Theme.nativeTint, sidebarTintOpacity)
    Rectangle {
        visible: surface.sidebarTintOpacity < surface.tintOpacity
        x: Math.min(surface.width, surface.sidebarGlassWidth)
        width: surface.width-x; height: surface.height
        color: Theme.withAlpha(Theme.nativeTint, (surface.tintOpacity-surface.sidebarTintOpacity)/Math.max(0.001,1-surface.sidebarTintOpacity))
    }
    // Native HWND clipping is applied AFTER every QML child is composed.
    radius: 0
}
