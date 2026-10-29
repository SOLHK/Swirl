import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

TextField {
    id: control
    property bool invalid: false
    implicitHeight: Theme.controlHeight
    leftPadding: Theme.controlPadding
    rightPadding: Theme.controlPadding
    topPadding: Theme.dp(5)
    bottomPadding: Theme.dp(5)
    hoverEnabled: true
    selectByMouse: true
    color: enabled ? Theme.text : Theme.muted
    selectionColor: Theme.fieldSelection
    selectedTextColor: Theme.text
    placeholderTextColor: Theme.muted
    font.family: Theme.fontFamily
    font.contextFontMerging: true
    font.preferTypoLineMetrics: true
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.bodySize
    font.hintingPreference: Font.PreferFullHinting
    renderType: TextInput.NativeRendering
    SwirlFontBinding { target: control; textRole: "input" }
    background: SwirlControlSurface {
        field: true
        hovered: control.hovered
        focused: control.activeFocus
        controlEnabled: control.enabled
        invalid: control.invalid
    }
}
