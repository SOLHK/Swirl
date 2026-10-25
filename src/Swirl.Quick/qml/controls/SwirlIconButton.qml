import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"
SwirlMotionButton {
    id: control
    property string iconName: "plus"
    property string tooltip: ""
    property bool quiet:false
    property real iconSize:Theme.dp(16)
    property color iconColor:Theme.muted
    implicitWidth:Theme.controlHeight; implicitHeight:Theme.controlHeight
    hoverEnabled: true
    background: Rectangle {
        Behavior on color { enabled:!SwirlMotion.reduced; ColorAnimation {duration:SwirlMotion.hoverDuration} }
        radius:Math.min(Theme.dp(9),height/2)
        color:control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet?"transparent":Theme.buttonBase
        border.width:control.visualFocus || Theme.increaseContrast?Theme.borderWidth:0
        border.color: Theme.text
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:control.iconSize; color:control.iconColor } }
    SwirlToolTip {
        id: hint
        parent: control
        visible: (control.hovered || control.visualFocus) && control.tooltip.length > 0 && !previewCaptureMode
        text: control.tooltip
    }
    Accessible.name: tooltip
}
