import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import QtCore
import SwirlQuick
import "components"
import "controls"
import "pages"
ApplicationWindow {
    id:window
    readonly property var engineControllerContext: engineController
    readonly property var systemProviderContext: systemProvider
    readonly property var captureProviderContext: captureProvider
    // Use Qt's standard SDR swapchain, also on an HDR desktop. Qt Quick 2D
    // cannot color-manage all foreground primitives via a window-wide shader
    // without text entering another texture. Clarity takes priority until that
    // path can operate per primitive. HDR capability/readback remains available
    // in the dedicated test renderer; no foreground postprocessing is applied.
    visible:true
    width:Theme.dp(914); height:Theme.dp(672)
    // Qt Quick reports logical dimensions and handles each QScreen's device
    // pixel ratio. Manual sizing is applied to design metrics, not a scene transform.
    readonly property real contentScale:1.0
    property bool geometryReady:false
    minimumWidth:Theme.windowMinimumWidth; minimumHeight:Theme.windowMinimumHeight
    title:"Swirl"; flags:Qt.Window | Qt.FramelessWindowHint; color:"transparent"
    font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(16)
    palette.window:Theme.canvas
    palette.base:Theme.material("field")
    palette.button:Theme.buttonBase
    palette.buttonText:Theme.text
    palette.text:Theme.text
    palette.highlight:Theme.selected
    palette.highlightedText:Theme.text
    palette.light:Theme.buttonBase
    palette.mid:Theme.controlBorder
    property bool swirlTransparencyEnabled:Theme.transparency
    function preparePreviewState(state){const item=previewPage==="dns"?settingsLoader.item:pageLoader.item;if(item&&item.preparePreviewState)item.preparePreviewState(state)}
    function previewScrollBottom() { if(pageLoader.item && pageLoader.item.scrollToBottom)pageLoader.item.scrollToBottom() }
    property real swirlWindowRadius:Theme.windowRadius
    readonly property real shellRadius:window.visibility===Window.Maximized || window.visibility===Window.FullScreen ? 0 : Theme.windowRadius
    Binding { target:window.captureProviderContext; property:"upstreamProxyPort"; value:window.engineControllerContext.processAlive?window.engineControllerContext.activeProxyPort:0 }
    Connections { target:window.captureProviderContext; function onStateChanged(){window.engineControllerContext.setCaptureProxyPort(window.captureProviderContext.running?window.captureProviderContext.port:0)} }
    Connections { target:backdrop; function onChanged() { Theme.backdropActive=backdrop.active } }
    Binding { target:Theme; property:"windowActive"; value:previewState==="inactive"?false:window.active }
    readonly property real sidebarGutter:Theme.pageInset
    readonly property real actualSidebarWidth:Theme.sidebarWidth
    Settings { id:windowSettings; category:"Window"; property int normalWidth:0; property int normalHeight:0 }
    onWidthChanged:if(geometryReady && visibility===Window.Windowed)windowSettings.normalWidth=Math.round(width)
    onHeightChanged:if(geometryReady && visibility===Window.Windowed)windowSettings.normalHeight=Math.round(height)
    background:Rectangle {
        radius:window.shellRadius; antialiasing:true
        color:"transparent"
        border.width:Theme.dp(0)
    }
    Component.onCompleted:{
        // Initial aspect ratio is a starting size, not a persistent constraint
        // that can overwrite the OS height when maximization changes width.
        if(windowSettings.normalWidth>=minimumWidth && windowSettings.normalHeight>=minimumHeight && windowSettings.normalWidth<=Screen.desktopAvailableWidth && windowSettings.normalHeight<=Screen.desktopAvailableHeight) {
            window.width=windowSettings.normalWidth
            window.height=windowSettings.normalHeight
        } else {
            window.width=minimumWidth
            window.height=minimumHeight
        }
        geometryReady=true
        backdrop.apply(window,Theme.transparency,Theme.dark)
        AppState.initializeHistory()
        if(previewTheme==="dark")Theme.mode="Dark"
        else if(previewTheme==="light")Theme.mode="Light"
        if(previewPage.length)AppState.currentPage=previewPage
        if(previewPage==="external")Qt.callLater(openDashboard)
        if(previewPage==="dns")Qt.callLater(function(){openSettings("dns")})
    }
    Connections {
        target: Theme
        function onTransparencyChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
        function onDarkChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
        function onUiScaleChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
    }
    Binding {
        target:Theme; property:"pageBranch"
        value:pageLoader.routeKey==="activity" || pageLoader.routeKey==="overview" || pageLoader.routeKey==="rewrite" ? "A" : "B"
    }
    Item {
        id:scaledCanvas
        // DWM supplies the native material underneath the sharp QML content.
        width:window.width; height:window.height
        SwirlGlassMaterial {anchors.fill:parent;targetWindow:window}

        MouseArea {
            objectName:"titleDragArea"
            x:Theme.dp(0); y:Theme.dp(0); width:parent.width; height:Theme.dp(68)
            acceptedButtons:Qt.LeftButton|Qt.RightButton
            property point pressPosition
            property bool nativeMoveStarted:false
            onPressed:mouse=>{ pressPosition=Qt.point(mouse.x,mouse.y);nativeMoveStarted=false;if(mouse.button===Qt.RightButton)backdrop.showSystemMenu() }
            onPositionChanged:mouse=>{ if(pressed&&(pressedButtons&Qt.LeftButton)&&!nativeMoveStarted&&Math.hypot(mouse.x-pressPosition.x,mouse.y-pressPosition.y)>Qt.styleHints.startDragDistance){nativeMoveStarted=true;window.startSystemMove()} }
            onDoubleClicked:window.visibility===Window.Maximized ? window.showNormal() : window.showMaximized()
        }
        SwirlSidebar { id:sidebar; width:window.actualSidebarWidth; height:parent.height; compactByWindow:false }
        Item {
            id:mainArea; x:window.actualSidebarWidth+window.sidebarGutter; width:parent.width-x-Theme.dp(12); height:parent.height
            RowLayout {
                id:toolbar; visible:AppState.currentPage==="activity"; x:Theme.dp(4); y:Theme.dp(8); width:parent.width-Theme.dp(14); height:Theme.statusHeight; spacing:Theme.dp(8)
                SwirlStatusCapsule { objectName:"eventsCapsule"; Layout.preferredWidth:implicitWidth; Layout.preferredHeight:Theme.statusHeight; label:systemProvider.eventCount>0?systemProvider.eventCount+" 个事件":"暂无事件";tone:systemProvider.eventCount>0?"info":"neutral";detail:"查看事件与活动记录"; onClicked:AppState.navigate("logs") }
                Item { Layout.fillWidth:true }
                SwirlStatusCapsule { objectName:"proxyCapsule"; Layout.preferredWidth:implicitWidth; Layout.preferredHeight:Theme.statusHeight; label:engineController.systemProxy.systemEnabled&&!engineController.systemProxy.owned?"系统代理 · 其他应用":"系统代理";tone:engineController.systemProxy.error.length||engineController.routingError.length?"warning":engineController.systemProxy.systemEnabled?"success":"neutral";detail:engineController.systemProxy.error||engineController.routingError||(engineController.systemProxy.systemEnabled&&!engineController.systemProxy.owned?"系统代理由其他应用启用，点击让 Swirl 接管":engineController.systemProxy.enabled?"系统代理已开启，点击关闭":"系统代理已关闭，点击开启"); enabled:!engineController.busy; onClicked:{window.proxyRequestedAction=!engineController.systemProxy.enabled;window.proxyTogglePending=true;engineController.setSystemProxy(window.proxyRequestedAction);window.showProxyError()} }
                SwirlStatusCapsule { objectName:"tunCapsule"; Layout.preferredWidth:implicitWidth; Layout.preferredHeight:Theme.statusHeight; label:"增强模式";detail:engineController.routingError||(engineController.tunEnabled?"增强模式已开启，点击关闭":"点击开启增强模式接管网络"); tone:engineController.tunEnabled?"success":"neutral"; enabled:!engineController.busy; onClicked:{if(!engineController.setTunEnabled(!engineController.tunRequested))AppState.notice(engineController.routingError||engineController.networkConfigurationError)} }
                SwirlButton { visible:captureProvider.running; text:"抓包中 · "+captureProvider.sessions.length; iconName:"capture"; font.pixelSize:Theme.fontSize(14); onClicked:AppState.navigate("capture") }

            }
            SwirlPageHost {
                routeKey:AppState.currentPage==="requestlogs" || AppState.currentPage==="dashboard" ? "activity" : AppState.currentPage
                id:pageLoader; objectName:"pageLoader"; x:Theme.dp(0); y:AppState.currentPage==="activity" || AppState.currentPage==="overview" || AppState.currentPage==="rewrite" ? Theme.dp(40):Theme.dp(12); width:parent.width; height:parent.height-y-Theme.dp(12)
                sourceComponent:AppState.currentPage==="overview" ? overview :
                                AppState.currentPage==="activity" || AppState.currentPage==="requestlogs" || AppState.currentPage==="dashboard" ? activity :
                                AppState.currentPage==="capture" ? capturePage :
                                AppState.currentPage==="connections" ? connections :
                                AppState.currentPage==="processes" ? processes :
                                AppState.currentPage==="proxies" ? proxies :
                                AppState.currentPage==="inspector" ? inspector :
                                AppState.currentPage==="scripts" ? scripts :
                                AppState.currentPage==="settings" ? settings :
                                AppState.currentPage==="toolbox" ? toolbox :
                                AppState.currentPage==="dns" ? dns :
                                AppState.currentPage==="rules" ? rules :
                                AppState.currentPage==="logs" ? logs :
                                AppState.currentPage==="tls" ? tls :
                                AppState.currentPage==="replay" ? replay :
                                AppState.currentPage==="rewrite" ? rewrite :
                                AppState.currentPage==="profiles" ? profiles :
                                AppState.currentPage==="subscriptions" ? subscriptions :
                                AppState.currentPage==="policies" ? policies :
                                AppState.currentPage==="traffic" ? traffic :
                                AppState.currentPage==="breakpoint" ? breakpoint :
                                AppState.currentPage==="map" ? mapLocal :
                                AppState.currentPage==="modules" ? modules :
                                AppState.currentPage==="automation" ? automation :
                                AppState.currentPage==="api" ? api :
                                AppState.currentPage==="gateway" ? gateway :
                                AppState.currentPage==="featurehub" ? featureHub :
                                FeatureCatalog.find(AppState.currentPage) ? featureModule :
                                AppState.currentPage==="external" ? externalTools : workbench
            }
        }
    }
    property bool proxyTogglePending:false
    property bool proxyRequestedAction:false
    function showProxyError(){if(!proxyTogglePending)return;const message=engineController.systemProxy.error||engineController.routingError;if(message.length){AppState.notice(message);proxyTogglePending=false}else if(proxyRequestedAction?engineController.systemProxy.owned:!engineController.systemProxy.enabled){if(!engineController.busy)proxyTogglePending=false}}
    Connections{target:engineController;function onStatusChanged(){window.showProxyError()}}
    Connections{target:engineController.systemProxy;function onChanged(){window.showProxyError()}}
    function openDashboard(){dashboardWindow.show();dashboardWindow.raise();dashboardWindow.requestActivate()}
    function openCaptureInspector(){captureInspectorDialog.open()}
    property Item settingsOrigin:null
    property rect settingsOriginRect:Qt.rect(0,0,0,0)
    property rect settingsOriginTitleRect:Qt.rect(0,0,0,0)
    property string settingsOriginTitle:""
    property real settingsOriginFontSize:Theme.fontSize(16)
    readonly property real settingsOriginProgress:settingsTransition.progress
    readonly property bool settingsOriginMoving:settingsOrigin!==null && settingsTransition.moving && !SwirlMotion.reduced
    readonly property rect settingsDestinationRect:Qt.rect(settingsSheet.x-window.x,settingsSheet.y-window.y,settingsSheet.width,settingsSheet.height)
    function openSettings(route,origin){
        if(settingsSheet.visible && route!==settingsSheet.section && (dismissals.hasPopup(settingsSheet) || (settingsSheet.section==='dns' && settingsSheet.savedFingerprint!==dismissals.fingerprint(settingsLoader.item)))) { settingsSheet.raise(); settingsSheet.requestActivate(); return }
        settingsSheet.closeApproved=false
        settingsOrigin=origin || null
        if(settingsOrigin) {
            const point=settingsOrigin.mapToItem(window.contentItem,0,0)
            settingsOriginRect=Qt.rect(point.x,point.y,settingsOrigin.width,settingsOrigin.height)
            const titleItem=settingsOrigin.motionTitle || settingsOrigin
            const titlePoint=titleItem.mapToItem(window.contentItem,0,0)
            settingsOriginTitleRect=Qt.rect(titlePoint.x,titlePoint.y,titleItem.width,titleItem.height)
            settingsOriginTitle=titleItem.text || ""
            settingsOriginFontSize=titleItem.font?titleItem.font.pixelSize:Theme.fontSize(16)
        }
        if(!settingsSheet.visible){settingsSheet.x=Math.round(window.x+(window.width-settingsSheet.width)/2);settingsSheet.y=Math.round(Math.max(0,Math.min(window.y,Screen.desktopAvailableHeight-settingsSheet.height)))}
        settingsSheet.section=route;settingsSheet.updateSettingsSection();settingsSheet.show()
        settingsTransition.moveTo(1);settingsSheet.raise();settingsSheet.requestActivate()
    }
    function closeSettings(){settingsSheet.close()}
    // Restore the original card-to-detail geometric path using the existing
    // reversible settings clock. Native settings windows and their cache stay
    // intact; only the material and live glyphs travel through the main scene.
    Item {
        anchors.fill:parent;z:997;visible:window.settingsOriginMoving
        readonly property real reveal:window.settingsOriginProgress
        readonly property rect destination:window.settingsDestinationRect
        readonly property real handoff:Math.max(0,Math.min(1,(reveal-0.7)/0.3))
        SwirlGlassPanel {
            x:Math.round(window.settingsOriginRect.x+(parent.destination.x-window.settingsOriginRect.x)*parent.reveal)
            y:Math.round(window.settingsOriginRect.y+(parent.destination.y-window.settingsOriginRect.y)*parent.reveal)
            width:Math.round(window.settingsOriginRect.width+(parent.destination.width-window.settingsOriginRect.width)*parent.reveal)
            height:Math.round(window.settingsOriginRect.height+(parent.destination.height-window.settingsOriginRect.height)*parent.reveal)
            cornerRadius:Theme.cardRadius+(Theme.windowRadius-Theme.cardRadius)*parent.reveal
            material:"floating";independentCard:false;opacity:1-parent.handoff
        }
        SwirlText {
            x:Math.round(window.settingsOriginTitleRect.x+(parent.destination.x+Theme.dp(64)-window.settingsOriginTitleRect.x)*parent.reveal)
            y:Math.round(window.settingsOriginTitleRect.y+(parent.destination.y+Theme.dp(12)-window.settingsOriginTitleRect.y)*parent.reveal)
            width:Math.round(window.settingsOriginTitleRect.width+(Math.max(0,parent.destination.width-Theme.dp(128))-window.settingsOriginTitleRect.width)*parent.reveal)
            height:Math.round(window.settingsOriginTitleRect.height+(Theme.dp(28)-window.settingsOriginTitleRect.height)*parent.reveal)
            text:window.settingsOriginTitle;color:Theme.text;visible:parent.handoff<1
            font.pixelSize:Math.round(window.settingsOriginFontSize+(Theme.fontSize(15)-window.settingsOriginFontSize)*parent.reveal)
            font.weight:Font.DemiBold;elide:Text.ElideRight;verticalAlignment:Text.AlignVCenter
        }
    }
    function openRewriteEditor(kind,title){rewriteRulesDialog.kind=kind;rewriteRulesDialog.title=title;rewriteRulesDialog.open()}
    RewriteRulesDialog{id:rewriteRulesDialog}
    SwirlSecondaryWindow {
        composition:panelBackdrop
        id:dashboardWindow;objectName:"dashboardWindow";function openProxyControl(){hide();AppState.navigate("policies");window.show();window.raise();window.requestActivate()}
        visible:false;width:Theme.dp(1300);height:Theme.dp(600);minimumWidth:Theme.dp(914);minimumHeight:Theme.dp(560);title:"Swirl 面板";flags:Qt.Window|Qt.FramelessWindowHint;color:"transparent"
        function openCaptureInspector(){window.openCaptureInspector()}
        ExternalToolsPage{anchors.fill:parent;clip:true}
    }

    SwirlSecondaryWindow {
        composition:settingsBackdrop
        id:settingsSheet;objectName:"settingsSheet";
        opacity:window.settingsOriginMoving?Math.max(0,Math.min(1,(settingsTransition.progress-0.7)/0.3)):1
        property string section:"dns";visible:false;width:Math.min(Theme.dp(900),Screen.desktopAvailableWidth);height:Math.min(Theme.dp(790),Screen.desktopAvailableHeight);title:section==="subscriptions"?"Swirl 订阅管理":section==="proxies"?"Swirl 节点管理":section==="profiles"?"Swirl 配置":section==="modules"?"Swirl 模块":section==="scripts"?"Swirl 脚本":"Swirl 设置";flags:Qt.Window|Qt.FramelessWindowHint;modality:Qt.WindowModal;transientParent:window;color:"transparent"
        function closeSettings(){settingsSheet.close()}
        function updateSettingsSection(){if(settingsLoader.item&&settingsLoader.item.section!==undefined)settingsLoader.item.section=section==="appearance"?"外观":section==="fonts"?"字体":section==="license"?"关于 Swirl":"常规"}
        readonly property real reveal:settingsTransition.progress
        property bool closeApproved:false
        SwirlTransitionCoordinator{id:settingsTransition;duration:SwirlMotion.dialogDuration
            onMovingChanged:if(!moving && destination===0 && settingsSheet.visible)
                Qt.callLater(function(){
                    if(!settingsTransition.moving && settingsTransition.destination===0 && settingsSheet.visible){
                        settingsSheet.closeApproved=true
                        settingsSheet.close()
                    }
                })
        }

        property string savedFingerprint:""
        property bool discardApproved:false
        onVisibleChanged:if(visible){discardApproved=false;closeApproved=false;settingsTransition.moveTo(1);Qt.callLater(function(){savedFingerprint=dismissals.fingerprint(settingsLoader.item)})}else{
            settingsTransition.destination=0;settingsTransition.finish()
            if(window.settingsOrigin && window.settingsOrigin.visible)window.settingsOrigin.forceActiveFocus()
            window.settingsOrigin=null
        }
        onClosing:close=>{
            if(!discardApproved && dismissals.hasPopup(settingsSheet)){close.accepted=false;dismissals.dismiss(settingsSheet);return}
            // DNS is an unapplied page form. Other settings persist on change.
            if(section==="dns" && !discardApproved && savedFingerprint!==dismissals.fingerprint(settingsLoader.item)) {
                close.accepted=false;settingsDiscard.open();return
            }
            if(!closeApproved && !SwirlMotion.reduced){close.accepted=false;if(settingsTransition.destination!==0){settingsTransition.moveTo(0)}return}
            closeApproved=false;window.requestActivate()
        }
        onSectionChanged:updateSettingsSection()
        SwirlDialog {
            id:settingsDiscard;objectName:"settingsDiscard";title:"放弃未保存的修改？";guardChanges:false
            parent:settingsSheet.contentItem
            ColumnLayout { width:parent.width;spacing:Theme.dp(14)
                SwirlText {text:"DNS 修改尚未应用。";color:Theme.text}
                RowLayout {Layout.alignment:Qt.AlignRight
                    SwirlButton {text:"继续编辑";onClicked:settingsDiscard.close()}
                    SwirlButton {text:"放弃修改";danger:true;onClicked:{settingsSheet.discardApproved=true;settingsDiscard.close();Qt.callLater(function(){settingsSheet.close()})}}
                }
            }
        }
        SwirlPageHost{id:settingsLoader;routeKey:settingsSheet.section;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.bottom:parent.bottom;clip:true
sourceComponent:settingsSheet.section==="subscriptions"?subscriptions:settingsSheet.section==="proxies"?proxies:settingsSheet.section==="dns"?dns:settingsSheet.section==="modules"?modules:settingsSheet.section==="profiles"?profiles:settingsSheet.section==="scripts"?scripts:settings;onItemChanged:Qt.callLater(settingsSheet.updateSettingsSection)}
    }
    SwirlDialog {
        id:captureInspectorDialog;title:"HTTP 请求详情";width:Math.min(Theme.dp(1000),window.width-Theme.dp(20));height:Math.min(Theme.dp(650),window.height-Theme.dp(20));padding:Theme.dp(14)
        CaptureInspectorPage{captureProvider:window.captureProviderContext;anchors.fill:parent}
    }
    // Native move and eight-edge resize keep Windows snap/DPI behavior.
    Repeater {
        model:[Qt.LeftEdge,Qt.RightEdge,Qt.TopEdge,Qt.BottomEdge,Qt.LeftEdge|Qt.TopEdge,Qt.RightEdge|Qt.TopEdge,Qt.LeftEdge|Qt.BottomEdge,Qt.RightEdge|Qt.BottomEdge]
        MouseArea {
            required property int modelData
            readonly property bool edgeleft:(modelData&Qt.LeftEdge)!==0
            readonly property bool edgeright:(modelData&Qt.RightEdge)!==0
            readonly property bool edgetop:(modelData&Qt.TopEdge)!==0
            readonly property bool edgebottom:(modelData&Qt.BottomEdge)!==0
            readonly property bool corner:(edgeleft||edgeright)&&(edgetop||edgebottom)
            z:100; visible:window.visibility!==Window.Maximized && window.visibility!==Window.FullScreen
            x:edgeright?window.width-width:Theme.dp(0); y:edgebottom?window.height-height:Theme.dp(0)
            width:corner?Theme.dp(10):(edgeleft||edgeright)?Theme.dp(5):window.width
            height:corner?Theme.dp(10):(edgetop||edgebottom)?Theme.dp(5):window.height
            cursorShape:corner?(edgeleft&&edgetop||edgeright&&edgebottom?Qt.SizeFDiagCursor:Qt.SizeBDiagCursor):(edgeleft||edgeright)?Qt.SizeHorCursor:Qt.SizeVerCursor
            onPressed:window.startSystemResize(modelData)
        }
    }
    Shortcut { sequence:"Alt+Space"; context:Qt.ApplicationShortcut; onActivated:backdrop.showSystemMenu() }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+K"; context:Qt.ApplicationShortcut; onActivated:sidebar.openSearch() }
    Shortcut { enabled:dismissals.count===0;sequence:"Alt+Left"; onActivated:AppState.goBack() }
    Shortcut { enabled:dismissals.count===0;sequence:"Alt+Right"; onActivated:AppState.goForward() }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+1"; onActivated:AppState.navigate("overview") }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+2"; onActivated:AppState.navigate("proxies") }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+3"; onActivated:AppState.navigate("connections") }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+4"; onActivated:AppState.navigate("inspector") }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+,"; onActivated:AppState.navigate("settings") }
    Shortcut { enabled:dismissals.count===0;sequence:"Ctrl+B"; onActivated:AppState.sidebarCollapsed=!AppState.sidebarCollapsed }
        Component { id:activity; ActivityPage { engineController:window.engineControllerContext; systemProvider:window.systemProviderContext } }
        Component { id:overview; OverviewPage { engineController:window.engineControllerContext; systemProvider:window.systemProviderContext } }
    Component { id:capturePage; CapturePage { captureProvider:window.captureProviderContext } }
    Component { id:externalTools; ExternalToolsPage {} }
    Component { id:featureHub; FeatureHubPage {} }
    Component { id:featureModule; FeatureModulePage { moduleId:parent.routeId } }
    Component { id:connections; ConnectionsPage {} }
    Component { id:processes; ProcessesPage { engineController:window.engineControllerContext } }
    Component { id:proxies; ProxiesPage {} }
    Component { id:inspector; InspectorPage {} }
    Component { id:scripts; ScriptsPage {} }
    Component { id:settings; SettingsPage {} }
    Component { id:toolbox; ToolboxPage {} }
    Component { id:dns; DNSPage {} }
    Component { id:rules; RulesPage { engineController:window.engineControllerContext } }
    Component { id:logs; LogsPage {} }
    Component { id:tls; TLSPage {} }
    Component { id:replay; ReplayPage {} }
    Component { id:rewrite; RewritePage {} }
    Component { id:profiles; ProfilesPage {} }
    Component { id:subscriptions; SubscriptionsPage {} }
    Component { id:policies; PolicyGroupsPage { engineController:window.engineControllerContext } }
    Component { id:traffic; TrafficAnalyticsPage {} }
    Component { id:breakpoint; BreakpointPage {} }
    Component { id:mapLocal; MapPage {} }
    Component { id:modules; ModulesPage {} }
    Component { id:automation; AutomationPage {} }
    Component { id:api; ApiPage {} }
    Component { id:gateway; GatewayPage {} }
    Component { id:workbench; WorkbenchPage { pageId:parent.routeId } }

    Timer { interval:1000; running:true; repeat:true; onTriggered:AppState.tickTraffic() }
    // Compatibility outline only. Native windows use one compositor contour.
    SwirlContinuousSurface {
        objectName:"windowOutline";visible:!backdrop.nativeCorners
        anchors.fill:parent;z:998;color:"transparent";antialiasing:true
        radius:window.shellRadius
        border.width:window.visibility===Window.Maximized?0:1/Screen.devicePixelRatio
        border.color:Theme.dark?Qt.rgba(1,1,1,window.active?0.30:0.20):Qt.rgba(0,0,0,window.active?0.12:0.08)
    }
    Timer { id:toastTimer; interval:3200; onTriggered:AppState.toast="" }
    Connections { target:AppState; function onToastChanged(){if(AppState.toast.length)toastTimer.restart()} }
    Rectangle {
        visible:AppState.toast.length>0; z:999
        anchors.horizontalCenter:parent.horizontalCenter; anchors.bottom:parent.bottom; anchors.bottomMargin:Theme.dp(28)
        width:Math.min(Theme.dp(570),window.width-Theme.dp(40)); height:Theme.dp(48); radius:Theme.controlRadius
        color:Theme.material("floating"); border.color:Theme.border
        SwirlText { anchors.fill:parent; anchors.margins:Theme.dp(12); text:AppState.toast; color:Theme.muted; font.pixelSize:Theme.fontSize(14); verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight }
    }
    Timer {
        running:smokeTestMode; repeat:true; interval:200
        property int index:0
        onTriggered:{
            if(index>=AppState.allPageIds.length){console.info("SMOKE_PAGES",index);stop();window.navigationSmokeCompleted();return}
            AppState.currentPage=AppState.allPageIds[index++]
        }
    }
    signal navigationSmokeCompleted()
}
