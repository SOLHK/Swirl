import QtQuick
import QtQuick.Controls
import SwirlQuick

// Shared policy for editors, selectable diagnostics and licence text. Pages may
// retain an explicit monospace family; its own metadata is used by the policy.
TextArea {
    id: control
    property string textRole: "input"
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.hintingPreference: Font.PreferFullHinting
    renderType: TextEdit.NativeRendering
    SwirlFontBinding { target: control; textRole: control.textRole }
}
