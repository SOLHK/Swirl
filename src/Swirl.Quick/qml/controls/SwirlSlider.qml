import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

Slider {
    id: control
    implicitWidth: horizontal ? Theme.dp(180) : Theme.controlHeight
    implicitHeight: horizontal ? Theme.controlHeight : Theme.dp(180)
    padding: Theme.dp(6)
    hoverEnabled: true
    background: Rectangle {
        x: control.horizontal ? control.leftPadding : control.leftPadding + (control.availableWidth - width) / 2
        y: control.horizontal ? control.topPadding + (control.availableHeight - height) / 2 : control.topPadding
        width: control.horizontal ? control.availableWidth : Theme.dp(4)
        height: control.horizontal ? Theme.dp(4) : control.availableHeight
        radius: Theme.dp(2)
        color: Theme.toggleTrack
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        Rectangle {
            x: 0
            y: control.horizontal ? 0 : control.visualPosition * parent.height
            width: control.horizontal ? control.visualPosition * parent.width : parent.width
            height: control.horizontal ? parent.height : (1 - control.visualPosition) * parent.height
            radius: parent.radius
            color: Theme.text
        }
    }
    handle: Rectangle {
        x: control.horizontal ? control.leftPadding + control.visualPosition * (control.availableWidth - width) : control.leftPadding + (control.availableWidth - width) / 2
        y: control.horizontal ? control.topPadding + (control.availableHeight - height) / 2 : control.topPadding + control.visualPosition * (control.availableHeight - height)
        implicitWidth: Theme.dp(20)
        implicitHeight: Theme.dp(20)
        radius: width / 2
        color: Theme.controlThumb
        border.width: Theme.borderWidth
        border.color: control.pressed ? Theme.text : Theme.controlBorder
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        scale: control.pressed ? 1.08 : 1
        Behavior on scale { enabled: !SwirlMotion.reduced; NumberAnimation { duration: control.pressed ? SwirlMotion.pressDuration : SwirlMotion.releaseDuration; easing.type: Easing.OutCubic } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -Theme.dp(3)
            visible: control.visualFocus; color: "transparent"
            radius: width / 2; border.width: Theme.dp(2); border.color: Theme.focusBorder
        }
    }
}
