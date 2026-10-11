import QtQuick
import QtQuick.Controls
import SwirlQuick
Dialog {
    id: dialog
    modal: true
    width: Math.min(470, parent ? parent.width-40 : 470)
    anchors.centerIn: Overlay.overlay
    padding: 23
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
        implicitHeight: 47
        Text {
            text: dialog.title
            color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold
            anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        color: Theme.material("floating")
        radius: 23; border.width: 1; border.color: Theme.glassRim
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin: 24; anchors.rightMargin: 24; anchors.top: parent.top
            anchors.topMargin: 1; height: 1; color: Theme.glassGlint
        }
    }
}
