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
 readonly property real accessoryWidth: Theme.dp(control.activityPhase.length ? 25 : 6)
 readonly property real accessorySpacing: Theme.dp(7)
 readonly property bool accessoryShown: !control.proxyWing || SwirlProxyWingMotion.progress > 0
 // Reserve the wing slot in the shell, while centering the currently visible
 // label/accessory group independently. An idle proxy has no empty icon slot.
 implicitWidth: Math.ceil((control.proxyWing ? proxyLabelMetrics.advanceWidth + Theme.dp(25) : caption.implicitWidth + accessoryWidth) + accessorySpacing + Theme.dp(24))
 implicitHeight:Theme.statusHeight
 leftPadding:Theme.dp(8);rightPadding:Theme.dp(8)
 topPadding:0;bottomPadding:0
 hoverEnabled:true
 background: Rectangle {
  id: capsuleSurface
  radius: Theme.pillRadius(height)
  antialiasing: true
  opacity: control.enabled ? 1 : Theme.disabledOpacity
  readonly property color base: control.tone === "success" ? Theme.successSurface : Theme.capsuleSurface
  gradient: Gradient {
   GradientStop { position: 0; color: control.enabled && control.down ? Theme.pressed : control.enabled && control.visualFocus ? Qt.tint(Theme.surface,Theme.withAlpha(Theme.text,0.08)) : control.enabled && control.hovered ? Theme.surface : Theme.withAlpha(Theme.surface, 0.95); Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } } }
   GradientStop { position: 1; color: control.enabled && control.down ? Theme.pressed : control.enabled && control.visualFocus ? Qt.tint(capsuleSurface.base,Theme.withAlpha(Theme.text,0.08)) : control.enabled && control.hovered ? Qt.lighter(capsuleSurface.base, 1.02) : capsuleSurface.base; Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } } }
  }
  border.width:1 / Screen.devicePixelRatio
  border.color:Theme.increaseContrast ? Theme.text : Theme.border
 }
 HoverHandler { enabled: control.enabled; cursorShape: Qt.PointingHandCursor }
 TextMetrics { id: proxyLabelMetrics; font: caption.font; text: qsTr("系统代理 · 外部") }
 contentItem: Item {
  id: content
  opacity: control.enabled ? 1 : Theme.disabledOpacity
  implicitHeight: caption.implicitHeight
  property real accessoryExtent: control.accessoryShown ? control.accessoryWidth + control.accessorySpacing : 0
  Behavior on accessoryExtent { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.hoverDuration; easing.type: Easing.InOutCubic } }
  Item {
   id: contentGroup
   objectName: "statusCapsuleContentGroup"
   width: caption.width + content.accessoryExtent
   height: parent.height
   x: (parent.width - width) / 2
   Item {
    objectName: "statusCapsuleAccessory"
    width: control.accessoryWidth; height: Theme.dp(14)
    anchors.verticalCenter: parent.verticalCenter
    opacity: control.accessoryShown ? 1 : 0
    Behavior on opacity { enabled: !SwirlMotion.reduced; NumberAnimation { duration: SwirlMotion.hoverDuration } }
    Rectangle { visible: !control.activityPhase.length; anchors.centerIn: parent; width: Theme.dp(6); height: width; radius: width / 2; color: control.tone === "success" ? Theme.successText : control.tone === "warning" ? Theme.orange : control.tone === "info" ? Theme.accent : Theme.muted; Behavior on color { ColorAnimation { duration: SwirlMotion.duration } } }
    SwirlFlow { visible: control.activityPhase.length > 0; anchors.fill: parent; phase: control.activityPhase; proxyWing: control.proxyWing }
   }
   SwirlText {
    id: caption
    objectName: "statusCapsuleLabel"
    x: content.accessoryExtent
    anchors.verticalCenter: parent.verticalCenter
    width: Math.min(implicitWidth, Math.max(0, content.width - control.accessoryWidth - control.accessorySpacing))
    height: implicitHeight
    textRole: "smallLabel"; tabularFigures: true; text: control.label
    color: control.tone === "success" ? Theme.successText : Theme.text
    font.pixelSize: Theme.fontSize(11); verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
   }
  }
 }
 Accessible.name:label+(detail.length?"，"+detail:"")
 SwirlToolTip {parent:control;visible:control.hovered&&control.detail.length>0&&!previewCaptureMode;text:control.detail;delay:650}
}
