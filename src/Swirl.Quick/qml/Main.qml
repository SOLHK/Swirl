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
    // The native bootstrap publishes the taskbar resources before first show.
    visible:false
    width:Theme.windowDefaultWidth; height:Theme.windowDefaultHeight
    // Qt Quick reports logical dimensions and handles each QScreen's device
    // pixel ratio. Manual sizing is applied to design metrics, not a scene transform.
    readonly property real contentScale:1.0
    property bool geometryReady:false
    minimumWidth:Theme.windowMinimumWidth; minimumHeight:Theme.windowMinimumHeight
    title:"Swirl"; flags:Qt.Window | Qt.FramelessWindowHint; color:"transparent"
    font.family:Theme.fontFamily; font.pixelSize:Theme.fontSize(16)
    SwirlFontBinding { target: window; fontWindow: window; textRole: "body" }
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
    function preparePreviewState(state){const item=pageLoader.item;if(item&&item.preparePreviewState)item.preparePreviewState(state)}
    function previewScrollBottom() { if(pageLoader.item && pageLoader.item.scrollToBottom)pageLoader.item.scrollToBottom() }
    property real swirlWindowRadius:Theme.windowRadius
    // DWM's ROUND preset cannot match the shared shell/sidebar radius exactly.
    property bool swirlExactWindowRadius:true
    readonly property real shellRadius:window.visibility===Window.Maximized || window.visibility===Window.FullScreen ? 0 : Theme.windowRadius
    Binding { target:window.captureProviderContext; property:"upstreamProxyPort"; value:window.engineControllerContext.processAlive?window.engineControllerContext.activeProxyPort:0 }
    Connections { target:window.captureProviderContext; function onStateChanged(){window.engineControllerContext.setCaptureProxyPort(window.captureProviderContext.running?window.captureProviderContext.port:0)} }
    Connections { target:backdrop; function onChanged() { Theme.backdropActive=backdrop.active||backdrop.micaActive||backdrop.blurActive;Theme.backdropTranslucent=backdrop.translucent } }
    Binding { target:Theme; property:"windowActive"; value:previewState==="inactive"?false:window.active }
    readonly property real sidebarGutter:0
    readonly property real actualSidebarWidth:sidebar.animatedWidth
    readonly property bool swirlUnifiedBlur:true
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
            window.width=Math.max(Theme.windowDefaultWidth,minimumWidth)
            window.height=Math.max(Theme.windowDefaultHeight,minimumHeight)
        }
        geometryReady=true
        backdrop.apply(window,Theme.transparency,Theme.dark)
        AppState.initializeHistory()
        console.info("MOTION_POLICY",JSON.stringify({systemReduced:motionPolicy.systemReducedMotion,followSystem:Theme.followSystemMotion,applicationReduced:Theme.reduceMotion,effectiveReduced:SwirlMotion.reduced,expandDuration:SwirlMotion.expandDuration}))
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
        SwirlWorkspaceBackdrop {
            id:appSceneBackdrop
            anchors.fill:parent;targetWindow:window
            glassSurface:sidebar.glassSurface;glassSampled:sidebar.glassSampled
        }

        Binding { target: SwirlProxyWingMotion; property: "windowVisible"; value: window.visible && window.visibility !== Window.Minimized }

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
        SwirlSidebar { id:sidebar; width:window.actualSidebarWidth; height:parent.height; compactByWindow:false;backdropSource:appSceneBackdrop.decorationSource }
        SwirlWindowControls {
            id:windowControls;objectName:"windowControls";z:70
            anchors.right:parent.right;anchors.rightMargin:Theme.dp(5);y:Theme.dp(5)
            targetWindow:window
        }
        Item {
            id:mainArea; x:window.actualSidebarWidth+window.sidebarGutter; width:parent.width-x-(AppState.currentPage==="activity"?0:Theme.dp(12)); height:parent.height
            RowLayout {
                id:toolbar; z:1; visible:AppState.currentPage==="activity"; x:Theme.pagePadding+Theme.dp(7); y:Theme.dp(9); width:parent.width-x-windowControls.width-Theme.dp(16); height:Theme.dp(32); spacing:Theme.dp(8)
                SwirlStatusCapsule { objectName:"eventsCapsule"; Layout.preferredWidth:implicitWidth; Layout.preferredHeight:Theme.dp(28); label:systemProvider.eventCount>0?systemProvider.eventCount+" 个事件":"暂无事件";tone:systemProvider.eventCount>0?"success":"neutral";detail:"查看事件与活动记录"; onClicked:AppState.navigate("logs") }
                Item {Layout.fillWidth:true}
                SwirlSystemProxyCapsule {id:proxyCapsule;objectName:"proxyCapsule";Layout.preferredWidth:implicitWidth;Layout.preferredHeight:Theme.dp(28);controller:engineController}

                SwirlStatusCapsule { objectName:"tunCapsule"; Layout.preferredWidth:implicitWidth; Layout.preferredHeight:Theme.dp(28); label:engineController.tunEnabled?"TUN · 已开":"TUN · 未开启";detail:engineController.routingError||(engineController.tunEnabled?"TUN 模式已开启，点击关闭":"当前 Rust Core 暂不支持 TUN 模式"); tone:engineController.tunEnabled?"success":"neutral"; enabled:!engineController.busy; onClicked:{if(!engineController.setTunEnabled(!engineController.tunRequested))AppState.notice(engineController.routingError||engineController.networkConfigurationError)} }

            }
            SwirlButton {
                id:settingsBack
                objectName:"settingsBackButton";z:60
                x:Theme.pagePadding;y:Theme.dp(12);height:Theme.dp(32)
                text:"返回";iconName:"chevron-left";quiet:true
                visible:AppState.inSettings
                opacity:pageLoader.pendingGrab?0:pageLoader.heroData && pageLoader.heroData.key==="settings"?
                    (pageLoader.heroData.returning?0:pageLoader.ramp(pageLoader.position,0.84,0.94)):
                    pageLoader.activeLoader && pageLoader.activeLoader.routeId===AppState.currentPage?1:0
                enabled:opacity>0.99
                onClicked:window.closeSettings()
                Accessible.name:"返回上一页，保留当前设置草稿"
            }
            SwirlPageHost {
                routeKey:AppState.currentPage==="requestlogs" || AppState.currentPage==="dashboard" ? "activity" : AppState.currentPage
                id:pageLoader; objectName:"pageLoader";insetRoutes:AppState.settingsRoutes;routeInset:0; x:Theme.dp(0); y:AppState.currentPage==="activity"?Theme.dp(12):Theme.dp(48); width:parent.width; height:parent.height-y-Theme.dp(12)
                sourceComponent:AppState.currentPage==="overview" ? overview :
                                AppState.currentPage==="activity" || AppState.currentPage==="requestlogs" || AppState.currentPage==="dashboard" ? activity :
                                AppState.currentPage==="capture" ? capturePage :
                                AppState.currentPage==="connections" ? connections :
                                AppState.currentPage==="processes" ? processes :
                                AppState.currentPage==="proxies" ? proxies :
                                AppState.currentPage==="inspector" ? inspector :
                                AppState.currentPage==="scripts" ? scripts :
                                AppState.currentPage==="settings" ? settings :
                                AppState.currentPage==="fonts" ? fonts :
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
    readonly property string proxyStatusLabel:engineController.systemProxy.error.length||engineController.routingError.length?"系统代理 · 接管失败":engineController.systemProxy.owned&&engineController.systemProxy.enabled?"系统代理 · Swirl":engineController.systemProxy.systemEnabled?"系统代理 · 其他应用":"系统代理 · 未启用"
    function openDashboard(){dashboardWindow.show();dashboardWindow.raise();dashboardWindow.requestActivate()}
    function openCaptureInspector(){
        captureInspectorLoader.wantOpen=true
        captureInspectorLoader.active=true
        showPendingCaptureInspector()
    }
    function showPendingCaptureInspector(){
        if(!captureInspectorLoader.wantOpen || captureInspectorLoader.status!==Loader.Ready || !captureInspectorLoader.item)return
        captureInspectorLoader.wantOpen=false
        captureInspectorLoader.item.open()
    }
    function openSettings(route,origin) {
        if(AppState.settingsRoutes.indexOf(route)<0)return
        if(origin)SwirlMotion.navigateFrom(origin,route,"settings")
        else AppState.navigate(route)
    }
    function closeSettings() {
        if(pageLoader.item && pageLoader.item.dismissDetail && pageLoader.item.dismissDetail())return
        if(AppState.historyIndex>0)AppState.goBack()
        else AppState.navigate("featurehub")
    }
    readonly property bool swirlBackAvailable:rewriteRulesLoader.wantOpen || captureInspectorLoader.wantOpen || AppState.canGoBack || (pageLoader.item!==null && pageLoader.item.detailOpen===true)
    function handleEscape() {
        if(rewriteRulesLoader.wantOpen){rewriteRulesLoader.wantOpen=false;return}
        if(captureInspectorLoader.wantOpen){captureInspectorLoader.wantOpen=false;return}
        if(pageLoader.item && pageLoader.item.dismissDetail && pageLoader.item.dismissDetail())return
        if(pageLoader.item && pageLoader.item.handleSectionEscape && pageLoader.item.handleSectionEscape())return
        if(AppState.canGoBack)AppState.goBack()
    }
    function persistExitDrafts(){
        const loader=pageLoader.pages["dns"]
        if(loader && loader.item && loader.item.persistExitDraft)loader.item.persistExitDraft()
    }
    function openRewriteEditor(kind,title){
        rewriteRulesLoader.requestedKind=kind
        rewriteRulesLoader.requestedTitle=title
        rewriteRulesLoader.wantOpen=true
        rewriteRulesLoader.active=true
        showPendingRewriteEditor()
    }
    function showPendingRewriteEditor(){
        if(!rewriteRulesLoader.wantOpen || rewriteRulesLoader.status!==Loader.Ready || !rewriteRulesLoader.item)return
        rewriteRulesLoader.wantOpen=false
        rewriteRulesLoader.item.kind=rewriteRulesLoader.requestedKind
        rewriteRulesLoader.item.title=rewriteRulesLoader.requestedTitle
        rewriteRulesLoader.item.open()
    }
    // Keep the first-created editor alive so reopening preserves its drafts.
    Loader {
        id:rewriteRulesLoader
        property string requestedKind:"redirect"
        property string requestedTitle:""
        property bool wantOpen:false
        objectName:"rewriteRulesLoader"
        active:false
        asynchronous:true
        sourceComponent:Component {RewriteRulesDialog {}}
        onLoaded:window.showPendingRewriteEditor()
    }
    SwirlSecondaryWindow {
        composition:panelBackdrop
        id:dashboardWindow;objectName:"dashboardWindow";function openProxyControl(){hide();AppState.navigate("policies");window.show();window.raise();window.requestActivate()}
        visible:false;width:Theme.windowDefaultWidth;height:Theme.windowDefaultHeight;minimumWidth:Theme.windowMinimumWidth;minimumHeight:Theme.windowMinimumHeight;title:"Swirl 面板";flags:Qt.Window|Qt.FramelessWindowHint;color:"transparent"
        function openCaptureInspector(){window.openCaptureInspector()}
        ExternalToolsPage{anchors.fill:parent;clip:true}
    }

    Loader {
        id:captureInspectorLoader;objectName:"captureInspectorLoader"
        property bool wantOpen:false
        active:false;asynchronous:true
        onLoaded:window.showPendingCaptureInspector()
        sourceComponent:Component {
            SwirlDialog {
                objectName:"captureInspectorDialog";ownerItem:window.contentItem;title:"HTTP 请求详情"
                width:Math.min(Theme.dp(1000),window.width-Theme.dp(20));height:Math.min(Theme.dp(650),window.height-Theme.dp(20));padding:Theme.dp(14)
                CaptureInspectorPage{captureProvider:window.captureProviderContext;anchors.fill:parent}
            }
        }
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
    Shortcut { enabled:dismissals.count===0;sequence:"Alt+Left"; onActivated:{if(pageLoader.item && pageLoader.item.dismissDetail && pageLoader.item.dismissDetail())return;AppState.goBack()} }
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
    Component { id:settings; SettingsPage {section:"常规"} }
    Component { id:fonts; SettingsPage {section:"字体"} }
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
    // Exact-region windows use this single matching rim; other native windows
    // retain their DWM rim. The native region clips all children at once.
    SwirlShellOutline {
        objectName:"windowOutline";visible:backdrop.exactCorners || !backdrop.nativeCorners
        anchors.fill:parent;z:998
        radius:window.shellRadius
        strokeWidth:window.visibility===Window.Maximized?0:1/Screen.devicePixelRatio
        strokeColor:Theme.increaseContrast?Theme.text:Theme.dark?Qt.rgba(1,1,1,0.14):Qt.rgba(0,0,0,0.055)
    }
    Timer { id:toastTimer; interval:3200; onTriggered:AppState.toast="" }
    WindowEdge {anchors.fill:parent;z:10000;radius:window.shellRadius}
    Connections {
        target:AppState
        function onToastChanged(){if(AppState.toast.length)toastTimer.restart()}
        function onCurrentPageChanged(){rewriteRulesLoader.wantOpen=false;captureInspectorLoader.wantOpen=false}
    }
    Rectangle {
        visible:AppState.toast.length>0; z:999
        anchors.horizontalCenter:parent.horizontalCenter; anchors.bottom:parent.bottom; anchors.bottomMargin:Theme.dp(28)
        width:Math.min(Theme.dp(380),window.width-Theme.dp(40)); height:Math.max(Theme.dp(48),toastText.implicitHeight+Theme.dp(24)); radius:Theme.controlRadius
        color:Theme.material("floating"); border.color:Theme.border
        SwirlText { id:toastText; anchors.left:parent.left;anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter; anchors.margins:Theme.dp(12);wrapMode:Text.Wrap; text:AppState.toast; color:Theme.muted; font.pixelSize:Theme.fontSize(14); verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight }
    }
    Timer {
        running:smokeTestMode; repeat:true; interval:200
        property int index:0
        onTriggered:{
            // Font review waits for real route loading and transition state;
            // the existing standalone smoke driver retains its rapid cadence.
            if(fontSmokeReadyMode){
                const loader=pageLoader.activeLoader
                if(pageLoader.pendingGrab || pageLoader.moving || !loader ||
                    loader.status!==Loader.Ready || !loader.item || loader.routeId!==pageLoader.routeKey)return
                if(index>0)console.info("FONT_SMOKE_ROUTE_READY",AppState.allPageIds[index-1],loader.routeId)
            }
            if(index>=AppState.allPageIds.length){console.info("SMOKE_PAGES",index);stop();window.navigationSmokeCompleted();return}
            AppState.currentPage=AppState.allPageIds[index++]
        }
    }
    signal navigationSmokeCompleted()
}
