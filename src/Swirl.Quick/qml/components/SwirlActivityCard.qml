import QtQuick
import SwirlQuick

SwirlGlassPanel {
    id: card
    property Item titleItem: null
    property string title: ""
    signal activated()
    default property alias contents: body.data
    interactive: true
    hovered: cardHover.hovered
    pressed: hit.pressed
    focused: activeFocus
    border.color: focused ? Theme.focusBorder : hovered ? Theme.cardHoverBorder : Theme.border
    // Keep the opaque white face; hover changes its edge and contact shadow.
    color: Theme.independentCard
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1详情").arg(title)
    Accessible.onPressAction: activated()
    Keys.onReturnPressed: activated()
    Keys.onSpacePressed: activated()
    transform: Translate {
        y: hit.pressed ? Theme.dp(0.5) : card.hovered || card.activeFocus ? -Theme.dp(1.5) : 0
        Behavior on y { NumberAnimation { duration: SwirlMotion.hoverDuration; easing.type: Easing.OutCubic } }
    }
    HoverHandler { id: cardHover }
    MouseArea {
        id: hit
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { card.forceActiveFocus(); card.activated() }
    }
    Item { id: body; anchors.fill: parent }
}
