import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import SwirlQuick
Switch {
    id: control
    property bool large: false
    property real motionScale:down?SwirlMotion.pressScale:1
    Behavior on motionScale {enabled:!SwirlMotion.reduced;NumberAnimation {duration:control.down?SwirlMotion.pressDuration:SwirlMotion.releaseDuration;easing.type:Easing.OutCubic}}
    Binding {target:control.indicator;property:"scale";value:control.motionScale}
    onPressed:SwirlMotion.noteTrigger(control)
    implicitWidth: Theme.dp(large ? 52 : 36)
    implicitHeight: Theme.dp(large ? 24 : 17)
    padding:Theme.dp(0)
    hoverEnabled: true
    indicator: Rectangle {
        width: control.width; height: control.height
        radius: height * 0.5
        color: control.checked ? Theme.primaryControl : Theme.dark ? "#626262" : "#DADADD"
        border.width: Theme.dp(control.visualFocus ? 2 : 0)
        border.color: Theme.focusBorder
        opacity: control.enabled?(control.hovered ? 0.88 : 1):0.45
        Behavior on opacity{NumberAnimation{duration:SwirlMotion.hoverDuration}}
        Rectangle {
            property real thumbPosition:control.checked?1:0
            width: parent.height - Theme.dp(4); height: width
            x:Math.round(Theme.dp(2)+(parent.width-width-2*Theme.dp(2))*thumbPosition); y:Theme.dp(2)
            radius: height * 0.5
            color: "#FEFEFF"
            RectangularShadow {
                anchors.fill:parent; z:-1
                visible:Theme.effectsSupported
                radius:parent.radius; blur:Theme.dp(6)
                offset:Qt.vector2d(0,Theme.dp(2)); color:"#30000000"
            }
            Behavior on thumbPosition {enabled:!SwirlMotion.reduced;NumberAnimation {duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}}
        }
        Behavior on color { ColorAnimation { duration: Theme.motion } }
    }
    contentItem: Item {}
}
