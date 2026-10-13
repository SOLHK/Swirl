import QtQuick
import QtQuick.Controls
import SwirlQuick
ScrollBar {
    id:bar
    hoverEnabled:true
    padding:Theme.dp(2)
    implicitWidth:Theme.dp(10)
    minimumSize:0.08
    policy:ScrollBar.AsNeeded
    property bool recent:false
    onActiveChanged:if(active){recent=true;fadeDelay.restart()}
    Timer { id:fadeDelay; interval:900; onTriggered:bar.recent=false }
    contentItem:Rectangle {
        implicitWidth:Theme.dp(5); implicitHeight:Theme.dp(5)
        radius:width/2; color:Theme.muted
        opacity:bar.size>=1?0:bar.pressed?0.8:(bar.active||bar.hovered||bar.recent||motionPolicy.alwaysShowScrollbars)?0.45:0
        Behavior on opacity { NumberAnimation { duration:SwirlMotion.reduced?0:180 } }
    }
    background:Item {}
}
