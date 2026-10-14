import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
TextField {
    id: control
    property bool borderless:false
    implicitHeight:Theme.dp(42)
    implicitWidth:Theme.dp(225)
    leftPadding:Theme.dp(24)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    rightPadding: Theme.dp(control.objectName === "pageSearch" && control.width > Theme.dp(130) ? 64 : 15)
    placeholderText: "搜索"
    placeholderTextColor: Theme.muted
    color: Theme.text
    selectedTextColor: "white"
    selectionColor: Theme.accent
    font.family: Theme.fontFamily
    font.pixelSize:Theme.fontSize(16)
    background: SwirlPillSurface {
        hovered:control.activeFocus
        radius: height/2
        gradient: null
        subtleShadow: false
        antialiasing: true
        color:Theme.dark?Theme.field:Theme.surface
        border.width:Theme.dp(control.activeFocus?2:control.borderless?0:1)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    Text { visible:control.objectName === "pageSearch" && control.width > Theme.dp(130); anchors.right:parent.right; anchors.rightMargin:Theme.dp(12); anchors.verticalCenter:parent.verticalCenter; text:"Ctrl+K"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
    SwirlIcon {
        anchors.left: parent.left; anchors.leftMargin:Theme.dp(8)
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size:Theme.dp(14); color: control.activeFocus ? Theme.focusBorder : Theme.muted
    }
}
