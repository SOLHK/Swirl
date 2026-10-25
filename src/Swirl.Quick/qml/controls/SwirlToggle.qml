import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

Switch {
    id: control
    property bool large: false
    property real motionScale: down ? SwirlMotion.pressScale : 1
    implicitWidth: Theme.dp(large ? 52 : 36)
    implicitHeight: Theme.dp(large ? 24 : 17)
    padding: 0
    hoverEnabled: true
    onPressed: SwirlMotion.noteTrigger(control)
    Behavior on motionScale { enabled: !SwirlMotion.reduced; NumberAnimation { duration: control.down ? SwirlMotion.pressDuration : SwirlMotion.releaseDuration; easing.type: Easing.OutCubic } }
    indicator: Rectangle {
        width: control.width; height: control.height
        scale: control.motionScale
        radius: height / 2
        color: control.checked ? Theme.primaryButton : Theme.toggleTrack
        opacity: control.enabled ? (control.hovered ? 0.9 : 1) : Theme.disabledOpacity
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.switchDuration } }
        Behavior on opacity { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.hoverDuration } }
        Rectangle {
            property real thumbPosition: control.checked ? 1 : 0
            width: parent.height - Theme.dp(4); height: width
            x: Theme.dp(2) + (parent.width - width - 2 * Theme.dp(2)) * thumbPosition
            y: Theme.dp(2); radius: height / 2
            color: control.checked ? Theme.primaryButtonText : Theme.controlThumb
            Behavior on thumbPosition { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.switchDuration; easing.type: Easing.OutCubic } }
            Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.switchDuration } }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -Theme.dp(3)
            visible: control.visualFocus; color: "transparent"; radius: height / 2
            border.width: Theme.dp(2); border.color: Theme.focusBorder
        }
    }
    contentItem: Item {}
}
