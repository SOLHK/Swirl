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
    Component.onCompleted: backdrop.apply(window, swirlTransparencyEnabled)
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
        SwirlSidebar { Layout.fillHeight:true }
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
                        placeholderText:"Go to a page..."
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
                    SwirlStatusBadge { label:"UI DEMO"; tone:"accent" }
                    SwirlButton { text:"Settings"; iconName:"settings"; quiet:true; onClicked:AppState.currentPage="settings" }
                }
            }
            Loader {
                id:pageLoader
                Layout.fillWidth:true
                Layout.fillHeight:true
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
                                AppState.currentPage==="logs" ? logs : workbench
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
    Component { id:workbench; WorkbenchPage { pageId:AppState.currentPage } }
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