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
    property string iconName: ""
    implicitWidth: Math.max(Theme.dp(76), contents.implicitWidth + Theme.dp(24))
    implicitHeight:Theme.dp(26)
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize:Theme.fontSize(13)
    leftPadding:Theme.dp(12); rightPadding:Theme.dp(12)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    property bool outlined:false
    background:Rectangle {
        radius:Theme.buttonRadius;color:control.primary?Theme.primaryControl:control.down?Theme.pressed:control.hovered?Theme.hover:control.quiet||control.outlined?"transparent":Theme.buttonBase
        border.width:control.activeFocus?Theme.dp(2):control.outlined?Theme.dp(1):0;border.color:control.activeFocus?Theme.focusBorder:Theme.border
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
        Text {
            text: AppState.zh(control.text)
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: Font.Normal
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
