import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../components"

TextField {
    id: control
    property bool borderless: false
    implicitHeight: Theme.controlHeight
    implicitWidth: Theme.dp(225)
    leftPadding: Theme.dp(32)
    rightPadding: Theme.dp(control.objectName === "pageSearch" && control.width > Theme.dp(130) ? 64 : 12)
    topPadding: Theme.dp(5)
    bottomPadding: Theme.dp(5)
    hoverEnabled: true
    selectByMouse: true
    placeholderText: qsTr("搜索")
    Accessible.name: placeholderText
    placeholderTextColor: Theme.muted
    color: enabled ? Theme.text : Theme.muted
    selectionColor: Theme.fieldSelection
    selectedTextColor: Theme.text
    font.family: Theme.fontFamily
    font.weight: Theme.bodyFontWeight
    font.pixelSize: Theme.bodySize
    font.hintingPreference: Font.PreferFullHinting
    renderType: TextInput.NativeRendering
    SwirlFontBinding { target: control; textRole: "input" }
    background: SwirlControlSurface {
        field: !control.borderless
        outlined: !control.borderless
        hovered: control.hovered
        focused: control.activeFocus
        controlEnabled: control.enabled
    }
    SwirlText {
        visible: control.objectName === "pageSearch" && control.width > Theme.dp(130)
        anchors.right: parent.right
        anchors.rightMargin: Theme.controlPadding
        anchors.verticalCenter: parent.verticalCenter
        text: "Ctrl+K"; color: Theme.muted; font.pixelSize: Theme.captionSize
        Accessible.ignored: true
    }
    SwirlIcon {
        anchors.left: parent.left
        anchors.leftMargin: Theme.dp(10)
        anchors.verticalCenter: parent.verticalCenter
        name: "search"; size: Theme.dp(14)
        color: control.activeFocus ? Theme.text : Theme.muted
        Accessible.ignored: true
    }
}
