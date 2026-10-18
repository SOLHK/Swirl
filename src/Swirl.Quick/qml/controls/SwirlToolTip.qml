import QtQuick
import QtQuick.Controls
import SwirlQuick

// Preserve the selected Qt Quick Controls style's popup, padding and transitions.
// A local ToolTip owns its font; the shared attached ToolTip cannot carry the
// correct size and window context independently for every originating item.
ToolTip {
    id: control
    font.family: Theme.fontFamily
    font.hintingPreference: Font.PreferFullHinting
    SwirlFontBinding {
        target: control
        when: control.visible
        textRole: "auxiliary"
        // Do not instantiate Qt's deferred tooltip content for every table cell.
        fontWindow: control.visible && control.contentItem ? control.contentItem.Window.window : null
    }
    Binding { target: control.visible ? control.contentItem : null; property: "renderType"; value: Text.NativeRendering; when: control.visible }
}
