import QtQuick
import SwirlQuick
Item {
    id: host
    property Component sourceComponent
    property string routeKey
    readonly property Item item: activeLoader ? activeLoader.item : null
    readonly property int cachedPageCount: Object.keys(pages).length
    readonly property bool moving: travel.running
    property var pages: ({})
    property var activeLoader: null
    property var leavingLoader: null
    property real progress: 1
    readonly property real position: Math.max(0, Math.min(1, progress))
    readonly property bool pendingGrab: false
    readonly property var heroData: null
    property bool initialized: false
    clip: moving
    function pageOffset(route) { return route === "overview" ? 0 : Theme.dp(46) }
    function releaseShared() {
        if (SwirlMotion.shared) motionPolicy.releaseGrab(SwirlMotion.shared.grabId)
        SwirlMotion.shared = null
    }
    function finish() {
        travel.stop(); progress = 1
        if (leavingLoader) leavingLoader.visible = false
        leavingLoader = null
        if (activeLoader) { activeLoader.visible = true; activeLoader.enabled = true }
        releaseShared(); SwirlMotion.transitioning = false
    }
    function requestRoute() {
        if (!initialized || !sourceComponent || !routeKey.length) return
        let next = pages[routeKey]
        if (!next) {
            next = pageFactory.createObject(host, {routeId: routeKey, sourceComponent: sourceComponent})
            if (!next || !next.item) { if(next)next.destroy(); return }
            const updated = Object.assign({}, pages); updated[routeKey] = next; pages = updated
        }
        releaseShared()
        if (next === activeLoader) return
        // Rapid retargeting retires the old outgoing page immediately. Every
        // route owns one persistent tree, including its drafts and scroll state.
        finish()
        const previous = activeLoader
        if (previous) motionPolicy.leavePage(previous.item)
        leavingLoader = previous; activeLoader = next
        for (const key of Object.keys(pages)) {
            pages[key].visible = pages[key] === next || pages[key] === previous
            pages[key].enabled = pages[key] === next
        }
        if (!previous || SwirlMotion.reduced) { finish(); return }
        progress = 0; SwirlMotion.transitioning = true; travel.restart()
    }
    onRouteKeyChanged: Qt.callLater(requestRoute)
    Component.onCompleted: { initialized = true; Qt.callLater(requestRoute) }
    Component.onDestruction: { initialized = false; releaseShared(); SwirlMotion.transitioning = false; SwirlMotion.returnShared = null }
    Connections { target: SwirlMotion; function onReducedChanged() { if(SwirlMotion.reduced) host.finish() } }
    Component {
        id: pageFactory
        Loader { property string routeId; x:0; y:host.pageOffset(routeId); width:host.width; height:host.height-y; visible:false }
    }
    Binding { target:host.activeLoader; property:"opacity"; value:host.moving ? host.position : 1; when:host.activeLoader!==null }
    Binding { target:host.activeLoader; property:"y"; value:host.activeLoader ? host.pageOffset(host.activeLoader.routeId)+(host.moving?Theme.dp(6)*(1-host.position):0) : 0; when:host.activeLoader!==null }
    Binding { target:host.leavingLoader; property:"opacity"; value:1-host.position; when:host.leavingLoader!==null }
    Binding { target:host.leavingLoader; property:"y"; value:host.leavingLoader ? host.pageOffset(host.leavingLoader.routeId)-Theme.dp(3)*host.position : 0; when:host.leavingLoader!==null }
    NumberAnimation { id:travel; target:host; property:"progress"; from:0; to:1; duration:180; easing.type:Easing.OutCubic; onFinished:host.finish() }
}
