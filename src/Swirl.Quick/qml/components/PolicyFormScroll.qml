import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../controls"

ScrollView {
    id:form
    property Item ownerItem:null
    property Item formBody:null
    readonly property var ownerWindow:ownerItem?ownerItem.Window.window:null
    readonly property Flickable viewport:contentItem as Flickable
    contentWidth:availableWidth
    contentHeight:formBody?formBody.implicitHeight:availableHeight
    clip:true
    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
    ScrollBar.vertical:SwirlScrollBar {}
    function revealFocus() {
        if(!visible||!formBody||!viewport||!ownerWindow)return
        const field=ownerWindow.activeFocusItem;if(!field)return
        let ancestor=field;while(ancestor&&ancestor!==formBody)ancestor=ancestor.parent
        if(!ancestor)return
        const top=field.mapToItem(formBody,0,0).y,bottom=top+field.height,margin=Theme.dp(6)
        if(top<viewport.contentY+margin)viewport.contentY=Math.max(0,top-margin)
        else if(bottom>viewport.contentY+viewport.height-margin)viewport.contentY=Math.min(Math.max(0,contentHeight-viewport.height),bottom-viewport.height+margin)
    }
    onVisibleChanged:if(visible)Qt.callLater(function(){if(form.viewport)form.viewport.contentY=0;form.revealFocus()})
    onHeightChanged:Qt.callLater(revealFocus)
    Connections {target:form.ownerWindow;function onActiveFocusItemChanged(){Qt.callLater(form.revealFocus)}}
}
