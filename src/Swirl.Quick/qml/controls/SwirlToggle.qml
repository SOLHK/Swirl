import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import SwirlQuick
Switch {
    id: control
    property bool large: false
    property real motionScale:down?SwirlMotion.pressScale:1
    Behavior on motionScale {enabled:!SwirlMotion.reduced;SwirlSpring{}}
    Binding {target:control.indicator;property:"scale";value:control.motionScale}
    onPressed:SwirlMotion.noteTrigger(control)
    implicitWidth: Theme.dp(large ? 86 : 60)
    implicitHeight: Theme.dp(large ? 46 : 32)
    padding:Theme.dp(0)
    hoverEnabled: true
    indicator: Rectangle {
        width: control.width; height: control.height
        radius: height * 0.5
        color: control.checked ? Theme.primaryControl : Theme.dark ? "#626262" : "#DADADD"
        border.width: Theme.dp(control.activeFocus ? 2 : 0)
        border.color: Theme.focusBorder
        opacity: control.hovered ? 0.88 : 1
        Rectangle {
            width: parent.height - Theme.dp(8); height: width
            x: control.checked ? parent.width - width - Theme.dp(4) : Theme.dp(4); y:Theme.dp(4)
            radius: height * 0.5
            color: "#FEFEFF"
            layer.enabled: Theme.effectsSupported
            layer.effect: MultiEffect { shadowEnabled:true; shadowBlur:0.35; shadowVerticalOffset:2; shadowColor:"#30000000" }
            Behavior on x {enabled:!SwirlMotion.reduced;SwirlSpring {epsilon:0.1}}
        }
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    contentItem: Item {}
}
