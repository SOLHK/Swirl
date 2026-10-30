import QtQuick
import SwirlQuick
import "../components"

Item {
    id: transition
    objectName: "activityDetailTransition"
    default property alias contents: detailBody.data
    property SwirlActivityCard sourceCard: null
    property string detailKey: ""
    property string title: ""
    property bool opened: false
    property rect origin: Qt.rect(0, 0, 1, 1)
    property point titleOrigin: Qt.point(18, 16)
    property real titlePixelSize: Theme.fontSize(16)
    property bool returnKeyboardFocus: false
    property rect geometryFrom: Qt.rect(0, 0, 1, 1)
    property rect geometryTo: Qt.rect(0, 0, 1, 1)
    property point headingFrom: Qt.point(18, 16)
    property point headingTo: Qt.point(20, 18)
    property real radiusFrom: Theme.cardRadius
    property real radiusTo: Theme.cardRadius
    property real segmentStart: 0
    property real segmentEnd: 1
    readonly property real progress: clock.progress
    readonly property bool moving: clock.moving
    readonly property bool activeDetail: opened || progress > 0 || moving
    property rect destination: Qt.rect(0, 0, 1, 1)
    readonly property real geometryProgress: segmentStart === segmentEnd ? 1
        : Math.max(0, Math.min(1, (progress - segmentStart) / (segmentEnd - segmentStart)))
    readonly property Item bodyItem: detailBody
    signal returning()
    signal returned()
    visible: activeDetail
    z: 20

    function updateOrigin() {
        if (!sourceCard) return
        const displayed = Qt.rect(surface.x, surface.y, surface.width, surface.height)
        const heading = Qt.point(sharedTitle.x, sharedTitle.y)
        const radius = surface.radius
        const p = sourceCard.mapToItem(transition, 0, 0)
        origin = Qt.rect(p.x, p.y, sourceCard.width, sourceCard.height)
        destination = Qt.rect(Theme.pagePadding, Theme.dp(52),
            Math.max(1, width - 2 * Theme.pagePadding), Math.max(1, height - Theme.dp(68)))
        if (sourceCard.titleItem) {
            titleOrigin = sourceCard.titleItem.mapToItem(sourceCard, 0, 0)
            titlePixelSize = sourceCard.titleItem.font.pixelSize
        }
        // Resizing/reflow changes the endpoint, never the currently drawn card.
        if (activeDetail) setSegment(displayed, heading, radius, opened)
    }
    function setSegment(displayed, heading, radius, expanding) {
        geometryFrom = displayed
        geometryTo = expanding ? destination : origin
        headingFrom = heading
        headingTo = expanding ? Qt.point(Theme.dp(20), Theme.dp(18)) : titleOrigin
        radiusFrom = radius
        radiusTo = expanding ? Theme.cardRadius : sourceCard.radius
        segmentStart = progress
        segmentEnd = expanding ? 1 : 0
    }
    function openFrom(card, key, caption) {
        if (activeDetail) return
        sourceCard = card
        detailKey = key
        title = caption
        returnKeyboardFocus = card.keyboardFocus
        updateOrigin()
        setSegment(origin, titleOrigin, sourceCard.radius, true)
        opened = true
        forceActiveFocus()
        clock.duration = SwirlMotion.ms(380)
        clock.moveTo(1)
    }
    function closeDetail() {
        if (!activeDetail) return false
        if (!opened) return true
        returning()
        updateOrigin()
        setSegment(Qt.rect(surface.x, surface.y, surface.width, surface.height),
            Qt.point(sharedTitle.x, sharedTitle.y), surface.radius, false)
        opened = false
        clock.duration = SwirlMotion.ms(300)
        clock.moveTo(0)
        return true
    }
    function reset() { opened = false; clock.destination = 0; clock.finish() }
    onWidthChanged: Qt.callLater(updateOrigin)
    onHeightChanged: Qt.callLater(updateOrigin)
    onActiveDetailChanged: if (!activeDetail) {
        if (sourceCard && sourceCard.visible) {
            sourceCard.forceActiveFocus()
            sourceCard.keyboardFocus = returnKeyboardFocus
        }
        returned()
    }
    Keys.onEscapePressed: event => {
        if (dismissals.hasPopup(Window.window)) dismissals.dismiss(Window.window)
        else closeDetail()
        event.accepted = true
    }
    SwirlTransitionCoordinator { id: clock }
    // The shield is present for the whole return, including interrupted travel.
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: wheel => wheel.accepted = true }
    SwirlActivitySurface {
        id: surface
        objectName: "activityDetailSurface"
        x: transition.geometryFrom.x + (transition.geometryTo.x - transition.geometryFrom.x) * transition.geometryProgress
        y: transition.geometryFrom.y + (transition.geometryTo.y - transition.geometryFrom.y) * transition.geometryProgress
        width: transition.geometryFrom.width + (transition.geometryTo.width - transition.geometryFrom.width) * transition.geometryProgress
        height: transition.geometryFrom.height + (transition.geometryTo.height - transition.geometryFrom.height) * transition.geometryProgress
        cornerRadius: transition.radiusFrom + (transition.radiusTo - transition.radiusFrom) * transition.geometryProgress
        color: Theme.independentCard
        // Only the simple surface changes dimensions. The details keep their final
        // layout throughout travel and are clipped, never scaled into a texture.
        Item {
            anchors.fill: parent
            clip: true
            SwirlText {
                id: sharedTitle
                objectName: "activityDetailTitle"
                x: transition.headingFrom.x + (transition.headingTo.x - transition.headingFrom.x) * transition.geometryProgress
                y: transition.headingFrom.y + (transition.headingTo.y - transition.headingFrom.y) * transition.geometryProgress
                width: Math.max(0, surface.width - x - Theme.dp(90))
                elide: Text.ElideRight
                text: transition.title
                color: Theme.text
                font.pixelSize: transition.titlePixelSize
                font.weight: Font.DemiBold
            }
            SwirlButton {
                objectName: "activityDetailBack"
                x: transition.destination.width - width - Theme.dp(16)
                y: Theme.dp(14)
                text: qsTr("返回"); iconName: "chevron-left"; quiet: true
                opacity: Math.max(0, (transition.progress - 0.18) / 0.82)
                onClicked: transition.closeDetail()
                Accessible.name: qsTr("返回活动页面")
            }
            Item {
                id: detailBody
                x: Theme.dp(18); y: Theme.dp(66) + Theme.dp(10) * (1 - transition.progress)
                width: Math.max(1, transition.destination.width - Theme.dp(36))
                height: Math.max(1, transition.destination.height - Theme.dp(84))
                opacity: Math.max(0, Math.min(1, (transition.progress - 0.30) / 0.70))
                enabled: transition.opened && transition.progress === 1 && !transition.moving
                visible: opacity > 0
            }
        }
    }
}
