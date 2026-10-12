import QtQuick
import QtQuick.Controls
import SwirlQuick
ComboBox {
    id: control
    implicitWidth:Theme.dp(146)
    implicitHeight:Theme.dp(44)
    hoverEnabled: true
    font.family: "Microsoft YaHei UI"
    font.pixelSize:Theme.fontSize(17)
    leftPadding:Theme.dp(15); rightPadding:Theme.dp(31)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    contentItem: Text {
        text: AppState.zh(control.displayText)
        color: Theme.text
        font: control.font
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment:Text.AlignHCenter
        elide: Text.ElideRight
        leftPadding:Theme.dp(4); rightPadding:Theme.dp(4)
    }
    indicator: Canvas {
        onVisibleChanged:if(visible)requestPaint();

        id: chevron
        x: control.width-width-Theme.dp(13); y: (control.height-height)/2
        width:Theme.dp(14); height:Theme.dp(14)
        onPaint: {
            var ctx=getContext("2d")
            ctx.reset(); ctx.strokeStyle=Theme.muted
            ctx.lineWidth=Theme.dp(1.65); ctx.lineCap="round"; ctx.lineJoin="round"
            ctx.beginPath(); ctx.moveTo(Theme.dp(3),Theme.dp(5)); ctx.lineTo(Theme.dp(7),Theme.dp(9)); ctx.lineTo(Theme.dp(11),Theme.dp(5)); ctx.stroke()
        }
        Connections { target: Theme; function onMutedChanged() { chevron.requestPaint() } }
    }
    background: SwirlPillSurface {
        pressed:control.pressed;hovered:control.hovered
        radius: Theme.pillRadius(height)
        antialiasing: true
        color: control.pressed ? Theme.pressed : control.hovered ? Theme.hover : Theme.material("field")
        border.width:Theme.dp(1)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        Behavior on color { ColorAnimation { duration: SwirlMotion.duration } }
    }
    delegate: ItemDelegate {
        SwirlPressMotion{}
        width: control.popup.availableWidth
        height:Theme.dp(36)
        text: String(modelData)
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: AppState.zh(parent.text)
            color: Theme.text; font.pixelSize:Theme.fontSize(17); font.family: "Microsoft YaHei UI"
            verticalAlignment: Text.AlignVCenter; leftPadding:Theme.dp(12)
        }
        background: Rectangle {
            radius: Theme.controlRadius; antialiasing:true; color: parent.highlighted ? Theme.selected : "transparent"
            Behavior on color { ColorAnimation { duration: SwirlMotion.duration } }
        }
    }
    popup: Popup {
        transformOrigin:Item.TopLeft
    onAboutToShow: {
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onClosed:{scale=1;opacity=1}

        y: control.height + Theme.dp(7)
        width: control.width
        padding:Theme.dp(6)
        implicitHeight: Math.min(Theme.dp(290), contentItem.implicitHeight+Theme.dp(12))
        enter: Transition {
        enabled:!SwirlMotion.reduced
            ParallelAnimation {
                NumberAnimation { property:"opacity";to:1; duration: SwirlMotion.duration }
                SwirlSpring { property:"scale";to:1 }
            }
        }
        exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} NumberAnimation {property:"scale";to:0.96;duration:SwirlMotion.duration;easing.type:Easing.InCubic} } }
        background: Rectangle {
            color: Theme.material("floating")
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
