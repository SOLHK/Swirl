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
 implicitHeight:Theme.statusHeight
 leftPadding:Theme.dp(8);rightPadding:Theme.dp(8)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background:Rectangle { radius:height/2;border.width:Theme.borderWidth;border.color:control.activeFocus?Theme.focusBorder:Theme.border;color:control.down?Theme.pressed:control.hovered?Theme.hover:Theme.capsuleSurface;Behavior on color{ColorAnimation{duration:SwirlMotion.hoverDuration}} }
 contentItem:RowLayout { id:content;spacing:Theme.dp(7)
  Rectangle { Layout.preferredWidth:Theme.dp(6);Layout.preferredHeight:Theme.dp(6);radius:width/2;color:control.tone==="success"?Theme.statusGreen:control.tone==="warning"?Theme.orange:control.tone==="info"?Theme.accent:Theme.muted;Behavior on color{ColorAnimation{duration:SwirlMotion.duration}} }
  SwirlText {renderType:Text.NativeRendering; text:control.label;color:Theme.text;font.pixelSize:Theme.fontSize(11);verticalAlignment:Text.AlignVCenter }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 ToolTip.visible:hovered&&detail.length>0&&!previewCaptureMode
 ToolTip.text:detail
 ToolTip.delay:650
}
