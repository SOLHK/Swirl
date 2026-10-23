import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"
ComboBox {
    id: control
    implicitWidth:Theme.dp(146)
    implicitHeight:Theme.controlHeight
    hoverEnabled: true
    // Let ComboBox own pointer grabs, keyboard activation and popup focus.
    // Opening its popup through an overlay MouseArea bypasses that lifecycle.
    focusPolicy:Qt.StrongFocus
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.hintingPreference:Font.PreferFullHinting
    SwirlFontBinding { target: control; textRole: "input" }
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.controlPadding; rightPadding:Theme.dp(28)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    contentItem: SwirlText {renderType:Text.NativeRendering;
        textRole:"input"
        text: AppState.zh(control.displayText)
        color: control.enabled ? Theme.text : Theme.muted
        font.family: control.font.family
        font.pixelSize: control.font.pixelSize
        font.weight: control.font.weight
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment:Text.AlignLeft
        elide: Text.ElideRight
        leftPadding:0; rightPadding:0
    }
    indicator: Image {
        x:Math.round(control.width-width-Theme.dp(6));y:Math.round((control.height-height)/2);width:Theme.dp(14);height:width
        source:"image://swirl/chevron-up-down/"+Theme.text.toString().slice(1)
    }
    background: SwirlClearGlassSurface {
        elevated:false
        hovered:control.hovered;pressed:control.pressed;focused:control.activeFocus
        radius: Theme.controlRadius
        antialiasing: true
        color: control.pressed ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.width:control.activeFocus || Theme.increaseContrast?1/Screen.devicePixelRatio:0
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Math.min(100,SwirlMotion.duration) } }
    }
    delegate: ItemDelegate {
        objectName:"swirlComboOption-"+index
        SwirlPressMotion{}
        width: control.popup.availableWidth
        height:Theme.controlHeight
        text: String(modelData)
        highlighted: control.highlightedIndex === index
        contentItem: SwirlText {renderType:Text.NativeRendering;
            textRole:"list"
            text: AppState.zh(parent.text)
            color: parent.highlighted ? "white" : Theme.text; font.pixelSize:Theme.fontSize(13); font.family: Theme.fontFamily
            verticalAlignment: Text.AlignVCenter; leftPadding:Theme.dp(24)
            Image{visible:control.currentIndex===index;x:Theme.dp(3);anchors.verticalCenter:parent.verticalCenter;width:Theme.dp(14);height:width;source:"image://swirl/checkmark/"+(parent.parent.highlighted?"ffffff":Theme.text.toString().slice(1))}
        }
        background: Rectangle {
            radius: Theme.controlRadius; antialiasing:true; color: parent.highlighted ? Theme.accent : "transparent"
            Behavior on color { ColorAnimation { duration: Math.min(100,SwirlMotion.duration) } }
        }
    }
    popup: Popup {
        parent:control
        focus:true
        popupType:Popup.Item
        closePolicy:Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        transformOrigin:Item.TopLeft
    onAboutToShow: {
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else opacity=0
    }
    onClosed:{scale=1;opacity=1}

        y: control.height+Theme.dp(4)
        x:0
        width: control.width
        padding:Theme.dp(5)
        implicitHeight: Math.min(Theme.dp(290), contentItem.implicitHeight+Theme.dp(12))
        enter: Transition {
        enabled:!SwirlMotion.reduced
            ParallelAnimation {
                NumberAnimation { property:"opacity";to:1; duration: Math.min(100,SwirlMotion.duration) }
            }
        }
        exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} } }
        background: SwirlClearGlassSurface { radius:Theme.popupRadius; elevated:false }
        contentItem: ListView { pixelAligned: true;
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
}
