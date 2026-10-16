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
 property var pendingLoader:null
 property bool preparing:false
 property int generation:0
 property bool initialized:false
 property bool animateRoutes:true
 property bool incubateRoutes:true
 property var insetRoutes:[]
 property real routeInset:0
 function insetFor(key){return insetRoutes.indexOf(key)>=0?routeInset:0}
 property int transitionToken:0
 readonly property Item item:activeLoader?activeLoader.item:null
 readonly property int cachedPageCount:Object.keys(pages).length
 readonly property bool moving:travel.running
 readonly property bool pendingGrab:pendingLoader!==null || preparing
 property real progress:1
 readonly property real position:Math.max(0,Math.min(1,progress))
 property var heroData:null
 property Item sourceSurface:null
 property Item targetSurface:null
 property rect surfaceStart:Qt.rect(0,0,0,0)
 property rect surfaceEnd:Qt.rect(0,0,0,0)
 property rect retargetRequestedRect:Qt.rect(0,0,0,0)
 property rect retargetCommittedRect:Qt.rect(0,0,0,0)
 readonly property bool contained:routeKey!=="activity"&&routeKey!=="overview"&&routeKey!=="rewrite"&&routeKey!=="proxies"
 clip:true
 Item {id:viewport;anchors.fill:parent;z:1}
 function rectFor(item){const p=item.mapToItem(host,0,0),q=item.mapToItem(host,item.width,item.height);return Qt.rect(p.x,p.y,q.x-p.x,q.y-p.y)}
 function ramp(value,start,end){const t=Math.max(0,Math.min(1,(value-start)/(end-start)));return t*t*(3-2*t)}
 readonly property real pageReveal:heroData!==null && heroData.key==="settings"?ramp(position,heroData.returning?0:0.20,heroData.returning?0.70:0.82):position
 function valid(item){return item && item.width>0 && item.height>0}
 function sampledColor(item){
  if(item && item.color!==undefined){const c=item.color;return Qt.rgba(c.r,c.g,c.b,c.a)}
  return Qt.rgba(Theme.independentCard.r,Theme.independentCard.g,Theme.independentCard.b,0)
 }
 function surfaceFor(page,key){return page.motionSurfaces && page.motionSurfaces[key] || page.motionSurface || null}
 function trimCache(){
  const next=Object.assign({},pages),saved=Object.assign({},savedPages)
  for(const key of accessOrder){if(Object.keys(next).length<=maximumCachedPages)break;const loader=next[key];if(!loader || loader===activeLoader || loader===leavingLoader || loader===pendingLoader || !loader.item || !loader.item.exportCacheState || (SwirlMotion.returnShared && SwirlMotion.returnShared.previous===key))continue;saved[key]=loader.item.exportCacheState();loader.destroy();delete next[key]}
  pages=next;savedPages=saved
 }
 function releaseShared(){SwirlMotion.shared=null}
 function releaseSurfaces(){
  if(sourceSurface && sourceSurface.surfaceHidden!==undefined)sourceSurface.surfaceHidden=false
  if(targetSurface && targetSurface.surfaceHidden!==undefined)targetSurface.surfaceHidden=false
 }
 function finish(){
  preparing=false
  travel.stop();progress=1
  releaseSurfaces()
  hero.cancel()
  sourceSurface=null;targetSurface=null;heroData=null
  for(const key of Object.keys(pages)){const loader=pages[key];loader.visible=loader===activeLoader;loader.enabled=loader===activeLoader;loader.startOpacity=loader===activeLoader?1:0;loader.endOpacity=loader.startOpacity}
  leavingLoader=null
  if(activeLoader){activeLoader.visible=true;activeLoader.enabled=true}
  SwirlTransitionRegistry.setActive(transitionToken,false);trimCache()
  const back=SwirlMotion.returnShared,focus=back?(back.card || back.source):null;if(back && back.previous===routeKey && focus && focus.visible)focus.forceActiveFocus()
 }
 function captureOpacities(next){
  // Snapshot all live layers before retargeting. A third click must not drop
  // the still-visible first page or reset the incoming page to transparent.
  const values=Object.keys(pages).map(key=>({loader:pages[key],alpha:pages[key].visible?pages[key].opacity:0}))
  for(const value of values){value.loader.startOpacity=value.alpha;value.loader.endOpacity=value.loader===next?1:0;value.loader.visible=value.alpha>0||value.loader===next;value.loader.enabled=value.loader===next}
 }
 function requestRoute(){
  if(!initialized || !sourceComponent || !routeKey.length)return
  const token=++generation
  let next=pages[routeKey]
  if(!next){
   // Incubate cold pages across frames while the current live page stays
   // visible. The initial page remains synchronous so startup has content.
   next=pageFactory.createObject(viewport,{routeId:routeKey,asynchronous:incubateRoutes&&activeLoader!==null,sourceComponent:sourceComponent})
   if(!next){releaseShared();return}
   const copy=Object.assign({},pages);copy[routeKey]=next;pages=copy
  }
  if(next.status===Loader.Loading){pendingLoader=next;return}
  pendingLoader=null
  if(!next.item){const copy=Object.assign({},pages);delete copy[routeKey];pages=copy;next.destroy();releaseShared();return}
  if(!next.stateRestored){if(savedPages[routeKey]&&next.item.restoreCacheState)next.item.restoreCacheState(savedPages[routeKey]);next.stateRestored=true}
  if(next===activeLoader){releaseShared();return}
  const request=SwirlMotion.shared,back=SwirlMotion.returnShared
  releaseShared()
  // Reverse the same two live trees without visiting either endpoint.
  if(moving && next===leavingLoader){
   const current=Qt.rect(morph.x,morph.y,morph.width,morph.height)
   retargetRequestedRect=current
   captureOpacities(next)
   travel.stop();const previous=activeLoader;activeLoader=leavingLoader;leavingLoader=previous
   const color=sampledColor(morph);if(heroData && heroData.key==="settings")heroData=Object.assign({},heroData,{fromColor:color,toColor:heroData.fromColor,returning:!heroData.returning})
   const rect=surfaceStart;surfaceStart=current;surfaceEnd=rect
   const surface=sourceSurface;sourceSurface=targetSurface;targetSurface=surface
   hero.reverse()
   progress=0;activeLoader.enabled=true;leavingLoader.enabled=false
   retargetCommittedRect=Qt.rect(morph.x,morph.y,morph.width,morph.height)
   animate();return
  }
  // A third route supersedes stale preparation and callbacks immediately.
  const carry=moving&&heroData?Qt.rect(morph.x,morph.y,morph.width,morph.height):null
  captureOpacities(next)
  travel.stop();hero.cancel()
  releaseSurfaces();sourceSurface=null;targetSurface=null;heroData=null
  const previous=activeLoader
  if(previous)motionPolicy.leavePage(previous.item)
  leavingLoader=previous;activeLoader=next
  preparing=true
  accessOrder=accessOrder.filter(key=>key!==routeKey).concat([routeKey])
  progress=0
  if(!previous || SwirlMotion.reduced || !animateRoutes){finish();return}
  // Let normal Qt polish settle layouts once. No recursive per-item polishing.
  next.item.ensurePolished()
  Qt.callLater(function(){
   if(token!==generation || activeLoader!==next)return
   let from=null,to=null,source=null,target=null
   if(request){from=request.surface;to=request.targetKey==="settings"?next.item:surfaceFor(next.item,request.targetKey);source=request.source;target=request.targetKey==="settings"?next.item.motionTitle:next.item.heroTargets?next.item.heroTargets[request.targetKey]:null}
   else if(back && back.previous===routeKey && back.route===previous.routeId){from=back.targetKey==="settings"?previous.item:surfaceFor(previous.item,back.targetKey);to=back.surface;source=back.targetKey==="settings"?previous.item.motionTitle:previous.item.heroTargets?previous.item.heroTargets[back.targetKey]:null;target=back.source}
   if(valid(from)&&valid(to)){sourceSurface=from;targetSurface=to;surfaceStart=carry||rectFor(from);surfaceEnd=rectFor(to);heroData={key:request?request.targetKey:back.targetKey,card:request?request.card:back.card,returning:!request,fromColor:sampledColor(from),toColor:sampledColor(to)};if(from.surfaceHidden!==undefined)from.surfaceHidden=true;if(to.surfaceHidden!==undefined)to.surfaceHidden=true}
   if(valid(source)&&valid(target))hero.start(source,target,source.text||"")
   animate()
  })
 }
 function animate(){preparing=false;SwirlTransitionRegistry.setActive(transitionToken,true);travel.from=progress;travel.to=1;travel.duration=Math.max(1,(heroData?SwirlMotion.expandDuration:SwirlMotion.pageDuration)*(1-progress));travel.start()}
 function retargetGeometry(){
  if(!moving || !heroData || !valid(targetSurface))return
  const current=Qt.rect(morph.x,morph.y,morph.width,morph.height)
  captureOpacities(activeLoader)
  travel.stop();surfaceStart=current;surfaceEnd=rectFor(targetSurface);progress=0;animate()
 }
 onWidthChanged:Qt.callLater(retargetGeometry)
 onHeightChanged:Qt.callLater(retargetGeometry)
 onRouteKeyChanged:Qt.callLater(requestRoute)
 Component.onCompleted:{transitionToken=SwirlTransitionRegistry.allocate();initialized=true;Qt.callLater(requestRoute)}
 Component.onDestruction:{releaseSurfaces();initialized=false;++generation;releaseShared();SwirlTransitionRegistry.setActive(transitionToken,false);SwirlMotion.returnShared=null}
 Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced){++host.generation;host.finish()}}}
 Component {id:pageFactory;Item {
  id:cachedLoader
  property string routeId
  property alias sourceComponent:pageContent.sourceComponent
  property alias asynchronous:pageContent.asynchronous
  readonly property alias status:pageContent.status
  readonly property alias item:pageContent.item
  property bool stateRestored:false
  property real startOpacity:0
  property real endOpacity:0
  opacity:startOpacity+(endOpacity-startOpacity)*host.pageReveal
  x:0;y:host.insetFor(routeId);width:host.width;height:host.height-y;visible:false
  z:host.heroData && host.heroData.key==="settings" && host.heroData.returning?
      (host.leavingLoader===cachedLoader?2:0):(host.activeLoader===cachedLoader?2:0)
  readonly property bool expandingDetails:host.heroData!==null && host.heroData.key==="settings" &&
      (host.heroData.returning?host.leavingLoader===cachedLoader:host.activeLoader===cachedLoader)
  // This is the animated reveal boundary, not a layout workaround. The page
  // keeps its final layout size throughout; only the visible expansion region
  // follows the same surface clock, without a second fade/geometry owner.
  Item {
   id:revealViewport
   x:cachedLoader.expandingDetails?morph.x-cachedLoader.x:0
   y:cachedLoader.expandingDetails?morph.y-cachedLoader.y:0
   width:cachedLoader.expandingDetails?morph.width:cachedLoader.width
   height:cachedLoader.expandingDetails?morph.height:cachedLoader.height
   clip:cachedLoader.expandingDetails
   Loader {
    id:pageContent
    readonly property string routeId:cachedLoader.routeId
    x:-revealViewport.x;y:-revealViewport.y;width:cachedLoader.width;height:cachedLoader.height
    onStatusChanged:if(cachedLoader===host.pendingLoader && status!==Loader.Loading)Qt.callLater(host.requestRoute)
   }
  }
 }}
 // Live trees cross-fade continuously; shared surfaces and titles keep their
 // independent geometry animation. Only the destination accepts input.
 SwirlGlassPanel {
  id:morph;objectName:"sharedSurface";parent:viewport;z:1;visible:host.heroData!==null
  readonly property bool settingsTransition:host.heroData!==null && host.heroData.key==="settings"
  readonly property real materialReveal:settingsTransition?host.ramp(host.position,host.heroData.returning?0:0.65,host.heroData.returning?0.35:0.92):host.position
  independentCard:!settingsTransition
  border.width:0
  x:host.surfaceStart.x+(host.surfaceEnd.x-host.surfaceStart.x)*host.position
  y:host.surfaceStart.y+(host.surfaceEnd.y-host.surfaceStart.y)*host.position
  width:host.surfaceStart.width+(host.surfaceEnd.width-host.surfaceStart.width)*host.position
  height:host.surfaceStart.height+(host.surfaceEnd.height-host.surfaceStart.height)*host.position
  cornerRadius:(host.sourceSurface && host.sourceSurface.radius!==undefined?host.sourceSurface.radius:settingsTransition?Theme.cardRadius:0)*(1-host.position)+(host.targetSurface && host.targetSurface.radius!==undefined?host.targetSurface.radius:settingsTransition?Theme.cardRadius:0)*host.position
  color:host.heroData && host.heroData.key==="settings"?Qt.rgba(
    host.heroData.returning?host.heroData.toColor.r:host.heroData.fromColor.r,
    host.heroData.returning?host.heroData.toColor.g:host.heroData.fromColor.g,
    host.heroData.returning?host.heroData.toColor.b:host.heroData.fromColor.b,
    host.heroData.fromColor.a*(1-materialReveal)+host.heroData.toColor.a*materialReveal):Theme.independentCard
  Column {
   readonly property var card:morph.settingsTransition?host.heroData.card:null
   x:Theme.cardPadding;y:Theme.cardPadding;spacing:Theme.dp(12)
   width:card && card.contentItem?card.contentItem.width:0
   visible:card!==null && card.motionIcon!==undefined
   opacity:!morph.settingsTransition?0:host.heroData.returning?host.ramp(host.position,0.65,1):1-host.ramp(host.position,0,0.35)
   SwirlIcon {name:parent.card && parent.card.motionIcon!==undefined?parent.card.motionIcon:"";size:Theme.dp(34);color:Theme.accent}
   Item {width:parent.width;height:parent.card && parent.card.motionTitle?parent.card.motionTitle.height:0}
   SwirlText {width:parent.width;text:parent.card && parent.card.motionDescription!==undefined?parent.card.motionDescription:"";font.pixelSize:Theme.fontSize(11);color:Theme.muted;wrapMode:Text.WordWrap}
  }
 }
 NumberAnimation {id:travel;objectName:"pageTravel";target:host;property:"progress";easing.type:Easing.OutCubic;onFinished:host.finish()}
 SwirlHeroTitle {id:hero;objectName:"pageHeroTitle";anchors.fill:parent;progress:host.position}
}
