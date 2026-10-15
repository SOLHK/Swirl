import QtQuick
import SwirlQuick
import "../components"
Item {
 id:host
 property Component sourceComponent
 property string routeKey
 property var pages:({})
 property var savedPages:({})
 property var accessOrder:[]
 property int maximumCachedPages:28
 property var activeLoader:null
 property var leavingLoader:null
 property int generation:0
 property bool initialized:false
 property bool animateRoutes:true
 readonly property Item item:activeLoader?activeLoader.item:null
 readonly property int cachedPageCount:Object.keys(pages).length
 readonly property bool moving:travel.running
 readonly property bool pendingGrab:false
 property real progress:1
 property real departureOpacity:1
 readonly property real position:Math.max(0,Math.min(1,progress))
 property var heroData:null
 property Item sourceSurface:null
 property Item targetSurface:null
 property rect surfaceStart:Qt.rect(0,0,0,0)
 property rect surfaceEnd:Qt.rect(0,0,0,0)
 readonly property bool contained:routeKey!=="activity"&&routeKey!=="overview"&&routeKey!=="rewrite"&&routeKey!=="proxies"
 clip:true
 Item {id:viewport;anchors.fill:parent;z:1}
 function rectFor(item){const p=item.mapToItem(host,0,0);return Qt.rect(p.x,p.y,item.width,item.height)}
 function valid(item){return item && item.width>0 && item.height>0}
 function surfaceFor(page,key){return page.motionSurfaces && page.motionSurfaces[key] || page.motionSurface || null}
 function trimCache(){
  const next=Object.assign({},pages),saved=Object.assign({},savedPages)
  for(const key of accessOrder){if(Object.keys(next).length<=maximumCachedPages)break;const loader=next[key];if(!loader || loader===activeLoader || loader===leavingLoader || !loader.item || !loader.item.exportCacheState || (SwirlMotion.returnShared && SwirlMotion.returnShared.previous===key))continue;saved[key]=loader.item.exportCacheState();loader.destroy();delete next[key]}
  pages=next;savedPages=saved
 }
 function releaseShared(){SwirlMotion.shared=null}
 function releaseSurfaces(){
  if(sourceSurface && sourceSurface.surfaceHidden!==undefined)sourceSurface.surfaceHidden=false
  if(targetSurface && targetSurface.surfaceHidden!==undefined)targetSurface.surfaceHidden=false
 }
 function finish(){
  releaseSurfaces()
  travel.stop();hero.cancel();progress=1
  sourceSurface=null;targetSurface=null;heroData=null
  if(leavingLoader){leavingLoader.visible=false;leavingLoader.enabled=false}
  leavingLoader=null
  if(activeLoader){activeLoader.visible=true;activeLoader.enabled=true}
  SwirlMotion.transitioning=false;trimCache()
  const back=SwirlMotion.returnShared;if(back && back.previous===routeKey && back.source && back.source.visible)back.source.forceActiveFocus()
 }
 function requestRoute(){
  if(!initialized || !sourceComponent || !routeKey.length)return
  const token=++generation
  let next=pages[routeKey]
  if(!next){next=pageFactory.createObject(viewport,{routeId:routeKey,sourceComponent:sourceComponent});if(!next || !next.item){if(next)next.destroy();releaseShared();return}if(savedPages[routeKey]&&next.item.restoreCacheState)next.item.restoreCacheState(savedPages[routeKey]);const copy=Object.assign({},pages);copy[routeKey]=next;pages=copy}
  if(next===activeLoader){releaseShared();return}
  const request=SwirlMotion.shared,back=SwirlMotion.returnShared
  releaseShared()
  // Reverse the same two live trees without visiting either endpoint.
  if(moving && next===leavingLoader){
   travel.stop();const previous=activeLoader;activeLoader=leavingLoader;leavingLoader=previous
   const rect=surfaceStart;surfaceStart=surfaceEnd;surfaceEnd=rect
   const surface=sourceSurface;sourceSurface=targetSurface;targetSurface=surface
   progress=1-progress;activeLoader.enabled=true;leavingLoader.enabled=false
   hero.reverse();animate();return
  }
  // A third route supersedes stale preparation and callbacks immediately.
  const carry=moving&&heroData?Qt.rect(morph.x,morph.y,morph.width,morph.height):null
  const previousOpacity=activeLoader?activeLoader.opacity:1
  travel.stop();hero.cancel()
  if(leavingLoader)leavingLoader.visible=false
  releaseSurfaces();sourceSurface=null;targetSurface=null;heroData=null
  const previous=activeLoader
  if(previous)motionPolicy.leavePage(previous.item)
  leavingLoader=previous;activeLoader=next;departureOpacity=previousOpacity
  accessOrder=accessOrder.filter(key=>key!==routeKey).concat([routeKey])
  for(const key of Object.keys(pages)){pages[key].visible=pages[key]===next || pages[key]===previous;pages[key].enabled=pages[key]===next}
  progress=0
  if(!previous || SwirlMotion.reduced || !animateRoutes){finish();return}
  // Let normal Qt polish settle layouts once. No recursive per-item polishing.
  next.item.ensurePolished()
  Qt.callLater(function(){
   if(token!==generation || activeLoader!==next)return
   let from=null,to=null,source=null,target=null
   if(request){from=request.surface;to=surfaceFor(next.item,request.targetKey);source=request.source;target=next.item.heroTargets?next.item.heroTargets[request.targetKey]:null}
   else if(back && back.previous===routeKey && back.route===previous.routeId){from=surfaceFor(previous.item,back.targetKey);to=back.surface;source=previous.item.heroTargets?previous.item.heroTargets[back.targetKey]:null;target=back.source}
   if(valid(from)&&valid(to)){sourceSurface=from;targetSurface=to;surfaceStart=carry||rectFor(from);surfaceEnd=rectFor(to);heroData={key:request?request.targetKey:back.targetKey};if(from.surfaceHidden!==undefined)from.surfaceHidden=true;if(to.surfaceHidden!==undefined)to.surfaceHidden=true}
   hero.duration=heroData?SwirlMotion.expandDuration:SwirlMotion.pageDuration
   if(valid(source)&&valid(target))hero.start(source,target,source.text||"")
   animate()
  })
 }
 function animate(){SwirlMotion.transitioning=true;travel.from=progress;travel.to=1;travel.duration=Math.max(1,(heroData?SwirlMotion.expandDuration:SwirlMotion.pageDuration)*(1-progress));travel.start()}
 function retargetGeometry(){
  if(!moving || !heroData || !valid(targetSurface))return
  const current=Qt.rect(morph.x,morph.y,morph.width,morph.height)
  travel.stop();surfaceStart=current;surfaceEnd=rectFor(targetSurface);progress=0;animate()
 }
 onWidthChanged:Qt.callLater(retargetGeometry)
 onHeightChanged:Qt.callLater(retargetGeometry)
 onRouteKeyChanged:Qt.callLater(requestRoute)
 Component.onCompleted:{initialized=true;Qt.callLater(requestRoute)}
 Component.onDestruction:{releaseSurfaces();initialized=false;++generation;releaseShared();SwirlMotion.transitioning=false;SwirlMotion.returnShared=null}
 Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced){++host.generation;host.finish()}}}
 Component {id:pageFactory;Loader {property string routeId;x:0;y:0;width:host.width;height:host.height;visible:false}}
 // The two pages never paint full content over each other. Shared text lives above them.
 Binding {target:host.activeLoader;property:"opacity";value:host.leavingLoader?Math.max(0,2*host.position-1):1;when:host.activeLoader!==null}
 Binding {target:host.leavingLoader;property:"opacity";value:host.departureOpacity*Math.max(0,1-2*host.position);when:host.leavingLoader!==null}
 SwirlGlassPanel {
  id:morph;objectName:"sharedSurface";z:0;visible:host.heroData!==null
  x:host.surfaceStart.x+(host.surfaceEnd.x-host.surfaceStart.x)*host.position
  y:host.surfaceStart.y+(host.surfaceEnd.y-host.surfaceStart.y)*host.position
  width:host.surfaceStart.width+(host.surfaceEnd.width-host.surfaceStart.width)*host.position
  height:host.surfaceStart.height+(host.surfaceEnd.height-host.surfaceStart.height)*host.position
  cornerRadius:(host.sourceSurface?host.sourceSurface.radius:Theme.cardRadius)*(1-host.position)+(host.targetSurface?host.targetSurface.radius:Theme.cardRadius)*host.position
 }
 NumberAnimation {id:travel;target:host;property:"progress";easing.type:Easing.OutCubic;onFinished:host.finish()}
 SwirlHeroTitle {id:hero;anchors.fill:parent}
}
