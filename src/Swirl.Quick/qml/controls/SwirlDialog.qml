import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
Dialog {
    id: dialog
    property bool guardChanges:true
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
        if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.96;opacity=0}
    }
    onAboutToHide:{dismissing=true;modal=false}
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
        background:Rectangle{radius:Theme.popupRadius;color:Theme.material("floating");border.color:Theme.border}
        contentItem:ColumnLayout {
            Text {text:"关闭后将丢失尚未保存的内容。";color:Theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"继续编辑";onClicked:discardPrompt.close()}
                SwirlButton {objectName:"discardChangesConfirm";text:"放弃修改";danger:true;onClicked:{discardPrompt.close();dialog.close()}}
            }
        }
    }
    enter: Transition {
        enabled:!SwirlMotion.reduced
        ParallelAnimation {
            NumberAnimation { property:"opacity";to:1; duration: SwirlMotion.dialogDuration }
            NumberAnimation { property:"scale";to:1;duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic }
        }
    }
    exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.exitDuration} NumberAnimation {property:"scale";to:0.96;duration:SwirlMotion.exitDuration;easing.type:Easing.InCubic} } }
    font.family: "Microsoft YaHei UI"
    header: Item {
        implicitHeight:Theme.dp(47)
        Text {
            text: dialog.title
            color: Theme.text; font.pixelSize:Theme.fontSize(18); font.weight: Font.DemiBold
            anchors.left: parent.left; anchors.leftMargin:dialog.leftPadding
            anchors.right:parent.right; anchors.rightMargin:dialog.rightPadding
            elide:Text.ElideRight; anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Rectangle {
        color: Theme.material("floating")
        radius:Theme.dp(27); antialiasing:true; border.width:Theme.dp(1); border.color: Theme.glassRim
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.leftMargin:Theme.dp(24); anchors.rightMargin:Theme.dp(24); anchors.top: parent.top
            anchors.topMargin:Theme.dp(1); height:Theme.dp(1); color: Theme.glassGlint
        }
    }
}
