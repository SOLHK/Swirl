import QtQuick
import QtQuick.Controls
import SwirlQuick
CheckBox {
 id:control;padding:0;spacing:Theme.dp(6);implicitHeight:Theme.dp(22)
 indicator:Rectangle {x:0;y:(control.height-height)/2;width:Theme.dp(16);height:width;radius:Theme.dp(4);color:control.checked?Theme.accent:Theme.buttonBase
  Image {visible:control.checked;anchors.fill:parent;anchors.margins:Theme.dp(2);source:"image://swirl/checkmark/ffffff"}
 }
 contentItem:Text {leftPadding:Theme.dp(22);text:control.text;font.pixelSize:Theme.fontSize(13);color:control.enabled?Theme.text:Theme.muted;verticalAlignment:Text.AlignVCenter}
}
