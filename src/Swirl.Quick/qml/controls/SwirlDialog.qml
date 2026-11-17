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
    property bool presentationReady:false
    property Item retainedBackground:null
    Component.onCompleted:presentationReady=true
    Component.onDestruction:presentationReady=false
    // Pages that move between native scenes provide their declaration owner.
    // Overlay.overlay on the Popup itself otherwise retains the first scene.
    property Item ownerItem:null
    // Keep non-visual motion helpers in explicit properties rather than default
    // contentData children, and do not dereference deferred background/contentItem
    // before the popup is shown: calling those getters during unopened page
    // finalization triggers incomplete deferred creation (QTBUG-122956) and lets
    // incremental V4 GC sweep child VME member storage.
    readonly property real heroProgress:heroClock.progress
    readonly property SwirlTransitionCoordinator heroMotionClock:SwirlTransitionCoordinator { id:heroClock;duration:SwirlMotion.dialogDuration }
    readonly property SwirlPopupMotion popupMotion:SwirlPopupMotion {id:reveal;popup:dialog;motionEnabled:dialog.heroSource===null}
    readonly property Translate contentMotionTransform:Translate {id:contentTravel;x:reveal.xOffset;y:reveal.yOffset}
    Binding {target:dialog.presentationReady && dialog.visible && dialog.background?dialog.background.parent:null;property:"transform";value:[contentTravel];when:dialog.presentationReady && dialog.visible && dialog.background!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.visible && dialog.heroSource!==null?dialog.contentItem:null;property:"opacity";value:Math.max(0,Math.min(1,(dialog.heroProgress-0.18)/0.65));when:dialog.visible && dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.visible && dialog.heroSource!==null?dialog.heroSource:null;property:"opacity";value:0;when:dialog.visible && dialog.heroSource!==null;restoreMode:Binding.RestoreBindingOrValue}
    Binding {target:dialog.dismissing?dialog.contentItem:null;property:"enabled";value:false;when:dialog.dismissing;restoreMode:Binding.RestoreBindingOrValue}
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
        const wasDismissing=dismissing
        if(!wasDismissing)returnFocus=ownerWindow?ownerWindow.activeFocusItem:null
        dismissing=false;modal=true
        dismissals.push(dialog,ownerWindow)
        transformOrigin=SwirlMotion.popupOrigin(dialog)
        reveal.prepare(SwirlMotion.popupVector(dialog))
        if(heroSource){scale=1;opacity=1;if(!wasDismissing)heroClock.progress=0;heroClock.moveTo(1)}
        else if(SwirlMotion.reduced){scale=1;opacity=1}
        else if(!wasDismissing && scale===1 && opacity===1){opacity=0}
    }
    // The modal can be opened (and Escape pressed) before a Qt.callLater
    // callback executes. Snapshot the initialized fields synchronously when
    // the popup reports opened, so an untouched form never prompts to discard.
    onOpened:markSaved()
    onAboutToHide:{dismissing=true;if(heroSource)heroClock.moveTo(0)}
    onClosed:{dismissals.pop(dialog);reveal.reset();scale=1;opacity=1}
    parent:ownerItem?ownerItem.Overlay.overlay:Overlay.overlay
    margins:Theme.dp(20)
    width: Math.floor(Math.min(Theme.dp(470), parent ? parent.width-Theme.dp(40) : Theme.dp(470)))
    x:parent ? Math.round((parent.width-width)/2) : 0
    y:parent ? Math.round((parent.height-height)/2) : 0
    padding:Theme.dp(23)
    closePolicy: Popup.NoAutoClose
    readonly property Dialog discardChangesDialog: Dialog {
        id:discardPrompt;objectName:"discardChangesPrompt"
        property var owner:dialog.ownerWindow
        property Item retainedBackground:null
        function requestDismiss(){close()}
        modal:true;focus:true;title:qsTr("放弃未保存的修改？")
        font.family:Theme.fontFamily
        // The style owns this header (including its bold weight and padding).
        // Resolve its actual font after inheritance, without replacing it.
        readonly property SwirlFontBinding headerFont:SwirlFontBinding {target:dialog.presentationReady?discardPrompt.header:null;textRole:"pageTitle"}
        Binding {target:dialog.presentationReady?discardPrompt.header:null;property:"font.hintingPreference";value:Font.PreferFullHinting;when:dialog.presentationReady && discardPrompt.header!==null}
        Binding {target:dialog.presentationReady?discardPrompt.header:null;property:"renderType";value:Text.NativeRendering;when:dialog.presentationReady && discardPrompt.header!==null}
        parent:dialog.parent
        margins:dialog.margins
        width:Math.floor(Math.min(Theme.dp(400),dialog.width))
        x:parent ? Math.round((parent.width-width)/2) : 0
        y:parent ? Math.round((parent.height-height)/2) : 0
        closePolicy:Popup.NoAutoClose
        readonly property SwirlPopupMotion popupMotion:SwirlPopupMotion {id:discardReveal;popup:discardPrompt}
        readonly property Translate discardMotionTransform:Translate {id:discardTravel;x:discardReveal.xOffset;y:discardReveal.yOffset}
        Binding {target:dialog.presentationReady && discardPrompt.visible && discardPrompt.background?discardPrompt.background.parent:null;property:"transform";value:[discardTravel];when:dialog.presentationReady && discardPrompt.visible && discardPrompt.background!==null;restoreMode:Binding.RestoreBindingOrValue}
        opacity:discardReveal.alpha
        enter:discardReveal.enterTransition
        exit:discardReveal.exitTransition
        onAboutToShow:{dismissals.push(discardPrompt,owner);discardReveal.prepare(SwirlMotion.popupVector(discardPrompt))}
        onClosed:{dismissals.pop(discardPrompt);discardReveal.reset()}
        background:SwirlCardSurface{id:discardBackground;Component.onCompleted:discardPrompt.retainedBackground=discardBackground;floating:true;cornerRadius:Theme.popupRadius}
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
            id:dialogEnter
            NumberAnimation { property:"opacity";to:1; duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic }
            NumberAnimation {target:reveal;property:"progress";to:1;duration:SwirlMotion.dialogDuration;easing.type:Easing.OutCubic}
        }
    }
    exit: Transition { enabled:!SwirlMotion.reduced; ParallelAnimation {
        id:dialogExit
        NumberAnimation {property:"opacity";to:0;duration:dialog.heroSource?SwirlMotion.dialogDuration:SwirlMotion.exitDuration;easing.type:Easing.InCubic}
        NumberAnimation {target:reveal;property:"progress";to:0;duration:SwirlMotion.exitDuration;easing.type:Easing.InOutCubic}
    } }
    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced){heroClock.finish();if(!dialog.dismissing){reveal.progress=1;dialog.opacity=1}motionPolicy.finishPopup(dialog)}}}
    font.family: Theme.fontFamily
    readonly property Item retainedHeader: headerItem
    header: Item {
        id:headerItem
        readonly property SwirlText retainedTitle: dialogTitle
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
        Component.onCompleted:dialog.retainedBackground=heroBackground
        readonly property point origin:dialog.heroSource?dialog.heroSource.mapToItem(heroBackground,0,0):Qt.point(0,0)
        readonly property SwirlCardSurface retainedCardSurface:heroSurface
        SwirlCardSurface {
            id:heroSurface
            floating:true
            x:Math.round(heroBackground.origin.x*(1-dialog.heroProgress));y:Math.round(heroBackground.origin.y*(1-dialog.heroProgress))
            width:Math.round(dialog.heroSource?dialog.heroSource.width+(parent.width-dialog.heroSource.width)*dialog.heroProgress:parent.width)
            height:Math.round(dialog.heroSource?dialog.heroSource.height+(parent.height-dialog.heroSource.height)*dialog.heroProgress:parent.height)
            cornerRadius:dialog.heroSource?Theme.buttonRadius+(Theme.popupRadius-Theme.buttonRadius)*dialog.heroProgress:Theme.popupRadius
            antialiasing:true
        }
    }
}
