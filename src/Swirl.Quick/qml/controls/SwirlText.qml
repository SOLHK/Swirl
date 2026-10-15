import QtQuick
import SwirlQuick

// Plain Qt Quick Text does not inherit live application-font changes. Keep the
// selected family and native hinting explicit for every foreground text item.
Text {
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontSize(13)
    font.hintingPreference: Font.PreferFullHinting
    renderType: Text.NativeRendering
}
