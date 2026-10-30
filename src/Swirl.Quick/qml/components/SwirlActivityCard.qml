import QtQuick
import SwirlQuick

SwirlCardSurface {
    id: card
    property Item titleItem: null
    property string title: ""
    property bool keyboardPressed: false
    property bool keyboardFocus: false
    signal activated()
    default property alias contents: body.data
    hovered: cardHover.hovered
    pressed: false
    focused: activeFocus && keyboardFocus
    property real lift: hovered ? -Theme.dp(1.5) : 0
    Behavior on lift { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.ms(150); easing.type: Easing.OutCubic } }
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
        y: card.lift
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
