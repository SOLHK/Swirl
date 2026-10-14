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
 implicitHeight:Theme.dp(22)
 leftPadding:Theme.dp(8);rightPadding:Theme.dp(8)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background:Rectangle { radius:height/2;color:control.down?Theme.pressed:control.hovered?Theme.hover:control.tone==="warning"?Theme.withAlpha(Theme.orange,0.16):Theme.capsuleSurface }
 contentItem:RowLayout { id:content;spacing:Theme.dp(7)
  Rectangle { Layout.preferredWidth:Theme.dp(6);Layout.preferredHeight:Theme.dp(6);radius:width/2;color:control.tone==="success"?Theme.statusGreen:control.tone==="warning"?Theme.orange:Theme.muted }
  Text { text:control.label;color:Theme.text;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;verticalAlignment:Text.AlignVCenter }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 ToolTip.visible:hovered&&detail.length>0&&!previewCaptureMode
 ToolTip.text:detail
}
