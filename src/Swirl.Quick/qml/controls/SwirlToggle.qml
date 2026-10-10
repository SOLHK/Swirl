import QtQuick
import QtQuick.Controls
import SwirlQuick
Switch {
    id: control
    implicitWidth: 55
    implicitHeight: 33
    hoverEnabled: true
    indicator: Rectangle {
        implicitWidth: 51
        implicitHeight: 30
        x: 2
        y: (control.height - height) / 2
        radius: 15
        antialiasing: true
        color: control.checked ? Theme.accent : (Theme.dark ? "#627589" : "#BCC9D7")
        border.width: 1
        border.color: control.checked ? Qt.lighter(Theme.accent, 1.25) : Theme.glassRim
        gradient: Gradient {
            GradientStop { position: 0; color: control.checked ? Qt.lighter(Theme.accent, 1.17) : (Theme.dark ? "#6A7C91" : "#CBD7E3") }
            GradientStop { position: 1; color: control.checked ? Theme.accent : (Theme.dark ? "#415269" : "#A5B6C9") }
        }
        Rectangle {
            x: control.checked ? 25 : 3
            y: 3
            width: 24
            height: 24
            radius: 12
            antialiasing: true
            color: "#FAFCFF"
            border.width: 1
            border.color: "#D7E4F1"
            Behavior on x {
                NumberAnimation { duration: Theme.reduceMotion ? 0 : 240; easing.type: Easing.OutCubic }
            }
            Rectangle {
                x: 5; y: 2; width: 14; height: 3
                radius: 2; color: "#FFFFFF"
                opacity: 0.8
            }
        }
    }
    contentItem: Item {}
}
