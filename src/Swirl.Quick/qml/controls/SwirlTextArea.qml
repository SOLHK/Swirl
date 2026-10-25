import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

TextArea {
    id: control
    property string textRole: "input"
    property bool invalid: false
    padding: Theme.controlPadding
    hoverEnabled: true
    selectByMouse: true
    color: enabled ? Theme.text : Theme.muted
    placeholderTextColor: Theme.muted
    selectionColor: Theme.fieldSelection
    selectedTextColor: Theme.text
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.bodySize
    font.hintingPreference: Font.PreferFullHinting
    renderType: TextEdit.NativeRendering
    SwirlFontBinding { target: control; textRole: control.textRole }
    background: SwirlControlSurface {
        field: true
        hovered: control.hovered
        focused: control.activeFocus
        controlEnabled: control.enabled
        invalid: control.invalid
    }
}
