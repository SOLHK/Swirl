import QtQuick
import SwirlQuick

// Plain Qt Quick Text does not inherit live application-font changes. Keep the
// selected family and native hinting explicit for every foreground text item.
Text {
    id: control
    property string textRole: "body"
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.fontSize(13)
    font.hintingPreference: Font.PreferFullHinting
    SwirlFontBinding { target: control; textRole: control.textRole }
    renderType: Text.NativeRendering
}
