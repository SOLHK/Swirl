import QtQuick
import QtQuick.Controls
import SwirlQuick
TextField {
    renderType:TextInput.NativeRendering
    font.hintingPreference:Font.PreferFullHinting
    SwirlFontBinding { target: control; textRole: "input" }
    id: control
    implicitHeight:Theme.controlHeight
    leftPadding:Theme.controlPadding; rightPadding:Theme.controlPadding
    color: enabled ? Theme.text : Theme.muted
    selectionColor: Theme.accent
    selectedTextColor: "white"
    placeholderTextColor: Theme.muted
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize:Theme.fontSize(13)
    background: Rectangle {
        radius: Theme.controlRadius
        antialiasing: true
        color:control.hovered&&!control.activeFocus?Theme.hover:Theme.dark?Theme.field:Theme.surface
        border.width: Theme.dp(control.activeFocus ? 2 : 1)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.width {NumberAnimation{duration:SwirlMotion.hoverDuration}}
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
}
