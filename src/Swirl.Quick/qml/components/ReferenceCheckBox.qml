import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../controls"

CheckBox {
    id: control
    padding: 0
    spacing: Theme.compactGap
    implicitHeight: Math.max(Theme.dp(22), label.implicitHeight)
    hoverEnabled: true
    indicator: Rectangle {
        x: 0; y: (control.height - height) / 2
        width: Theme.dp(16); height: width; radius: Theme.dp(4)
        color: control.checked ? Theme.primaryButton : control.hovered ? Theme.hover : Theme.buttonBase
        border.width: control.checked ? 0 : Theme.borderWidth
        border.color: Theme.controlBorder
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        scale: control.down ? SwirlMotion.pressScale : 1
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.switchDuration } }
        Behavior on scale { enabled: !SwirlMotion.reduced; NumberAnimation { duration: control.down ? SwirlMotion.pressDuration : SwirlMotion.releaseDuration; easing.type: Easing.OutCubic } }
        SwirlIcon {
            anchors.centerIn: parent; size: Theme.dp(12)
            name: "checkmark"
            color: Theme.primaryButtonText
            opacity: control.checkState === Qt.Checked ? 1 : 0
            scale: opacity > 0 ? 1 : 0.65
            Behavior on opacity { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.releaseDuration } }
            Behavior on scale { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.switchDuration; easing.type: Easing.OutCubic } }
            Accessible.ignored: true
        }
        Rectangle {
            anchors.centerIn: parent
            width: Theme.dp(8); height: Theme.dp(2); radius: Theme.dp(1)
            color: Theme.primaryButtonText
            visible: control.checkState === Qt.PartiallyChecked
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -Theme.dp(3)
            visible: control.visualFocus; color: "transparent"; radius: Theme.dp(6)
            border.width: Theme.dp(2); border.color: Theme.focusBorder
        }
    }
    contentItem: SwirlText {
        id: label
        leftPadding: control.indicator.width + control.spacing
        text: control.text; textRole: "button"; font.pixelSize: Theme.bodySize
        color: control.enabled ? Theme.text : Theme.muted
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
