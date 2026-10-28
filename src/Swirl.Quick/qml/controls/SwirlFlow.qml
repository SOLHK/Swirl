import QtQuick
import SwirlQuick

// A state consumer, never a source of business success. Callers bind phase to
// actual pending/succeeded/failed receipts. Idle and reduced-motion are static.
Item {
    id: flow
    property string phase:"idle"
    property real sweep:1
    property real clock:0
    property bool initialized:false
    readonly property bool pending:phase==="pending"
    readonly property bool windowVisible:!Window.window || (Window.window.visible && Window.window.visibility!==Window.Minimized)
    readonly property bool animate:visible && windowVisible && !SwirlMotion.reduced
    readonly property bool moving:pendingClock.running || successClock.running
    readonly property real head:pending?clock:phase==="succeeded"?sweep:1
    implicitWidth:Theme.dp(40)
    implicitHeight:Theme.dp(18)
    Accessible.ignored:true
    function updatePhase(){
        if(!initialized)return
        successClock.stop()
        if(phase==="succeeded" && animate){sweep=0;successClock.start()}else sweep=1
    }
    onPhaseChanged:updatePhase()
    onAnimateChanged:if(initialized && !animate){successClock.stop();sweep=1}
    Component.onCompleted:{initialized=true;updatePhase()}
    NumberAnimation {id:pendingClock;target:flow;property:"clock";from:0;to:1;duration:Math.max(1,SwirlMotion.activityCycleDuration/SwirlMotion.flowSpeed);loops:Animation.Infinite;running:flow.pending && flow.animate}
    NumberAnimation {id:successClock;target:flow;property:"sweep";from:0;to:1;duration:SwirlMotion.successDuration;easing.type:Easing.OutCubic}
    Image {
        anchors.fill: parent
        source: "qrc:/swirl/icons/swirl-wing.svg"
        sourceSize: Qt.size(Math.ceil(width * Screen.devicePixelRatio), Math.ceil(height * Screen.devicePixelRatio))
        fillMode: Image.PreserveAspectFit
        opacity: flow.phase === "idle" ? 0.62 : flow.pending ? 0.72 + 0.28 * Math.sin(flow.clock * Math.PI) : 1
        scale: flow.phase === "succeeded" ? 0.94 + 0.06 * flow.sweep : 1
    }
}
