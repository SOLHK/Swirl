import QtQuick
import SwirlQuick
import "../controls"
Rectangle {
    id: badge
    property string label: ""
    property string tone: "neutral"
    property bool busy:false
    Accessible.role:Accessible.StaticText
    Accessible.name:AppState.zh(label)
    Behavior on color{enabled:!SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.statusDuration}}
    SwirlActivityIndicator{anchors.left:parent.left;anchors.leftMargin:Theme.dp(6);anchors.verticalCenter:parent.verticalCenter;busy:badge.busy}
    implicitWidth: caption.implicitWidth + Theme.dp(busy?40:20)
    implicitHeight:Theme.dp(24)
    radius:Theme.roundedRadius(width,height)
    border.width:Theme.increaseContrast?Theme.borderWidth:0
    border.color: Theme.glassRim
    color: tone === "success" ? Theme.successSurface : tone === "warning" ? Theme.warningSurface : tone === "accent" ? Theme.selected : Theme.buttonBase
    SwirlText {
        id: caption
        anchors.centerIn: parent
        anchors.horizontalCenterOffset:badge.busy?Theme.dp(8):0
        text: AppState.zh(badge.label)
        font.pixelSize:Theme.fontSize(11)
        font.weight: Font.Medium
        color: badge.tone === "success" ? Theme.successText : badge.tone === "warning" ? Theme.warningText : badge.tone === "accent" ? Theme.text : Theme.muted
    }
}
