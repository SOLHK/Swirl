import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"
TextField {
    renderType:TextInput.NativeRendering
    font.hintingPreference:Font.PreferFullHinting
    SwirlFontBinding { target: control; textRole: "input" }
    id: control
    property bool borderless:false
    implicitHeight:Theme.controlHeight
    implicitWidth:Theme.dp(225)
    leftPadding:Theme.dp(32)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    rightPadding: Theme.dp(control.objectName === "pageSearch" && control.width > Theme.dp(130) ? 64 : 15)
    placeholderText: "搜索"
    placeholderTextColor: Theme.muted
    color: enabled ? Theme.text : Theme.muted
    selectedTextColor: Theme.text
    selectionColor: Theme.selected
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize:Theme.fontSize(13)
    background: Rectangle {
        radius: Math.min(Theme.dp(9),height/2)
        color: Theme.buttonBase
        border.width:control.activeFocus || Theme.increaseContrast || !control.borderless?Theme.borderWidth:0
        border.color: control.activeFocus || Theme.increaseContrast ? Theme.text : Theme.controlBorder
        Behavior on color { enabled:!SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
        Behavior on border.color { enabled:!SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
    SwirlText { visible:control.objectName === "pageSearch" && control.width > Theme.dp(130); anchors.right:parent.right; anchors.rightMargin:Theme.dp(12); anchors.verticalCenter:parent.verticalCenter; text:"Ctrl+K"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
    SwirlIcon {
        anchors.left: parent.left; anchors.leftMargin:Theme.dp(8)
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size:Theme.dp(14); color: control.activeFocus ? Theme.text : Theme.muted
    }
}
