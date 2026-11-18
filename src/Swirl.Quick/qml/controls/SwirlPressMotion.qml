import QtQuick
import SwirlQuick
Item {
    id:motion
    property var control:parent
    property bool presentationReady:false
    Component.onCompleted:presentationReady=true
    Component.onDestruction:presentationReady=false
    property bool pressed:motion.control && motion.control.down
    readonly property real value:1-(1-SwirlMotion.pressScale)*feedback.contact
    readonly property Item ownedInteractionMotion: SwirlInteractionMotion {id:feedback;parent:motion;pressed:motion.pressed;controlEnabled:motion.control && motion.control.enabled}
    Binding {target:motion.presentationReady && motion.control?motion.control.background:null;property:"scale";value:motion.value;when:motion.presentationReady && motion.control!==null && motion.control.background!==null}
    Binding {target:motion.presentationReady && motion.control?motion.control.contentItem:null;property:"scale";value:motion.value;when:motion.presentationReady && motion.control!==null && motion.control.contentItem!==null}
    onPressedChanged:if(pressed && control)SwirlMotion.noteTrigger(control)
}
