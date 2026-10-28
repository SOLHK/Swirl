import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
SwirlMotionButton {
 id:control
 property string label:""
 property string tone:"neutral"
 property string detail:""
 property string activityPhase:""
 property bool proxyWing:false
 implicitWidth:content.implicitWidth+Theme.dp(24)
 implicitHeight:Theme.statusHeight
 leftPadding:Theme.dp(8);rightPadding:Theme.dp(8)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background: Rectangle {
  id: capsuleSurface
  radius: height / 2
  antialiasing: true
  readonly property color base: control.tone === "success" ? Theme.successSurface : Theme.capsuleSurface
  gradient: Gradient {
   GradientStop { position: 0; color: control.down ? Theme.pressed : control.hovered ? Theme.surface : Theme.withAlpha(Theme.surface, 0.95) }
   GradientStop { position: 1; color: control.down ? Theme.pressed : control.hovered ? Qt.lighter(capsuleSurface.base, 1.02) : capsuleSurface.base }
  }
  border.width: 1 / Screen.devicePixelRatio
  border.color: control.visualFocus ? Theme.focusBorder : control.tone === "success" ? Theme.withAlpha(Theme.successText, 0.26) : Theme.withAlpha(Theme.text, control.hovered ? 0.25 : 0.16)
  Behavior on border.color { ColorAnimation { duration: SwirlMotion.hoverDuration } }
 }
 HoverHandler { cursorShape: Qt.PointingHandCursor }
 contentItem:RowLayout { id:content;spacing:Theme.dp(7)
  Rectangle { visible:!control.activityPhase.length;Layout.preferredWidth:Theme.dp(6);Layout.preferredHeight:Theme.dp(6);radius:width/2;color:control.tone==="success"?Theme.successText:control.tone==="warning"?Theme.orange:control.tone==="info"?Theme.accent:Theme.muted;Behavior on color{ColorAnimation{duration:SwirlMotion.duration}} }
  SwirlFlow {visible:control.activityPhase.length>0;Layout.preferredWidth:Theme.dp(25);Layout.preferredHeight:Theme.dp(14);phase:control.activityPhase;proxyWing:control.proxyWing}
  SwirlText {textRole:"smallLabel";renderType:Text.NativeRendering; text:control.label;color:control.tone==="success"?Theme.successText:Theme.text;font.pixelSize:Theme.fontSize(11);verticalAlignment:Text.AlignVCenter }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 SwirlToolTip {parent:control;visible:control.hovered&&control.detail.length>0&&!previewCaptureMode;text:control.detail;delay:650}
}
