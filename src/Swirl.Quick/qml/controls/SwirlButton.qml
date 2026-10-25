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
    implicitWidth: Math.round(Math.max(Theme.dp(76), contents.implicitWidth + Theme.dp(24)))
    implicitHeight:Theme.controlHeight
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.weight: control.primary ? Font.DemiBold : Font.Medium
    SwirlFontBinding { target: control; textRole: "button" }
    font.hintingPreference:Font.PreferFullHinting
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.dp(12); rightPadding:Theme.dp(12)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    property bool outlined:false
    background:Rectangle {
        radius:Math.min(Theme.dp(9),height/2)
        color:control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet?"transparent":Theme.buttonBase
        border.width:control.visualFocus || Theme.increaseContrast || control.outlined?Theme.borderWidth:0
        border.color:control.visualFocus || Theme.increaseContrast?Theme.text:Theme.controlBorder
        Behavior on color {enabled:!SwirlMotion.reduced;ColorAnimation{duration:SwirlMotion.hoverDuration}}
        opacity:control.enabled?1:0.45
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
            color: !control.enabled ? Theme.muted : control.danger ? Theme.red : control.primary ? Theme.text : Theme.muted
        }
        SwirlText {
            text: AppState.zh(control.text)+(control.development?" · 研发中":"")
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: control.font.weight
            textRole: "button"
            Layout.fillWidth: true; elide: Text.ElideRight
            color: !control.enabled ? Theme.muted : control.danger ? Theme.red : Theme.text
            Layout.alignment: Qt.AlignVCenter
            horizontalAlignment:Text.AlignHCenter
            verticalAlignment:Text.AlignVCenter
        }
        }
    }
    Accessible.name: text
}
