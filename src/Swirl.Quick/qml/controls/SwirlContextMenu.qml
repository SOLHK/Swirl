import QtQuick
import QtQuick.Controls
import SwirlQuick
Menu {
    id: menu
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    padding: 6
    background: Rectangle {
        color: Theme.material("floating")
        radius: 15
        border.width: 1
        border.color: Theme.glassRim
    }
    Repeater {
        model: menu.items
        MenuItem {
            text: AppState.zh(String(modelData))
            height: 36
            contentItem: Text {
                text: parent.text; color: Theme.text
                font.pixelSize: 12; font.family: "Microsoft YaHei UI"
                leftPadding: 12; verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { radius: 10; color: parent.highlighted ? Theme.selected : "transparent" }
            onTriggered: {
                if (text === "复制" || text === "Copy") {
                    demoProvider.copyText(menu.payload)
                    AppState.toast = "已复制演示表格内容"
                } else {
                    AppState.notice(text)
                }
            }
        }
    }
}
