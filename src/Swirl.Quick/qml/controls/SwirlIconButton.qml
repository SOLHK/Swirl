import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"

SwirlMotionButton {
    id: control
    property string iconName: "plus"
    property string tooltip: ""
    property bool quiet: false
    property real iconSize: Theme.dp(16)
    property color iconColor: Theme.muted
    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    hoverEnabled: true
    background: SwirlControlSurface {
        hovered: control.hovered
        pressed: control.down
        focused: control.visualFocus
        quiet: control.quiet
        controlEnabled: control.enabled
    }
    contentItem: Item {
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        SwirlIcon { anchors.centerIn: parent; name: control.iconName; size: control.iconSize; color: control.iconColor }
    }
    SwirlToolTip {
        parent: control
        visible: (control.hovered || control.visualFocus) && control.tooltip.length > 0 && !previewCaptureMode
        text: control.tooltip
    }
    Accessible.name: tooltip
}
