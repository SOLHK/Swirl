import QtQuick
import QtQuick.Controls
import SwirlQuick
ComboBox {
    id: control
    implicitWidth:Theme.dp(146)
    implicitHeight:Theme.dp(24)
    hoverEnabled: true
    // Let ComboBox own pointer grabs, keyboard activation and popup focus.
    // Opening its popup through an overlay MouseArea bypasses that lifecycle.
    focusPolicy:Qt.StrongFocus
    font.family: Theme.fontFamily
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.dp(8); rightPadding:Theme.dp(20)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    contentItem: Text {
        text: AppState.zh(control.displayText)
        color: Theme.text
        font: control.font
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment:Text.AlignHCenter
        elide: Text.ElideRight
        leftPadding:0; rightPadding:0
    }
    indicator: Image {
        x:control.width-width-Theme.dp(6);y:(control.height-height)/2;width:Theme.dp(14);height:width
        source:"image://swirl/chevron-up-down/"+Theme.text.toString().slice(1)
    }
    background: SwirlContinuousSurface {
        radius: Math.min(height/2,Theme.dp(9))
        antialiasing: true
        color: control.pressed ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.width:Theme.dp(0.7)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.withAlpha(Theme.dark?"#A9BDD5":"#7892B1",0.24)
        Behavior on color { ColorAnimation { duration: SwirlMotion.duration } }
    }
    delegate: ItemDelegate {
        objectName:"swirlComboOption-"+index
        SwirlPressMotion{}
        width: control.popup.availableWidth
        height:Theme.dp(24)
        text: String(modelData)
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: AppState.zh(parent.text)
            color: parent.highlighted ? "white" : Theme.text; font.pixelSize:Theme.fontSize(13); font.family: Theme.fontFamily
            verticalAlignment: Text.AlignVCenter; leftPadding:Theme.dp(24)
            Image{visible:control.currentIndex===index;x:Theme.dp(3);anchors.verticalCenter:parent.verticalCenter;width:Theme.dp(14);height:width;source:"image://swirl/checkmark/"+(parent.parent.highlighted?"ffffff":Theme.text.toString().slice(1))}
        }
        background: Rectangle {
            radius: Theme.controlRadius; antialiasing:true; color: parent.highlighted ? Theme.accent : "transparent"
            Behavior on color { ColorAnimation { duration: SwirlMotion.duration } }
        }
    }
    popup: Popup {
        focus:true
        popupType:Popup.Window
        transformOrigin:Item.TopLeft
    onAboutToShow: {
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onClosed:{scale=1;opacity=1}

        y: -control.currentIndex*Theme.dp(24)-Theme.dp(3)
        x:-Theme.dp(12)
        width: control.width
        padding:Theme.dp(5)
        implicitHeight: Math.min(Theme.dp(290), contentItem.implicitHeight+Theme.dp(12))
        enter: Transition {
        enabled:!SwirlMotion.reduced
            ParallelAnimation {
                NumberAnimation { property:"opacity";to:1; duration: SwirlMotion.duration }
                NumberAnimation{property:"scale";to:1;duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic}
            }
        }
        exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} NumberAnimation {property:"scale";to:0.96;duration:SwirlMotion.duration;easing.type:Easing.InCubic} } }
        background: Rectangle {
            color:Theme.dark?Theme.field:"#EDF8FC"
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
