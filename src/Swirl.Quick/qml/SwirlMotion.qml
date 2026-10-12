pragma Singleton
import QtQuick
import SwirlQuick
QtObject {
    id: motion
    // Animation policy only: no colors, sizes, fonts or layout tokens live here.
    property real speed: 1
    readonly property bool reduced: Theme.reduceMotion || motionPolicy.systemReducedMotion
    readonly property real spring: 3.2 * speed * speed
    readonly property real damping: 0.28
    readonly property int duration: reduced ? 0 : Math.round(180 / speed)
    readonly property real pressScale: reduced ? 1 : 0.972
    property bool transitioning: false
    onTransitioningChanged:motionPolicy.setTransitioning(transitioning)
    property var triggerRect: Qt.rect(0,0,0,0)
    property var navigationRect: null
    property var shared: null
    property var returnShared: null
    property int sharedGeneration: 0
    function noteTrigger(item) {
        const p=item.mapToItem(null,0,0)
        triggerRect=Qt.rect(p.x,p.y,item.width,item.height)
    }
    function popupOrigin(popup) {
        if (!popup.parent || triggerRect.width===0) return Item.Center
        const p=popup.parent.mapToItem(null,popup.x,popup.y)
        const x=triggerRect.x+triggerRect.width/2-p.x
        const y=triggerRect.y+triggerRect.height/2-p.y
        return y<popup.height/3 ? (x<popup.width/3?Item.TopLeft:x>popup.width*2/3?Item.TopRight:Item.Top) :
               y>popup.height*2/3 ? (x<popup.width/3?Item.BottomLeft:x>popup.width*2/3?Item.BottomRight:Item.Bottom) : Item.Center
    }
    function navigateFrom(item, route) {
        if (reduced || !motionPolicy.complexMotion) { AppState.navigate(route); return }
        const generation=++sharedGeneration
        const point=item.mapToItem(null,0,0)
        const origin=Qt.rect(point.x,point.y,item.width,item.height)
        const previous=AppState.currentPage
        // The item remains alive until the asynchronous scene-graph grab completes.
        const accepted=motionPolicy.capture(item,function(grabId,url) {
            if (generation!==sharedGeneration || AppState.currentPage!==previous) {motionPolicy.releaseGrab(grabId);return}
            shared={route:route,previous:previous,rect:origin,grabId:grabId,url:url,reverse:false}
            returnShared={route:route,previous:previous,rect:origin}
            AppState.navigate(route)
        })
        if(!accepted)AppState.navigate(route)
    }
    function returnToHub(item) {
        if (returnShared && returnShared.route===AppState.currentPage && !reduced) {
            const p=item.mapToItem(null,0,0)
            const data=returnShared
            const generation=++sharedGeneration
            const accepted=motionPolicy.capture(item,function(grabId,url) {
                if(generation!==sharedGeneration){motionPolicy.releaseGrab(grabId);return}
                shared={route:data.previous,previous:data.route,rect:Qt.rect(p.x,p.y,item.width,item.height),
                        target:data.rect,grabId:grabId,url:url,reverse:true}
                AppState.navigate(data.previous)
            })
            if(!accepted)AppState.navigate(data.previous)
        } else AppState.navigate("featurehub")
    }
}
