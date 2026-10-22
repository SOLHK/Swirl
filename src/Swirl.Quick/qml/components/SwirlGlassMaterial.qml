import QtQuick
import SwirlQuick
// Common top-level surface. The HWND contour clips background and content
// together, using either Swirl's exact region or the system corner preset.
// No wallpaper image, desktop capture, QML blur or whole-window texture mask.
Rectangle {
    id: surface
    required property var targetWindow
    property var composition: backdrop
    readonly property bool nativeMaterial: composition.active && Theme.transparency
    readonly property real cornerRadius: composition.nativeCorners ? 0 : Theme.windowRadius
    anchors.fill: parent
    color: Theme.withAlpha(Theme.nativeTint, composition.blurActive && Theme.transparency ? (Theme.dark?0.80:0.82) : nativeMaterial ? Theme.nativeTintOpacity : composition.translucent && Theme.transparency ? Theme.alphaTintOpacity : 1)
    // Native HWND clipping is applied AFTER every QML child is composed.
    radius: 0
}
