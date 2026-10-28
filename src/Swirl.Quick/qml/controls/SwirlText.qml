import QtQuick
import QtQuick.Layouts
import SwirlQuick

// Plain Qt Quick Text does not inherit live application-font changes. Keep the
// selected family and native hinting explicit for every foreground text item.
Text {
    id: control
    property string textRole: "body"
    // Only constrained, eliding single-line labels participate. Body copy,
    // editors, rich text and numeric data retain their natural typography.
    property bool fitWidth: textRole === "button" || textRole === "navigation" || textRole === "pageTitle"
    readonly property bool widthFitting: fitWidth && wrapMode === Text.NoWrap
        && parent && (parent instanceof RowLayout || parent instanceof ColumnLayout || parent instanceof GridLayout)
        && elide !== Text.ElideNone && textFormat !== Text.RichText && textFormat !== Text.StyledText
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.fontSize(13)
    font.hintingPreference: Font.PreferFullHinting
    readonly property SwirlFontBinding ownedFontBinding: SwirlFontBinding { id:fontBinding; target: control; textRole: control.textRole; fitWidth: control.widthFitting }
    // Layouts always see the natural advance. Compressing the rendered label
    // therefore cannot shrink its parent's implicit size and feed back into fit.
    Layout.preferredWidth: control.widthFitting && fontBinding.naturalWidth > 0 ? fontBinding.naturalWidth : -1
    renderType: Text.NativeRendering
}
