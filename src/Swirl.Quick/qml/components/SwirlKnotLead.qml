pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

// Persistent cubic elements: only control points and trim change during flight.
Item {
    id: lead
    required property var route
    required property color ink
    required property color tip
    property real amount: 0
    property real withdrawal: 0
    property real bend: 0
    property real ropeWidth: Theme.dp(3.8)
    visible: route !== null && amount > withdrawal
    Accessible.ignored: true

    component ThreadPath: ShapePath {
        id: threadPath
        property bool highlight: false
        fillColor: "transparent"
        strokeWidth: lead.ropeWidth * (highlight ? 0.22 : 1)
        capStyle: ShapePath.RoundCap
        joinStyle: ShapePath.RoundJoin
        trim.start: lead.withdrawal
        trim.end: lead.amount
        strokeGradient: LinearGradient {
            x1: lead.route ? lead.route.start.x : 0
            y1: lead.route ? lead.route.start.y : 0
            x2: lead.route ? lead.route.end.x : 1
            y2: lead.route ? lead.route.end.y : 1
            GradientStop { position: 0; color: threadPath.highlight ? Qt.lighter(lead.ink, 1.18) : lead.ink }
            GradientStop { position: 1; color: threadPath.highlight ? Qt.lighter(lead.tip, 1.18) : lead.tip }
        }
        startX: lead.route ? lead.route.start.x : 0
        startY: lead.route ? lead.route.start.y : 0
        PathCubic {
            control1X: lead.route ? lead.route.c1.x : 0
            control1Y: lead.route ? lead.route.c1.y : 0
            control2X: lead.route ? lead.route.c2.x + lead.bend : 0
            control2Y: lead.route ? lead.route.c2.y : 0
            x: lead.route ? lead.route.a.x : 0; y: lead.route ? lead.route.a.y : 0
        }
        PathCubic {
            control1X: lead.route ? lead.route.c3.x + lead.bend : 0
            control1Y: lead.route ? lead.route.c3.y : 0
            control2X: lead.route ? lead.route.c4.x : 0
            control2Y: lead.route ? lead.route.c4.y + lead.bend : 0
            x: lead.route ? lead.route.b.x : 0; y: lead.route ? lead.route.b.y : 0
        }
        PathCubic {
            control1X: lead.route ? lead.route.c5.x : 0
            control1Y: lead.route ? lead.route.c5.y : 0
            control2X: lead.route ? lead.route.c6.x : 0
            control2Y: lead.route ? lead.route.c6.y : 0
            x: lead.route ? lead.route.c.x : 0; y: lead.route ? lead.route.c.y : 0
        }
        PathCubic {
            control1X: lead.route ? lead.route.c7.x : 0
            control1Y: lead.route ? lead.route.c7.y : 0
            control2X: lead.route ? lead.route.c8.x : 0
            control2Y: lead.route ? lead.route.c8.y : 0
            x: lead.route ? lead.route.end.x : 0; y: lead.route ? lead.route.end.y : 0
        }
    }
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ThreadPath {}
        ThreadPath { highlight: true }
    }
}
