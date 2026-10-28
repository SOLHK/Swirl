import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

Switch {
    id: control
    property bool large: false
    property real motionScale:1-(1-SwirlMotion.pressScale)*feedback.contact
    SwirlInteractionMotion {id:feedback;hovered:control.hovered;pressed:control.down;focused:control.visualFocus;controlEnabled:control.enabled}
    implicitWidth: Theme.dp(large ? 52 : 36)
    implicitHeight: Theme.dp(large ? 24 : 17)
    padding: 0
    hoverEnabled: true
    onPressed: SwirlMotion.noteTrigger(control)
    indicator: Rectangle {
        width: control.width; height: control.height
        scale: control.motionScale
        radius: height / 2
        color: control.checked ? Theme.primaryButton : Theme.toggleTrack
        opacity:control.enabled ? 1-0.1*feedback.hover : Theme.disabledOpacity
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.switchDuration } }
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
            visible:opacity>0;opacity:feedback.focusAmount;color: "transparent"; radius: height / 2
            border.width: Theme.dp(2); border.color: Theme.focusBorder
        }
    }
    contentItem: Item {}
}
