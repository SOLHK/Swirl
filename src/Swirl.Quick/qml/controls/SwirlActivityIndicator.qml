import QtQuick
import SwirlQuick
import "../components"
Item {
    id:indicator
    property bool busy:false
    property color color:Theme.accent
    implicitWidth:Theme.dp(14);implicitHeight:implicitWidth
    visible:busy
    SwirlIcon{id:mark;anchors.centerIn:parent;name:"refresh";size:indicator.width;color:indicator.color}
    RotationAnimator {
        target:mark;from:0;to:360;duration:Math.max(1,SwirlMotion.activityCycleDuration);loops:Animation.Infinite
        running:indicator.busy && indicator.visible && indicator.Window.window && indicator.Window.window.visible && indicator.Window.window.visibility!==Window.Minimized && !SwirlMotion.reduced
        onRunningChanged:if(!running)mark.rotation=0
    }
}
