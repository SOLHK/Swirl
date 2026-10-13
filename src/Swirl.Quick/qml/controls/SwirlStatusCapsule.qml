import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
SwirlMotionButton {
 id:control
 property string label:""
 property string tone:"neutral"
 property string detail:""
 implicitWidth:content.implicitWidth+Theme.dp(24)
 implicitHeight:Theme.capsuleHeight
 leftPadding:Theme.dp(12);rightPadding:Theme.dp(12)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background:Rectangle { radius:height/2;color:control.down?Theme.pressed:control.hovered?Theme.hover:Theme.capsuleSurface }
 contentItem:RowLayout { id:content;spacing:Theme.dp(7)
  Rectangle { Layout.preferredWidth:Theme.dp(6);Layout.preferredHeight:Theme.dp(6);radius:width/2;color:control.tone==="success"?Theme.statusGreen:control.tone==="warning"?Theme.orange:Theme.muted }
  Text { text:control.label;color:Theme.text;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;verticalAlignment:Text.AlignVCenter }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 ToolTip.visible:hovered&&detail.length>0&&!previewCaptureMode
 ToolTip.text:detail
}
