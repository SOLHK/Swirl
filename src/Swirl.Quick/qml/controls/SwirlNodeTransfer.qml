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
 property int geometryRevision:0
 function refreshGeometry(){++geometryRevision}
 Connections {target:transfer.parent;function onWidthChanged(){Qt.callLater(transfer.refreshGeometry)}function onHeightChanged(){Qt.callLater(transfer.refreshGeometry)}}
 readonly property bool moving:clock.moving
 readonly property string phase:moving?(opened?(retargeting?"Retargeting":"Opening"):"Closing"):(opened?"Open":"Closed")
 readonly property real progress:moving?(opened?clock.progress:1-clock.progress):(opened?1:0)
 readonly property rect destination:{
  geometryRevision;targetSlot.width;targetSlot.height;targetSlot.x;targetSlot.y
  const p=targetSlot.mapToItem(transfer.parent,0,0)
  return Qt.rect(p.x,p.y,targetSlot.width,targetSlot.height)
 }
 readonly property real cardX:moving?fromRect.x+(toRect.x-fromRect.x)*clock.progress:destination.x
 readonly property real cardY:moving?fromRect.y+(toRect.y-fromRect.y)*clock.progress:destination.y
 readonly property real cardWidth:moving?fromRect.width+(toRect.width-fromRect.width)*clock.progress:destination.width
 readonly property real cardHeight:moving?fromRect.height+(toRect.height-fromRect.height)*clock.progress:destination.height
 readonly property real reveal:retargeting?1:progress
 function currentRect(){return Qt.rect(cardX,cardY,cardWidth,cardHeight)}
 function sourceRect(row){
  if(row&&row.visible){
   const p=row.mapToItem(transfer.parent,0,0)
   const v=sourceViewport?row.mapToItem(sourceViewport,0,0):Qt.point(0,0)
   if(!sourceViewport||(v.y+row.height>0&&v.y<sourceViewport.height))return Qt.rect(p.x,p.y,row.width,row.height)
  }
  return Qt.rect(destination.x-Theme.dp(16),destination.y,destination.width,destination.height)
 }
 function start(row){
  refreshGeometry()
  const wasOpen=opened&&!moving
  const current=moving?currentRect():(wasOpen?destination:sourceRect(row))
  configuring=true;clock.stop();sourceRow=row;retargeting=wasOpen
  opened=true;fromRect=current;toRect=destination;clock.progress=0;clock.moveTo(1);configuring=false
 }
 function returnTo(row){
  const current=currentRect()
  configuring=true;clock.stop();retargeting=false;sourceRow=row
  opened=false;fromRect=current;toRect=sourceRect(row);clock.progress=0;clock.moveTo(1);configuring=false
 }
 onOpenedChanged:if(!configuring){if(opened)start(sourceRow);else returnTo(sourceRow)}
 onDestinationChanged:if(moving&&!configuring){
  const current=currentRect();configuring=true;clock.stop();fromRect=current
  toRect=opened?destination:sourceRect(sourceRow);clock.progress=0;clock.moveTo(1);configuring=false
 }
 SwirlTransitionCoordinator {id:clock;duration:SwirlMotion.expandDuration
  onMovingChanged:if(!moving&&!transfer.configuring&&!transfer.opened&&transfer.sourceRow&&transfer.sourceRow.visible)transfer.sourceRow.forceActiveFocus()
 }
 Component.onCompleted:{clock.destination=1;clock.finish()}
}
