import QtQuick
import SwirlQuick

// Plain Qt Quick Text does not inherit live application-font changes. Keep the
// selected family and native hinting explicit for every foreground text item.
Text {
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.fontSize(13)
    font.hintingPreference: Font.PreferFullHinting
    // Updating a subproperty synchronously from the same font value causes a
    // value-type binding loop. Defer the axis write until family/weight settle.
    Binding on font.variableAxes { delayed:true; value:Theme.variableAxesFor(font.family,font.weight) }
    renderType: Text.NativeRendering
}
