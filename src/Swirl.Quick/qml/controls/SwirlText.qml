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
    property bool fitWidth: textRole === "button" || textRole === "navigation"
        || textRole === "pageTitle" || textRole === "largeTitle" || textRole === "label"
    // Non-Layout content must opt in only when its control owns the available
    // width independently of this Text's compressed implicit size.
    property bool fitInFixedWidth: false
    readonly property bool inTextLayout: parent && (parent instanceof RowLayout
        || parent instanceof ColumnLayout || parent instanceof GridLayout)
    readonly property bool widthFitting: fitWidth && wrapMode === Text.NoWrap && renderType === Text.NativeRendering
        && (inTextLayout || fitInFixedWidth) && elide !== Text.ElideNone
        && (textFormat === Text.PlainText || (textFormat === Text.AutoText && text.indexOf("<") < 0))
        && !/[\n\r\u2028\u2029\u009c]/.test(text)
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.fontSize(13)
    font.hintingPreference: Font.PreferFullHinting
    SwirlFontBinding {
        id: fontBinding; target: control; textRole: control.textRole; fitWidth: control.widthFitting
        availableWidth: Math.max(0, control.width - control.leftPadding - control.rightPadding)
    }
    // Layouts always see the natural advance. Compressing the rendered label
    // therefore cannot shrink its parent's implicit size and feed back into fit.
    Layout.preferredWidth: control.widthFitting && fontBinding.naturalWidth > 0
        ? fontBinding.naturalWidth + control.leftPadding + control.rightPadding : -1
    renderType: Text.NativeRendering
}
