import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
Button {
    id: control
    property string iconName: "plus"
    property string tooltip: ""
    implicitWidth: 46; implicitHeight: 46
    hoverEnabled: true
    background: SwirlPillSurface {
        hovered: control.hovered; pressed: control.down
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Item { SwirlIcon { anchors.centerIn:parent; name:control.iconName; size:24; color:Theme.muted } }
    ToolTip.visible: hovered && tooltip.length > 0
    ToolTip.text: tooltip
    Accessible.name: tooltip
}
