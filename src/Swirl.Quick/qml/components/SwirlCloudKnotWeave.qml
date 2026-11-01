pragma ComponentBehavior: Bound
import QtQuick
import SwirlQuick
import "SwirlCloudKnotPaths.js" as Knot
import "../controls/SwirlWingMaster.js" as Wings

Item {
    id: weave
    required property Item connectionItem
    required property Item transferItem
    required property Item sourcesItem
    required property Item diagnosticItem
    required property Item connectionsItem
    required property Item behindCards
    required property Item frontLayer
    required property Item knotTarget
    required property Item cardViewport
    property Item proxyAnchor: null
    property var toolbarItems: []
    property Item sidebarAnchor: null
    property var wingScene: null
    property bool active: false
    property bool presentationActive: true
    property bool wide: true
    property real gap: Theme.dp(16)
    property real progress: 0
    property real release: 1
    property bool initialized: false
    property bool previewing: false
    property rect knotRect: Qt.rect(0,0,0,0)
    property rect viewportRect: Qt.rect(0,0,0,0)
    property var routes: ({})
    property matrix4x4 backLayerTransform: Qt.matrix4x4(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
    property matrix4x4 knotLayerTransform: Qt.matrix4x4(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
    property matrix4x4 frontToKnotTransform: Qt.matrix4x4(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)
    readonly property var materials: Knot.materials(Wings.feathers,Wings.echoFeathers)
    readonly property bool windowVisible: !Window.window || (Window.window.visible && Window.window.visibility !== Window.Minimized)
    readonly property bool moving: flight.running || withdrawal.running
    readonly property bool freeFlight: release < 1 && (progress < 1 || release > 0 || withdrawal.running)
    readonly property real artScale: Math.min(knotTarget.width*.90/820,knotTarget.height*.85/640)
    readonly property point localOrigin: Qt.point(knotTarget.width/2-487*artScale,knotTarget.height/2-544*artScale)
    readonly property real releaseOpacity: 1-Knot.phaseEase(.25,1,release)
    // Every depth view consumes the same pose objects and the same clock. A
    // foreground clip changes occlusion only, never the feather's trajectory.
    readonly property var poses: {
        const origin=freeFlight?Qt.point(knotRect.x+localOrigin.x,knotRect.y+localOrigin.y):localOrigin;
        const guides=routes,phase=progress,removal=release,scale=artScale,spacing=gap;
        return materials.map(material=>Knot.pose(material,guides[material.key] || null,phase,removal,origin,scale,spacing));
    }
    Accessible.ignored: true

    function rectFor(item) {
        const p=item.mapToItem(frontLayer,0,0);
        return Qt.rect(p.x,p.y,item.width,item.height);
    }
    function layerTransform(source,target) {
        const p=source.mapToItem(target,0,0),x=source.mapToItem(target,1,0),y=source.mapToItem(target,0,1);
        return Qt.matrix4x4(x.x-p.x,y.x-p.x,0,p.x,x.y-p.y,y.y-p.y,0,p.y,0,0,1,0,0,0,0,1);
    }
    function updateGeometry(force) {
        if(!initialized || (!force && !freeFlight && !previewing))return;
        knotRect=rectFor(knotTarget); viewportRect=rectFor(cardViewport);
        backLayerTransform=layerTransform(frontLayer,behindCards);
        knotLayerTransform=layerTransform(knotTarget,frontLayer);
        frontToKnotTransform=layerTransform(frontLayer,knotTarget);
        if(!force && !flight.running && !previewing)return;
        if(!wingScene)return;
        const scene={sidebar:rectFor(sidebarAnchor),viewport:viewportRect,
            traffic:rectFor(transferItem),sources:rectFor(sourcesItem),connections:rectFor(connectionsItem),
            toolbar:toolbarItems.map(item=>rectFor(item))};
        const next={};
        for(let i=0;i<materials.length;++i){
            const material=materials[i],lane={warm:0,return:1,forward:2,crown:0,heart:1}[material.key];
            const source=wingScene.featherSource(frontLayer,material.side,lane);
            if(!source)continue;
            const dest=Knot.point(knotRect.x+localOrigin.x+material.targetCenter.x*artScale,
                                 knotRect.y+localOrigin.y+material.targetCenter.y*artScale);
            next[material.key]=Knot.flight(material,source,scene,dest,gap);
        }
        routes=next;
    }
    function previewAt(phase,removal) {
        flight.stop();withdrawal.stop();previewing=true;
        progress=phase;release=removal;updateGeometry(true);
    }
    function settleHidden() {
        flight.stop();withdrawal.stop();
        progress=active?1:0;release=active?0:1;
    }
    function retarget() {
        if(!initialized)return;
        previewing=false;flight.stop();withdrawal.stop();
        if(!visible || !windowVisible || !presentationActive || SwirlMotion.reduced || Theme.increaseContrast){settleHidden();return;}
        updateGeometry(true);
        // An already reached endpoint needs no animation clock: Qt's threaded
        // render loop also submits frames for animations without visual changes.
        if(active){
            if(progress===0 && release===1)release=0;
            else if(release!==0){withdrawal.to=0;withdrawal.duration=SwirlMotion.ms(250);withdrawal.start();}
            if(progress<1){flight.from=progress;flight.to=1;flight.duration=Math.max(1,SwirlMotion.ms(6000*(1-progress)));flight.start();}
        }else if(release!==1){
            withdrawal.to=1;withdrawal.duration=SwirlMotion.ms(850);withdrawal.start();
        }else progress=0;
    }
    onActiveChanged:retarget()
    onVisibleChanged:if(!visible && initialized)settleHidden()
    onWindowVisibleChanged:if(!windowVisible && initialized)settleHidden()
    onPresentationActiveChanged:{if(!initialized)return;if(presentationActive)retarget();else{flight.stop();withdrawal.stop();}}
    // Detail navigation fades the overview to zero after pausing it. Opacity is
    // only presentation: settling here discards the interrupted weave position.
    // Actual page/window hiding and hidden proxy changes still settle above.
    onWidthChanged:Qt.callLater(updateGeometry)
    onHeightChanged:Qt.callLater(updateGeometry)
    onWideChanged:Qt.callLater(updateGeometry)
    Component.onCompleted:{initialized=true;settleHidden();}
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced)weave.retarget();}}
    Connections {target:Theme;function onUiScaleChanged(){Qt.callLater(weave.updateGeometry);}}
    Connections {
        target:weave.behindCards
        function onXChanged(){Qt.callLater(weave.updateGeometry);}
        function onYChanged(){Qt.callLater(weave.updateGeometry);}
        function onScaleChanged(){Qt.callLater(weave.updateGeometry);}
        function onRotationChanged(){Qt.callLater(weave.updateGeometry);}
        function onWidthChanged(){Qt.callLater(weave.updateGeometry);}
        function onHeightChanged(){Qt.callLater(weave.updateGeometry);}
    }
    Connections {
        target:weave.frontLayer
        function onXChanged(){Qt.callLater(weave.updateGeometry);}
        function onYChanged(){Qt.callLater(weave.updateGeometry);}
        function onScaleChanged(){Qt.callLater(weave.updateGeometry);}
        function onRotationChanged(){Qt.callLater(weave.updateGeometry);}
        function onWidthChanged(){Qt.callLater(weave.updateGeometry);}
        function onHeightChanged(){Qt.callLater(weave.updateGeometry);}
    }
    Connections {
        target:weave.knotTarget
        function onXChanged(){Qt.callLater(weave.updateGeometry);}
        function onYChanged(){Qt.callLater(weave.updateGeometry);}
        function onWidthChanged(){Qt.callLater(weave.updateGeometry);}
        function onHeightChanged(){Qt.callLater(weave.updateGeometry);}
    }
    Connections {
        target:weave.connectionItem
        // SwirlActivityCard supplies lift; plain Item hosts need no hover hook.
        ignoreUnknownSignals:true
        function onLiftChanged(){Qt.callLater(weave.updateGeometry);}
    }
    NumberAnimation {id:flight;target:weave;property:"progress";easing.type:Easing.Linear;paused:running && (!weave.presentationActive || !weave.windowVisible)}
    NumberAnimation {id:withdrawal;target:weave;property:"release";easing.type:Easing.InOutSine;paused:running && (!weave.presentationActive || !weave.windowVisible);onFinished:if(!weave.active && weave.release===1)weave.progress=0}

    Item {
        id:flightView;objectName:"cloudKnotBackFlight";parent:weave.behindCards
        width:weave.frontLayer.width;height:weave.frontLayer.height
        visible:weave.visible && weave.freeFlight
        opacity:weave.opacity*weave.releaseOpacity
        transform:Matrix4x4 {matrix:weave.backLayerTransform}
        Accessible.ignored:true
    }
    // Card and toolbar surfaces naturally hide the travelling bodies. Only
    // the reserved brand area opens a foreground window onto that same scene.
    // Mapping both directions also works when the two host layers are offset
    // or scaled; no shared-parent/origin assumption is needed.
    Item {
        id:frontView;objectName:"cloudKnotFrontFlight";parent:weave.frontLayer
        width:weave.knotTarget.width;height:weave.knotTarget.height
        visible:weave.visible && weave.freeFlight
        opacity:weave.opacity*weave.releaseOpacity
        clip:true
        transform:Matrix4x4 {matrix:weave.knotLayerTransform}
        Accessible.ignored:true
        Item {
            id:frontGeometry;objectName:"cloudKnotFrontGeometry"
            width:weave.frontLayer.width;height:weave.frontLayer.height
            transform:Matrix4x4 {matrix:weave.frontToKnotTransform}
            Accessible.ignored:true
        }
    }
    Item {
        id:restView;objectName:"cloudKnotRest";parent:weave.knotTarget
        anchors.fill:parent
        visible:weave.visible && weave.release<1
        Accessible.ignored:true
    }
    component FeatherBody: WholeFeatherItem {
            id:piece
            required property var material
            width:1024;height:1024
            readonly property var pose:weave.poses[material.index]
            readonly property color sourceInk:material.record.color
            readonly property color finalInk:material.ink
            readonly property real tint:Knot.phaseEase(.08,.65,weave.progress)
            sourcePath:material.record.path
            sourceRoot:Qt.point(material.sourceRoot.x,material.sourceRoot.y)
            sourceTip:Qt.point(material.sourceTip.x,material.sourceTip.y)
            targetPath:material.targetPath
            targetRoot:Qt.point(material.targetRoot.x,material.targetRoot.y)
            targetTip:Qt.point(material.targetTip.x,material.targetTip.y)
            morphProgress:pose.morph
            ink:Theme.increaseContrast?Theme.text:Qt.rgba(sourceInk.r+(finalInk.r-sourceInk.r)*tint,sourceInk.g+(finalInk.g-sourceInk.g)*tint,sourceInk.b+(finalInk.b-sourceInk.b)*tint,1)
            opacity:pose.opacity
            transform:Matrix4x4 {matrix:Qt.matrix4x4(piece.pose.a,piece.pose.c,0,piece.pose.tx,piece.pose.b,piece.pose.d,0,piece.pose.ty,0,0,1,0,0,0,0,1)}
    }
    Repeater {
        parent:restView
        model:weave.materials
        delegate:FeatherBody {
            required property var modelData
            material:modelData
            objectName:"cloudFeather-"+modelData.key
            z:modelData.index
            parent:weave.freeFlight?flightView:restView
        }
    }
    Repeater {
        parent:frontGeometry
        model:weave.materials
        delegate:FeatherBody {
            required property var modelData
            material:modelData
            objectName:"cloudFeatherFront-"+modelData.key
            z:modelData.index
        }
    }
    // Local copies change only depth where completed feather bodies cross.
    // They share the complete outlines; no independent stroke ends are created.
    Repeater {
        parent:restView
        model:[{part:0,x:335,y:460,w:74,h:72},{part:1,x:449,y:535,w:66,h:61},{part:2,x:485,y:568,w:68,h:70},{part:3,x:485,y:572,w:58,h:54}]
        delegate:Item {
            id:overpass
            required property var modelData
            readonly property var material:weave.materials[modelData.part]
            readonly property real blend:Knot.phaseEase(.94,.98,weave.progress)*(1-Knot.phaseEase(0,.25,weave.release))
            readonly property point origin:weave.freeFlight?Qt.point(weave.knotRect.x+weave.localOrigin.x,weave.knotRect.y+weave.localOrigin.y):weave.localOrigin
            readonly property var pose:weave.poses[modelData.part]
            parent:weave.freeFlight?frontGeometry:restView
            z:20+modelData.part
            visible:blend>0
            opacity:blend
            x:origin.x+modelData.x*weave.artScale;y:origin.y+modelData.y*weave.artScale
            width:modelData.w*weave.artScale;height:modelData.h*weave.artScale
            clip:true
            WholeFeatherItem {
                width:1024;height:1024
                sourcePath:overpass.material.record.path
                sourceRoot:Qt.point(overpass.material.sourceRoot.x,overpass.material.sourceRoot.y)
                sourceTip:Qt.point(overpass.material.sourceTip.x,overpass.material.sourceTip.y)
                targetPath:overpass.material.targetPath
                targetRoot:Qt.point(overpass.material.targetRoot.x,overpass.material.targetRoot.y)
                targetTip:Qt.point(overpass.material.targetTip.x,overpass.material.targetTip.y)
                morphProgress:overpass.pose.morph
                ink:Theme.increaseContrast?Theme.text:overpass.material.ink
                transform:Matrix4x4 {matrix:Qt.matrix4x4(overpass.pose.a,overpass.pose.c,0,overpass.pose.tx-overpass.x,overpass.pose.b,overpass.pose.d,0,overpass.pose.ty-overpass.y,0,0,1,0,0,0,0,1)}
            }
        }
    }
}
