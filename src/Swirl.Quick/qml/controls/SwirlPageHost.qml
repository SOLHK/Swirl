import QtQuick
import QtQuick.Effects
import SwirlQuick
import "../components"
Item {
    id: host
    property Component sourceComponent
    property string routeKey
    readonly property Item item: activeLoader ? activeLoader.item : null
    readonly property int cachedPageCount: Object.keys(pages).length
    readonly property bool moving: travel.running
    property var pages: ({})
    property var savedPages: ({})
    property var accessOrder: []
    property int maximumCachedPages: 28
    function trimCache() {
        const next=Object.assign({},pages)
        const saved=Object.assign({},savedPages)
        for(const key of accessOrder) {
            if(Object.keys(next).length<=maximumCachedPages)break
            const loader=next[key]
            if(!loader || loader===activeLoader || loader===leavingLoader || !loader.item || !loader.item.exportCacheState)continue
            // Only pages with an explicit restore contract can be retired.
            saved[key]=loader.item.exportCacheState();loader.destroy();delete next[key]
        }
        pages=next;savedPages=saved
    }
    property var activeLoader: null
    property var leavingLoader: null
    property real progress: 1
    readonly property real position: Math.max(0, Math.min(1, progress))
    readonly property bool pendingGrab: false
    readonly property var heroData: null
    readonly property bool contained: routeKey!=="activity" && routeKey!=="overview" && routeKey!=="rewrite" && routeKey!=="proxies"
    property bool initialized: false
    clip: moving
    Item { id:viewport; anchors.fill:parent; clip:host.contained || host.moving }
    function pageOffset(route) { return route === "overview" || route === "activity" ? 0 : Theme.dp(0) }
    function releaseShared() {
        if (SwirlMotion.shared && SwirlMotion.shared.grabId) motionPolicy.releaseGrab(SwirlMotion.shared.grabId)
        SwirlMotion.shared = null
    }
    function finish() {
        hero.cancel()
        travel.stop(); progress = 1
        if (leavingLoader) leavingLoader.visible = false
        leavingLoader = null
        if (activeLoader) { activeLoader.visible = true; activeLoader.enabled = true }
        trimCache()
        releaseShared(); SwirlMotion.transitioning = false
    }
    function requestRoute() {
        if (!initialized || !sourceComponent || !routeKey.length) return
        let next = pages[routeKey]
        if (!next) {
            next = pageFactory.createObject(host, {routeId: routeKey, sourceComponent: sourceComponent})
            if (!next || !next.item) { if(next)next.destroy(); return }
            if(savedPages[routeKey] && next.item.restoreCacheState)next.item.restoreCacheState(savedPages[routeKey])
            const updated = Object.assign({}, pages); updated[routeKey] = next; pages = updated
        }
        const sharedRequest=SwirlMotion.shared
        const returnRequest=SwirlMotion.returnShared
        releaseShared()
        if (next === activeLoader) return
        // Rapid retargeting retires the old outgoing page immediately. Every
        // route owns one persistent tree, including its drafts and scroll state.
        finish()
        const previous = activeLoader
        if (previous) motionPolicy.leavePage(previous.item)
        leavingLoader = previous; activeLoader = next
        accessOrder=accessOrder.filter(key=>key!==routeKey).concat([routeKey])
        for (const key of Object.keys(pages)) {
            pages[key].visible = pages[key] === next || pages[key] === previous
            pages[key].enabled = pages[key] === next
        }
        if (!previous || SwirlMotion.reduced) { finish(); return }
        progress = 0; SwirlMotion.transitioning = true; travel.restart()
        if(sharedRequest && next.item.heroTargets && next.item.heroTargets[sharedRequest.targetKey])hero.start(sharedRequest.source,next.item.heroTargets[sharedRequest.targetKey],sharedRequest.text)
        else if(AppState.navigationDirection<0 && returnRequest && returnRequest.previous===routeKey && previous.item.heroTargets && previous.item.heroTargets[returnRequest.targetKey])hero.start(previous.item.heroTargets[returnRequest.targetKey],returnRequest.source,previous.item.heroTargets[returnRequest.targetKey].text)
    }
    onRouteKeyChanged: Qt.callLater(requestRoute)
    Component.onCompleted: { initialized = true; Qt.callLater(requestRoute) }
    Component.onDestruction: { initialized = false; releaseShared(); SwirlMotion.transitioning = false; SwirlMotion.returnShared = null }
    Connections { target: SwirlMotion; function onReducedChanged() { if(SwirlMotion.reduced) host.finish() } }
    Component {
        id: pageFactory
        Loader { parent:viewport; property string routeId; x:0; y:host.pageOffset(routeId); width:host.width; height:host.height-host.pageOffset(routeId); visible:false }
    }
    Binding { target:host.activeLoader; property:"opacity"; value:host.moving ? host.position : 1; when:host.activeLoader!==null }
    Binding { target:host.activeLoader; property:"y"; value:host.activeLoader ? host.pageOffset(host.activeLoader.routeId)+(host.moving?AppState.navigationDirection*Theme.dp(6)*(1-host.position):0) : 0; when:host.activeLoader!==null }
    Binding { target:host.leavingLoader; property:"opacity"; value:1-host.position; when:host.leavingLoader!==null }
    Binding { target:host.leavingLoader; property:"y"; value:host.leavingLoader ? host.pageOffset(host.leavingLoader.routeId)-AppState.navigationDirection*Theme.dp(3)*host.position : 0; when:host.leavingLoader!==null }
    NumberAnimation { id:travel; target:host; property:"progress"; from:0; to:1; duration:SwirlMotion.pageDuration; easing.type:Easing.OutCubic; onFinished:host.finish() }
    SwirlHeroTitle {id:hero;anchors.fill:parent}
}
