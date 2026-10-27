import QtQuick
import SwirlQuick
// Common top-level surface. The HWND contour clips background and content
// together, using either Swirl's exact region or the system corner preset.
// No wallpaper image, desktop capture, QML blur or whole-window texture mask.
Rectangle {
    id: surface
    required property var targetWindow
    property var composition: backdrop
    readonly property bool nativeMaterial: (composition.active || composition.micaActive || composition.blurActive) && Theme.transparency
    readonly property real cornerRadius: composition.nativeCorners ? 0 : Theme.windowRadius
    readonly property real tintOpacity: nativeMaterial ? Theme.nativeTintOpacity : 1
    readonly property real materialInset: targetWindow.visibility === Window.Maximized || targetWindow.visibility === Window.FullScreen
        ? 1 / Screen.devicePixelRatio
        : Math.max(1, Math.ceil(Theme.windowRadius * Screen.devicePixelRatio * (1 - Math.pow(0.5, 0.4)) + 1)) / Screen.devicePixelRatio
    anchors.fill: parent
    color: Theme.withAlpha(Theme.nativeTint, tintOpacity)
    border.width: nativeMaterial ? materialInset : 0
    border.color: Theme.canvas
    // Native HWND clipping is applied AFTER every QML child is composed.
    radius: 0
}
