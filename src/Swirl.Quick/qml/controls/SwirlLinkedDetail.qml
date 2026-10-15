import QtQuick
import SwirlQuick
import "../components"
Item {
    id:slot
    required property Item animationLayer
    property Item sourceRow:null
    property Item sourceViewport:null
    property bool detailOpen:false
    property bool componentReady:false
    Component.onCompleted:componentReady=true
    readonly property bool moving:transfer.moving
    readonly property Item motionSurface:surface
    default property alias contents:body.data
    function present(row){sourceRow=row;transfer.start(row)}
    onDetailOpenChanged:if(componentReady){if(detailOpen)transfer.start(sourceRow);else transfer.returnTo(sourceRow)}
    SwirlNodeTransfer {
        id:transfer;parent:slot.animationLayer;targetSlot:slot;sourceViewport:slot.sourceViewport
    }
    SwirlGlassPanel {
        id:surface;parent:slot.animationLayer;z:10
        visible:slot.visible;enabled:slot.enabled
        x:transfer.cardX;y:transfer.cardY;width:transfer.cardWidth;height:transfer.cardHeight
        clip:true
        Item {
            id:body;width:slot.width;height:slot.height
            opacity:transfer.moving?Math.max(0,Math.min(1,(transfer.reveal-0.15)/0.7)):1
        }
    }
}
