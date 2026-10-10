import QtQuick
import QtQuick.Controls
import SwirlQuick
ComboBox {
    id:control
    implicitWidth:142; implicitHeight:38
    font.family:"Segoe UI"; font.pixelSize:13
    leftPadding:12; rightPadding:25
    contentItem:Text {
        text:control.displayText
        color:Theme.text
        font:control.font
        verticalAlignment:Text.AlignVCenter
        elide:Text.ElideRight
        leftPadding:12; rightPadding:25
    }
    indicator:Text {
        text:"⌄"; color:Theme.muted; font.pixelSize:18
        anchors.right:parent.right; anchors.rightMargin:10
        anchors.verticalCenter:parent.verticalCenter
    }
    background:Rectangle { radius:10; color:Theme.surface; border.color:Theme.border }
    delegate:ItemDelegate {
        width:control.width
        height:33
        text:String(modelData)
        highlighted:control.highlightedIndex===index
        contentItem:Text {
            text:parent.text
            color:Theme.text; font.pixelSize:13
            verticalAlignment:Text.AlignVCenter
            leftPadding:10
        }
        background:Rectangle {
            radius:7
            color:parent.highlighted?Theme.selected:"transparent"
        }
    }
    popup:Popup {
        y:control.height+4; width:control.width; padding:5
        implicitHeight:Math.min(280,contentItem.implicitHeight+10)
        background:Rectangle { color:Theme.raised; radius:11; border.color:Theme.border }
        contentItem:ListView {
            clip:true
            implicitHeight:contentHeight
            model:control.popup.visible?control.delegateModel:null
            currentIndex:control.highlightedIndex
            ScrollIndicator.vertical:ScrollIndicator {}
        }
    }
}