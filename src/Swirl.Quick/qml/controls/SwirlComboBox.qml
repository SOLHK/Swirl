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
    SwirlToolTip {parent:control;visible:(control.hovered||control.activeFocus)&&control.contentItem.truncated&&!popupLayer.visible;text:AppState.zh(control.displayText);delay:600}
    indicator: Image {
        x:Math.round(control.width-width-Theme.dp(6));y:Math.round((control.height-height)/2);width:Theme.dp(14);height:width
        source:"image://swirl/chevron-up-down/"+Theme.text.toString().slice(1)
    }
    background: SwirlClearGlassSurface {
        hovered:control.hovered;pressed:control.pressed;focused:control.activeFocus
        radius: height/2
        antialiasing: true
        color: control.pressed ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.width:control.activeFocus || Theme.increaseContrast?1/Screen.devicePixelRatio:0
        border.color: control.activeFocus ? Theme.focusBorder : Theme.controlBorder
        Behavior on color { ColorAnimation { duration: Math.min(100,SwirlMotion.duration) } }
    }
    delegate: ItemDelegate {
        id:option
        required property int index
        objectName:"swirlComboOption-"+index
        SwirlPressMotion{}
        width: ListView.view.width
        implicitHeight:Math.max(Theme.controlHeight,contentItem.implicitHeight+topPadding+bottomPadding)
        height:implicitHeight
        leftPadding:Theme.dp(5);rightPadding:Theme.dp(5)
        topPadding:Theme.dp(4);bottomPadding:Theme.dp(4)
        text: control.textAt(index)
        highlighted: control.highlightedIndex === index
        contentItem: SwirlText {renderType:Text.NativeRendering;
            textRole:"list"
            text: AppState.zh(option.text)
            color: option.highlighted ? "white" : Theme.text; font.pixelSize:Theme.fontSize(13); font.family: Theme.fontFamily
            verticalAlignment: Text.AlignVCenter; leftPadding:Theme.dp(24);rightPadding:Theme.dp(5);elide:Text.ElideRight
            Image{visible:control.currentIndex===option.index;x:Theme.dp(3);anchors.verticalCenter:parent.verticalCenter;width:Theme.dp(14);height:width;sourceSize:Qt.size(width,height);source:"image://swirl/checkmark/"+(option.highlighted?"ffffff":Theme.text.toString().slice(1))}
        }
        background: Rectangle {
            radius: height/2; antialiasing:true; color: option.highlighted ? Theme.accent : "transparent"
            Behavior on color { ColorAnimation { duration: Math.min(100,SwirlMotion.duration) } }
        }
    }
    popup: Popup {
        id:popupLayer
        function requestDismiss(){close()}
        parent:control.Overlay.overlay
        property point anchorPoint:Qt.point(0,0)
        readonly property real edgeMargin:Theme.dp(8)
        readonly property real below:parent?Math.max(0,parent.height-anchorPoint.y-control.height-Theme.dp(4)-edgeMargin):0
        readonly property real above:Math.max(0,anchorPoint.y-Theme.dp(4)-edgeMargin)
        readonly property real desiredHeight:Math.min(Theme.dp(290),contentItem.implicitHeight+topPadding+bottomPadding)
        readonly property bool opensAbove:below<desiredHeight && above>below
        focus:true
        popupType:Popup.Item
        closePolicy:Popup.CloseOnEscape | Popup.CloseOnPressOutside
        transformOrigin:Item.TopLeft
    onAboutToShow: {
        anchorPoint=control.mapToItem(parent,0,0)
        dismissals.push(popupLayer,control.Window.window)
        Qt.callLater(function(){popupList.positionViewAtIndex(control.currentIndex,ListView.Contain)})
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else opacity=0
    }
    onClosed:{dismissals.pop(popupLayer);scale=1;opacity=1}

        y:opensAbove?anchorPoint.y-height-Theme.dp(4):anchorPoint.y+control.height+Theme.dp(4)
        x:parent?Math.max(edgeMargin,Math.min(anchorPoint.x,parent.width-width-edgeMargin)):0
        width:parent?Math.min(control.width,parent.width-2*edgeMargin):control.width
        height:Math.min(desiredHeight,Math.max(above,below))
        padding:Theme.dp(5)
        margins:edgeMargin
        enter: Transition {
        enabled:!SwirlMotion.reduced
            ParallelAnimation {
                NumberAnimation { property:"opacity";to:1; duration: Math.min(100,SwirlMotion.duration) }
            }
        }
        exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} } }
        background: SwirlClearGlassSurface { radius:Theme.popupRadius; color:Theme.material("floating") }
        contentItem: ListView { pixelAligned: true;
            id:popupList
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            highlightMoveDuration:0
            boundsBehavior:Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}
        }
    }
}
