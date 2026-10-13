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
    property var visits: []
    property var activeLoader: null
    property var leavingLoader: null
    property int frozenGrab: 0
    property real progress: 1
    readonly property real position: Math.max(0,Math.min(1,progress))
    property int direction: 1
    property int generation: 0
    property bool initialized: false
    property bool pendingGrab: false
    property var heroData: null
    property rect heroStart
    property rect heroEnd
    clip: moving || pendingGrab
    function pageOffset(route) { return route==="overview" || route==="activity" ? 0 : Theme.dp(46) }
    function targetRect(root) {
        if(!root)return Qt.rect(0,0,width,height)
        if(root.objectName==="motion-detail") {
            const p=root.mapToItem(host,0,0)
            return Qt.rect(p.x,p.y,root.width,root.height)
        }
        for(let i=0;i<root.children.length;i++) {
            const result=findTarget(root.children[i])
            if(result)return result
        }
        return Qt.rect(0,pageOffset(routeKey),width,height-pageOffset(routeKey))
    }
    function findTarget(root) {
        if(root.objectName==="motion-detail") {
            const p=root.mapToItem(host,0,0)
            return Qt.rect(p.x,p.y,root.width,root.height)
        }
        for(let i=0;i<root.children.length;i++){const found=findTarget(root.children[i]);if(found)return found}
        return null
    }
    function finish() {
        travel.stop(); progress=1
        if(leavingLoader) { leavingLoader.visible=false; leavingLoader.x=0 }
        leavingLoader=null
        if(activeLoader){activeLoader.visible=true;activeLoader.x=0;activeLoader.enabled=true}
        frozen.visible=false; frozen.source=""; motionPolicy.releaseGrab(frozenGrab); frozenGrab=0
        if(heroData)motionPolicy.releaseGrab(heroData.grabId)
        heroData=null; SwirlMotion.shared=null; SwirlMotion.transitioning=false
    }
    function showRoute(snapshot) {
        if(!initialized || !sourceComponent || !routeKey.length){if(snapshot)motionPolicy.releaseGrab(snapshot.id);return}
        const key=routeKey
        let next=pages[key]
        if(!next) {
            next=pageFactory.createObject(host,{routeId:key,sourceComponent:sourceComponent})
            if(!next || !next.item) {if(next)next.destroy();if(snapshot)motionPolicy.releaseGrab(snapshot.id);return}
            const updated=Object.assign({},pages)
            updated[key]=next
            pages=updated
        }
        // Cache is bounded by the finite route catalogue; a route owns exactly one
        // Loader. Keeping its QObject tree preserves drafts, selection and scroll,
        // including state that cannot safely be serialized into generic properties.
        visits=visits.filter(function(id){return id!==key}).concat([key])
        if(next===activeLoader && !snapshot)return
        const previous=activeLoader
        if(previous && previous!==next)motionPolicy.leavePage(previous.item)
        if(leavingLoader && leavingLoader!==previous)leavingLoader.visible=false
        travel.stop()
        leavingLoader=previous
        activeLoader=next
        for(const id of Object.keys(pages)) {
            const page=pages[id]
            page.visible=page===next || (!snapshot && page===previous)
            page.enabled=page===next
            page.x=0
        }
        if(!previous || SwirlMotion.reduced) {if(snapshot)motionPolicy.releaseGrab(snapshot.id);finish();return}
        direction=AppState.navigationHistory.indexOf(key)<AppState.navigationHistory.indexOf(previous.routeId)?-1:1
        if(snapshot){motionPolicy.releaseGrab(frozenGrab);frozenGrab=snapshot.id;frozen.source=snapshot.url;frozen.visible=true}
        else {frozen.visible=false;frozen.source="";motionPolicy.releaseGrab(frozenGrab);frozenGrab=0}
        progress=0
        if(heroData)motionPolicy.releaseGrab(heroData.grabId)
        heroData=SwirlMotion.shared && SwirlMotion.shared.route===key?SwirlMotion.shared:null
        if(heroData) {
            const p=host.mapFromItem(null,heroData.rect.x,heroData.rect.y)
            heroStart=Qt.rect(p.x,p.y,heroData.rect.width,heroData.rect.height)
            if(heroData.reverse) {
                const end=host.mapFromItem(null,heroData.target.x,heroData.target.y)
                heroEnd=Qt.rect(end.x,end.y,heroData.target.width,heroData.target.height)
            } else heroEnd=targetRect(next.item)
        }
        SwirlMotion.transitioning=true
        Qt.callLater(function(){if(host.moving)leavingTexture.scheduleUpdate()})
        travel.restart()
    }
    function sharedItem(root) {
        if(!root)return null
        if(root.objectName==="motion-detail")return root
        for(let i=0;i<root.children.length;i++){const found=sharedItem(root.children[i]);if(found)return found}
        return null
    }
    function requestRoute() {
        if(!initialized)return
        ++generation
        if(pendingGrab)return
        const returning=SwirlMotion.returnShared
        if(returning && activeLoader && routeKey===returning.previous && activeLoader.routeId===returning.route &&
           !SwirlMotion.shared && !SwirlMotion.reduced && motionPolicy.complexMotion) {
            const detail=sharedItem(activeLoader.item)
            if(detail) {
                const start=detail.mapToItem(null,0,0)
                pendingGrab=true
                const accepted=motionPolicy.capture(detail,function(grabId,url) {
                    if(!host || !host.initialized){motionPolicy.releaseGrab(grabId);return}
                    pendingGrab=false
                    if(routeKey!==returning.previous){motionPolicy.releaseGrab(grabId);requestRoute();return}
                    SwirlMotion.shared={route:returning.previous,previous:returning.route,
                        rect:Qt.rect(start.x,start.y,detail.width,detail.height),target:returning.rect,
                        grabId:grabId,url:url,reverse:true}
                    showRoute(null)
                })
                if(accepted)return
                pendingGrab=false
            }
        }
        if(moving && motionPolicy.complexMotion && !SwirlMotion.reduced) {
            // Snapshot the currently composed viewport before retargeting. The
            // callback uses the latest requested route; no stale page can win.
            pendingGrab=true
            travel.pause()
            const accepted=motionPolicy.capture(host,function(grabId,url){
                if(!host || !host.initialized){motionPolicy.releaseGrab(grabId);return}
                pendingGrab=false
                showRoute({id:grabId,url:url})
            })
            if(!accepted){pendingGrab=false;finish();showRoute(null)}
        } else {if(moving)finish();showRoute(null)}
    }
    onRouteKeyChanged: Qt.callLater(requestRoute)
    Component.onCompleted: {initialized=true;Qt.callLater(requestRoute)}
    Component.onDestruction: {initialized=false;motionPolicy.releaseGrab(frozenGrab);if(heroData)motionPolicy.releaseGrab(heroData.grabId);SwirlMotion.transitioning=false;SwirlMotion.shared=null;SwirlMotion.returnShared=null}
    Connections {
        target:SwirlMotion
        function onReducedChanged(){if(SwirlMotion.reduced)host.finish()}
    }
    Component {
        id:pageFactory
        Loader {
            property string routeId
            y:host.pageOffset(routeId)
            width:host.width; height:host.height-y
            visible:false
        }
    }
    Binding { target:host.activeLoader; property:"x"; value:host.moving ? host.direction*host.width*(1-host.position) : 0; when:host.activeLoader!==null }
    Binding { target:host.leavingLoader; property:"x"; value:-host.direction*host.width*host.position; when:host.leavingLoader!==null }
    // Cache the leaving page on the GPU for ordinary transitions. Its QObject
    // tree and state stay alive, while only one live page needs to be drawn.
    ShaderEffectSource {
        id:leavingTexture
        sourceItem:visible?host.leavingLoader:null
        visible:motionPolicy.complexMotion && host.moving && host.leavingLoader!==null && !frozen.visible
        hideSource:true;live:!visible
        x:-host.direction*host.width*host.position
        y:host.leavingLoader?host.leavingLoader.y:0
        width:host.width
        height:host.leavingLoader?host.leavingLoader.height:0
        z:5
    }
    Image {
        id:frozen
        cache:false
        width:host.width;height:host.height
        x:-host.direction*host.width*host.position
        visible:false;z:10
    }
    Image {
        id:hero;z:11
        cache:false
        visible:host.heroData!==null && host.moving
        source:host.heroData?host.heroData.url:""
        x:host.heroStart.x+(host.heroEnd.x-host.heroStart.x)*host.position
        y:host.heroStart.y+(host.heroEnd.y-host.heroStart.y)*host.position
        width:host.heroStart.width+(host.heroEnd.width-host.heroStart.width)*host.position
        height:host.heroStart.height+(host.heroEnd.height-host.heroStart.height)*host.position
        opacity:Math.min(1,(1-host.position)*7)
    }
    SwirlSpring {
        id:travel;target:host;property:"progress";from:0;to:1
        spring:SwirlMotion.spring*0.55; damping:0.24
        onFinished:host.finish()
    }
}
