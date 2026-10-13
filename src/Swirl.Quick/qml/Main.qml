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
    // Qt 6.10 RHI requests FP16 scRGB and falls back to SDR when unsupported.
    // Version-specific Qt hook; HdrOutput checks the actual swapchain format.
    property string _qt_sg_hdr_format:"scrgb"
    Component {
        id:hdrComposite
        ShaderEffect {
            property var source
            property vector2d outputSize:Qt.vector2d(window.width,window.height)
            property real hdrActive:hdrOutput.active?1:0
            property real whiteScale:hdrOutput.whiteScale
            property real peakValue:hdrOutput.peakValue
            property real glowEnabled:hdrOutput.glowEnabled?1:0
            property vector4d redLamp:Qt.vector4d(Theme.dp(sidebar.effectivelyCollapsed?14:34),Theme.dp(sidebar.effectivelyCollapsed?26:28),Theme.dp(sidebar.effectivelyCollapsed?6:8),1)
            property vector4d yellowLamp:Qt.vector4d(Theme.dp(sidebar.effectivelyCollapsed?33:60),redLamp.y,redLamp.z,1)
            property vector4d greenLamp:Qt.vector4d(Theme.dp(sidebar.effectivelyCollapsed?52:86),redLamp.y,redLamp.z,1)
            fragmentShader:"qrc:/swirl/shaders/hdr-ui.frag.qsb"
        }
    }
    Binding { target:window.contentItem.layer; property:"enabled"; value:hdrOutput.active }
    Binding { target:window.contentItem.layer; property:"effect"; value:hdrComposite }
    // Qt Controls popups live in the overlay, outside ApplicationWindow content.
    readonly property Item popupOverlay:window.contentItem ? window.contentItem.Overlay.overlay : null
    Binding { target:window.popupOverlay ? window.popupOverlay.layer : null; property:"enabled"; value:hdrOutput.active; when:window.popupOverlay!==null }
    Binding { target:window.popupOverlay ? window.popupOverlay.layer : null; property:"effect"; value:hdrComposite; when:window.popupOverlay!==null }
    visible:true
    width:Theme.dp(760); height:Theme.dp(520)
    // Qt Quick reports logical dimensions and handles each QScreen's device
    // pixel ratio. Manual sizing is applied to design metrics, not a scene transform.
    readonly property real contentScale:1.0
    property bool geometryReady:false
    minimumWidth:Math.min(Theme.dp(760),Screen.desktopAvailableWidth); minimumHeight:Math.min(Theme.dp(520),Screen.desktopAvailableHeight)
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
    function previewScrollBottom() { if(pageLoader.item && pageLoader.item.scrollToBottom)pageLoader.item.scrollToBottom() }
    property real swirlWindowRadius:Theme.windowRadius
    readonly property real shellRadius:backdrop.nativeCorners || window.visibility===Window.Maximized ? 0 : Theme.windowRadius
    Connections { target:backdrop; function onChanged() { Theme.backdropActive=backdrop.active } }
    readonly property real sidebarGutter:Theme.dp(Math.min(24,Math.max(12,window.width*0.017)))
    readonly property real actualSidebarWidth:AppState.sidebarCollapsed || scaledCanvas.width<Theme.dp(900) ? Theme.dp(82) : Math.min(Theme.sidebarWidth,Math.max(Theme.dp(188),Theme.dp(scaledCanvas.width*0.172)))
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
            // Derive a roomy first-run size from the current logical work area.
            // Assign once so the user can resize freely after startup.
            const maxWidth=Screen.desktopAvailableWidth*0.91
            const maxHeight=Screen.desktopAvailableHeight*0.91
            const aspect=1464/930
            window.width=Math.max(minimumWidth,Math.min(maxWidth,maxHeight*aspect))
            window.height=Math.max(minimumHeight,Math.min(maxHeight,window.width/aspect))
        }
        geometryReady=true
        backdrop.apply(window,Theme.transparency,Theme.dark)
        AppState.initializeHistory()
        if(previewTheme==="dark")Theme.mode="Dark"
        else if(previewTheme==="light")Theme.mode="Light"
        if(previewPage.length)AppState.currentPage=previewPage
    }
    Connections {
        target: Theme
        function onTransparencyChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
        function onDarkChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
        function onUiScaleChanged() { backdrop.apply(window, Theme.transparency, Theme.dark) }
    }
    Rectangle {
        id:windowCornerMask
        width:window.width; height:window.height
        radius:window.shellRadius; antialiasing:true
        color:"white"; visible:false; layer.enabled:true
    }
    Item {
        id:scaledCanvas
        // Clip all page layers, including controls' shadows, to the same soft
        // window outline. Background rectangles alone cannot clip descendants.
        layer.enabled:Theme.effectsSupported
        layer.effect:MultiEffect { maskEnabled:true; maskSource:windowCornerMask }
        width:window.width; height:window.height
        Rectangle {
            width:window.actualSidebarWidth + Theme.windowRadius; height:parent.height
            radius:window.shellRadius; antialiasing:true
            color:Theme.sidebar

        }
        Rectangle {
            x: window.actualSidebarWidth
            width: parent.width - x; height: parent.height
            radius: window.shellRadius; antialiasing:true
            color: Theme.canvas
            Rectangle { width: Theme.windowRadius; height: parent.height; color: Theme.canvas }
        }
        Rectangle { x: window.actualSidebarWidth - 1; width:Theme.dp(1); height: parent.height; color: Theme.border }
        MouseArea {
            x:Theme.dp(0); y:Theme.dp(0); width:parent.width; height:Theme.dp(68)
            property point pressPosition
            property bool nativeMoveStarted:false
            onPressed:mouse=>{ pressPosition=Qt.point(mouse.x,mouse.y);nativeMoveStarted=false }
            onPositionChanged:mouse=>{ if(pressed&&!nativeMoveStarted&&Math.hypot(mouse.x-pressPosition.x,mouse.y-pressPosition.y)>Qt.styleHints.startDragDistance){nativeMoveStarted=true;window.startSystemMove()} }
            onDoubleClicked:window.visibility===Window.Maximized ? window.showNormal() : window.showMaximized()
        }
        MouseArea {
            objectName:"titleDragArea"
            visible:false
            x:window.actualSidebarWidth; y:Theme.dp(0); width:parent.width-x-Theme.dp(240)
            height:pageLoader.item && pageLoader.item.scrollOffset>0 ? Theme.dp(22) : Theme.dp(68); z:20
            acceptedButtons:Qt.LeftButton|Qt.RightButton
            property point pressPosition
            property bool nativeMoveStarted:false
            onPressed:mouse=>{ pressPosition=Qt.point(mouse.x,mouse.y);nativeMoveStarted=false;if(mouse.button===Qt.RightButton)backdrop.showSystemMenu() }
            onPositionChanged:mouse=>{ if(pressed&&(pressedButtons&Qt.LeftButton)&&!nativeMoveStarted&&Math.hypot(mouse.x-pressPosition.x,mouse.y-pressPosition.y)>Qt.styleHints.startDragDistance){nativeMoveStarted=true;window.startSystemMove()} }
            onDoubleClicked:window.visibility===Window.Maximized?window.showNormal():window.showMaximized()
        }
        SwirlSidebar { id:sidebar; width:window.actualSidebarWidth; height:parent.height; compactByWindow:scaledCanvas.width<Theme.dp(900) }
        Item {
            id:mainArea; x:window.actualSidebarWidth+window.sidebarGutter; width:parent.width-x-window.sidebarGutter; height:parent.height
            RowLayout {
                id:toolbar; visible:true; x:Theme.dp(0); y:Theme.dp(12); width:parent.width; height:Theme.dp(44); spacing:Theme.dp(18)
                Item {
                    width:Theme.dp(85); height:Theme.dp(42)
                    SwirlPillSurface { anchors.fill:parent }
                    Row {
                        anchors.fill:parent
                        Repeater {
                            model:["chevron-left","chevron-right"]
                            SwirlMotionButton {
                                required property int index
                                required property string modelData
                                objectName:index===0?"historyBackButton":"historyForwardButton"
                                width:Theme.dp(42); height:Theme.dp(42); hoverEnabled:true
                                enabled:index===0 ? AppState.historyIndex>0 : AppState.historyIndex<AppState.navigationHistory.length-1
                                background:Rectangle{radius:Math.min(width,height)/2;color:parent.hovered?Theme.hover:"transparent"
 Behavior on color {ColorAnimation {duration:SwirlMotion.duration}}
 }
                                contentItem:SwirlIcon{name:modelData;size:Theme.dp(20);color:parent.enabled?Theme.muted:Theme.withAlpha(Theme.muted,0.4)}
                                onClicked:index===0?AppState.goBack():AppState.goForward()
                                Accessible.name:index===0?"返回":"前进"
                            }
                        }
                    }
                }
                Item { Layout.fillWidth:true }
                SwirlStatusCapsule { objectName:"eventsCapsule"; label:systemProvider.eventCount>0?systemProvider.eventCount+" 个事件":"无事件";tone:systemProvider.eventCount>0?"warning":"neutral"; onClicked:AppState.navigate("logs") }
                Item { Layout.fillWidth:true }
                SwirlStatusCapsule { objectName:"proxyCapsule"; label:engineController.systemProxy.systemEnabled&&!engineController.systemProxy.owned?"系统代理 · 其他应用":"系统代理";tone:engineController.systemProxy.error.length||engineController.routingError.length?"warning":engineController.systemProxy.systemEnabled?"success":"neutral";detail:engineController.systemProxy.error||engineController.routingError||(engineController.systemProxy.systemEnabled&&!engineController.systemProxy.owned?"Windows 系统代理已由其他应用启用，Swirl 未接管":"点击控制 Swirl 系统代理"); enabled:!engineController.busy; onClicked:engineController.setSystemProxy(!engineController.systemProxy.enabled) }
                SwirlStatusCapsule { objectName:"tunCapsule"; label:"增强模式 · 未实现";detail:"本阶段尚未实现 TUN";enabled:false }
                SwirlButton { visible:captureProvider.running; text:"抓包中 · "+captureProvider.sessions.length; iconName:"capture"; font.pixelSize:Theme.fontSize(14); onClicked:AppState.navigate("capture") }

            }
            SwirlPageHost {
                routeKey:AppState.currentPage
                id:pageLoader; objectName:"pageLoader"; x:Theme.dp(0); y:Theme.dp(68); width:parent.width; height:parent.height-y-Theme.dp(17)
                sourceComponent:AppState.currentPage==="overview" ? overview :
                                AppState.currentPage==="capture" ? capturePage :
                                AppState.currentPage==="connections" || AppState.currentPage==="requestlogs" ? connections :
                                AppState.currentPage==="processes" ? processes :
                                AppState.currentPage==="proxies" ? proxies :
                                AppState.currentPage==="inspector" ? inspector :
                                AppState.currentPage==="scripts" ? scripts :
                                AppState.currentPage==="settings" ? settings :
                                AppState.currentPage==="toolbox" ? toolbox :
                                AppState.currentPage==="dashboard" ? dashboard :
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
            z:100; visible:window.visibility!==Window.Maximized
            x:edgeright?window.width-width:Theme.dp(0); y:edgebottom?window.height-height:Theme.dp(0)
            width:corner?Theme.dp(10):(edgeleft||edgeright)?Theme.dp(5):window.width
            height:corner?Theme.dp(10):(edgetop||edgebottom)?Theme.dp(5):window.height
            cursorShape:corner?(edgeleft&&edgetop||edgeright&&edgebottom?Qt.SizeFDiagCursor:Qt.SizeBDiagCursor):(edgeleft||edgeright)?Qt.SizeHorCursor:Qt.SizeVerCursor
            onPressed:window.startSystemResize(modelData)
        }
    }
    Shortcut { sequence:"Alt+Space"; context:Qt.ApplicationShortcut; onActivated:backdrop.showSystemMenu() }
    Shortcut { sequence:"Ctrl+K"; context:Qt.ApplicationShortcut; onActivated:sidebar.searchField.forceActiveFocus() }
    Shortcut { sequence:"Alt+Left"; onActivated:AppState.goBack() }
    Shortcut { sequence:"Alt+Right"; onActivated:AppState.goForward() }
    Shortcut { sequence:"Ctrl+1"; onActivated:AppState.navigate("overview") }
    Shortcut { sequence:"Ctrl+2"; onActivated:AppState.navigate("proxies") }
    Shortcut { sequence:"Ctrl+3"; onActivated:AppState.navigate("connections") }
    Shortcut { sequence:"Ctrl+4"; onActivated:AppState.navigate("inspector") }
    Shortcut { sequence:"Ctrl+,"; onActivated:AppState.navigate("settings") }
    Shortcut { sequence:"Ctrl+B"; onActivated:AppState.sidebarCollapsed=!AppState.sidebarCollapsed }
        Component { id:overview; OverviewPage {} }
    Component { id:capturePage; CapturePage {} }
    Component { id:externalTools; ExternalToolsPage {} }
    Component { id:featureHub; FeatureHubPage {} }
    Component { id:featureModule; FeatureModulePage { moduleId:parent.routeId } }
    Component { id:connections; ConnectionsPage {} }
    Component { id:processes; ProcessesPage {} }
    Component { id:proxies; ProxiesPage {} }
    Component { id:inspector; InspectorPage {} }
    Component { id:scripts; ScriptsPage {} }
    Component { id:settings; SettingsPage {} }
    Component { id:toolbox; ToolboxPage {} }
    Component { id:dashboard; DashboardPage {} }
    Component { id:dns; DNSPage {} }
    Component { id:rules; RulesPage {} }
    Component { id:logs; LogsPage {} }
    Component { id:tls; TLSPage {} }
    Component { id:replay; ReplayPage {} }
    Component { id:rewrite; RewritePage {} }
    Component { id:profiles; ProfilesPage {} }
    Component { id:subscriptions; SubscriptionsPage {} }
    Component { id:policies; PolicyGroupsPage {} }
    Component { id:traffic; TrafficAnalyticsPage {} }
    Component { id:breakpoint; BreakpointPage {} }
    Component { id:mapLocal; MapPage {} }
    Component { id:modules; ModulesPage {} }
    Component { id:automation; AutomationPage {} }
    Component { id:api; ApiPage {} }
    Component { id:gateway; GatewayPage {} }
    Component { id:workbench; WorkbenchPage { pageId:parent.routeId } }

    Timer { interval:1000; running:true; repeat:true; onTriggered:AppState.tickTraffic() }
    // A thin outline gives overlapping pale windows a visible boundary. Qt
    // owns the rounded HDR outline, so do not enable a mismatched DWM rectangle.
    Rectangle {
        objectName:"windowOutline"
        anchors.fill:parent;z:998;color:"transparent";antialiasing:true
        radius:window.shellRadius
        border.width:window.visibility===Window.Maximized?0:1/Screen.devicePixelRatio
        border.color:Theme.dark?Qt.rgba(1,1,1,window.active?0.30:0.20):Qt.rgba(0,0,0,window.active?0.32:0.22)
    }
    Timer { id:toastTimer; interval:3200; onTriggered:AppState.toast="" }
    Connections { target:AppState; function onToastChanged(){if(AppState.toast.length)toastTimer.restart()} }
    Rectangle {
        visible:AppState.toast.length>0; z:999
        anchors.horizontalCenter:parent.horizontalCenter; anchors.bottom:parent.bottom; anchors.bottomMargin:Theme.dp(28)
        width:Math.min(Theme.dp(570),window.width-Theme.dp(40)); height:Theme.dp(48); radius:Theme.controlRadius
        color:Theme.material("floating"); border.color:Theme.border
        Text { anchors.fill:parent; anchors.margins:Theme.dp(12); text:AppState.toast; color:Theme.muted; font.pixelSize:Theme.fontSize(14); verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight }
    }
    Timer {
        running:smokeTestMode; repeat:true; interval:200
        property int index:0
        onTriggered:{
            if(index>=AppState.allPageIds.length){console.info("SMOKE_PAGES",index);stop();smokeFinished.start();return}
            AppState.currentPage=AppState.allPageIds[index++]
        }
    }
    Timer { id:smokeFinished; interval:300; onTriggered:Qt.quit() }
}
