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
    implicitWidth:Theme.dp(46); implicitHeight:Theme.dp(46)
    hoverEnabled: true
    background: SwirlPillSurface {
        Behavior on color { ColorAnimation {duration:SwirlMotion.duration} }
        radius:Math.min(width,height)/2
        color:control.quiet?"transparent":Theme.buttonBase
        gradient:null
        border.width:control.quiet?0:Theme.borderWidth
        hovered: control.hovered; pressed: control.down
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:control.iconSize; color:Theme.muted } }
    ToolTip.visible: hovered && tooltip.length > 0 && !previewCaptureMode
    ToolTip.text: tooltip
    Accessible.name: tooltip
}
