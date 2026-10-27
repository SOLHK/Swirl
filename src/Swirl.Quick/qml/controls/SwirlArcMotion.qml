import QtQuick
import SwirlQuick

// Presentation-only clock. Input geometry remains stationary and interactive.
// Cubic Hermite endpoints preserve the rendered position and velocity when a
// new destination interrupts an active trajectory; the lateral lobe has zero
// derivative at both ends. No timer or animation runs at rest.
Item {
    id: arc
    property real targetX:0
    property real targetY:0
    property int duration:SwirlMotion.selectionDuration
    property real bend:SwirlMotion.navigationArc
    property bool motionEnabled:true
    property real progress:1
    property point start:Qt.point(0,0)
    property point destination:Qt.point(0,0)
    property point tangent:Qt.point(0,0)
    property point normal:Qt.point(1,0)
    property bool initialized:false
    property int token:0
    property int generation:0
    readonly property bool moving:travel.running
    readonly property bool windowVisible:!Window.window || (Window.window.visible && Window.window.visibility!==Window.Minimized)
    readonly property real u:Math.max(0,Math.min(1,progress))
    readonly property real h:3*u*u-2*u*u*u
    readonly property real v:u*u*u-2*u*u+u
    readonly property point position:Qt.point(start.x+(destination.x-start.x)*h+tangent.x*v+normal.x*bend*SwirlMotion.arch(u),
                                             start.y+(destination.y-start.y)*h+tangent.y*v+normal.y*bend*SwirlMotion.arch(u))
    readonly property point velocity:Qt.point(((destination.x-start.x)*(6*u-6*u*u)+tangent.x*(3*u*u-4*u+1)+normal.x*bend*32*u*(1-u)*(1-2*u))/Math.max(1,travel.duration),
                                             ((destination.y-start.y)*(6*u-6*u*u)+tangent.y*(3*u*u-4*u+1)+normal.y*bend*32*u*(1-u)*(1-2*u))/Math.max(1,travel.duration))
    function settle(){travel.stop();start=Qt.point(targetX,targetY);destination=start;tangent=Qt.point(0,0);progress=1}
    function retarget(){
        if(!initialized)return
        const current=Qt.point(position.x,position.y), speed=moving?Qt.point(velocity.x,velocity.y):Qt.point(0,0)
        const target=Qt.point(targetX,targetY),dx=target.x-current.x,dy=target.y-current.y
        if(Math.hypot(dx,dy)<0.01){settle();return}
        ++generation
        travel.stop()
        if(!motionEnabled || !visible || !windowVisible || SwirlMotion.reduced){settle();return}
        start=current;destination=target
        const length=Math.max(1,Math.hypot(dx,dy)),time=Math.max(1,duration)
        // Limit carried velocity only for a near-coincident destination, where
        // an old distant throw would otherwise overshoot several target rows.
        const carry=Math.min(1,length*2.4/Math.max(1,Math.hypot(speed.x,speed.y)*time))
        tangent=Qt.point(speed.x*time*carry,speed.y*time*carry)
        normal=Qt.point(Math.abs(dy)/length,-dx/length*(dy<0?-1:1))
        progress=0;travel.duration=time;travel.start()
    }
    onTargetXChanged:Qt.callLater(retarget)
    onTargetYChanged:Qt.callLater(retarget)
    onMotionEnabledChanged:if(initialized && !motionEnabled)settle()
    onVisibleChanged:if(initialized && !visible)settle()
    onWindowVisibleChanged:if(initialized && !windowVisible)settle()
    onMovingChanged:SwirlTransitionRegistry.setActive(token,moving)
    Component.onCompleted:{token=SwirlTransitionRegistry.allocate();settle();initialized=true}
    Component.onDestruction:SwirlTransitionRegistry.setActive(token,false)
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced)arc.settle()}}
    NumberAnimation {id:travel;target:arc;property:"progress";from:0;to:1;easing.type:Easing.Linear}
}
