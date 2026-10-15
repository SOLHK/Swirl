import QtQuick
import SwirlQuick
import "../controls"
Rectangle {
    id: badge
    property string label: ""
    property string tone: "neutral"
    property bool busy:false
    Behavior on color{ColorAnimation{duration:SwirlMotion.duration}}
    SwirlActivityIndicator{anchors.left:parent.left;anchors.leftMargin:Theme.dp(6);anchors.verticalCenter:parent.verticalCenter;busy:badge.busy}
    implicitWidth: caption.implicitWidth + Theme.dp(busy?40:20)
    implicitHeight:Theme.dp(24)
    radius:Theme.roundedRadius(width,height)
    border.width:Theme.dp(1)
    border.color: Theme.glassRim
    color: tone === "success" ? (Theme.dark ? "#82407765" : "#B6DCF6EA") :
           tone === "warning" ? (Theme.dark ? "#A36B4B30" : "#B9FFF0DA") :
           tone === "accent" ? Theme.selected : Theme.material("secondary")
    SwirlText {
        id: caption
        anchors.centerIn: parent
        anchors.horizontalCenterOffset:badge.busy?Theme.dp(8):0
        text: AppState.zh(badge.label)
        font.pixelSize:Theme.fontSize(11)
        font.weight: Font.Medium
        color: tone === "success" ? Theme.green :
               tone === "warning" ? Theme.orange :
               tone === "accent" ? Theme.accent : Theme.muted
    }
}
