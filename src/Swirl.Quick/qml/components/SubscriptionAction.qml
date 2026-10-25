pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"

SwirlMotionButton {
    id: control
    property string iconName: ""
    property bool solid: false
    property bool selected: false
    property bool danger: false
    property bool spinning: false
    property string tooltip: ""
    property bool tooltipEnabled: true
    readonly property bool iconOnly: text.length === 0
    implicitWidth: iconOnly ? Theme.dp(44) : contents.implicitWidth + Theme.dp(24)
    implicitHeight: Theme.controlHeight
    hoverEnabled: true
    padding: Theme.dp(8)
    Accessible.name: text
    background: SwirlControlSurface {
        anchors.centerIn: parent
        width: control.iconOnly ? Theme.controlHeight : parent.width
        height: control.iconOnly ? Theme.controlHeight : parent.height
        hovered: control.hovered
        pressed: control.down
        focused: control.visualFocus
        selected: control.selected
        primary: control.solid
        quiet: !control.solid && !control.selected
        controlEnabled: control.enabled
    }
    contentItem: Item {
        implicitWidth: contents.implicitWidth
        implicitHeight: contents.implicitHeight
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        RowLayout {
            id: contents
            anchors.centerIn: parent
            spacing: Theme.dp(7)
            SwirlIcon {
                visible: control.iconName.length > 0
                name: control.iconName; size: Theme.dp(16)
                color: control.solid ? Theme.primaryButtonText : control.danger ? Theme.red : Theme.text
                Accessible.ignored: true
                RotationAnimator on rotation { running: control.spinning && control.visible && control.Window.window && control.Window.window.visible && control.Window.window.visibility !== Window.Minimized && !SwirlMotion.reduced; from: 0; to: 360; duration: 1000; loops: Animation.Infinite }
            }
            SwirlText {
                visible: !control.iconOnly
                text: control.text; textRole: "button"
                color: control.solid ? Theme.primaryButtonText : control.danger ? Theme.red : Theme.text
                font.pixelSize: Theme.buttonSize
                font.weight: control.solid || control.selected ? Font.DemiBold : Font.Medium
            }
        }
    }
    SwirlToolTip {
        parent: control
        visible: control.tooltipEnabled && control.enabled && (control.hovered || control.visualFocus) && control.tooltip.length > 0
        text: control.tooltip
    }
}
