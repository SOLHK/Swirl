import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import SwirlQuick
Switch {
    id: control
    property bool large: false
    implicitWidth: large ? 86 : 60
    implicitHeight: large ? 46 : 32
    padding: 0
    hoverEnabled: true
    indicator: Rectangle {
        width: control.width; height: control.height
        radius: Theme.pillRadius(height)
        color: control.checked ? Theme.accent : Theme.dark ? "#5E6C80" : control.large ? "#D3D7DF" : "#E3EBF4"
        border.width: control.activeFocus ? 1.5 : 0
        border.color: Theme.accent
        opacity: control.hovered ? 0.88 : 1
        Rectangle {
            width: parent.height - 8; height: width
            x: control.checked ? parent.width - width - 4 : 4; y: 4
            radius: Theme.pillRadius(height)
            color: "#FEFEFF"
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled:true; shadowBlur:0.35; shadowVerticalOffset:2; shadowColor:"#30586A85" }
            Behavior on x { NumberAnimation { duration: Theme.motion; easing.type: Easing.OutCubic } }
        }
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    contentItem: Item {}
}
