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
        elevated:false
        Behavior on color { ColorAnimation {duration:SwirlMotion.duration} }
        radius:Theme.controlRadius
        color:control.down?Theme.interactionPressed:control.hovered?Theme.interactionHover:control.quiet?"transparent":Theme.glassFill
        glassEnabled:Theme.transparency && !Theme.increaseContrast && !control.quiet
        border.width:control.activeFocus || Theme.increaseContrast?1/Screen.devicePixelRatio:0
        hovered: control.hovered; pressed: control.down
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:control.iconSize; color:control.iconColor } }
    SwirlToolTip { parent: control; visible: control.hovered && control.tooltip.length > 0 && !previewCaptureMode; text: control.tooltip }
    Accessible.name: tooltip
}
