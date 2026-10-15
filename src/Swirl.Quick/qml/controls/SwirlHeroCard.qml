import QtQuick
import SwirlQuick
import "../components"
SwirlGlassPanel {
    id: card
    property bool expanded: false
    property real collapsedHeight: 0
    property real expandedHeight: collapsedHeight
    readonly property real reveal: clock.progress
    readonly property bool moving: clock.moving
    height: Math.round(collapsedHeight+(expandedHeight-collapsedHeight)*reveal)
    cornerRadius: Theme.independentCardRadius
    clip: true
    interactive: true
    onExpandedChanged: clock.moveTo(expanded?1:0)
    onVisibleChanged:if(!visible)clock.finish()
    Connections {target:card.Window.window;function onVisibilityChanged(){if(card.Window.window.visibility===Window.Minimized)clock.finish()}}
    SwirlTransitionCoordinator { id: clock }
    Component.onCompleted: { clock.destination=expanded?1:0; clock.finish() }
}
