import QtQuick
import SwirlQuick

Item {
    id: feedback
    property bool hovered:false
    property bool pressed:false
    property bool focused:false
    property bool controlEnabled:true
    property real hover:0
    property real contact:0
    property real focusAmount:0
    readonly property real light:Math.max(hover*0.55,focusAmount*0.8,contact)
    readonly property bool moving:hoverTravel.running || pressTravel.running || contactTravel.running || focusTravel.running
    property bool initialized:false
    readonly property bool windowVisible:!Window.window || (Window.window.visible && Window.window.visibility!==Window.Minimized)
    function finish(){
        if(!initialized)return
        hoverTravel.stop();pressTravel.stop();contactTravel.stop();focusTravel.stop()
        hover=controlEnabled && hovered?1:0
        contact=controlEnabled && pressed?1:0
        focusAmount=controlEnabled && focused?1:0
    }
    function retarget(){
        if(!initialized)return
        if(!visible || !windowVisible || !controlEnabled || SwirlMotion.reduced){finish();return}
        hoverTravel.stop();hoverTravel.from=hover;hoverTravel.to=controlEnabled && hovered?1:0
        if(hoverTravel.from!==hoverTravel.to)hoverTravel.start()
        focusTravel.stop();focusTravel.from=focusAmount;focusTravel.to=controlEnabled && focused?1:0
        if(focusTravel.from!==focusTravel.to)focusTravel.start()
        if(pressed){
            contactTravel.stop()
            if(!pressTravel.running && contact!==1){pressTravel.from=contact;pressTravel.start()}
        }else{
            pressTravel.stop()
            if(!contactTravel.running && contact!==0)contactTravel.start()
        }
    }
    onHoveredChanged:retarget()
    onPressedChanged:retarget()
    onFocusedChanged:retarget()
    onControlEnabledChanged:retarget()
    onVisibleChanged:if(!visible)finish()
    onWindowVisibleChanged:if(!windowVisible)finish()
    Component.onCompleted:{initialized=true;finish()}
    NumberAnimation{id:hoverTravel;target:feedback;property:"hover";duration:SwirlMotion.hoverDuration;easing.type:Easing.OutCubic}
    NumberAnimation{id:pressTravel;target:feedback;property:"contact";to:1;duration:SwirlMotion.pressDuration;easing.type:Easing.OutExpo}
    SpringAnimation{id:contactTravel;target:feedback;property:"contact";to:0;spring:SwirlMotion.interactionSpring;damping:SwirlMotion.interactionDamping;epsilon:0.002}
    NumberAnimation{id:focusTravel;target:feedback;property:"focusAmount";duration:SwirlMotion.focusDuration;easing.type:Easing.OutCubic}
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced)feedback.finish()}}
}
