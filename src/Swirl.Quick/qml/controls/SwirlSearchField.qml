import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
TextField {
    id: control
    implicitHeight:Theme.dp(42)
    implicitWidth:Theme.dp(225)
    leftPadding:Theme.dp(39)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    rightPadding: Theme.dp(control.objectName === "pageSearch" && control.width > Theme.dp(130) ? 64 : 15)
    placeholderText: "搜索"
    placeholderTextColor: Theme.muted
    color: Theme.text
    selectedTextColor: "white"
    selectionColor: Theme.accent
    font.family: "Microsoft YaHei UI"
    font.pixelSize:Theme.fontSize(16)
    background: SwirlPillSurface {
        hovered:control.activeFocus
        radius: Theme.controlRadius
        gradient: null
        subtleShadow: false
        antialiasing: true
        color: control.activeFocus ? Theme.hover : Theme.material("field")
        border.width: Theme.dp(control.activeFocus ? 2 : 1)
        border.color: control.activeFocus ? Theme.focusBorder : Theme.pillRim
        Behavior on color { ColorAnimation { duration: Theme.motion } }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    Text { visible:control.objectName === "pageSearch" && control.width > Theme.dp(130); anchors.right:parent.right; anchors.rightMargin:Theme.dp(12); anchors.verticalCenter:parent.verticalCenter; text:"Ctrl+K"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
    SwirlIcon {
        anchors.left: parent.left; anchors.leftMargin:Theme.dp(14)
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size:Theme.dp(22); color: control.activeFocus ? Theme.focusBorder : Theme.text
    }
}
