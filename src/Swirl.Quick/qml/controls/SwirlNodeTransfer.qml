import QtQuick
import SwirlQuick
Item {
    id:transfer
    required property Item targetSlot
    property Item sourceRow:null
    property rect origin:Qt.rect(0,0,0,0)
    property bool opened:true
    readonly property bool moving:clock.moving
    readonly property real progress:clock.progress
    readonly property rect destination:{
        progress;targetSlot.x;targetSlot.y;targetSlot.width;targetSlot.height
        const p=targetSlot.mapToItem(transfer.parent,0,0)
        return Qt.rect(p.x,p.y,targetSlot.width,targetSlot.height)
    }
    readonly property real cardX:moving?origin.x+(destination.x-origin.x)*progress:destination.x
    readonly property real cardY:moving?origin.y+(destination.y-origin.y)*progress:destination.y
    readonly property real cardWidth:moving?origin.width+(destination.width-origin.width)*progress:destination.width
    readonly property real cardHeight:moving?origin.height+(destination.height-origin.height)*progress:destination.height
    readonly property real reveal:moving?progress:1
    function start(row){
        const current=moving?Qt.rect(cardX,cardY,cardWidth,cardHeight):null
        clock.finish()
        opened=true;sourceRow=row
        if(!row||SwirlMotion.reduced){sourceRow=null;return}
        const p=row.mapToItem(transfer.parent,0,0)
        origin=current||Qt.rect(p.x,p.y,row.width,row.height)
        clock.progress=0;clock.moveTo(1)
    }
    function returnTo(row){
        if(!row||!row.visible||SwirlMotion.reduced){cancel();opened=false;return}
        const p=row.mapToItem(transfer.parent,0,0)
        origin=Qt.rect(p.x,p.y,row.width,row.height);sourceRow=row
        clock.progress=1;clock.moveTo(0)
    }
    function cancel(){clock.destination=1;clock.finish();sourceRow=null}
    SwirlTransitionCoordinator {id:clock;duration:SwirlMotion.expandDuration
        onMovingChanged:if(!moving){if(destination===0)transfer.opened=false;transfer.sourceRow=null}
    }
    Binding {target:transfer.sourceRow;property:"opacity";value:0;when:transfer.moving&&transfer.sourceRow!==null;restoreMode:Binding.RestoreBindingOrValue}
    Component.onCompleted:{clock.destination=1;clock.finish()}
    onVisibleChanged:if(!visible)cancel()
}
