import QtQuick
import SwirlQuick
Rectangle {
    id: badge
    property string label: "演示"
    property string tone: "neutral"
    implicitWidth: caption.implicitWidth + 20
    implicitHeight: 24
    radius: 11
    border.width: 1
    border.color: Theme.glassRim
    color: tone === "success" ? (Theme.dark ? "#82407765" : "#B6DCF6EA") :
           tone === "warning" ? (Theme.dark ? "#A36B4B30" : "#B9FFF0DA") :
           tone === "accent" ? Theme.selected : Theme.material("secondary")
    Text {
        id: caption
        anchors.centerIn: parent
        text: badge.label
        font.pixelSize: 11
        font.weight: Font.Medium
        color: tone === "success" ? Theme.green :
               tone === "warning" ? Theme.orange :
               tone === "accent" ? Theme.accent : Theme.muted
    }
}
