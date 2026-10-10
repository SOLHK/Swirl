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