import QtQuick
import SwirlQuick
// Common top-level surface. DWM clips background, content and shadow together.
// No wallpaper image, desktop capture, QML blur or whole-window texture mask.
Rectangle {
    id: surface
    required property var targetWindow
    property var composition: backdrop
    readonly property bool nativeMaterial: composition.active && Theme.transparency
    readonly property real cornerRadius: composition.nativeCorners ? 0 : Theme.windowRadius
    anchors.fill: parent
    color: Theme.withAlpha(Theme.nativeTint, nativeMaterial ? Theme.nativeTintOpacity : 1)
    // Native DWM corner clipping is applied AFTER every QML child is composed.
    radius: 0
}
