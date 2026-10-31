import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
SwirlMotionButton {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool danger: false
    property bool development: false
    Accessible.description:development?"研发中，此操作尚未实现。":""
    property string iconName: ""
    implicitWidth: Math.ceil(Math.max(Theme.dp(76), contents.implicitWidth + leftPadding + rightPadding))
    implicitHeight:Math.max(Theme.controlHeight,contents.implicitHeight+topPadding+bottomPadding)
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.weight: control.primary ? Font.DemiBold : Font.Medium
    SwirlFontBinding { target: control; textRole: "button" }
    font.hintingPreference:Font.PreferFullHinting
    font.pixelSize:Theme.buttonSize
    leftPadding:Theme.dp(16); rightPadding:Theme.dp(16)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    property bool outlined:false
    background: SwirlControlSurface {
        hovered: control.hovered
        pressed: control.down
        focused: control.visualFocus
        quiet: control.quiet
        primary: control.primary
        outlined: control.outlined
        controlEnabled: control.enabled
    }
    contentItem: Item {
        implicitWidth: contents.implicitWidth
        implicitHeight: contents.implicitHeight
        RowLayout {
        id: contents
        x:Math.round((parent.width-width)/2)
        y:Math.round((parent.height-height)/2)
        width:Math.round(Math.min(implicitWidth,parent.width))
        spacing:Theme.dp(8)
        SwirlIcon {
            visible: control.iconName !== ""
            name: control.iconName; size:Theme.dp(16)
            color: !control.enabled ? Theme.muted : control.primary ? Theme.primaryButtonText : control.danger ? Theme.red : Theme.muted
        }
        SwirlText {
            id:label
            text: AppState.zh(control.text)+(control.development?" · 研发中":"")
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: control.font.weight
            textRole: "button"
            Layout.fillWidth: true; elide: Text.ElideRight
            color: !control.enabled ? Theme.muted : control.primary ? Theme.primaryButtonText : control.danger ? Theme.red : Theme.text
            Layout.alignment: Qt.AlignVCenter
            horizontalAlignment:Text.AlignHCenter
            verticalAlignment:Text.AlignVCenter
        }
        }
    }
    Accessible.name: text

}
