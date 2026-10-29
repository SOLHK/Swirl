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
    readonly property real progress: clock.progress
    readonly property bool moving: clock.moving
    readonly property bool activeDetail: opened || progress > 0 || moving
    readonly property rect destination: Qt.rect(Theme.pagePadding, Theme.dp(52),
        Math.max(1, width - 2 * Theme.pagePadding), Math.max(1, height - Theme.dp(68)))
    readonly property Item bodyItem: detailBody
    signal returned()
    visible: activeDetail
    z: 20

    function updateOrigin() {
        if (!sourceCard) return
        const p = sourceCard.mapToItem(transition, 0, 0)
        origin = Qt.rect(p.x, p.y, sourceCard.width, sourceCard.height)
        if (sourceCard.titleItem) {
            titleOrigin = sourceCard.titleItem.mapToItem(sourceCard, 0, 0)
            titlePixelSize = sourceCard.titleItem.font.pixelSize
        }
    }
    function openFrom(card, key, caption) {
        if (activeDetail) return
        sourceCard = card
        detailKey = key
        title = caption
        updateOrigin()
        opened = true
        forceActiveFocus()
        clock.duration = SwirlMotion.ms(410)
        clock.moveTo(1)
    }
    function closeDetail() {
        if (!activeDetail) return false
        if (!opened) return true
        updateOrigin()
        opened = false
        clock.duration = SwirlMotion.ms(350)
        clock.moveTo(0)
        return true
    }
    function reset() { opened = false; clock.destination = 0; clock.finish() }
    onWidthChanged: Qt.callLater(updateOrigin)
    onHeightChanged: Qt.callLater(updateOrigin)
    onActiveDetailChanged: if (!activeDetail) {
        if (sourceCard && sourceCard.visible) sourceCard.forceActiveFocus()
        returned()
    }
    Keys.onEscapePressed: event => { closeDetail(); event.accepted = true }
    SwirlTransitionCoordinator { id: clock }
    // The shield is present for the whole return, including interrupted travel.
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: wheel => wheel.accepted = true }
    SwirlGlassPanel {
        id: surface
        objectName: "activityDetailSurface"
        x: transition.origin.x + (transition.destination.x - transition.origin.x) * transition.progress
        y: transition.origin.y + (transition.destination.y - transition.origin.y) * transition.progress
        width: transition.origin.width + (transition.destination.width - transition.origin.width) * transition.progress
        height: transition.origin.height + (transition.destination.height - transition.origin.height) * transition.progress
        cornerRadius: transition.sourceCard ? transition.sourceCard.radius + (Theme.dp(32) - transition.sourceCard.radius) * transition.progress : Theme.dp(32)
        color: Theme.independentCard
        // Only the simple surface changes dimensions. The details keep their final
        // layout throughout travel and are clipped, never scaled into a texture.
        Item {
            anchors.fill: parent
            clip: true
            SwirlText {
                id: sharedTitle
                objectName: "activityDetailTitle"
                x: transition.titleOrigin.x + (Theme.dp(20) - transition.titleOrigin.x) * transition.progress
                y: transition.titleOrigin.y + (Theme.dp(18) - transition.titleOrigin.y) * transition.progress
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
