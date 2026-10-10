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
    title: "Swirl"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"
    background: Rectangle {
        radius: window.visibility === Window.Maximized ? 0 : 18
        color: Theme.canvas
        border.width: 1
        border.color: Theme.border
    }
    property bool swirlTransparencyEnabled: Theme.transparency
    Component.onCompleted: {
        backdrop.apply(window, swirlTransparencyEnabled)
        if (previewTheme==="dark") Theme.mode="Dark"
        else if (previewTheme==="light") Theme.mode="Light"
        if (previewPage.length && AppState.page(previewPage).id===previewPage)
            AppState.currentPage=previewPage
    }
    onSwirlTransparencyEnabledChanged: backdrop.apply(window, swirlTransparencyEnabled)
    font.family: "Microsoft YaHei UI"
    font.pixelSize: 13
    Rectangle {
        id: windowToolbar
        z: 50
        width: parent.width
        height: 49
        radius: window.visibility === Window.Maximized ? 0 : 18
        color: Theme.sidebar
        border.color: Theme.border
        border.width: 0
        Rectangle {
            anchors.left:parent.left; anchors.right:parent.right
            anchors.bottom:parent.bottom; height:20
            color:Theme.sidebar
        }
        // Native system move preserves Windows snapping and multitasking.
        MouseArea {
            anchors.fill:parent
            acceptedButtons: Qt.LeftButton
            onPressed: window.startSystemMove()
            onDoubleClicked: {
                if (window.visibility === Window.Maximized) window.showNormal()
                else window.showMaximized()
            }
        }
        RowLayout {
            z: 1
            anchors.fill:parent; anchors.leftMargin:19; anchors.rightMargin:21
            spacing:9
            Repeater {
                model: ["#FF605C","#FFBD44","#00CA4E"]
                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    width:13; height:13; radius:7
                    color:modelData
                    border.color:Qt.darker(modelData,1.12)
                    MouseArea {
                        anchors.fill:parent
                        cursorShape:Qt.PointingHandCursor
                        onClicked: {
                            if (index===0) window.close()
                            else if (index===1) window.showMinimized()
                            else if (window.visibility===Window.Maximized) window.showNormal()
                            else window.showMaximized()
                        }
                    }
                }
            }
            Item { Layout.fillWidth:true }
            Text { text:"Swirl"; color:Theme.text; font.family:"Segoe UI"; font.pixelSize:13; font.weight:Font.DemiBold }
            Item { Layout.fillWidth:true }
            Text { text:"界面预览 · 所有网络操作均为模拟"; color:Theme.muted; font.pixelSize:11 }
        }
    }
    // Frameless windows still support native edge resizing.
    MouseArea {
        z: 100
        visible:window.visibility !== Window.Maximized
        anchors.left:parent.left; anchors.top:parent.top; anchors.bottom:parent.bottom
        width:6; cursorShape:Qt.SizeHorCursor
        onPressed:window.startSystemResize(Qt.LeftEdge)
    }
    MouseArea {
        z:100; visible:window.visibility !== Window.Maximized
        anchors.right:parent.right; anchors.top:parent.top; anchors.bottom:parent.bottom
        width:6; cursorShape:Qt.SizeHorCursor
        onPressed:window.startSystemResize(Qt.RightEdge)
    }
    MouseArea {
        z:100; visible:window.visibility !== Window.Maximized
        anchors.bottom:parent.bottom; anchors.left:parent.left; anchors.right:parent.right
        height:6; cursorShape:Qt.SizeVerCursor
        onPressed:window.startSystemResize(Qt.BottomEdge)
    }
    Item {
        id: scaledCanvas
        y: windowToolbar.height
        width:window.width/Theme.uiScale
        height:(window.height-windowToolbar.height)/Theme.uiScale
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
                        placeholderText:"搜索功能 · Ctrl+K"
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
                            AppState.notice("没有找到对应功能")
                        }
                    }
                    SwirlButton {
                        text:"界面演示"; iconName:"grid"; quiet:true
                        onClicked:demoStatesMenu.popup()
                        Menu {
                            id:demoStatesMenu
                            y:parent.height+3
                            background:Rectangle { radius:11; color:Theme.raised; border.color:Theme.border }
                            MenuItem {
                                text:"正常模式"
                                onTriggered:{AppState.demoLoading=false;AppState.demoError=false;AppState.demoEmpty=false}
                            }
                            MenuItem {
                                text:"加载中"
                                onTriggered:{AppState.demoLoading=true;AppState.demoError=false;AppState.demoEmpty=false}
                            }
                            MenuItem {
                                text:"空数据"
                                onTriggered:{AppState.demoEmpty=true;AppState.demoLoading=false;AppState.demoError=false}
                            }
                            MenuItem {
                                text:"错误状态"
                                onTriggered:{AppState.demoError=true;AppState.demoLoading=false;AppState.demoEmpty=false}
                            }
                        }
                    }
                    SwirlButton { text:"设置"; iconName:"settings"; quiet:true; onClicked:AppState.currentPage="settings" }
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
                            headline:AppState.demoError?"模拟加载失败":"没有匹配的记录"
                            detail:AppState.demoError?"这是模拟的加载错误。":"当前正在演示空数据状态。"
                            Layout.alignment:Qt.AlignHCenter
                        }
                        Text {
                            visible:AppState.demoLoading
                            text:"正在加载演示数据…"
                            color:Theme.muted; font.pixelSize:13
                            Layout.alignment:Qt.AlignHCenter
                        }
                        SwirlButton {
                            text:AppState.demoError?"重试":"恢复正常"
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
                    Text { text:"●  当前为界面演示，不会执行真实网络操作"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                    Text { text:"Swirl  ·  测试版 0.1"; color:Theme.muted; font.pixelSize:11 }
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
    Component { id:settings; 设置Page {} }
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