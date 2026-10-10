import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "components"
import "controls"
import "pages"
ApplicationWindow {
    id: window
    visible: true
    width: 1450
    height: 895
    minimumWidth: 920
    minimumHeight: 600
    title: "Swirl · UI Preview"
    color: Theme.transparency ? Qt.rgba(Theme.canvas.r,Theme.canvas.g,Theme.canvas.b,0.91) : Theme.canvas
    property bool swirlTransparencyEnabled: Theme.transparency
    Component.onCompleted: {
        backdrop.apply(window, swirlTransparencyEnabled)
        if (previewTheme==="dark") Theme.mode="Dark"
        else if (previewTheme==="light") Theme.mode="Light"
        if (previewPage.length && AppState.page(previewPage).id===previewPage)
            AppState.currentPage=previewPage
    }
    onSwirlTransparencyEnabledChanged: backdrop.apply(window, swirlTransparencyEnabled)
    font.family: "Segoe UI"
    font.pixelSize: 13
    Item {
        id: scaledCanvas
        width:window.width/Theme.uiScale
        height:window.height/Theme.uiScale
        scale:Theme.uiScale
        transformOrigin:Item.TopLeft
    RowLayout {
        anchors.fill: parent
        spacing: 0
        SwirlSidebar { Layout.fillHeight:true; compactByWindow:scaledCanvas.width<1160 }
        ColumnLayout {
            Layout.fillWidth:true
            Layout.fillHeight:true
            spacing:0
            Rectangle {
                Layout.fillWidth:true
                implicitHeight:75
                color:Theme.canvas
                RowLayout {
                    anchors.fill:parent
                    anchors.leftMargin:27
                    anchors.rightMargin:26
                    spacing:16
                    ColumnLayout {
                        Layout.fillWidth:true
                        spacing:2
                        Text {
                            text:AppState.page(AppState.currentPage).title
                            color:Theme.text
                            font.pixelSize:23
                            font.weight:Font.DemiBold
                        }
                        Text {
                            text:AppState.page(AppState.currentPage).sub
                            color:Theme.muted
                            font.pixelSize:12
                        }
                    }
                    SwirlSearchField {
                        visible:window.width>1120
                        implicitWidth:210
                        id:pageSearch
                        placeholderText:"Search pages · Ctrl+K"
                        onAccepted:{
                            var q=text.toLowerCase()
                            for (var i=0;i<AppState.groups.length;++i)
                                for (var j=0;j<AppState.groups[i].pages.length;++j) {
                                    var p=AppState.groups[i].pages[j]
                                    if (p.title.toLowerCase().indexOf(q)>=0) {
                                        AppState.currentPage=p.id
                                        text=""
                                        return
                                    }
                                }
                            AppState.notice("No matching page")
                        }
                    }
                    SwirlButton {
                        text:"UI DEMO"; iconName:"grid"; quiet:true
                        onClicked:demoStatesMenu.popup()
                        Menu {
                            id:demoStatesMenu
                            y:parent.height+3
                            background:Rectangle { radius:11; color:Theme.raised; border.color:Theme.border }
                            MenuItem {
                                text:"Normal view"
                                onTriggered:{AppState.demoLoading=false;AppState.demoError=false;AppState.demoEmpty=false}
                            }
                            MenuItem {
                                text:"Loading state"
                                onTriggered:{AppState.demoLoading=true;AppState.demoError=false;AppState.demoEmpty=false}
                            }
                            MenuItem {
                                text:"Empty state"
                                onTriggered:{AppState.demoEmpty=true;AppState.demoLoading=false;AppState.demoError=false}
                            }
                            MenuItem {
                                text:"Error state"
                                onTriggered:{AppState.demoError=true;AppState.demoLoading=false;AppState.demoEmpty=false}
                            }
                        }
                    }
                    SwirlButton { text:"Settings"; iconName:"settings"; quiet:true; onClicked:AppState.currentPage="settings" }
                }
            }
            Item {
                Layout.fillWidth:true; Layout.fillHeight:true
            Loader {
                id:pageLoader
                anchors.fill:parent
                clip:true
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
                                AppState.currentPage==="gateway" ? gateway : workbench
                }

                Rectangle {
                    anchors.fill:parent
                    z:20
                    visible:AppState.demoEmpty||AppState.demoLoading||AppState.demoError
                    color:Theme.canvas
                    ColumnLayout {
                        anchors.centerIn:parent
                        spacing:14
                        BusyIndicator {
                            visible:AppState.demoLoading
                            running:visible
                            Layout.alignment:Qt.AlignHCenter
                        }
                        SwirlEmptyState {
                            visible:!AppState.demoLoading
                            headline:AppState.demoError?"Demo error state":"No matching records"
                            detail:AppState.demoError?"A simulated loading failure occurred.":"This preview is showing an intentionally empty state."
                            Layout.alignment:Qt.AlignHCenter
                        }
                        Text {
                            visible:AppState.demoLoading
                            text:"Loading demonstration data…"
                            color:Theme.muted; font.pixelSize:13
                            Layout.alignment:Qt.AlignHCenter
                        }
                        SwirlButton {
                            text:AppState.demoError?"Retry preview":"Return to normal"
                            Layout.alignment:Qt.AlignHCenter
                            onClicked:{AppState.demoEmpty=false;AppState.demoError=false;AppState.demoLoading=false}
                        }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth:true
                implicitHeight:31
                color:Theme.canvas
                RowLayout {
                    anchors.fill:parent
                    anchors.leftMargin:27; anchors.rightMargin:26
                    Text { text:"●  UI demonstration mode · no live network activity"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                    Text { text:"Swirl Quick   •   Preview 0.1"; color:Theme.muted; font.pixelSize:11 }
                }
            }
        }
    }
    // Desktop keyboard navigation; all destinations remain UI-only.
    Shortcut { sequence:"Ctrl+K"; context:Qt.ApplicationShortcut; onActivated:pageSearch.forceActiveFocus() }
    Shortcut { sequence:"Ctrl+1"; context:Qt.ApplicationShortcut; onActivated:AppState.currentPage="overview" }
    Shortcut { sequence:"Ctrl+2"; context:Qt.ApplicationShortcut; onActivated:AppState.currentPage="proxies" }
    Shortcut { sequence:"Ctrl+3"; context:Qt.ApplicationShortcut; onActivated:AppState.currentPage="connections" }
    Shortcut { sequence:"Ctrl+4"; context:Qt.ApplicationShortcut; onActivated:AppState.currentPage="inspector" }
    Shortcut { sequence:"Ctrl+,"; context:Qt.ApplicationShortcut; onActivated:AppState.currentPage="settings" }
    Shortcut { sequence:"Ctrl+B"; context:Qt.ApplicationShortcut; onActivated:AppState.sidebarCollapsed=!AppState.sidebarCollapsed }
    Component { id:overview; OverviewPage {} }
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
    NumberAnimation {
        id:pageTransition
        target:pageLoader
        property:"opacity"
        from:0.52; to:1
        duration:Theme.motion
        easing.type:Easing.OutCubic
    }
    Connections {
        target:AppState
        function onCurrentPageChanged(){pageTransition.restart()}
    }
    Timer { id:toastTimer; interval:2800; onTriggered:AppState.toast="" }
    // Smoke mode deliberately visits every navigation destination and fails CI
    // if the QML engine reports page-loading warnings.
    Timer {
        id:smokeNavigator
        running:smokeTestMode
        repeat:true
        interval:60
        property int groupIndex:0
        property int pageIndex:0
        onTriggered:{
            if (groupIndex>=AppState.groups.length) {stop();return}
            AppState.currentPage=AppState.groups[groupIndex].pages[pageIndex].id
            ++pageIndex
            if (pageIndex>=AppState.groups[groupIndex].pages.length) {
                pageIndex=0
                ++groupIndex
            }
        }
    }
    Connections {
        target:AppState
        function onToastChanged() { if (AppState.toast.length) toastTimer.restart() }
    }
    Rectangle {
        visible:AppState.toast.length>0
        width:Math.min(530,window.width-40)
        height:46; radius:12
        anchors.horizontalCenter:parent.horizontalCenter
        anchors.bottom:parent.bottom
        anchors.bottomMargin:54
        z:999
        color:Theme.raised
        border.color:Theme.border
        Text {
            anchors.fill:parent
            anchors.margins:12
            text:AppState.toast
            color:Theme.text
            verticalAlignment:Text.AlignVCenter
            elide:Text.ElideRight
            font.pixelSize:12
        }
    }
    }
}