pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"
ComboBox {
    id: control
    implicitWidth:Theme.dp(146)
    implicitHeight:Theme.controlHeight
    hoverEnabled: true
    SwirlPressMotion {pressed:control.pressed}
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
        id: valueLabel
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
    SwirlToolTip {
        id: hint
        parent:control;visible:(control.hovered||control.visualFocus)&&valueLabel.truncated&&!popupLayer.visible;text:AppState.zh(control.displayText);delay:600
    }
    indicator: SwirlIcon {
        x:Math.round(control.width-width-Theme.dp(6));y:Math.round((control.height-height)/2)
        name:"chevron-right";size:Theme.dp(14);rotation:control.popup.visible?270:90;color:Theme.muted
        Behavior on rotation {enabled:!SwirlMotion.reduced;NumberAnimation{duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}}
    }
    background: SwirlControlSurface {
        hovered: control.hovered
        pressed: control.pressed
        focused: control.visualFocus
        controlEnabled: control.enabled
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
            color: Theme.text; font.pixelSize:Theme.fontSize(13); font.family: Theme.fontFamily
            verticalAlignment: Text.AlignVCenter; leftPadding:Theme.dp(24);rightPadding:Theme.dp(5);elide:Text.ElideRight
            SwirlIcon{visible:control.currentIndex===option.index;x:Theme.dp(3);anchors.verticalCenter:parent.verticalCenter;size:Theme.dp(14);name:"checkmark";color:Theme.text}
        }
        background: SwirlControlSurface {
            radius:Math.min(Theme.dp(8),height/2)
            quiet:true
            hovered:option.hovered
            pressed:option.down
            selected:option.highlighted
            focused:option.visualFocus
            controlEnabled:option.enabled
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
        // ComboBox owns arrow/Enter handling while its item popup is open.
        // Giving the bare Popup focus steals those keys from the control.
        focus:false
        popupType:Popup.Item
        closePolicy:Popup.CloseOnEscape | Popup.CloseOnPressOutside
        transformOrigin:opensAbove?Item.BottomLeft:Item.TopLeft
        readonly property SwirlPopupMotion popupMotion:SwirlPopupMotion {id:reveal;popup:popupLayer;enterDuration:SwirlMotion.menuEnterDuration;leaveDuration:SwirlMotion.menuExitDuration}
        opacity:reveal.alpha
    onAboutToShow: {
        anchorPoint=control.mapToItem(parent,0,0)
        dismissals.push(popupLayer,control.Window.window)
        Qt.callLater(function(){popupList.positionViewAtIndex(control.currentIndex,ListView.Contain)})
        reveal.prepare(Qt.point(0,(opensAbove?1:-1)*SwirlMotion.popupDistance*0.5))
    }
    onClosed:{dismissals.pop(popupLayer);reveal.reset()}

        y:opensAbove?anchorPoint.y-height-Theme.dp(4):anchorPoint.y+control.height+Theme.dp(4)
        x:parent?Math.max(edgeMargin,Math.min(anchorPoint.x,parent.width-width-edgeMargin)):0
        width:parent?Math.min(control.width,parent.width-2*edgeMargin):control.width
        height:Math.min(desiredHeight,Math.max(above,below))
        padding:Theme.dp(5)
        margins:edgeMargin
        enter:reveal.enterTransition
        exit:reveal.exitTransition
        background: Rectangle { transform:Translate{x:reveal.xOffset;y:reveal.yOffset}
            radius:Theme.menuRadius; color:Theme.material("floating"); border.width:Theme.borderWidth; border.color:Theme.increaseContrast?Theme.text:Theme.border }
        contentItem: ListView { pixelAligned: true;
            id:popupList
            transform:Translate{x:reveal.xOffset;y:reveal.yOffset}
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            highlightMoveDuration:0
            boundsBehavior:Flickable.StopAtBounds
            ScrollBar.vertical: SwirlScrollBar {}
        }
    }
}
