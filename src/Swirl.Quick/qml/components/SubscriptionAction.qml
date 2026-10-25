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
    implicitHeight: Theme.dp(34)
    hoverEnabled: true
    padding: Theme.dp(8)
    Accessible.name: text
    background: Rectangle {
        anchors.centerIn: parent
        width: control.iconOnly ? Theme.dp(32) : parent.width
        height: control.iconOnly ? Theme.dp(32) : parent.height
        radius: Theme.dp(9)
        color: control.down ? Theme.pressed : control.hovered ? Theme.hover : control.selected ? Theme.segmentSelected : control.solid ? Theme.buttonBase : "transparent"
        border.width: control.visualFocus || Theme.increaseContrast ? Theme.borderWidth : 0
        border.color: Theme.text
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
    contentItem: Item {
        implicitWidth: contents.implicitWidth
        implicitHeight: contents.implicitHeight
        opacity: control.enabled ? 1 : 0.4
        RowLayout {
            id: contents
            anchors.centerIn: parent
            spacing: Theme.dp(7)
            SwirlIcon {
                visible: control.iconName.length > 0
                name: control.iconName; size: Theme.dp(16)
                color: control.danger ? Theme.red : Theme.text
                Accessible.ignored: true
                RotationAnimator on rotation { running: control.spinning && control.visible && !SwirlMotion.reduced; from: 0; to: 360; duration: 1000; loops: Animation.Infinite }
            }
            SwirlText {
                visible: !control.iconOnly
                text: control.text; textRole: "button"
                color: control.danger ? Theme.red : Theme.text
                font.pixelSize: Theme.fontSize(12)
                font.weight: control.solid || control.selected ? Font.DemiBold : Font.Medium
            }
        }
    }
    ToolTip {
        parent: control
        visible: control.tooltipEnabled && control.enabled && (control.hovered || control.visualFocus) && control.tooltip.length > 0
        delay: 600
        padding: Theme.dp(8)
        contentItem: SwirlText { text: control.tooltip; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
        background: Rectangle { color: Theme.material("floating"); radius: Theme.dp(8); border.width: Theme.borderWidth; border.color: Theme.border }
    }
}
