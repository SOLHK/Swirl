import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick
import "../controls"

CheckBox {
    id: control
    padding: 0
    spacing: Theme.compactGap
    implicitHeight: Math.max(Theme.dp(22), label.implicitHeight)
    hoverEnabled: true
    property bool motionInitialized:false
    property color shownColor:targetColor
    property real markOpacity:0
    property real markScale:0.65
    readonly property color targetColor:checked?Theme.primaryButton:enabled && hovered?Theme.hover:Theme.buttonBase
    readonly property bool windowVisible:!Window.window || (Window.window.visible && Window.window.visibility!==Window.Minimized)
    readonly property bool animate:visible && windowVisible && !SwirlMotion.reduced
    readonly property bool moving:colorTravel.running || markFade.running || markTravel.running || contact.moving
    function finishMotion(){
        if(!motionInitialized)return
        colorTravel.stop();markFade.stop();markTravel.stop()
        shownColor=targetColor;markOpacity=checkState===Qt.Checked?1:0;markScale=checkState===Qt.Checked?1:0.65
    }
    function retargetMotion(){
        if(!motionInitialized)return
        if(!animate){finishMotion();return}
        colorTravel.stop();colorTravel.from=shownColor;colorTravel.to=targetColor
        if(shownColor!==targetColor)colorTravel.start()
        markFade.stop();markFade.from=markOpacity;markFade.to=checkState===Qt.Checked?1:0
        if(markOpacity!==markFade.to)markFade.start()
        markTravel.stop();markTravel.from=markScale;markTravel.to=checkState===Qt.Checked?1:0.65
        if(markScale!==markTravel.to)markTravel.start()
    }
    onTargetColorChanged:retargetMotion()
    onCheckStateChanged:retargetMotion()
    onAnimateChanged:if(!animate)finishMotion()
    Component.onCompleted:{motionInitialized=true;finishMotion()}
    ColorAnimation {id:colorTravel;target:control;property:"shownColor";duration:SwirlMotion.switchDuration}
    NumberAnimation {id:markFade;target:control;property:"markOpacity";duration:SwirlMotion.releaseDuration}
    NumberAnimation {id:markTravel;target:control;property:"markScale";duration:SwirlMotion.switchDuration;easing.type:Easing.OutCubic}
    SwirlInteractionMotion {id:contact;hovered:control.hovered;pressed:control.down;focused:control.visualFocus;controlEnabled:control.enabled}
    indicator: Rectangle {
        x: 0; y: (control.height - height) / 2
        width: Theme.dp(16); height: width; radius: Theme.dp(4)
        color: control.shownColor
        border.width: control.checked ? 0 : Theme.borderWidth
        border.color: Theme.controlBorder
        opacity: control.enabled ? 1 : Theme.disabledOpacity
        scale: 1-(1-SwirlMotion.pressScale)*contact.contact
        SwirlIcon {
            anchors.centerIn: parent; size: Theme.dp(12)
            name: "checkmark"
            color: Theme.primaryButtonText
            opacity: control.markOpacity
            scale: control.markScale
            Accessible.ignored: true
        }
        Rectangle {
            anchors.centerIn: parent
            width: Theme.dp(8); height: Theme.dp(2); radius: Theme.dp(1)
            color: Theme.primaryButtonText
            visible: control.checkState === Qt.PartiallyChecked
        }
        Rectangle {
            anchors.fill: parent
            visible:opacity>0;opacity:contact.focusAmount;color:Theme.withAlpha(Theme.text,0.12);radius:Theme.dp(4)
        }
    }
    contentItem: SwirlText {
        id: label
        leftPadding: control.indicator.width + control.spacing
        text: control.text; textRole: "button"; font.pixelSize: Theme.bodySize
        color: control.enabled ? Theme.text : Theme.muted
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.Wrap
    }
}
