import QtQuick
import QtQuick.Controls
import SwirlQuick
Dialog {
    id: dialog
    modal: true
    width: Math.min(Theme.dp(470), parent ? parent.width-Theme.dp(40) : Theme.dp(470))
    anchors.centerIn: Overlay.overlay
    padding:Theme.dp(23)
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.motion; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motion } }
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
