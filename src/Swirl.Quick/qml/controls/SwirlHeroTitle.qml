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
    property real sourceWeight:Font.DemiBold
    property real sourceBaseline:0
    property real progress:0
    property bool active:false
    readonly property bool moving:active
    // The page host owns the only clock. Restore the real title before that
    // clock completes, so retiring the shared layer cannot remove a glyph.
    readonly property real handoff: {
        const t=Math.max(0,Math.min(1,(progress-0.92)/0.07))
        return t*t*(3-2*t)
    }
    readonly property Item labelItem:label
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
        sourceWeight=source.font.weight
        sourceBaseline=source.baselineOffset
        active=true
    }
    function reverse() {
        if(!sourceItem || !targetItem)return
        const oldSource=sourceItem,oldTarget=targetItem
        const current=Qt.rect(label.x,label.y,label.width,label.height)
        const currentFont=label.font.pixelSize
        const currentWeight=label.font.weight
        const currentBaseline=label.baselineOffset
        sourceItem=oldTarget;targetItem=oldSource;title=oldTarget.text||"";origin=current;sourceFont=currentFont
        sourceWeight=currentWeight
        sourceBaseline=currentBaseline
    }
    function retarget() {
        if(!active || !targetItem)return
        const current=Qt.rect(label.x,label.y,label.width,label.height)
        const currentFont=label.font.pixelSize,currentWeight=label.font.weight,currentBaseline=label.baselineOffset
        if(handoff>0.5)title=targetItem.text||title
        origin=current;sourceFont=currentFont;sourceWeight=currentWeight;sourceBaseline=currentBaseline
    }
    function cancel() {
        active=false
        sourceItem = null; targetItem = null; title = ""
    }
    Binding { target: hero.sourceItem; property: "opacity"; value: 0; when: hero.moving && hero.sourceItem!==null; restoreMode: Binding.RestoreBindingOrValue }
    Binding { target: hero.targetItem; property: "opacity"; value: hero.handoff; when: hero.moving && hero.targetItem!==null; restoreMode: Binding.RestoreBindingOrValue }
    SwirlText {
        id:label;objectName:"sharedTitle"
        fitWidth: false // The shared title retains its existing transform/size animation.
        textRole:hero.targetItem && hero.targetItem.textRole ? hero.targetItem.textRole : "pageTitle"
        visible: hero.moving
        opacity:1-hero.handoff
        x: hero.origin.x+(hero.targetRect.x-hero.origin.x)*hero.progress
        y: hero.origin.y+(hero.targetRect.y-hero.origin.y)*hero.progress+
           hero.sourceBaseline*(1-hero.progress)+(hero.targetItem?hero.targetItem.baselineOffset:hero.sourceBaseline)*hero.progress-baselineOffset
        width: hero.origin.width+(hero.targetRect.width-hero.origin.width)*hero.progress
        height: hero.origin.height+(hero.targetRect.height-hero.origin.height)*hero.progress
        text: hero.title; textFormat: Text.PlainText; color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Math.round(hero.sourceFont+((hero.targetItem?hero.targetItem.font.pixelSize:hero.sourceFont)-hero.sourceFont)*hero.progress)
        font.weight: Math.round(hero.sourceWeight+((hero.targetItem?hero.targetItem.font.weight:hero.sourceWeight)-hero.sourceWeight)*hero.progress)
        font.italic: hero.targetItem?hero.targetItem.font.italic:false
        verticalAlignment: Text.AlignTop
        horizontalAlignment: Text.AlignLeft
        elide: Text.ElideRight
    }
    onVisibleChanged: if (!visible) cancel()
}
