import QtQuick
import SwirlQuick

QtObject {
    id: motion
    property bool initialized:false
    property bool motionEnabled:true
    property var popup:null
    property real progress:1
    property point origin:Qt.point(0,SwirlMotion.popupDistance)
    property int enterDuration:SwirlMotion.dialogDuration
    property int leaveDuration:SwirlMotion.exitDuration
    readonly property real xOffset:motionEnabled?origin.x*(1-progress)+origin.y*0.3*SwirlMotion.arch(progress):0
    readonly property real yOffset:motionEnabled?origin.y*(1-progress)-origin.x*0.3*SwirlMotion.arch(progress):0
    readonly property real alpha:motionEnabled?Math.min(1,progress/0.72):1
    function prepare(vector){
        origin=vector
        if(!motionEnabled || SwirlMotion.reduced)progress=1
        else if(progress===1)progress=0
    }
    function reset(){progress=1}
    // Omitting from is intentional: reopening during exit reverses from the
    // currently displayed point, with no jump to a synthetic start state.
    property Transition enterTransition:Transition {
        enabled:motion.initialized && motion.motionEnabled && !SwirlMotion.reduced
        NumberAnimation {id:enterTravel;target:motion.initialized?motion:null;property:"progress";to:1;duration:motion.enterDuration;easing.type:Easing.OutCubic}
    }
    property Transition exitTransition:Transition {
        enabled:motion.initialized && motion.motionEnabled && !SwirlMotion.reduced
        NumberAnimation {id:leaveTravel;target:motion.initialized?motion:null;property:"progress";to:0;duration:motion.leaveDuration;easing.type:Easing.InOutCubic}
    }
    property Connections policyConnection:Connections {target:motion.initialized?SwirlMotion:null;function onReducedChanged(){if(SwirlMotion.reduced){motion.progress=1;motionPolicy.finishPopup(motion.popup)}}}
    Component.onCompleted:initialized=true
    Component.onDestruction:initialized=false
}
