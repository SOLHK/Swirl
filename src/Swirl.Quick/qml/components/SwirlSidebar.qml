import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Item {
    id: sidebar
    property bool compactByWindow: false
    property alias searchField: pageSearch
    readonly property bool effectivelyCollapsed: AppState.sidebarCollapsed || compactByWindow
    implicitWidth: Theme.sidebarWidth
    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: sidebar.effectivelyCollapsed ? 8 : 18
        anchors.rightMargin: sidebar.effectivelyCollapsed ? 8 : 18
        anchors.bottomMargin: 12
        spacing: 0
        Item {
            Layout.fillWidth: true; Layout.preferredHeight: 112
            Row {
                x: sidebar.effectivelyCollapsed?0:8; y: 20; spacing: sidebar.effectivelyCollapsed?7:10
                Repeater {
                    model: ["#FF6055", "#FFBD2E", "#00C84D"]
                    Button {
                        required property int index
                        required property string modelData
                        objectName:index===0?"windowCloseButton":index===1?"windowMinimizeButton":"windowMaximizeButton"
                        width: sidebar.effectivelyCollapsed?12:16; height: width; hoverEnabled: true
                        background: Rectangle { radius: Theme.roundedRadius(width,height); color: parent.modelData; opacity: parent.down ? 0.7 : 1 }
                        contentItem: Text { text: parent.hovered ? parent.index === 0 ? "×" : parent.index === 1 ? "−" : "+" : ""; font.pixelSize: 13; color: "#703030"; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                        onClicked: {
                            if (index === 0) sidebar.Window.window.close()
                            else if (index === 1) sidebar.Window.window.showMinimized()
                            else if (sidebar.Window.window.visibility === Window.Maximized) sidebar.Window.window.showNormal()
                            else sidebar.Window.window.showMaximized()
                        }
                        Accessible.name: index === 0 ? "关闭" : index === 1 ? "最小化" : "最大化或还原"
                    }
                }
            }
            RowLayout {
                x: 10; y: 53; width: parent.width - 16; spacing: 12
                SwirlBrandIcon { Layout.preferredWidth: sidebar.effectivelyCollapsed ? 40 : 48; Layout.preferredHeight: sidebar.effectivelyCollapsed ? 40 : 48 }
                Column {
                    visible: !sidebar.effectivelyCollapsed; Layout.fillWidth: true; spacing: 3
                    Text { text: "Swirl"; font.family: "Segoe UI"; font.pixelSize: 23; font.weight: Font.DemiBold; color: Theme.text }
                    Text { text: "网络代理工具"; font.pixelSize: 14; color: Theme.muted }
                }
            }
        }
        SwirlSearchField {
            id: pageSearch; objectName: "pageSearch"
            Layout.fillWidth: true; Layout.preferredHeight: 36
            placeholderText: sidebar.effectivelyCollapsed ? "" : "搜索功能"
            leftPadding: sidebar.effectivelyCollapsed ? 10 : 48
            font.pixelSize: 14
            Accessible.name: "搜索功能、节点或设置"
                    onAccepted:{
                        var q=text.trim().toLowerCase()
                        if(!q.length)return
                        for(var i=0;i<AppState.groups.length;i++)for(var j=0;j<AppState.groups[i].pages.length;j++){
                            var p=AppState.groups[i].pages[j]
                            if(p.title.toLowerCase().indexOf(q)>=0){AppState.navigate(p.id);text="";return}
                        }
                        var matches=FeatureCatalog.entries.filter(function(f){return (f.title+" "+f.keywords).toLowerCase().indexOf(q)>=0})
                        if(matches.length){AppState.navigate(matches[0].id);text="";return}
                        if(q.indexOf("模块中心")>=0){AppState.navigate("featurehub");text="";return}
                        if(q.indexOf("新加坡")>=0 || q.indexOf("节点")>=0)AppState.navigate("proxies")
                        else AppState.toast="没有找到对应功能或演示节点"
                    }

        }
        ScrollView {
            id: scroll; Layout.fillWidth: true; Layout.fillHeight: true
            Layout.topMargin: 8; clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: scroll.availableWidth; spacing: 0
                Repeater {
                    model: AppState.navigationGroups
                    delegate: Column {
                        required property var modelData
                        required property int index
                        width: parent.width
                        Item {
                            width: parent.width; height: index === 0 ? 30 : 38
                            Rectangle { visible: false; x: 3; width: parent.width - 6; y: 12; height: 1; color: Theme.controlBorder }
                            Text { visible: !sidebar.effectivelyCollapsed; x: 12; y: index === 0 ? 8 : 17; text: index === 0 ? "主要功能" : modelData.title; font.pixelSize: 14; font.weight: Font.Normal; color: Theme.muted }
                            Button {
                                visible: modelData.title === "分析与调试" && !sidebar.effectivelyCollapsed
                                x: parent.width - 60; y: 12; width: 60; height: 28
                                text: "全部 ›"; font.pixelSize: 12; palette.buttonText: Theme.muted
                                background: Rectangle { color: parent.hovered ? Theme.hover : "transparent"; radius: Theme.roundedRadius(width,height) }
                                onClicked: AppState.navigate("featurehub"); Accessible.name: "全部功能模块"
                            }
                        }
                        Repeater {
                            model: modelData.pages
                            delegate: SwirlNavigationItem {
                                required property var modelData
                                width: parent.width; pageId: modelData.id; title: modelData.title
                                iconName: modelData.icon; compact: sidebar.effectivelyCollapsed
                                onActivated: AppState.navigate(pageId)
                            }
                        }
                    }
                }
            }
        }
        Text { visible: !sidebar.effectivelyCollapsed; text:"通用"; color:Theme.muted; font.pixelSize:14; Layout.leftMargin:12; Layout.preferredHeight:28 }
        SwirlNavigationItem { Layout.fillWidth: true; pageId: "settings"; title: "设置"; iconName: "settings"; compact: sidebar.effectivelyCollapsed; onActivated: AppState.navigate(pageId) }
        SwirlNavigationItem { Layout.fillWidth: true; pageId: "logs"; title: "日志"; iconName: "document"; compact: sidebar.effectivelyCollapsed; onActivated: AppState.navigate(pageId) }
    }
}
