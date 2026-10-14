import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../controls"
CheckBox {
 id:control;padding:0;
 SwirlPressMotion{}
spacing:Theme.dp(6);implicitHeight:Theme.dp(22)
 indicator:Rectangle {x:0;y:(control.height-height)/2;width:Theme.dp(16);height:width;radius:Theme.dp(4);color:control.checked?Theme.accent:Theme.buttonBase
  Behavior on color{ColorAnimation{duration:SwirlMotion.switchDuration}}
  Image {opacity:control.checked?1:0;scale:control.checked?1:0.75;Behavior on opacity{NumberAnimation{duration:SwirlMotion.switchDuration}}Behavior on scale{enabled:!SwirlMotion.reduced;SwirlSpring{}}anchors.fill:parent;anchors.margins:Theme.dp(2);source:"image://swirl/checkmark/ffffff"}
 }
 contentItem:Text {leftPadding:Theme.dp(22);text:control.text;font.pixelSize:Theme.fontSize(13);color:control.enabled?Theme.text:Theme.muted;verticalAlignment:Text.AlignVCenter}
}
