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
    background: SwirlClearGlassSurface {
        Behavior on color { ColorAnimation {duration:SwirlMotion.duration} }
        radius:height/2
        color:control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet?"transparent":Theme.buttonBase
        border.width:control.activeFocus || Theme.increaseContrast?1/Screen.devicePixelRatio:0
        hovered: control.hovered; pressed: control.down
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:control.iconSize; color:control.iconColor } }
    SwirlToolTip { parent: control; visible: control.hovered && control.tooltip.length > 0 && !previewCaptureMode; text: control.tooltip }
    Accessible.name: tooltip
}
