import QtQuick
import QtQuick.Controls
import SwirlQuick
Menu {
    id: menu
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    padding:Theme.dp(6)
    background: Rectangle {
        color: Theme.material("floating")
        radius:Theme.popupRadius; antialiasing:true
        border.width:Theme.dp(1)
        border.color: Theme.glassRim
    }
    Repeater {
        model: menu.items
        MenuItem {
            text: AppState.zh(String(modelData))
            height:Theme.dp(36)
            contentItem: Text {
                text: parent.text; color: Theme.text
                font.pixelSize:Theme.fontSize(12); font.family: "Microsoft YaHei UI"
                leftPadding:Theme.dp(12); verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { radius: Theme.roundedRadius(width,height); color: parent.highlighted ? Theme.selected : "transparent" }
            onTriggered: {
                if (text === "复制" || text === "Copy") {
                    systemProvider.copyText(menu.payload)
                    AppState.toast = "已复制表格内容"
                } else {
                    AppState.notice(text)
                }
            }
        }
    }
}
