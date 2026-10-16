import QtQuick
import SwirlQuick
Item {
 id:transfer
 required property Item targetSlot
 property Item sourceRow:null
 property Item sourceViewport:null
 property rect fromRect:Qt.rect(0,0,0,0)
 property rect toRect:Qt.rect(0,0,0,0)
 property bool opened:false
 property bool retargeting:false
 property bool configuring:false
 property real fromReveal:0
 property real toReveal:1
 property int geometryRevision:0
 function refreshGeometry(){++geometryRevision}
 Connections {target:transfer.parent;function onWidthChanged(){Qt.callLater(transfer.refreshGeometry)}function onHeightChanged(){Qt.callLater(transfer.refreshGeometry)}}
 readonly property bool moving:clock.moving
 readonly property string phase:moving?(opened?(retargeting?"Retargeting":"Opening"):"Closing"):(opened?"Open":"Closed")
 readonly property real progress:moving?fromReveal+(toReveal-fromReveal)*clock.progress:(opened?1:0)
 readonly property rect destination:{
  geometryRevision;targetSlot.width;targetSlot.height;targetSlot.x;targetSlot.y
  const p=targetSlot.mapToItem(transfer.parent,0,0)
  return Qt.rect(p.x,p.y,targetSlot.width,targetSlot.height)
 }
 readonly property real cardX:moving?fromRect.x+(toRect.x-fromRect.x)*clock.progress:destination.x
 readonly property real cardY:moving?fromRect.y+(toRect.y-fromRect.y)*clock.progress:destination.y
 readonly property real cardWidth:moving?fromRect.width+(toRect.width-fromRect.width)*clock.progress:destination.width
 readonly property real cardHeight:moving?fromRect.height+(toRect.height-fromRect.height)*clock.progress:destination.height
 readonly property real reveal:progress
 function currentRect(){return Qt.rect(cardX,cardY,cardWidth,cardHeight)}
 function sourceRect(row){
  if(row&&row.visible){
   const p=row.mapToItem(transfer.parent,0,0)
   let left=p.x,top=p.y,right=p.x+row.width,bottom=p.y+row.height
   // Intersect in the animation's coordinate space, including horizontal
   // scrolling and every clipping ancestor, not just the ListView's Y axis.
   for(let ancestor=row.parent;ancestor;ancestor=ancestor.parent){
    if(!ancestor.visible){right=left;break}
    if(ancestor.clip||ancestor===sourceViewport){
     const a=ancestor.mapToItem(transfer.parent,0,0)
     left=Math.max(left,a.x);top=Math.max(top,a.y)
     right=Math.min(right,a.x+ancestor.width);bottom=Math.min(bottom,a.y+ancestor.height)
    }
   }
   if(right>left&&bottom>top)return Qt.rect(left,top,right-left,bottom-top)
  }
  return Qt.rect(destination.x-Theme.dp(16),destination.y,destination.width,destination.height)
 }
 function start(row){
  refreshGeometry()
  const wasOpen=opened&&!moving
  const current=moving?currentRect():(wasOpen?destination:sourceRect(row))
  const currentReveal=reveal
  configuring=true;clock.stop();sourceRow=row;retargeting=wasOpen
  opened=true;fromReveal=currentReveal;toReveal=1;fromRect=current;toRect=destination;clock.progress=0;clock.moveTo(1);configuring=false
 }
 function returnTo(row){
  const current=currentRect()
  const currentReveal=reveal
  configuring=true;clock.stop();retargeting=false;sourceRow=row
  opened=false;fromReveal=currentReveal;toReveal=0;fromRect=current;toRect=sourceRect(row);clock.progress=0;clock.moveTo(1);configuring=false
 }
 onOpenedChanged:if(!configuring){if(opened)start(sourceRow);else returnTo(sourceRow)}
 onDestinationChanged:if(moving&&!configuring){
  const current=currentRect(),currentReveal=reveal;configuring=true;clock.stop();fromRect=current;fromReveal=currentReveal;toReveal=opened?1:0
  toRect=opened?destination:sourceRect(sourceRow);clock.progress=0;clock.moveTo(1);configuring=false
 }
 SwirlTransitionCoordinator {id:clock;duration:SwirlMotion.expandDuration
  onMovingChanged:if(!moving&&!transfer.configuring&&!transfer.opened&&transfer.sourceRow&&transfer.sourceRow.visible)transfer.sourceRow.forceActiveFocus()
 }
 Component.onCompleted:{clock.destination=1;clock.finish()}
}
