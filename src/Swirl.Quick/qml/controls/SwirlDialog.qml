import QtQuick
import QtQuick.Controls
import SwirlQuick
Dialog {
    id:dialog
    modal:true
    width:Math.min(470,parent?parent.width-40:470)
    anchors.centerIn:Overlay.overlay
    padding:22
    closePolicy:Popup.CloseOnEscape|Popup.CloseOnPressOutside
    enter:Transition {
        ParallelAnimation {
            NumberAnimation { property:"opacity"; from:0; to:1; duration:Theme.motion }
            NumberAnimation { property:"scale"; from:0.97; to:1; duration:Theme.motion; easing.type:Easing.OutCubic }
        }
    }
    exit:Transition {
        ParallelAnimation {
            NumberAnimation { property:"opacity"; from:1; to:0; duration:Theme.motion }
            NumberAnimation { property:"scale"; from:1; to:0.97; duration:Theme.motion }
        }
    }
    font.family:"Segoe UI"
    header:Item {
        implicitHeight:45
        Text {
            text:dialog.title
            color:Theme.text; font.pixelSize:19
            font.weight:Font.DemiBold
            anchors.left:parent.left
            anchors.verticalCenter:parent.verticalCenter
        }
    }
    background:Rectangle { color:Theme.raised; radius:17; border.color:Theme.border }
}