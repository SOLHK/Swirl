pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick
import "SwirlWingMaster.js" as Master

Item {
    id: wing
    property real progress: 0
    property real ribbonProgress: 0
    property real ribbonStrength: 1
    property bool largeWing: false
    property bool echoWing: false
    property bool silhouette: false
    readonly property var masterFeathers: echoWing ? Master.echoFeathers : Master.feathers
    readonly property int featherCount: largeWing ? masterFeathers.length : smallPaths.length
    readonly property real artWidth: largeWing ? (echoWing ? Master.echoWidth : Master.width) : 96
    readonly property real artHeight: largeWing ? (echoWing ? Master.echoHeight : Master.height) : 48
    readonly property real fit: Math.min(width / artWidth, height / artHeight)
    readonly property var emissionFeathers: echoWing ? [0, 5] : [7, 10, 11]
    readonly property var emissionColors: echoWing ? ["#459AB3", "#59A990"] : ["#E9A54E", "#DD6A78", "#8874C2"]
    readonly property real peelTravel: Theme.dp(echoWing ? 7 : 8)
    readonly property real peelAngle: (echoWing ? 2.8 : -3.2) * Math.PI / 180
    readonly property real peelDirection: echoWing ? -1 : 1
    readonly property real peelStretch: 0.035
    readonly property real peelNarrowing: 0.10
    readonly property var smallRoots: [Qt.point(5, 39), Qt.point(10, 42), Qt.point(18, 44), Qt.point(30, 45)]
    readonly property var smallPaths: [
        "M5 39C21 37 26 22 42 14C57 6 76 5 92 4C83 12 72 17 58 20C39 24 26 39 5 39Z",
        "M10 42C30 39 40 27 57 24C67 22 77 20 85 16C79 25 67 30 55 31C36 33 25 43 10 42Z",
        "M18 44C34 41 43 35 56 34C65 33 65 37 60 39C48 40 30 45 18 44Z",
        "M30 45C40 42 47 42 54 42C59 42 63 41 67 39C62 44 56 46 50 45C42 44 37 46 30 45Z"
    ]
    implicitWidth: Theme.dp(40)
    implicitHeight: Theme.dp(20)
    visible: progress > 0
    Accessible.ignored: true

    function mapMasterPoint(target, x, y) { return artwork.mapToItem(target, x, y) }
    function featherSource(target, lane) {
        const item=featherRepeater.itemAt(emissionFeathers[lane])
        if (!item) return null
        const p=item.mapToItem(target,0,0), x=item.mapToItem(target,1,0), y=item.mapToItem(target,0,1)
        return {a:x.x-p.x,b:x.y-p.y,c:y.x-p.x,d:y.y-p.y,tx:p.x,ty:p.y}
    }
    function routePoint(target, name, lane) {
        if (lane !== undefined) {
            const record=masterFeathers[emissionFeathers[lane]], item=featherRepeater.itemAt(emissionFeathers[lane])
            const t=[0,.33,.66,1][["root","shoulder","tip","gap"].indexOf(name)]
            return item.mapToItem(target,record.root[0]+(record.tip[0]-record.root[0])*t,record.root[1]+(record.tip[1]-record.root[1])*t)
        }
        const p=(echoWing?Master.echoRoute:Master.route)[name]
        return mapMasterPoint(target,p[0],p[1])
    }
    function featherProgress(index) {
        const order = largeWing ? masterFeathers[index].order : index
        const delay = largeWing ? order * 0.065 : index * 0.2
        const duration = largeWing ? 0.65 : 0.4
        const t = Math.max(0, Math.min(1, (progress - delay) / duration))
        return t * t * (3 - 2 * t)
    }
    function passageResponse(lane) {
        // The actual departing pieces are carried by the foreground renderer.
        // Only their remaining neighbours respond to the brief wingbeat.
        if (!largeWing || lane >= 0 || SwirlMotion.reduced) return 0
        const t=Math.max(0,Math.min(1,ribbonProgress/.18))
        return Math.sin(Math.PI*t)*0.35*ribbonStrength
    }
    function handoffResponse(lane) {
        if (!largeWing || lane < 0 || SwirlMotion.reduced) return 0
        const t=Math.max(0,Math.min(1,ribbonProgress/.035))
        return t*t*(3-2*t)*ribbonStrength
    }

    Item {
        id: artwork
        x: (wing.width - wing.artWidth * wing.fit) / 2
        y: (wing.height - wing.artHeight * wing.fit) / 2
        width: wing.artWidth; height: wing.artHeight
        scale: wing.fit; transformOrigin: Item.TopLeft
        Repeater {
            id: featherRepeater
            model: wing.featherCount
            Item {
                id: feather
                required property int index
                objectName: "wingFeather" + index
                readonly property var record: wing.largeWing ? wing.masterFeathers[index] : null
                readonly property real reveal: wing.featherProgress(index)
                readonly property int emissionLane: wing.emissionFeathers.indexOf(index)
                readonly property real response: wing.passageResponse(emissionLane) * reveal
                readonly property real handoff: wing.handoffResponse(emissionLane)
                readonly property point rootPoint: record ? Qt.point(record.root[0], record.root[1]) : wing.smallRoots[index]
                readonly property point tipPoint: record ? Qt.point(record.tip[0], record.tip[1]) : Qt.point(92, 4)
                readonly property real axisLength: Math.hypot(tipPoint.x-rootPoint.x, tipPoint.y-rootPoint.y)
                readonly property real axisX: (tipPoint.x-rootPoint.x)/axisLength
                readonly property real axisY: (tipPoint.y-rootPoint.y)/axisLength
                readonly property real along: wing.largeWing ? 0.86 + 0.14 * reveal + wing.peelStretch * response : 0.18 + 0.82 * reveal
                readonly property real across: wing.largeWing ? 0.94 + 0.06 * reveal - wing.peelNarrowing * response : 0.70 + 0.30 * reveal
                readonly property real mxx: across + (along-across)*axisX*axisX
                readonly property real mxy: (along-across)*axisX*axisY
                readonly property real myy: across + (along-across)*axisY*axisY
                readonly property real peelCos: Math.cos(wing.peelAngle * response)
                readonly property real peelSin: Math.sin(wing.peelAngle * response)
                readonly property real rxx: peelCos * mxx - peelSin * mxy
                readonly property real rxy: peelCos * mxy - peelSin * myy
                readonly property real ryx: peelSin * mxx + peelCos * mxy
                readonly property real ryy: peelSin * mxy + peelCos * myy
                readonly property real peelOffset: wing.fit > 0 ? wing.peelDirection * wing.peelTravel / wing.fit * response : 0
                readonly property color restingColor: record ? record.color : Theme.wingSmallMid
                readonly property color emissionColor: emissionLane >= 0 ? wing.emissionColors[emissionLane] : restingColor
                readonly property color featherColor: Qt.rgba(
                    restingColor.r + (emissionColor.r - restingColor.r) * response,
                    restingColor.g + (emissionColor.g - restingColor.g) * response,
                    restingColor.b + (emissionColor.b - restingColor.b) * response, 1)
                readonly property color rootColor: record && record.rootColor ? record.rootColor : featherColor
                width: wing.artWidth; height: wing.artHeight
                visible: reveal > 0
                opacity: wing.largeWing ? Math.min(1, reveal * 5) * (1 - handoff)
                    : Math.min(1, reveal * 8) * (1-index*0.18)
                transform: [
                    Matrix4x4 {
                        matrix: Qt.matrix4x4(feather.rxx, feather.rxy, 0,
                            feather.rootPoint.x-feather.rxx*feather.rootPoint.x-feather.rxy*feather.rootPoint.y+feather.axisX*feather.peelOffset,
                            feather.ryx, feather.ryy, 0,
                            feather.rootPoint.y-feather.ryx*feather.rootPoint.x-feather.ryy*feather.rootPoint.y+feather.axisY*feather.peelOffset,
                            0, 0, 1, 0, 0, 0, 0, 1)
                    },
                    Rotation {
                        origin.x: feather.rootPoint.x; origin.y: feather.rootPoint.y
                        angle: wing.largeWing ? (1-feather.reveal)*1.5 : (1-feather.reveal)*8
                    }
                ]
                Shape {
                    objectName: wing.largeWing && feather.index === 0 ? "apecFlatWingPaths" : "wingFeatherPath" + feather.index
                    width: wing.artWidth; height: wing.artHeight
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: 0; strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: feather.rootPoint.x; y1: feather.rootPoint.y
                            x2: feather.tipPoint.x; y2: feather.tipPoint.y
                            GradientStop { position: 0; color: wing.silhouette ? Theme.text : wing.largeWing ? Theme.withAlpha(feather.rootColor, 0.20) : Theme.wingSmallStart }
                            GradientStop { position: 0.28; color: wing.silhouette ? Theme.text : wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.21) : Theme.wingSmallMid }
                            GradientStop { position: 0.65; color: wing.silhouette ? Theme.text : wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.28+feather.response*0.06) : Theme.wingSmallMid }
                            GradientStop { position: 1; color: wing.silhouette ? Theme.text : wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.30+feather.response*0.045) : Theme.wingSmallEnd }
                        }
                        PathSvg { path: feather.record ? feather.record.path : wing.smallPaths[feather.index] }
                    }
                }
            }
        }
    }
}
