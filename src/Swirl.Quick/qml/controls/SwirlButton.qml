import QtQuick
import QtQuick.Controls
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
    implicitWidth: Math.max(Theme.dp(76), contents.implicitWidth + Theme.dp(24))
    implicitHeight:Theme.controlHeight
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.hintingPreference:Font.PreferFullHinting
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.dp(12); rightPadding:Theme.dp(12)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    property bool outlined:false
    background:SwirlContinuousSurface {
        radius:Theme.controlRadius
        color:control.primary?(control.down?Qt.darker(Theme.primaryControl,1.15):control.hovered?Qt.lighter(Theme.primaryControl,1.08):Theme.primaryControl):control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet?"transparent":Theme.buttonBase
        border.width:control.activeFocus?Theme.dp(2):control.primary||control.quiet?0:Theme.borderWidth
        border.color:control.activeFocus?Theme.focusBorder:Theme.controlBorder
        Behavior on color {ColorAnimation{duration:SwirlMotion.hoverDuration}}
        opacity:control.enabled?1:0.45
    }
    contentItem: Item {
        opacity:control.enabled?1:0.45
        implicitWidth: contents.implicitWidth
        implicitHeight: contents.implicitHeight
        RowLayout {
        id: contents
        anchors.centerIn:parent
        width:Math.min(implicitWidth,parent.width)
        spacing:Theme.dp(8)
        SwirlIcon {
            visible: control.iconName !== ""
            name: control.iconName; size:Theme.dp(16)
            color: control.primary ? "white" : control.danger ? Theme.red : Theme.muted
        }
        SwirlText {
            text: AppState.zh(control.text)+(control.development?" · 研发中":"")
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: Font.Medium
            Layout.fillWidth: true; elide: Text.ElideRight
            color: control.primary ? "white" : control.danger ? Theme.red : Theme.text
            Layout.alignment: Qt.AlignVCenter
            horizontalAlignment:Text.AlignHCenter
            verticalAlignment:Text.AlignVCenter
        }
        }
    }
    Accessible.name: text
}
