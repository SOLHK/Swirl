import QtQuick
import QtQuick.Controls
import SwirlQuick
Menu {
    id:menu
    property var items:["Details","Copy","Export"]
    padding:5
    background:Rectangle { color:Theme.raised; radius:11; border.color:Theme.border }
    Repeater {
        model:menu.items
        MenuItem {
            text:modelData
            height:34
            contentItem:Text {
                text:parent.text; color:Theme.text
                font.pixelSize:13; leftPadding:12
                verticalAlignment:Text.AlignVCenter
            }
            background:Rectangle { radius:7; color:parent.highlighted?Theme.hover:"transparent" }
            onTriggered:AppState.notice(text)
        }
    }
}