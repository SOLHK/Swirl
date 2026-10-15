import QtQuick
import QtQuick.Controls
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
    background: SwirlPillSurface {
        Behavior on color { ColorAnimation {duration:SwirlMotion.duration} }
        radius:Theme.controlRadius
        color:control.quiet?"transparent":Theme.buttonBase
        gradient:null
        border.width:control.quiet?0:Theme.borderWidth
        hovered: control.hovered; pressed: control.down
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:control.iconSize; color:control.iconColor } }
    ToolTip.visible: hovered && tooltip.length > 0 && !previewCaptureMode
    ToolTip.text: tooltip
    Accessible.name: tooltip
}
