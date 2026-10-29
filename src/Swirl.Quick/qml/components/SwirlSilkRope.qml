pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick
import "SwirlSilkRopeGeometry.js" as Geometry

Item {
    id: rope
    property string guide: ""
    property real ropeWidth: 48
    property var stops: []
    property var gradient: [0, 0, 1, 0]
    property real trimStart: 0
    property real trimEnd: 1
    readonly property var fiberPaths: Geometry.build(guide, ropeWidth)
    readonly property int geometryPointCount: fiberPaths.length ? fiberPaths[0].count * fiberPaths.length : 0
    readonly property bool hasLength: trimEnd > trimStart && guide.length > 0
    Accessible.ignored: true

    function stopAt(index) {
        return stops.length ? stops[Math.min(index, stops.length - 1)]
            : { position: index ? 1 : 0, light: "transparent", dark: "transparent" }
    }
    function stopColor(index, shade) {
        if (Theme.increaseContrast) return Theme.text
        const stop = stopAt(index)
        const color = Theme.dark ? stop.dark : stop.light
        return shade === 1 ? color : Qt.darker(color, shade)
    }

    component RopeGradient: LinearGradient {
        id: ink
        property real shade: 1
        x1: rope.gradient[0]; y1: rope.gradient[1]
        x2: rope.gradient[2]; y2: rope.gradient[3]
        GradientStop { position: rope.stopAt(0).position; color: rope.stopColor(0, ink.shade) }
        GradientStop { position: rope.stopAt(1).position; color: rope.stopColor(1, ink.shade) }
        GradientStop { position: rope.stopAt(2).position; color: rope.stopColor(2, ink.shade) }
        GradientStop { position: rope.stopAt(3).position; color: rope.stopColor(3, ink.shade) }
    }
    component FiberPath: ShapePath {
        id: fiber
        property int lane: 0
        readonly property var geometry: rope.fiberPaths[lane]
        objectName: "silkFiberPath-" + lane
        fillColor: "transparent"
        strokeWidth: rope.hasLength && !Theme.increaseContrast ? rope.ropeWidth * (lane === 1 ? 0.038 : 0.046) : -1
        capStyle: ShapePath.RoundCap
        joinStyle: ShapePath.RoundJoin
        // Both ends refer to the same base-curve arclength as the main rope.
        // The static table compensates for the extra length of a twisted fiber.
        trim.start: Geometry.fraction(geometry, rope.trimStart)
        trim.end: Geometry.fraction(geometry, rope.trimEnd)
        strokeGradient: RopeGradient { shade: fiber.lane === 1 ? 1.10 : 1.16 }
        PathSvg { path: fiber.geometry ? fiber.geometry.path : "" }
    }
    Shape {
        objectName: "silkSourceShape"
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            objectName: "silkBasePath"
            fillColor: "transparent"
            strokeWidth: rope.hasLength ? rope.ropeWidth : -1
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            trim.start: rope.trimStart
            trim.end: rope.trimEnd
            strokeGradient: RopeGradient {}
            PathSvg { path: rope.guide }
        }
        FiberPath { lane: 0 }
        FiberPath { lane: 1 }
        FiberPath { lane: 2 }
    }
}
