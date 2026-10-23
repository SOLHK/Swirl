import QtQuick
import SwirlQuick
Window {
    id: shell
    required property var composition
    default property alias body: bodyItem.data
    readonly property alias bodySurface: bodyItem
    readonly property real titleBarHeight: titleBar.height
    property bool swirlDismissibleWindow: true
    property real swirlWindowRadius: Theme.windowRadius
    property bool swirlExactWindowRadius: true
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    minimumWidth: Math.min(Theme.dp(760), Screen.desktopAvailableWidth)
    minimumHeight: Math.min(Theme.dp(560), Screen.desktopAvailableHeight)
    onVisibleChanged: if (visible) composition.apply(shell, Theme.transparency, Theme.dark)
    Connections {
        target: Theme
        function onTransparencyChanged() { shell.composition.apply(shell, Theme.transparency, Theme.dark) }
        function onDarkChanged() { shell.composition.apply(shell, Theme.transparency, Theme.dark) }
        function onUiScaleChanged() { shell.composition.apply(shell, Theme.transparency, Theme.dark) }
    }
    SwirlGlassMaterial { targetWindow: shell; composition: shell.composition }
    SwirlWindowTitleBar { id: titleBar; anchors.left:parent.left; anchors.right:parent.right; targetWindow:shell }
    Item { id:bodyItem; anchors.left:parent.left;anchors.right:parent.right;anchors.top:titleBar.bottom;anchors.bottom:parent.bottom;clip:true }
    SwirlShellOutline {
        parent:shell.contentItem;anchors.fill:parent;z:998
        visible:shell.composition.exactCorners
        radius:shell.visibility===Window.Maximized || shell.visibility===Window.FullScreen?0:Theme.windowRadius
        strokeWidth:shell.visibility===Window.Maximized || shell.visibility===Window.FullScreen?0:1/Screen.devicePixelRatio
        strokeColor:Theme.dark?Qt.rgba(1,1,1,shell.active?0.14:0.10):Qt.rgba(0,0,0,shell.active?0.055:0.04)
    }
    WindowEdge {parent:shell.contentItem;anchors.fill:parent;z:10000;radius:shell.visibility===Window.Maximized || shell.visibility===Window.FullScreen?0:Theme.windowRadius}
}
