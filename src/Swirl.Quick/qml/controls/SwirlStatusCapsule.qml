import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
SwirlMotionButton {
 id:control
 property string label:""
 property string tone:"neutral"
 property string detail:""
 property string activityPhase:""
 implicitWidth:content.implicitWidth+Theme.dp(24)
 implicitHeight:Theme.statusHeight
 leftPadding:Theme.dp(8);rightPadding:Theme.dp(8)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background:SwirlClearGlassSurface { radius:height/2;focused:control.activeFocus;pressed:control.down;hovered:control.hovered }
 contentItem:RowLayout { id:content;spacing:Theme.dp(7)
  Rectangle { visible:!control.activityPhase.length;Layout.preferredWidth:Theme.dp(6);Layout.preferredHeight:Theme.dp(6);radius:width/2;color:control.tone==="success"?Theme.statusGreen:control.tone==="warning"?Theme.orange:control.tone==="info"?Theme.accent:Theme.muted;Behavior on color{ColorAnimation{duration:SwirlMotion.duration}} }
  SwirlFlow {visible:control.activityPhase.length>0;Layout.preferredWidth:Theme.dp(25);Layout.preferredHeight:Theme.dp(14);phase:control.activityPhase}
  SwirlText {textRole:"smallLabel";renderType:Text.NativeRendering; text:control.label;color:Theme.text;font.pixelSize:Theme.fontSize(11);verticalAlignment:Text.AlignVCenter }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 SwirlToolTip {parent:control;visible:control.hovered&&control.detail.length>0&&!previewCaptureMode;text:control.detail;delay:650}
}
