import QtQuick
import SwirlQuick
Item {
    id:motion
    property var control:parent
    readonly property real value:1-(1-SwirlMotion.pressScale)*feedback.contact
    SwirlInteractionMotion {id:feedback;pressed:motion.control && motion.control.down;controlEnabled:motion.control && motion.control.enabled}
    Binding {target:motion.control?motion.control.background:null;property:"scale";value:motion.value;when:motion.control!==null && motion.control.background!==null}
    Connections {target:motion.control;function onPressed(){SwirlMotion.noteTrigger(motion.control)}}
}
