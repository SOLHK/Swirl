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
    implicitWidth: Math.max(76, contents.implicitWidth + 30)
    implicitHeight: 38
    hoverEnabled: true
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 12
    leftPadding: 15; rightPadding: 15
    background: Rectangle {
        radius: 13
        antialiasing: true
        border.width: 1
        border.color: control.primary ? (Theme.dark ? "#9FC9FA" : "#6697F0") :
                      control.quiet && !control.hovered ? "transparent" : Theme.glassRim
        color: control.primary ? Theme.accent :
               control.down ? Theme.selected :
               control.hovered ? Theme.material("floating") :
               control.quiet ? "transparent" : Theme.material("secondary")
        gradient: Gradient {
            GradientStop {
                position: 0
                color: control.primary ? Qt.lighter(Theme.accent, 1.16) :
                       control.down ? Theme.selected :
                       control.quiet && !control.hovered ? "transparent" :
                       Theme.dark ? "#A24A6280" : "#EEFFFFFF"
            }
            GradientStop {
                position: 1
                color: control.primary ? Theme.accent :
                       control.down ? Theme.selected :
                       control.quiet && !control.hovered ? "transparent" :
                       Theme.material("secondary")
            }
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 13; anchors.rightMargin: 13
            anchors.topMargin: 1
            height: 1; color: Theme.glassGlint
            opacity: control.quiet && !control.hovered ? 0 : 0.62
        }
        Behavior on border.color { ColorAnimation { duration: Theme.motion } }
    }
    contentItem: RowLayout {
        id: contents
        spacing: 7
        SwirlIcon {
            visible: control.iconName !== ""
            name: control.iconName; size: 16
            color: control.primary ? (Theme.dark ? "#172A42" : "#FFFFFF") : control.danger ? Theme.red : Theme.text
        }
        Text {
            text: control.text
            font.family: control.font.family
            font.pixelSize: control.font.pixelSize
            font.weight: control.primary ? Font.DemiBold : Font.Medium
            color: control.primary ? (Theme.dark ? "#172A42" : "white") : control.danger ? Theme.red : Theme.text
            Layout.alignment: Qt.AlignVCenter
        }
    }
}
