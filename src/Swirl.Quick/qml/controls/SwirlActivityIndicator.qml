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
    RotationAnimation {
        target:mark;property:"rotation";from:0;to:360;duration:900;loops:Animation.Infinite
        running:indicator.busy && indicator.visible && indicator.Window.window && indicator.Window.window.visible && indicator.Window.window.visibility!==Window.Minimized && !SwirlMotion.reduced
        onRunningChanged:if(!running)mark.rotation=0
    }
}
