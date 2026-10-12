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
    implicitWidth: Math.max(Theme.dp(76), contents.implicitWidth + Theme.dp(36))
    implicitHeight:Theme.dp(44)
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize:Theme.fontSize(17)
    leftPadding:Theme.dp(12); rightPadding:Theme.dp(12)
    topPadding:Theme.dp(4); bottomPadding:Theme.dp(4)
    background: SwirlPillSurface {
        Behavior on color { ColorAnimation {duration:SwirlMotion.duration} }
        primary: control.primary
        gradient:control.quiet && !control.hovered && !control.down ? null : pillGradient
        property Gradient pillGradient:Gradient {
            GradientStop { position:0; color:control.primary ? Theme.primaryControl : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.pillTop; Behavior on color { ColorAnimation { duration:SwirlMotion.duration } } }
            GradientStop { position:1; color:control.primary ? Theme.primaryControl : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.pillBottom; Behavior on color { ColorAnimation { duration:SwirlMotion.duration } } }
        }
        hovered: control.hovered || control.activeFocus
        pressed: control.down
        subtleShadow: !control.quiet
        opacity: control.enabled ? 1 : 0.45
        color: control.quiet && !control.hovered && !control.down ? "transparent" :
               control.primary ? Theme.primaryControl : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.color: control.activeFocus ? Theme.focusBorder : control.quiet ? "transparent" : Theme.pillRim
    }
    contentItem: Item {
        implicitWidth: contents.implicitWidth
        implicitHeight: contents.implicitHeight
        RowLayout {
        id: contents
        anchors.centerIn:parent
        width:Math.min(implicitWidth,parent.width)
        spacing:Theme.dp(8)
        SwirlIcon {
            visible: control.iconName !== ""
            name: control.iconName; size:Theme.dp(23)
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
