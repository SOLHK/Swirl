import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
Button {
    id: control
    property bool primary: false
    property bool quiet: false
    property bool danger: false
    property string iconName: ""
    implicitWidth: Math.max(76, contents.implicitWidth + 36)
    implicitHeight: 44
    hoverEnabled: true
    font.family: Theme.fontFamily
    font.pixelSize: 17
    leftPadding: 18; rightPadding: 18
    background: SwirlPillSurface {
        primary: control.primary
        gradient:control.quiet && !control.hovered && !control.down ? null : pillGradient
        property Gradient pillGradient:Gradient {
            GradientStop { position:0; color:control.primary ? "#389BFF" : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.pillTop }
            GradientStop { position:1; color:control.primary ? "#087EFF" : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.pillBottom }
        }
        hovered: control.hovered || control.activeFocus
        pressed: control.down
        subtleShadow: !control.quiet
        opacity: control.enabled ? 1 : 0.45
        color: control.quiet && !control.hovered && !control.down ? "transparent" :
               control.primary ? Theme.accent : control.down ? Theme.pressed : control.hovered ? Theme.hover : Theme.buttonBase
        border.color: control.activeFocus ? Theme.focusBorder : control.quiet ? "transparent" : Theme.pillRim
    }
    contentItem: RowLayout {
        id: contents
        spacing: 10
        SwirlIcon {
            visible: control.iconName !== ""
            name: control.iconName; size: 23
            color: control.primary ? "white" : control.danger ? Theme.red : Theme.muted
        }
        Text {
            text: control.text
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: Font.DemiBold
            color: control.primary ? "white" : control.danger ? Theme.red : Theme.text
            Layout.alignment: Qt.AlignVCenter
        }
    }
    Accessible.name: text
}
