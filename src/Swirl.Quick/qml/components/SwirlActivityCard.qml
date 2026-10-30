import QtQuick
import SwirlQuick

SwirlGlassPanel {
    id: card
    property Item titleItem: null
    property string title: ""
    property bool keyboardPressed: false
    property bool keyboardFocus: false
    signal activated()
    default property alias contents: body.data
    interactive: true
    hovered: cardHover.hovered
    pressed: hit.pressed || keyboardPressed
    focused: activeFocus && keyboardFocus
    border.color: focused ? Theme.focusBorder : hovered ? Theme.cardHoverBorder : Theme.border
    // Keep the opaque white face; hover changes its edge and contact shadow.
    color: Theme.independentCard
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1详情").arg(title)
    Accessible.onPressAction: activated()
    onActiveFocusChanged: {
        if (activeFocus) keyboardFocus = !hit.containsMouse
        else keyboardPressed = false
    }
    Keys.onPressed: event => {
        if (!card.activeFocus) return
        if (event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter && event.key !== Qt.Key_Space) return
        keyboardFocus = true
        if (!event.isAutoRepeat) keyboardPressed = true
        event.accepted = true
    }
    Keys.onReleased: event => {
        if (!card.activeFocus) return
        if (event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter && event.key !== Qt.Key_Space) return
        if (!event.isAutoRepeat && keyboardPressed) {
            keyboardPressed = false
            activated()
        }
        event.accepted = true
    }
    transform: Translate {
        y: card.pressed ? Theme.dp(1) : card.hovered || card.focused ? -Theme.dp(1.5) : 0
        Behavior on y { NumberAnimation { duration: SwirlMotion.ms(card.pressed ? 90 : 150); easing.type: Easing.OutCubic } }
    }
    HoverHandler { id: cardHover }
    MouseArea {
        id: hit
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { card.keyboardFocus = false; card.forceActiveFocus(); card.activated() }
    }
    Item { id: body; anchors.fill: parent }
}
