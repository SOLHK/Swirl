import QtQuick
import QtQuick.Controls
import SwirlQuick
Dialog {
    id: dialog
    modal: true
    focus: true
    transformOrigin:Item.Center
    onAboutToShow: {
        transformOrigin=SwirlMotion.popupOrigin(dialog)
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onClosed:{scale=1;opacity=1}
    width: Math.min(Theme.dp(470), parent ? parent.width-Theme.dp(40) : Theme.dp(470))
    anchors.centerIn: Overlay.overlay
    padding:Theme.dp(23)
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation { property:"opacity";to:1; duration: SwirlMotion.duration }
            SwirlSpring { property:"scale";to:1 }
        }
    }
    exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} NumberAnimation {property:"scale";to:0.96;duration:SwirlMotion.duration;easing.type:Easing.InCubic} } }
    font.family: "Microsoft YaHei UI"
    header: Item {
        implicitHeight:Theme.dp(47)
        Text {
            text: dialog.title
            color: Theme.text; font.pixelSize:Theme.fontSize(18); font.weight: Font.DemiBold
            anchors.left: parent.left; anchors.leftMargin:dialog.leftPadding
            anchors.right:parent.right; anchors.rightMargin:dialog.rightPadding
            elide:Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        color: Theme.material("floating")
        radius:Theme.popupRadius; antialiasing:true; border.width:Theme.dp(1); border.color: Theme.glassRim
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin:Theme.dp(24); anchors.rightMargin:Theme.dp(24); anchors.top: parent.top
            anchors.topMargin:Theme.dp(1); height:Theme.dp(1); color: Theme.glassGlint
        }
    }
}
