import QtQuick
import QtQuick.Shapes
import SwirlQuick
Item {
 id:outline
 Shape {
  anchors.fill:parent;antialiasing:true
  ShapePath {fillColor:"transparent";strokeColor:Theme.border;strokeWidth:Theme.dp(1);strokeStyle:ShapePath.DashLine;dashPattern:[3,3]
   startX:Theme.dp(10);startY:0
   PathLine{x:outline.width-Theme.dp(10);y:0}
   PathArc{x:outline.width;y:Theme.dp(10);radiusX:Theme.dp(10);radiusY:Theme.dp(10)}
   PathLine{x:outline.width;y:outline.height-Theme.dp(10)}
   PathArc{x:outline.width-Theme.dp(10);y:outline.height;radiusX:Theme.dp(10);radiusY:Theme.dp(10)}
   PathLine{x:Theme.dp(10);y:outline.height}
   PathArc{x:0;y:outline.height-Theme.dp(10);radiusX:Theme.dp(10);radiusY:Theme.dp(10)}
   PathLine{x:0;y:Theme.dp(10)}
   PathArc{x:Theme.dp(10);y:0;radiusX:Theme.dp(10);radiusY:Theme.dp(10)}
  }
 }
}
