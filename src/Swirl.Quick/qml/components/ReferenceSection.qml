import QtQuick
import SwirlQuick
Item {
 property string title:""
 property color tint:Theme.accent
 implicitHeight:Theme.dp(24)
 SwirlText {text:parent.title;color:parent.tint;font.pixelSize:Theme.fontSize(13);anchors.left:parent.left;anchors.top:parent.top}
 Rectangle {anchors.left:parent.left;anchors.right:parent.right;anchors.bottom:parent.bottom;height:Theme.dp(1);color:Theme.border}
}
