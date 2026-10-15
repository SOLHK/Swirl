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
    function ms(value){return reduced ? 0 : Math.round(value/Math.max(0.25,speed))}
    readonly property int duration:ms(180)
    readonly property int pressDuration:ms(110)
    readonly property int hoverDuration:ms(150)
    readonly property int switchDuration:ms(180)
    readonly property int pageDuration:ms(160)
    readonly property int dialogDuration:ms(264)
    readonly property int exitDuration:ms(160)
    readonly property int expandDuration:ms(288)
    readonly property real pressScale: reduced ? 1 : 0.972
    property bool transitioning: false
    readonly property bool busy: transitioning || SwirlTransitionRegistry.activeCount>0
    onBusyChanged:motionPolicy.setTransitioning(busy)
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
    function navigateFrom(item, route, targetKey) {
        const titleItem=item.motionTitle || item
        const surface=item.motionSurface || (item.motionTitle?item:null)
        // Existing Activity/traffic links remain title-only. A card explicitly
        // supplies its material/heading and keeps the original shared boundary.
        shared={source:titleItem,surface:surface,route:route,previous:AppState.currentPage,
            targetKey:targetKey || "title",text:titleItem.text || ""}
        returnShared={route:route,previous:AppState.currentPage,source:titleItem,
            surface:surface,targetKey:targetKey || "title"}
        AppState.navigate(route)
    }
    function returnToHub(item) {
        AppState.navigate(returnShared && returnShared.route===AppState.currentPage ? returnShared.previous : "featurehub")
    }
}
