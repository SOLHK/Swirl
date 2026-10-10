import QtQuick
import SwirlQuick
Rectangle {
    id:badge
    property string label:"UI Demo"
    property string tone:"neutral"
    implicitWidth:caption.implicitWidth+18
    implicitHeight:24
    radius:8
    color:tone==="success"?(Theme.dark?"#254439":"#E2F6EE"):
          tone==="warning"?(Theme.dark?"#4A392A":"#FFF0DB"):
          tone==="accent"?Theme.selected:Theme.field
    Text {
        id:caption
        anchors.centerIn:parent
        text:badge.label
        font.pixelSize:11
        font.weight:Font.DemiBold
        color:tone==="success"?Theme.green:
              tone==="warning"?Theme.orange:
              tone==="accent"?Theme.accent:Theme.muted
    }
}