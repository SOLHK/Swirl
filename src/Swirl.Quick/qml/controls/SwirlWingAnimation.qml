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
    function routePoint(target, name) {
        const p = Master.route[name]
        return mapMasterPoint(target, p[0], p[1])
    }
    function featherProgress(index) {
        const order = largeWing ? masterFeathers[index].order : index
        const delay = largeWing ? order * 0.065 : index * 0.2
        const duration = largeWing ? 0.65 : 0.4
        const t = Math.max(0, Math.min(1, (progress - delay) / duration))
        return t * t * (3 - 2 * t)
    }
    function passageResponse(index) {
        if (!largeWing || echoWing || (index !== 10 && index !== 7) || SwirlMotion.reduced) return 0
        const centre = index === 10 ? 0.045 : 0.085
        const t = Math.max(0, 1 - Math.abs(ribbonProgress - centre) / 0.05)
        return t * t * (3 - 2 * t) * ribbonStrength
    }

    Item {
        id: artwork
        x: (wing.width - wing.artWidth * wing.fit) / 2
        y: (wing.height - wing.artHeight * wing.fit) / 2
        width: wing.artWidth; height: wing.artHeight
        scale: wing.fit; transformOrigin: Item.TopLeft
        Repeater {
            model: wing.featherCount
            Item {
                id: feather
                required property int index
                objectName: "wingFeather" + index
                readonly property var record: wing.largeWing ? wing.masterFeathers[index] : null
                readonly property real reveal: wing.featherProgress(index)
                readonly property real response: wing.passageResponse(index)
                readonly property point rootPoint: record ? Qt.point(record.root[0], record.root[1]) : wing.smallRoots[index]
                readonly property point tipPoint: record ? Qt.point(record.tip[0], record.tip[1]) : Qt.point(92, 4)
                readonly property real axisLength: Math.hypot(tipPoint.x-rootPoint.x, tipPoint.y-rootPoint.y)
                readonly property real axisX: (tipPoint.x-rootPoint.x)/axisLength
                readonly property real axisY: (tipPoint.y-rootPoint.y)/axisLength
                readonly property real along: wing.largeWing ? 0.86 + 0.14 * reveal : 0.18 + 0.82 * reveal
                readonly property real across: wing.largeWing ? 0.94 + 0.06 * reveal : 0.70 + 0.30 * reveal
                readonly property real mxx: across + (along-across)*axisX*axisX
                readonly property real mxy: (along-across)*axisX*axisY
                readonly property real myy: across + (along-across)*axisY*axisY
                readonly property color featherColor: record ? record.color : Theme.wingSmallMid
                readonly property color rootColor: record && record.rootColor ? record.rootColor : featherColor
                width: wing.artWidth; height: wing.artHeight
                visible: reveal > 0
                opacity: wing.largeWing ? Math.min(1, reveal * 5) : Math.min(1, reveal * 8) * (1-index*0.18)
                transform: [
                    Matrix4x4 {
                        matrix: Qt.matrix4x4(feather.mxx, feather.mxy, 0,
                            feather.rootPoint.x-feather.mxx*feather.rootPoint.x-feather.mxy*feather.rootPoint.y,
                            feather.mxy, feather.myy, 0,
                            feather.rootPoint.y-feather.mxy*feather.rootPoint.x-feather.myy*feather.rootPoint.y,
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
