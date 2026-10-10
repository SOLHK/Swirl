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
    // Paint the chevron as vectors instead of depending on a rare font glyph.
    // This renders consistently on Chinese, English and headless Windows kits.
    indicator:Canvas {
        id:chevron
        x:control.width-width-12
        y:(control.height-height)/2
        width:13; height:13
        onPaint:{
            var ctx=getContext("2d")
            ctx.reset()
            ctx.strokeStyle=Theme.muted
            ctx.lineWidth=1.7
            ctx.lineCap="round"
            ctx.lineJoin="round"
            ctx.beginPath()
            ctx.moveTo(2.5,5)
            ctx.lineTo(6.5,9)
            ctx.lineTo(10.5,5)
            ctx.stroke()
        }
        Connections {
            target:Theme
            function onMutedChanged(){chevron.requestPaint()}
        }
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
        enter:Transition { NumberAnimation { property:"opacity"; from:0; to:1; duration:Theme.motion } }
        exit:Transition { NumberAnimation { property:"opacity"; from:1; to:0; duration:Theme.motion } }
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