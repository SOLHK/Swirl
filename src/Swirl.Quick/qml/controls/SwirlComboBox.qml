import QtQuick
import QtQuick.Controls
import SwirlQuick
ComboBox {
    id: control
    implicitWidth:Theme.dp(146)
    implicitHeight:Theme.controlHeight
    hoverEnabled: true
    // Let ComboBox own pointer grabs, keyboard activation and popup focus.
    // Opening its popup through an overlay MouseArea bypasses that lifecycle.
    opacity:enabled?1:0.45
    focusPolicy:Qt.StrongFocus
    font.family: Theme.fontFamily
    font.hintingPreference:Font.PreferFullHinting
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.controlPadding; rightPadding:Theme.dp(28)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    contentItem: SwirlText {renderType:Text.NativeRendering;
        text: AppState.zh(control.displayText)
        color: Theme.text
        font: control.font
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment:Text.AlignLeft
        elide: Text.ElideRight
        leftPadding:0; rightPadding:0
    }
    indicator: Image {
        x:control.width-width-Theme.dp(6);y:(control.height-height)/2;width:Theme.dp(14);height:width
        source:"image://swirl/chevron-up-down/"+Theme.text.toString().slice(1)
    }
    background: SwirlContinuousSurface {
        radius: Theme.controlRadius
        antialiasing: true
        color: control.pressed ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.width:control.activeFocus?Theme.dp(2):Theme.borderWidth
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
        focus:true
        popupType:Popup.Window
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
        background: Rectangle {
            color:Theme.surface
            radius: Theme.popupRadius; antialiasing:true
            border.width:Theme.dp(1); border.color: Theme.pillRim
        }
        contentItem: ListView {
                    add: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";to:1;duration:SwirlMotion.duration} }
                    remove: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} }
                    move: Transition {enabled:!SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:!SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
}
