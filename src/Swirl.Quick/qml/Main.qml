import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "components"
import "controls"
import "pages"
ApplicationWindow {
    id:window
    visible:true
    width:Math.min(1450,Screen.desktopAvailableWidth-40)
    height:Math.min(884,Screen.desktopAvailableHeight-40)
    minimumWidth:1000; minimumHeight:650
    title:"Swirl"; flags:Qt.Window | Qt.FramelessWindowHint; color:"transparent"
    font.family:Theme.fontFamily; font.pixelSize:16
    property bool swirlTransparencyEnabled:Theme.transparency
    function previewScrollBottom() { if(pageLoader.item && pageLoader.item.scrollToBottom)pageLoader.item.scrollToBottom() }
    property real swirlWindowRadius:Theme.windowRadius
    readonly property real actualSidebarWidth:AppState.sidebarCollapsed || scaledCanvas.width<1160 ? 82 : Theme.sidebarWidth
    background:Rectangle {
        radius:window.visibility===Window.Maximized ? 0 : Theme.windowRadius
        color:Theme.canvas
        border.width:1; border.color:Theme.glassRim
    }
    Component.onCompleted:{
        backdrop.apply(window,false)
        AppState.initializeHistory()
        if(previewTheme==="dark")Theme.mode="Dark"
        else if(previewTheme==="light")Theme.mode="Light"
        if(previewPage.length)AppState.currentPage=previewPage
    }
    Item {
        id:scaledCanvas
        width:window.width/Theme.uiScale; height:window.height/Theme.uiScale
        scale:Theme.uiScale; transformOrigin:Item.TopLeft
        Rectangle {
            width:window.actualSidebarWidth; height:parent.height
            radius:window.visibility===Window.Maximized ? 0 : Theme.windowRadius
            color:Theme.material("sidebar")
            Rectangle { anchors.right:parent.right; width:Theme.windowRadius; height:parent.height; color:Theme.material("sidebar") }
        }
        MouseArea {
            x:0; y:0; width:parent.width; height:68
            onPressed:window.startSystemMove()
            onDoubleClicked:window.visibility===Window.Maximized ? window.showNormal() : window.showMaximized()
        }
        SwirlSidebar { id:sidebar; width:window.actualSidebarWidth; height:parent.height; compactByWindow:scaledCanvas.width<1160 }
        Item {
            id:mainArea; x:window.actualSidebarWidth+15; width:parent.width-x-15; height:parent.height
            RowLayout {
                id:toolbar; x:0; y:12; width:parent.width; height:44; spacing:18
                Item {
                    width:85; height:42
                    SwirlPillSurface { anchors.fill:parent }
                    Row {
                        anchors.fill:parent
                        Repeater {
                            model:["chevron-left","chevron-right"]
                            Button {
                                required property int index
                                required property string modelData
                                width:42; height:42; hoverEnabled:true
                                enabled:index===0 ? AppState.historyIndex>0 : AppState.historyIndex<AppState.navigationHistory.length-1
                                background:Rectangle{radius:Theme.pillRadius(height);color:parent.hovered?Theme.hover:"transparent"}
                                contentItem:SwirlIcon{name:modelData;size:20;color:parent.enabled?Theme.muted:Theme.withAlpha(Theme.muted,0.4)}
                                onClicked:index===0?AppState.goBack():AppState.goForward()
                                Accessible.name:index===0?"返回":"前进"
                            }
                        }
                    }
                }
                SwirlSearchField {
                    id:pageSearch; objectName:"pageSearch"; Layout.preferredWidth:Math.min(475,mainArea.width*0.5)
                    placeholderText:"搜索功能、节点或设置…"; rightPadding:95
                    onAccepted:{
                        var q=text.trim().toLowerCase()
                        if(!q.length)return
                        for(var i=0;i<AppState.groups.length;i++)for(var j=0;j<AppState.groups[i].pages.length;j++){
                            var p=AppState.groups[i].pages[j]
                            if(p.title.toLowerCase().indexOf(q)>=0){AppState.navigate(p.id);text="";return}
                        }
                        if(q.indexOf("新加坡")>=0 || q.indexOf("节点")>=0)AppState.navigate("proxies")
                        else AppState.toast="没有找到对应功能或演示节点"
                    }
                    Rectangle {
                        anchors.right:parent.right; anchors.rightMargin:9; anchors.verticalCenter:parent.verticalCenter
                        width:82; height:29; radius:Theme.pillRadius(height); color:Theme.selected; opacity:0.5
                    }
                    Text { anchors.right:parent.right; anchors.rightMargin:20; anchors.verticalCenter:parent.verticalCenter; text:"Ctrl + K"; font.pixelSize:15; color:Theme.muted }
                }
                Item { Layout.fillWidth:true }
                SwirlIconButton { objectName:"addButton"; iconName:"plus"; tooltip:"添加配置或节点"; onClicked:addMenu.popup(); Menu {
                    id:addMenu
                    MenuItem { text:"添加演示节点"; onTriggered:AppState.navigate("proxies") }
                    MenuItem { text:"导入配置预览"; onTriggered:AppState.navigate("profiles") }
                    MenuItem { text:"订阅管理"; onTriggered:AppState.navigate("subscriptions") }
                    MenuSeparator {}
                    MenuItem { text:"更多工具"; onTriggered:AppState.navigate("toolbox") }
                } }
                SwirlIconButton { iconName:"settings"; tooltip:"设置"; onClicked:AppState.navigate("settings") }
            }
            Loader {
                id:pageLoader; objectName:"pageLoader"; x:0; y:68; width:parent.width; height:parent.height-y-17
                sourceComponent:AppState.currentPage==="overview" ? overview :
                                AppState.currentPage==="connections" ? connections :
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
            x:edgeright?window.width-width:0; y:edgebottom?window.height-height:0
            width:corner?10:(edgeleft||edgeright)?5:window.width
            height:corner?10:(edgetop||edgebottom)?5:window.height
            cursorShape:corner?(edgeleft&&edgetop||edgeright&&edgebottom?Qt.SizeFDiagCursor:Qt.SizeBDiagCursor):(edgeleft||edgeright)?Qt.SizeHorCursor:Qt.SizeVerCursor
            onPressed:window.startSystemResize(modelData)
        }
    }
    Shortcut { sequence:"Ctrl+K"; context:Qt.ApplicationShortcut; onActivated:pageSearch.forceActiveFocus() }
    Shortcut { sequence:"Alt+Left"; onActivated:AppState.goBack() }
    Shortcut { sequence:"Alt+Right"; onActivated:AppState.goForward() }
    Shortcut { sequence:"Ctrl+1"; onActivated:AppState.navigate("overview") }
    Shortcut { sequence:"Ctrl+2"; onActivated:AppState.navigate("proxies") }
    Shortcut { sequence:"Ctrl+3"; onActivated:AppState.navigate("connections") }
    Shortcut { sequence:"Ctrl+4"; onActivated:AppState.navigate("inspector") }
    Shortcut { sequence:"Ctrl+,"; onActivated:AppState.navigate("settings") }
    Shortcut { sequence:"Ctrl+B"; onActivated:AppState.sidebarCollapsed=!AppState.sidebarCollapsed }
        Component { id:overview; OverviewPage {} }
    Component { id:externalTools; ExternalToolsPage {} }
    Component { id:connections; ConnectionsPage {} }
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
    Component { id:workbench; WorkbenchPage { pageId:AppState.currentPage } }

    Timer { interval:1000; running:true; repeat:true; onTriggered:AppState.tickTraffic() }
    Timer { id:toastTimer; interval:3200; onTriggered:AppState.toast="" }
    Connections { target:AppState; function onToastChanged(){if(AppState.toast.length)toastTimer.restart()} }
    Rectangle {
        visible:AppState.toast.length>0; z:999
        anchors.horizontalCenter:parent.horizontalCenter; anchors.bottom:parent.bottom; anchors.bottomMargin:28
        width:Math.min(570,window.width-40); height:48; radius:Theme.controlRadius
        color:Theme.material("floating"); border.color:Theme.border
        Text { anchors.fill:parent; anchors.margins:12; text:AppState.toast; color:Theme.muted; font.pixelSize:14; verticalAlignment:Text.AlignVCenter; elide:Text.ElideRight }
    }
    Timer {
        running:smokeTestMode; repeat:true; interval:200
        property int groupIndex:0; property int pageIndex:0
        onTriggered:{
            if(groupIndex>=AppState.groups.length){AppState.currentPage="external";stop();smokeFinished.start();return}
            AppState.currentPage=AppState.groups[groupIndex].pages[pageIndex].id
            if(++pageIndex>=AppState.groups[groupIndex].pages.length){pageIndex=0;groupIndex++}
        }
    }
    Timer { id:smokeFinished; interval:300; onTriggered:Qt.quit() }
}
