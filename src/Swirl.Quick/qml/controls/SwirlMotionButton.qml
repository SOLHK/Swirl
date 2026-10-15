import QtQuick
import QtQuick.Controls
import SwirlQuick
Button {
    id: control
    // Press depth affects the background; text and hit areas stay at full scale.
    property real motionScale: enabled && down ? SwirlMotion.pressScale : 1
    property real clickLight:0
    Behavior on motionScale {
        enabled: !SwirlMotion.reduced
        NumberAnimation {duration:control.down?SwirlMotion.pressDuration:SwirlMotion.hoverDuration;easing.type:control.down?Easing.OutCubic:Easing.OutBack;easing.overshoot:0.45}
    }
    Binding { target:control.background; property:"scale"; value:control.motionScale; when:control.background!==null }
    onPressed: SwirlMotion.noteTrigger(control)
    onClicked:if(enabled && visible && !SwirlMotion.reduced)lightPulse.restart()
    onVisibleChanged:if(!visible){lightPulse.stop();clickLight=0}
    onEnabledChanged:if(!enabled){lightPulse.stop();clickLight=0}
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced){lightPulse.stop();control.clickLight=0}}}
    SwirlClickLight {
        parent:control.background;anchors.fill:parent
        cornerRadius:parent && parent.radius!==undefined?parent.radius:Theme.buttonRadius
        amount:control.clickLight
    }
    SequentialAnimation {
        id:lightPulse
        NumberAnimation {target:control;property:"clickLight";from:0;to:0.14;duration:SwirlMotion.ms(45)}
        NumberAnimation {target:control;property:"clickLight";to:0;duration:SwirlMotion.hoverDuration;easing.type:Easing.OutCubic}
    }
}
