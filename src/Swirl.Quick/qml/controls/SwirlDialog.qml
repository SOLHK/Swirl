pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
Dialog {
    id: dialog
    property Item returnFocus:null
    property bool guardChanges:true
    property Item heroSource:null
    // Pages that move between native scenes provide their declaration owner.
    // Overlay.overlay on the Popup itself otherwise retains the first scene.
    property Item ownerItem:null
    readonly property real heroProgress:heroClock.progress
    SwirlTransitionCoordinator { id:heroClock;parent:dialog.background;duration:SwirlMotion.dialogDuration }
    Binding {target:dialog.contentItem;property:"opacity";value:Math.max(0,Math.min(1,(dialog.heroProgress-0.18)/0.65));when:dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.heroSource;property:"opacity";value:0;when:dialog.visible && dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.contentItem;property:"enabled";value:false;when:dialog.dismissing;restoreMode:Binding.RestoreBindingOrValue}
    property bool dismissing:false
    property string savedFingerprint:""
    property string stateFingerprint:""
    property bool dismissBlocked:false
    readonly property var ownerWindow:ownerItem?ownerItem.Window.window:parent ? parent.Window.window : null
    function currentFingerprint(){return dismissals.fingerprint(contentItem)+":"+stateFingerprint}
    function markSaved(){savedFingerprint=currentFingerprint()}
    function requestDismiss(){
        if(!visible || dismissing || dismissBlocked)return
        if(guardChanges && savedFingerprint!==currentFingerprint())discardPrompt.open()
        else close()
    }
    modal: true
    focus: true
    transformOrigin:Item.Center
    onAboutToShow: {
        returnFocus=ownerWindow?ownerWindow.activeFocusItem:null
        dismissing=false;modal=true
        dismissals.push(dialog,ownerWindow)
        transformOrigin=SwirlMotion.popupOrigin(dialog)
        if(heroSource){scale=1;opacity=1;heroClock.progress=0;heroClock.moveTo(1)}
        else if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(scale===1 && opacity===1){scale=0.975;opacity=0}
    }
    // The modal can be opened (and Escape pressed) before a Qt.callLater
    // callback executes. Snapshot the initialized fields synchronously when
    // the popup reports opened, so an untouched form never prompts to discard.
    onOpened:markSaved()
    onAboutToHide:{dismissing=true;if(heroSource)heroClock.moveTo(0)}
    onClosed:{dismissals.pop(dialog);scale=1;opacity=1;if(returnFocus && returnFocus.visible)returnFocus.forceActiveFocus()}
    parent:ownerItem?ownerItem.Overlay.overlay:Overlay.overlay
    width: Math.floor(Math.min(Theme.dp(470), parent ? parent.width-Theme.dp(40) : Theme.dp(470)))
    x:parent ? Math.round((parent.width-width)/2) : 0
    y:parent ? Math.round((parent.height-height)/2) : 0
    padding:Theme.dp(23)
    closePolicy: Popup.NoAutoClose
    Dialog {
        id:discardPrompt;objectName:"discardChangesPrompt"
        property var owner:dialog.ownerWindow
        function requestDismiss(){close()}
        modal:true;focus:true;title:"放弃未保存的修改？"
        font.family:Theme.fontFamily
        // The style owns this header (including its bold weight and padding).
        // Resolve its actual font after inheritance, without replacing it.
        SwirlFontBinding {target:discardPrompt.header;textRole:"pageTitle"}
        Binding {target:discardPrompt.header;property:"font.hintingPreference";value:Font.PreferFullHinting}
        Binding {target:discardPrompt.header;property:"renderType";value:Text.NativeRendering}
        parent:dialog.parent
        width:Math.floor(Math.min(Theme.dp(400),dialog.width))
        x:parent ? Math.round((parent.width-width)/2) : 0
        y:parent ? Math.round((parent.height-height)/2) : 0
        closePolicy:Popup.NoAutoClose
        enter:Transition{enabled:!SwirlMotion.reduced;ParallelAnimation{NumberAnimation{property:"opacity";from:0;to:1;duration:SwirlMotion.dialogDuration}}}
        exit:Transition{enabled:!SwirlMotion.reduced;ParallelAnimation{NumberAnimation{property:"opacity";to:0;duration:SwirlMotion.exitDuration}}}
        onAboutToShow:dismissals.push(discardPrompt,owner)
        onClosed:dismissals.pop(discardPrompt)
        background:SwirlClearGlassSurface{radius:Theme.popupRadius;color:Theme.material("floating")}
        // Retain the prompt shell and header hook; its controls are only
        // instantiated while a real unsaved-change confirmation is visible.
        contentItem: Loader {
            active: discardPrompt.visible
            sourceComponent: ColumnLayout {
                spacing: Theme.gap
                SwirlText {text:qsTr("关闭后将丢失尚未保存的内容。");color:Theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
                RowLayout {Layout.alignment:Qt.AlignRight;spacing:Theme.compactGap
                    SwirlButton {text:qsTr("继续编辑");onClicked:discardPrompt.close()}
                    SwirlButton {objectName:"discardChangesConfirm";text:qsTr("放弃修改");danger:true;onClicked:{discardPrompt.close();dialog.close()}}
                }
            }
        }
    }
    enter: Transition {
        enabled:!SwirlMotion.reduced && dialog.heroSource===null
        ParallelAnimation {
            NumberAnimation { property:"opacity";to:1; duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic }
            NumberAnimation { property:"scale";to:1; duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic }
        }
    }
    exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation {
        NumberAnimation {property:"opacity";to:0;duration:dialog.heroSource?SwirlMotion.dialogDuration:SwirlMotion.exitDuration;easing.type:Easing.InCubic}
        NumberAnimation {property:"scale";to:dialog.heroSource?1:0.985;duration:SwirlMotion.exitDuration;easing.type:Easing.InCubic}
    } }
    font.family: Theme.fontFamily
    header: Item {
        implicitHeight:Math.max(Theme.dp(47),dialogTitle.implicitHeight+Theme.dp(20))
        opacity:dialog.heroSource?Math.max(0,Math.min(1,(dialog.heroProgress-0.18)/0.65)):1
        SwirlText {
            id:dialogTitle
            textRole: "pageTitle"
            fitWidth:false
            text: dialog.title
            color: Theme.text; font.pixelSize:Theme.fontSize(18); font.weight: Font.DemiBold
            anchors.left: parent.left; anchors.leftMargin:dialog.leftPadding
            anchors.right:parent.right; anchors.rightMargin:dialog.rightPadding
            wrapMode:Text.Wrap; anchors.verticalCenter: parent.verticalCenter
        }
    }
    background: Item {
        id:heroBackground
        readonly property point origin:dialog.heroSource?dialog.heroSource.mapToItem(heroBackground,0,0):Qt.point(0,0)
        SwirlClearGlassSurface {
            x:Math.round(heroBackground.origin.x*(1-dialog.heroProgress));y:Math.round(heroBackground.origin.y*(1-dialog.heroProgress))
            width:Math.round(dialog.heroSource?dialog.heroSource.width+(parent.width-dialog.heroSource.width)*dialog.heroProgress:parent.width)
            height:Math.round(dialog.heroSource?dialog.heroSource.height+(parent.height-dialog.heroSource.height)*dialog.heroProgress:parent.height)
            color: Theme.material("floating")
            radius:dialog.heroSource?Theme.buttonRadius+(Theme.popupRadius-Theme.buttonRadius)*dialog.heroProgress:Theme.popupRadius
            antialiasing:true
        }
    }
}
