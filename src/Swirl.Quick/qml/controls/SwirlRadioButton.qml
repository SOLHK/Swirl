import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

RadioButton {
    id: control
    padding: Theme.dp(2)
    spacing: Theme.compactGap
    implicitHeight: Math.max(Theme.controlHeight, label.implicitHeight + topPadding + bottomPadding)
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: Theme.bodySize
    font.weight: Theme.bodyFontWeight
    SwirlFontBinding { target: control; textRole: "button" }
    indicator: Rectangle {
        x: control.leftPadding
        y: (control.height - height) / 2
        width: Theme.dp(18); height: width; radius: width / 2
        color: control.checked ? Theme.primaryButton : control.hovered ? Theme.hover : Theme.field
        border.width: control.checked ? 0 : Theme.borderWidth
        border.color: Theme.controlBorder
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.switchDuration } }
        Rectangle {
            anchors.centerIn: parent; width: Theme.dp(6); height: width; radius: width / 2
            color: Theme.primaryButtonText
            opacity: control.checked ? 1 : 0
            scale: control.checked ? 1 : 0.5
            Behavior on opacity { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.releaseDuration } }
            Behavior on scale { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.switchDuration; easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent; anchors.margins: -Theme.dp(3)
            visible: control.visualFocus; color: "transparent"; radius: width / 2
            border.width: Theme.dp(2); border.color: Theme.focusBorder
        }
    }
    contentItem: SwirlText {
        id: label
        text: control.text; textRole: "button"
        font: control.font
        color: control.enabled ? Theme.text : Theme.muted
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
