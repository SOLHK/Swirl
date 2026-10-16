import QtQuick
import SwirlQuick
// Common top-level surface. The HWND contour clips background and content
// together, using either Swirl's exact region or the system corner preset.
// No wallpaper image, desktop capture, QML blur or whole-window texture mask.
Rectangle {
    id: surface
    required property var targetWindow
    property var composition: backdrop
    property real sidebarWidth:0
    readonly property color sidebarTint:sidebarWidth>0 && composition.sidebarBlur && Theme.transparency ? Theme.withAlpha(Theme.nativeTint,Theme.dark?0.58:0.60) : color
    readonly property bool nativeMaterial: composition.active && Theme.transparency
    readonly property real cornerRadius: composition.nativeCorners ? 0 : Theme.windowRadius
    anchors.fill: parent
    color: Theme.withAlpha(Theme.nativeTint, nativeMaterial ? Theme.nativeTintOpacity : composition.translucent && Theme.transparency ? Theme.alphaTintOpacity : 1)
    gradient:Gradient {
        orientation:Gradient.Horizontal
        GradientStop {position:0;color:surface.sidebarTint}
        GradientStop {position:Math.min(1,surface.sidebarWidth/Math.max(1,surface.width));color:surface.sidebarTint}
        GradientStop {position:Math.min(1,(surface.sidebarWidth+Theme.dp(48))/Math.max(1,surface.width));color:surface.color}
        GradientStop {position:1;color:surface.color}
    }
    // Native HWND clipping is applied AFTER every QML child is composed.
    radius: 0
}
