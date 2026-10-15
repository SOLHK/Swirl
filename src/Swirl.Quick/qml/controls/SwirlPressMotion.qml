import QtQuick
import SwirlQuick
Item {
    id:motion
    property var control:parent
    property real value:control && control.down?SwirlMotion.pressScale:1
    Behavior on value {enabled:!SwirlMotion.reduced;SwirlSpring{}}
    Binding {target:motion.control?motion.control.background:null;property:"scale";value:motion.value;when:motion.control!==null && motion.control.background!==null}
    Connections {target:motion.control;function onPressed(){SwirlMotion.noteTrigger(motion.control)}}
}
