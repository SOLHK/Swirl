import QtQuick
import SwirlQuick
Window {
    id: shell
    required property var composition
    default property alias body: bodyItem.data
    readonly property real titleBarHeight: titleBar.height
    property bool swirlDismissibleWindow: true
    property real swirlWindowRadius: Theme.windowRadius
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
}
