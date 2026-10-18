import QtQuick
import QtQuick.Controls
import SwirlQuick
Menu {
    id: menu
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    padding:Theme.dp(6)
    transformOrigin:Item.TopLeft
    onAboutToShow: {
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onClosed:{scale=1;opacity=1}
    enter:Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation {property:"opacity";to:1;duration:SwirlMotion.duration}
            SwirlSpring {property:"scale";to:1}
        }
    }
    exit:Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration}
            NumberAnimation {property:"scale";to:0.97;duration:SwirlMotion.duration;easing.type:Easing.InCubic}
        }
    }
    background: Rectangle {
        color: Theme.material("floating")
        radius:Theme.popupRadius; antialiasing:true
        border.width:Theme.dp(1)
        border.color: Theme.glassRim
    }
    Repeater {
        model: menu.items
        MenuItem {
            SwirlPressMotion{}
            text: AppState.zh(String(modelData))
            height:Theme.dp(36)
            contentItem: SwirlText {
                textRole:"list"
                text: parent.text; color: Theme.text
                font.pixelSize:Theme.fontSize(12); font.family: Theme.fontFamily
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
