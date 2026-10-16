import QtQuick
import SwirlQuick
import "../components"

// A single live surface owns the flight. The native detail window is opaque
// and only becomes visible after this surface reaches its final rectangle.
// This tool window covers the union of the source and destination, so a detail
// taller than the main window is not clipped by the main window's swapchain.
Window {
    id: flight
    required property var ownerWindow
    required property var detailWindow
    required property var composition
    property Item origin: null
    readonly property alias bodySurface: body
    property string phase: "Idle"
    readonly property bool moving: phase === "Expanding" || phase === "Collapsing"
    readonly property bool ownsContent: moving
    readonly property bool swirlDismissibleWindow: true
    readonly property real reveal: fromReveal + (toReveal-fromReveal)*clock.progress
    readonly property rect surfaceRect: Qt.rect(fromRect.x+(toRect.x-fromRect.x)*clock.progress,
                                               fromRect.y+(toRect.y-fromRect.y)*clock.progress,
                                               fromRect.width+(toRect.width-fromRect.width)*clock.progress,
                                               fromRect.height+(toRect.height-fromRect.height)*clock.progress)
    property rect fromRect: Qt.rect(0,0,1,1)
    property rect toRect: Qt.rect(0,0,1,1)
    property real fromReveal: 0
    property real toReveal: 1
    property rect destinationRect: Qt.rect(0,0,1,1)
    property real sourceRadius: Theme.cardRadius
    property color sourceColor: Theme.material("content")
    property real fromRadius:Theme.cardRadius
    property real toRadius:Theme.cardRadius
    readonly property real surfaceRadius:fromRadius+(toRadius-fromRadius)*clock.progress
    property color fromColor:Theme.material("content")
    property color toColor:Theme.material("content")
    readonly property color destinationColor:Theme.withAlpha(Theme.nativeTint,
        composition.active && Theme.transparency ? Theme.nativeTintOpacity :
        composition.translucent && Theme.transparency ? Theme.alphaTintOpacity : 1)
    readonly property color surfaceColor:Qt.rgba(fromColor.r+(toColor.r-fromColor.r)*clock.progress,
                                               fromColor.g+(toColor.g-fromColor.g)*clock.progress,
                                               fromColor.b+(toColor.b-fromColor.b)*clock.progress,
                                               fromColor.a+(toColor.a-fromColor.a)*clock.progress)
    property string sourceIcon: ""
    property string sourceTitle: ""
    property string sourceDescription: ""
    property real sourceContentWidth:1
    property bool fadeFallback: false
    property int generation: 0
    // Internal regression evidence samples the exact handler boundary; native
    // input delivery may advance the animation before a test regains control.
    property rect retargetRequestedRect:Qt.rect(0,0,1,1)
    property rect retargetCommittedRect:Qt.rect(0,0,1,1)
    property real retargetRequestedReveal:0
    property real retargetCommittedReveal:0
    property real retargetRequestedRadius:0
    property real retargetCommittedRadius:0
    property bool retargeting:false
    signal entered()
    signal returned()
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    transientParent: ownerWindow
    modality: Qt.WindowModal
    color: "transparent"
    visible: false
    title: detailWindow.title

    function rectangleFor(item) {
        if (!item || !item.visible || item.width <= 0 || item.height <= 0) return null
        const surface=item.background || item
        const a=surface.mapToGlobal(0,0),b=surface.mapToGlobal(surface.width,surface.height)
        // Inspect actual clipping ancestors; an offscreen return card uses a
        // fade at the current surface, never a flight into an obsolete slot.
        let ancestor=item.parent
        while(ancestor) {
            if(!ancestor.visible)return null
            if(ancestor.clip) {
                const p=ancestor.mapToGlobal(0,0)
                if(b.x<=p.x || a.x>=p.x+ancestor.width || b.y<=p.y || a.y>=p.y+ancestor.height)return null
            }
            ancestor=ancestor.parent
        }
        return Qt.rect(a.x,a.y,b.x-a.x,b.y-a.y)
    }
    function cover(a,b) {
        // The window geometry changes once per request, not on every frame.
        const left=Math.floor(Math.min(a.x,b.x)),top=Math.floor(Math.min(a.y,b.y))
        x=left;y=top;width=Math.ceil(Math.max(a.x+a.width,b.x+b.width))-left
        height=Math.ceil(Math.max(a.y+a.height,b.y+b.height))-top
    }
    function animate(rectangle, value, nextPhase) {
        const current=surfaceRect,currentReveal=reveal,currentRadius=surfaceRadius,currentColor=surfaceColor
        retargetRequestedRect=current;retargetRequestedReveal=currentReveal;retargetRequestedRadius=currentRadius
        retargeting=true
        ++generation
        clock.stop()
        fromRect=current;toRect=rectangle;fromReveal=currentReveal;toReveal=value
        fromRadius=currentRadius;toRadius=value===1?Theme.windowRadius:origin && origin.background?origin.background.radius:sourceRadius
        fromColor=currentColor;toColor=value===1?destinationColor:origin && origin.background?origin.background.color:sourceColor
        phase=nextPhase;clock.progress=0;clock.destination=0
        cover(current,rectangle)
        retargetCommittedRect=surfaceRect;retargetCommittedReveal=reveal;retargetCommittedRadius=surfaceRadius
        retargeting=false
        show();raise();requestActivate()
        clock.duration=Math.max(1,Math.round(SwirlMotion.dialogDuration*Math.max(0.35,Math.abs(value-currentReveal))))
        clock.moveTo(1)
    }
    function expand(source) {
        const wasMoving=moving
        origin=source || null
        destinationRect=Qt.rect(detailWindow.x,detailWindow.y,detailWindow.width,detailWindow.height)
        const sourceRect=rectangleFor(origin)
        fadeFallback=sourceRect===null
        if(!wasMoving) {
            fromRect=sourceRect || destinationRect;toRect=fromRect
            fromReveal=0;toReveal=0;clock.progress=0;clock.destination=0
        }
        sourceIcon=origin && origin.motionIcon!==undefined?origin.motionIcon:""
        sourceTitle=origin && origin.motionTitle?origin.motionTitle.text:""
        sourceDescription=origin && origin.motionDescription!==undefined?origin.motionDescription:""
        sourceContentWidth=origin && origin.contentItem?origin.contentItem.width:sourceRect?Math.max(0,sourceRect.width-2*Theme.cardPadding):1
        sourceRadius=origin && origin.background?origin.background.radius:Theme.cardRadius
        sourceColor=origin && origin.background?origin.background.color:Theme.material("content")
        if(!wasMoving){fromRadius=sourceRadius;toRadius=sourceRadius;fromColor=sourceColor;toColor=sourceColor}
        animate(destinationRect,1,"Expanding")
    }
    function collapse() {
        if(phase==="Idle" || phase==="Collapsing")return
        if(!moving) {
            destinationRect=Qt.rect(detailWindow.x,detailWindow.y,detailWindow.width,detailWindow.height)
            fromRect=destinationRect;toRect=destinationRect;fromReveal=1;toReveal=1;clock.progress=0;clock.destination=0
            fromRadius=detailWindow.visibility===Window.FullScreen || detailWindow.visibility===Window.Maximized?0:Theme.windowRadius;toRadius=fromRadius
            fromColor=destinationColor;toColor=fromColor
        }
        const sourceRect=rectangleFor(origin)
        sourceContentWidth=origin && origin.contentItem?origin.contentItem.width:sourceRect?Math.max(0,sourceRect.width-2*Theme.cardPadding):sourceContentWidth
        fadeFallback=sourceRect===null
        animate(sourceRect || surfaceRect,0,"Collapsing")
        detailWindow.hide()
    }
    function complete() {
        if(clock.moving || !moving)return
        if(phase==="Expanding") {
            phase="Detail"
            // Reparenting happens only at this endpoint. The native window
            // receives the same cached page, with no duplicate page or texture.
            entered()
        } else {
            phase="Idle";hide();returned()
        }
    }
    function settle() { if(moving){clock.finish();complete()} }
    function closeSettings() { detailWindow.requestClose() }
    function requestDismiss() { detailWindow.requestClose() }
    function reset() { ++generation;clock.stop();phase="Idle";hide();origin=null }
    function updateContour(){
        if(visible && !retargeting)composition.applyTransientClip(flight,Qt.rect(surfaceRect.x-x,surfaceRect.y-y,surfaceRect.width,surfaceRect.height),surfaceRadius)
    }
    onXChanged:updateContour()
    onYChanged:updateContour()
    onRetargetingChanged:if(!retargeting)updateContour()
    onVisibleChanged:if(visible)updateContour();else composition.clearTransientClip(flight)
    onClosing: close=>{close.accepted=false;detailWindow.requestClose()}
    SwirlTransitionCoordinator {
        id:clock
        onProgressChanged:flight.updateContour()
        onMovingChanged:if(!moving && flight.moving)Qt.callLater(flight.complete)
    }
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced)flight.settle()}}
    Connections {target:flight.detailWindow;function onFrameSwapped(){if(flight.phase==="Detail" && flight.visible){flight.hide();flight.detailWindow.raise();flight.detailWindow.requestActivate()}}}
    QtObject {
        id:windowActions
        readonly property string title:flight.detailWindow.title
        readonly property int visibility:flight.detailWindow.visibility
        function close(){flight.detailWindow.requestClose()}
        function finish(){flight.settle();flight.hide()}
        function showMinimized(){finish();flight.detailWindow.showMinimized()}
        function showFullScreen(){finish();flight.detailWindow.showFullScreen()}
        function showMaximized(){finish();flight.detailWindow.showMaximized()}
        function showNormal(){finish();flight.detailWindow.showNormal()}
        function startSystemMove(){finish();flight.detailWindow.startSystemMove()}
    }
    Item {
        id: frame
        objectName:"settingsTransferSurface"
        x:flight.surfaceRect.x-flight.x;y:flight.surfaceRect.y-flight.y
        width:flight.surfaceRect.width;height:flight.surfaceRect.height
        clip:true
        opacity:flight.fadeFallback?flight.reveal:1
        SwirlContinuousSurface {
            anchors.fill:parent
            radius:flight.surfaceRadius
            color:flight.surfaceColor
            border.width:Theme.borderWidth;border.color:Theme.border
        }
        Column {
            x:Theme.cardPadding;y:Theme.cardPadding;spacing:Theme.dp(12)
            width:flight.sourceContentWidth
            visible:!flight.fadeFallback
            opacity:Math.max(0,1-flight.reveal/0.32)
            SwirlIcon {name:flight.sourceIcon;size:Theme.dp(34);color:Theme.accent;visible:name.length>0}
            SwirlText {text:flight.sourceTitle;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
            SwirlText {text:flight.sourceDescription;color:Theme.muted;font.pixelSize:Theme.fontSize(11);width:parent.width;wrapMode:Text.WordWrap}
        }
        Item {
            width:flight.destinationRect.width;height:flight.destinationRect.height
            opacity:Math.max(0,Math.min(1,(flight.reveal-0.22)/0.56))
            SwirlWindowTitleBar {id:header;objectName:"settingsTransferTitleBar";anchors.left:parent.left;anchors.right:parent.right;targetWindow:windowActions}
            Item {id:body;x:0;y:header.height;width:parent.width;height:parent.height-header.height;clip:true;enabled:false}
        }
        WindowEdge {anchors.fill:parent;z:10000;radius:flight.surfaceRadius}
    }
}
