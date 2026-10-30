import QtQuick
import QtQuick.Shapes

Item {
    id: rope
    property string guide: ""
    property real ropeWidth: 36
    property color flatInk: "transparent"
    property real trimStart: 0
    property real trimEnd: 1
    readonly property bool hasLength: trimEnd > trimStart && guide.length > 0
    visible: hasLength
    Accessible.ignored: true
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            fillColor: "transparent"; strokeColor: rope.flatInk
            strokeWidth: rope.ropeWidth
            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            trim.start: rope.trimStart; trim.end: rope.trimEnd
            PathSvg { path: rope.guide }
        }
    }
}
