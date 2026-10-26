import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id:canvas
    property var targetWindow:Window.window
    SwirlGlassMaterial {anchors.fill:parent;targetWindow:canvas.targetWindow}
    // Quiet, stationary app-scene curves provide a real backdrop signal for
    // the navigation glass. They never simulate network activity or cross the
    // central reading area; runtime flow remains in state-driven components.
    Shape {
        x:0;y:canvas.height-Theme.dp(300);width:Theme.dp(300);height:Theme.dp(300)
        visible:Theme.transparency && !Theme.increaseContrast
        preferredRendererType:Shape.CurveRenderer
        ShapePath {strokeColor:Theme.withAlpha(Theme.accent,Theme.dark?0.15:0.09);strokeWidth:Theme.dp(22);fillColor:"transparent";capStyle:ShapePath.RoundCap
            startX:-Theme.dp(36);startY:Theme.dp(286)
            PathCubic {control1X:Theme.dp(40);control1Y:Theme.dp(248);control2X:Theme.dp(90);control2Y:Theme.dp(80);x:Theme.dp(184);y:Theme.dp(44)}
        }
        ShapePath {strokeColor:Theme.withAlpha(Theme.brandBlue,Theme.dark?0.12:0.06);strokeWidth:Theme.dp(9);fillColor:"transparent";capStyle:ShapePath.RoundCap
            startX:-Theme.dp(18);startY:Theme.dp(310)
            PathCubic {control1X:Theme.dp(70);control1Y:Theme.dp(284);control2X:Theme.dp(125);control2Y:Theme.dp(144);x:Theme.dp(190);y:Theme.dp(122)}
        }
    }
}
