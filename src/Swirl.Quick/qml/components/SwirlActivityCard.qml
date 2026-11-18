import QtQuick
import SwirlQuick

SwirlCardSurface {
    id: card
    property Item titleItem: null
    property string title: ""
    readonly property Item decorationLayer: decorations
    property bool keyboardPressed: false
    property bool keyboardFocus: false
    signal activated()
    default property alias contents: body.data
    hovered: cardHover.hovered
    pressed: false
    focused: activeFocus && keyboardFocus
    property real lift: hovered || focused ? -Theme.dp(1.5) : 0
    Behavior on lift { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.ms(150); easing.type: Easing.OutCubic } }
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("%1详情").arg(title)
    Accessible.onPressAction: activated()
    onActiveFocusChanged: {
        // A parked pointer must not hide focus reached with Tab. Pointer
        // activation clears this after taking focus, in the same event turn.
        if (activeFocus) keyboardFocus = true
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
        onClicked: { card.forceActiveFocus(Qt.MouseFocusReason); card.keyboardFocus = false; card.activated() }
    }
    Item {
        id: decorations
        parent: card
        // Stay inside the continuous rounded fill, leaving its edge clear.
        x: card.radius * 0.25; y: x
        width: card.width - 2 * x; height: card.height - 2 * y
        clip: true; enabled: false; Accessible.ignored: true
    }
    Item { id: body; objectName: "activityCardContent"; anchors.fill: parent; z: 1 }
}
