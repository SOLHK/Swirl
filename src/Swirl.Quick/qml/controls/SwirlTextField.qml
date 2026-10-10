import QtQuick
import QtQuick.Controls
import SwirlQuick
TextField {
    id:control
    implicitHeight:39
    leftPadding:12; rightPadding:12
    color:Theme.text
    selectionColor:Theme.accent
    placeholderTextColor:Theme.muted
    font.family:"Segoe UI"
    font.pixelSize:13
    background:Rectangle {
        radius:10
        color:Theme.field
        border.color:control.activeFocus?Theme.accent:Theme.border
    }
}