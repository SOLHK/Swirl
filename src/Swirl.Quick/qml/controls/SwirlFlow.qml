import QtQuick
import QtQuick.Shapes
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
    ShaderEffect {
        anchors.fill:parent
        visible:Theme.effectsSupported && !Theme.increaseContrast
        property vector2d surfaceSize:Qt.vector2d(width,height)
        property real head:flow.head
        property real pending:flow.pending?1:0
        property real energy:flow.phase==="idle"?0:1
        property color coldColor:flow.phase==="failed"?Theme.red:Theme.accent
        fragmentShader:"qrc:/swirl/shaders/swirl-flow.frag.qsb"
    }
    // Software/high-contrast material fallback retains the same two curves;
    // it intentionally does not claim to render the shader's travelling light.
    Shape {
        anchors.fill:parent;visible:!Theme.effectsSupported || Theme.increaseContrast
        ShapePath {strokeColor:flow.phase==="failed"?Theme.red:Theme.accent;strokeWidth:Theme.dp(2);fillColor:"transparent";capStyle:ShapePath.RoundCap
            startX:flow.width*0.06;startY:flow.height*0.8
            PathCubic {control1X:flow.width*0.3;control1Y:flow.height*0.8;control2X:flow.width*0.56;control2Y:flow.height*0.1;x:flow.width*0.94;y:flow.height*0.2}
        }
        ShapePath {strokeColor:Theme.withAlpha(Theme.accent,0.45);strokeWidth:Theme.dp(1.5);fillColor:"transparent";capStyle:ShapePath.RoundCap
            startX:flow.width*0.17;startY:flow.height*0.95
            PathCubic {control1X:flow.width*0.43;control1Y:flow.height*0.95;control2X:flow.width*0.63;control2Y:flow.height*0.35;x:flow.width*0.87;y:flow.height*0.43}
        }
    }
}
