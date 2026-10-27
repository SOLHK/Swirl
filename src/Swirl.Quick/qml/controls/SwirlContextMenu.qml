pragma ComponentBehavior: Bound
import QtQuick
import QtQml.Models
import QtQuick.Controls.Basic
import SwirlQuick
Menu {
    id: contextMenu
    popupType:Popup.Item
    objectName:"swirlContextMenu"
    property bool presentationReady:false
    Component.onCompleted:presentationReady=true
    Component.onDestruction:presentationReady=false
    function requestDismiss(){close()}
    function showAt(anchor,x,y){
        if(motionPolicy.reversePopupExit(contextMenu))return
        if(anchor)popup(anchor,x||0,y||0)
        else popup()
    }
    property var items: ["查看详情", "复制", "导出"]
    property string payload: ""
    property bool handleItemsInternally:true
    implicitWidth:Math.ceil(Math.max(Theme.dp(150),items.reduce((width,label)=>Math.max(width,itemMetrics.advanceWidth(AppState.zh(String(label)))+Theme.dp(24)+leftPadding+rightPadding),0)))
    FontMetrics {id:itemMetrics;font.family:Theme.fontFamily;font.pixelSize:Theme.buttonSize;font.weight:Theme.bodyFontWeight}
    signal itemTriggered(int index)
    padding:Theme.dp(6)
    transformOrigin:Item.TopLeft
    SwirlPopupMotion {id:reveal;popup:contextMenu;enterDuration:SwirlMotion.menuEnterDuration;leaveDuration:SwirlMotion.menuExitDuration}
    readonly property alias popupMotion:reveal
    // Popup owns x/y placement (including screen clamping); translate its
    // visual content and background without changing pointer/keyboard grabs.
    Binding {target:contextMenu.presentationReady?contextMenu.contentItem:null;property:"transform";value:[contentTravel];when:contextMenu.presentationReady;restoreMode:Binding.RestoreBindingOrValue}
    Translate {id:contentTravel;x:reveal.xOffset;y:reveal.yOffset}
    opacity:reveal.alpha
    onAboutToShow: {
        dismissals.push(contextMenu,parent?parent.Window.window:null)
        reveal.prepare(Qt.point(-SwirlMotion.popupDistance*0.25,-SwirlMotion.popupDistance*0.5))
    }
    onClosed:{dismissals.pop(contextMenu);reveal.reset()}
    enter:reveal.enterTransition
    exit:reveal.exitTransition
    background: Rectangle {
        transform:Translate{x:reveal.xOffset;y:reveal.yOffset}
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
