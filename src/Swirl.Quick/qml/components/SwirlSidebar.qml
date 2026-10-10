import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import SwirlQuick
import "../controls"
SwirlGlassPanel {
    id: sidebar
    material: "sidebar"
    property bool compactByWindow: false
    readonly property bool effectivelyCollapsed: AppState.sidebarCollapsed || compactByWindow
    cornerRadius: 22
    Layout.preferredWidth: sidebar.effectivelyCollapsed ? 72 : 237
    Layout.fillHeight: true
    border.color: Theme.glassRim
    Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.motion; easing.type: Easing.OutCubic } }
    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 4; anchors.bottomMargin: 8
        spacing: 4
        Item {
            Layout.fillWidth: true; Layout.preferredHeight: 78
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: sidebar.effectivelyCollapsed ? 15 : 18
                anchors.rightMargin: 12
                spacing: 10
                Image {
                    source: "qrc:/swirl/swirl-256.png"
                    sourceSize.width: 42; sourceSize.height: 42
                    Layout.preferredWidth: 37; Layout.preferredHeight: 37
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    layer.enabled: Theme.transparency
                    layer.effect: MultiEffect {
                        shadowEnabled: true
                        shadowBlur: 0.17
                        shadowVerticalOffset: 2
                        shadowColor: Theme.glassShadow
                    }
                }
                Column {
                    visible: !sidebar.effectivelyCollapsed
                    Layout.fillWidth: true; spacing: 2
                    Text { text: "Swirl"; color: Theme.text; font.pixelSize: 20; font.weight: Font.DemiBold; font.family: "Segoe UI Variable" }
                    Text { text: "专业网络工作台"; color: Theme.muted; font.pixelSize: 10; font.letterSpacing: 0.7 }
                }
            }
        }
        ScrollView {
            id: scroll
            Layout.fillWidth: true; Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                id: menuStack
                width: scroll.availableWidth
                spacing: 11
                Repeater {
                    model: AppState.groups
                    delegate: Column {
                        width: menuStack.width; spacing: 2
                        Text {
                            visible: !sidebar.effectivelyCollapsed
                            text: modelData.title
                            color: Theme.muted
                            font.pixelSize: 10
                            font.weight: Font.Medium
                            font.letterSpacing: 0.8
                            leftPadding: 21; topPadding: 12; bottomPadding: 7
                        }
                        Rectangle {
                            visible: sidebar.effectivelyCollapsed
                            width: 27; height: 1
                            color: Theme.glassRim
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Repeater {
                            model: modelData.pages
                            delegate: SwirlNavigationItem {
                                width: menuStack.width
                                pageId: modelData.id
                                title: modelData.title
                                iconName: modelData.icon
                                compact: sidebar.effectivelyCollapsed
                                onActivated: AppState.currentPage = pageId
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.leftMargin: 16; Layout.rightMargin: 16; height: 1; color: Theme.glassRim; opacity: 0.75 }
        SwirlNavigationItem {
            Layout.fillWidth: true
            pageId: "toggle-sidebar"
            title: sidebar.effectivelyCollapsed ? "展开侧边栏" : "收起侧边栏"
            iconName: "layers"
            compact: sidebar.effectivelyCollapsed
            onActivated: {
                if (sidebar.compactByWindow) AppState.toast = "请放大窗口以展开导航"
                else AppState.sidebarCollapsed = !AppState.sidebarCollapsed
            }
        }
    }
}
