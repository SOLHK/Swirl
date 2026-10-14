import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
Dialog {
    id: dialog
    property bool guardChanges:true
    property Item heroSource:null
    readonly property real heroProgress:heroClock.progress
    SwirlTransitionCoordinator { id:heroClock;duration:SwirlMotion.dialogDuration }
    Binding {target:dialog.contentItem;property:"opacity";value:Math.max(0,Math.min(1,(dialog.heroProgress-0.18)/0.65));when:dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.heroSource;property:"opacity";value:0;when:dialog.visible && dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.contentItem;property:"enabled";value:false;when:dialog.dismissing;restoreMode:Binding.RestoreBindingOrValue}
    property bool dismissing:false
    property string savedFingerprint:""
    readonly property var ownerWindow:parent ? parent.Window.window : null
    function markSaved(){savedFingerprint=dismissals.fingerprint(contentItem)}
    function requestDismiss(){
        if(!visible || dismissing)return
        if(guardChanges && savedFingerprint!==dismissals.fingerprint(contentItem))discardPrompt.open()
        else close()
    }
    modal: true
    focus: true
    transformOrigin:Item.Center
    onAboutToShow: {
        dismissing=false;modal=true
        dismissals.push(dialog,ownerWindow)
        Qt.callLater(markSaved)
        transformOrigin=SwirlMotion.popupOrigin(dialog)
        if(heroSource){scale=1;opacity=1;heroClock.progress=0;heroClock.moveTo(1)}
        else if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onAboutToHide:{dismissing=true;if(heroSource)heroClock.moveTo(0)}
    onClosed:{dismissals.pop(dialog);scale=1;opacity=1}
    width: Math.min(Theme.dp(470), parent ? parent.width-Theme.dp(40) : Theme.dp(470))
    anchors.centerIn: Overlay.overlay
    padding:Theme.dp(23)
    closePolicy: Popup.NoAutoClose
    Dialog {
        id:discardPrompt;objectName:"discardChangesPrompt"
        property var owner:dialog.ownerWindow
        function requestDismiss(){close()}
        modal:true;focus:true;title:"放弃未保存的修改？"
        anchors.centerIn:Overlay.overlay;width:Math.min(Theme.dp(400),dialog.width)
        closePolicy:Popup.NoAutoClose
        enter:Transition{enabled:!SwirlMotion.reduced;ParallelAnimation{NumberAnimation{property:"opacity";from:0;to:1;duration:SwirlMotion.dialogDuration}NumberAnimation{property:"scale";from:0.97;to:1;duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic}}}
        exit:Transition{enabled:!SwirlMotion.reduced;ParallelAnimation{NumberAnimation{property:"opacity";to:0;duration:SwirlMotion.exitDuration}NumberAnimation{property:"scale";to:0.97;duration:SwirlMotion.exitDuration}}}
        onAboutToShow:dismissals.push(discardPrompt,owner)
        onClosed:dismissals.pop(discardPrompt)
        background:SwirlContinuousSurface{radius:Theme.popupRadius;color:Theme.material("floating");border.color:Theme.border;border.width:Theme.borderWidth}
        contentItem:ColumnLayout {
            Text {text:"关闭后将丢失尚未保存的内容。";color:Theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"继续编辑";onClicked:discardPrompt.close()}
                SwirlButton {objectName:"discardChangesConfirm";text:"放弃修改";danger:true;onClicked:{discardPrompt.close();dialog.close()}}
            }
        }
    }
    enter: Transition {
        enabled:!SwirlMotion.reduced && dialog.heroSource===null
        ParallelAnimation {
            NumberAnimation { property:"opacity";to:1; duration: SwirlMotion.dialogDuration }
            NumberAnimation { property:"scale";to:1;duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic }
        }
    }
    exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:dialog.heroSource?SwirlMotion.dialogDuration:SwirlMotion.exitDuration} NumberAnimation {property:"scale";to:dialog.heroSource?1:0.96;duration:dialog.heroSource?SwirlMotion.dialogDuration:SwirlMotion.exitDuration;easing.type:Easing.InCubic} } }
    font.family: Theme.fontFamily
    header: Item {
        implicitHeight:Theme.dp(47)
        opacity:dialog.heroSource?Math.max(0,Math.min(1,(dialog.heroProgress-0.18)/0.65)):1
        Text {
            text: dialog.title
            color: Theme.text; font.pixelSize:Theme.fontSize(18); font.weight: Font.DemiBold
            anchors.left: parent.left; anchors.leftMargin:dialog.leftPadding
            anchors.right:parent.right; anchors.rightMargin:dialog.rightPadding
            elide:Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Item {
        id:heroBackground
        readonly property point origin:dialog.heroSource?dialog.heroSource.mapToItem(heroBackground,0,0):Qt.point(0,0)
        SwirlContinuousSurface {
            x:heroBackground.origin.x*(1-dialog.heroProgress);y:heroBackground.origin.y*(1-dialog.heroProgress)
            width:dialog.heroSource?dialog.heroSource.width+(parent.width-dialog.heroSource.width)*dialog.heroProgress:parent.width
            height:dialog.heroSource?dialog.heroSource.height+(parent.height-dialog.heroSource.height)*dialog.heroProgress:parent.height
            color: Theme.material("floating")
            radius:Theme.dp(dialog.heroSource?10+17*dialog.heroProgress:27)
            antialiasing:true; border.width:Theme.dp(1);border.color:Theme.glassRim
        }
    }
}
