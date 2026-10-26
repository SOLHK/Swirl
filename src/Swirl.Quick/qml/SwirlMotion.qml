pragma Singleton
import QtQuick
import SwirlQuick
QtObject {
    id: motion
    // Animation policy only: no colors, sizes, fonts or layout tokens live here.
    property real speed: 1
    readonly property bool reduced: Theme.reduceMotion || (Theme.followSystemMotion && motionPolicy.systemReducedMotion)
    readonly property real spring: 3.2 * speed * speed
    readonly property real damping: 0.28
    readonly property int standardEasing: Easing.OutCubic
    function ms(value){return reduced ? 0 : Math.round(value/Math.max(0.25,speed))}
    readonly property int duration:ms(180)
    readonly property int pressDuration:ms(70)
    readonly property int releaseDuration:ms(140)
    readonly property int selectionDuration:ms(240)
    readonly property int hoverDuration:ms(110)
    readonly property int focusDuration:ms(150)
    readonly property int switchDuration:ms(210)
    readonly property int pageDuration:ms(300)
    readonly property int returnDuration:ms(240)
    readonly property int dialogDuration:ms(280)
    readonly property int exitDuration:ms(180)
    readonly property int menuEnterDuration:ms(170)
    readonly property int menuExitDuration:ms(110)
    readonly property int listDuration:ms(180)
    readonly property int expandDuration:ms(360)
    readonly property int statusDuration:ms(160)
    readonly property int activityCycleDuration:ms(900)
    readonly property int successDuration:ms(520)
    readonly property int rowStagger:ms(24)
    readonly property real navigationArc:Theme.dp(9)
    readonly property real pageDistance:Theme.dp(18)
    readonly property real pageArc:Theme.dp(7)
    readonly property real popupDistance:Theme.dp(18)
    readonly property real flowSpeed:0.85
    readonly property real interactionSpring:4.2
    readonly property real interactionDamping:0.38
    // A bounded perpendicular excursion; zero slope at either endpoint.
    function arch(t){const u=Math.max(0,Math.min(1,t));return 16*u*u*(1-u)*(1-u)}
    function popupVector(popup) {
        if(!popup.parent || triggerRect.width===0)return Qt.point(0,popupDistance)
        const p=popup.parent.mapToItem(null,popup.x+popup.width/2,popup.y+popup.height/2)
        const dx=triggerRect.x+triggerRect.width/2-p.x,dy=triggerRect.y+triggerRect.height/2-p.y
        const length=Math.max(1,Math.hypot(dx,dy))
        return Qt.point(dx/length*popupDistance,dy/length*popupDistance)
    }
    readonly property real pressScale: reduced ? 1 : 0.98
    property bool transitioning: false
    readonly property bool busy: transitioning || SwirlTransitionRegistry.activeCount>0
    onBusyChanged:motionPolicy.setTransitioning(busy)
    property var triggerRect: Qt.rect(0,0,0,0)
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
        // Stable semantic keys pair the same metric and its surface across routes.
        shared={generation:++sharedGeneration,source:titleItem,surface:surface,card:item,route:route,previous:AppState.currentPage,
            targetKey:targetKey || "title",text:titleItem.text || ""}
        returnShared={route:route,previous:AppState.currentPage,source:titleItem,card:item,
            surface:surface,targetKey:targetKey || "title"}
        AppState.openDetail(route)
    }
    function returnToHub(item) {
        if(AppState.canGoBack)AppState.goBack()
        else AppState.navigate(returnShared && returnShared.route===AppState.currentPage ? returnShared.previous : "featurehub")
    }
}
