pragma ComponentBehavior: Bound
import QtQuick
import QtQml.Models
import QtQuick.Controls.Basic
import SwirlQuick
Menu {
    id: contextMenu
    objectName:"swirlContextMenu"
    function requestDismiss(){close()}
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    property bool handleItemsInternally:true
    implicitWidth:Math.ceil(Math.max(Theme.dp(150),items.reduce((width,label)=>Math.max(width,itemMetrics.advanceWidth(AppState.zh(String(label)))+Theme.dp(24)+leftPadding+rightPadding),0)))
    FontMetrics {id:itemMetrics;font.family:Theme.fontFamily;font.pixelSize:Theme.buttonSize;font.weight:Theme.bodyFontWeight}
    signal itemTriggered(int index)
    padding:Theme.dp(6)
    transformOrigin:Item.TopLeft
    onAboutToShow: {
        dismissals.push(contextMenu,parent?parent.Window.window:null)
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.98;opacity=0}
    }
    onClosed:{dismissals.pop(contextMenu);scale=1;opacity=1}
    enter:Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation {property:"opacity";to:1;duration:SwirlMotion.menuEnterDuration;easing.type:Easing.OutCubic}
            NumberAnimation {property:"scale";to:1;duration:SwirlMotion.menuEnterDuration;easing.type:Easing.OutCubic}
        }
    }
    exit:Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.menuExitDuration;easing.type:Easing.InCubic}
            NumberAnimation {property:"scale";to:0.98;duration:SwirlMotion.menuExitDuration;easing.type:Easing.InCubic}
        }
    }
    background: Rectangle {
        color: Theme.material("floating")
        radius:Theme.menuRadius; antialiasing:true
        border.width:Theme.dp(1)
        border.color: Theme.glassRim
    }
    Instantiator {
        model: contextMenu.items
        onObjectAdded:(index,object)=>contextMenu.insertItem(index,object)
        onObjectRemoved:(index,object)=>contextMenu.removeItem(object)
        delegate:MenuItem {
            id: option
            required property int index
            required property var modelData
            objectName:"swirlContextOption-"+index
            SwirlPressMotion{}
            text: AppState.zh(String(modelData))
            height:Theme.dp(36)
            contentItem: SwirlText {
                textRole:"list"
                text: option.text; color: Theme.text
                font.pixelSize:Theme.buttonSize; font.family: Theme.fontFamily
                leftPadding:Theme.dp(12); verticalAlignment: Text.AlignVCenter
            }
            background: SwirlControlSurface {
                quiet: true
                selected: option.highlighted
                focused: option.visualFocus
                controlEnabled: option.enabled
            }
            onTriggered: {
                contextMenu.itemTriggered(index)
                if(!contextMenu.handleItemsInternally)return
                if (text === "复制" || text === "Copy") {
                    systemProvider.copyText(contextMenu.payload)
                    AppState.toast = "已复制表格内容"
                } else {
                    AppState.notice(text)
                }
            }
        }
    }
}
