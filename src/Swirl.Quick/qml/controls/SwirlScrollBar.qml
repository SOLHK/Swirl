import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
ScrollBar {
    id:bar
    hoverEnabled:true
    padding:Theme.dp(2)
    implicitWidth:Theme.dp(10)
    minimumSize:0.08
    policy:ScrollBar.AsNeeded
    readonly property bool needed:policy===ScrollBar.AlwaysOn || (policy===ScrollBar.AsNeeded && size<1)
    visible:needed
    property bool recent:false
    onActiveChanged:if(active){recent=true;fadeDelay.restart()}
    Timer { id:fadeDelay; interval:900; onTriggered:bar.recent=false }
    contentItem:Rectangle {
        implicitWidth:Theme.dp(5); implicitHeight:Theme.dp(5)
        radius:width/2; color:Theme.muted
        property real animatedOpacity:!bar.needed?0:bar.pressed?0.8:(bar.active||bar.hovered||bar.recent||motionPolicy.alwaysShowScrollbars)?0.45:0.22
        opacity:bar.needed?animatedOpacity:0
        Behavior on animatedOpacity { enabled:!SwirlMotion.reduced; NumberAnimation { duration:SwirlMotion.releaseDuration } }
    }
    background:Item {}
}
