import QtQuick
import QtQml.Models
import QtQuick.Controls
import SwirlQuick
Menu {
    id: menu
    objectName:"swirlContextMenu"
    function requestDismiss(){close()}
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    property bool handleItemsInternally:true
    implicitWidth:Math.ceil(Math.max(Theme.dp(150),items.reduce((width,label)=>Math.max(width,itemMetrics.advanceWidth(AppState.zh(String(label)))+Theme.dp(24)+leftPadding+rightPadding),0)))
    FontMetrics {id:itemMetrics;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12);font.weight:Theme.bodyFontWeight}
    signal itemTriggered(int index)
    padding:Theme.dp(6)
    transformOrigin:Item.TopLeft
    onAboutToShow: {
        dismissals.push(menu,parent?parent.Window.window:null)
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onClosed:{dismissals.pop(menu);scale=1;opacity=1}
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
    Instantiator {
        model: menu.items
        onObjectAdded:(index,object)=>menu.insertItem(index,object)
        onObjectRemoved:(index,object)=>menu.removeItem(object)
        delegate:MenuItem {
            required property int index
            required property var modelData
            objectName:"swirlContextOption-"+index
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
                menu.itemTriggered(index)
                if(!menu.handleItemsInternally)return
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
