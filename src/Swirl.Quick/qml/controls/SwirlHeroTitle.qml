import QtQuick
import SwirlQuick
Item {
    id: hero
    z: 50
    property Item sourceItem: null
    property Item targetItem: null
    property string title: ""
    property rect origin: Qt.rect(0,0,0,0)
    property real sourceFont: Theme.fontSize(12)
    property int duration:SwirlMotion.pageDuration
    readonly property bool moving: clock.moving
    readonly property real progress: clock.progress
    // The target is mapped again as the window/layout changes. Only two small
    // text items participate; no table snapshot or offscreen texture is made.
    readonly property rect targetRect: {
        progress; width; height
        if (!targetItem) return origin
        targetItem.width; targetItem.height; targetItem.x; targetItem.y
        const point = targetItem.mapToItem(hero,0,0)
        const offset = targetItem.horizontalAlignment===Text.AlignHCenter ? Math.max(0,(targetItem.width-targetItem.contentWidth)/2) : 0
        return Qt.rect(point.x+offset,point.y,targetItem.width-offset,targetItem.height)
    }
    function start(source, target, name) {
        cancel()
        if (!source || !target || SwirlMotion.reduced) return
        sourceItem = source; targetItem = target; title = name
        const point = source.mapToItem(hero,0,0)
        origin = Qt.rect(point.x,point.y,source.width,source.height)
        sourceFont = source.font.pixelSize
        clock.progress = 0
        clock.moveTo(1)
    }
    function cancel() {
        clock.finish()
        sourceItem = null; targetItem = null; title = ""
    }
    SwirlTransitionCoordinator { id: clock; duration: hero.duration }
    Connections { target: clock; function onMovingChanged() { if (!clock.moving) { hero.sourceItem=null; hero.targetItem=null; hero.title="" } } }
    Binding { target: hero.sourceItem; property: "opacity"; value: 0; when: hero.moving && hero.sourceItem!==null; restoreMode: Binding.RestoreBindingOrValue }
    Binding { target: hero.targetItem; property: "opacity"; value: 0; when: hero.moving && hero.targetItem!==null; restoreMode: Binding.RestoreBindingOrValue }
    SwirlText {
        visible: hero.moving
        x: hero.origin.x+(hero.targetRect.x-hero.origin.x)*hero.progress
        y: hero.origin.y+(hero.targetRect.y-hero.origin.y)*hero.progress
        width: hero.origin.width+(hero.targetRect.width-hero.origin.width)*hero.progress
        height: hero.origin.height+(hero.targetRect.height-hero.origin.height)*hero.progress
        text: hero.title; textFormat: Text.PlainText; color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Math.round(hero.sourceFont+((hero.targetItem?hero.targetItem.font.pixelSize:hero.sourceFont)-hero.sourceFont)*hero.progress)
        font.weight: Font.DemiBold
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: Text.AlignLeft
        elide: Text.ElideRight
    }
    onVisibleChanged: if (!visible) cancel()
}
