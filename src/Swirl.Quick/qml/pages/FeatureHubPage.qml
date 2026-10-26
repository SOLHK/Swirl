pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    component Entry: SwirlMotionButton {
        id: entry
        required property string entryTitle
        required property string entryDescription
        required property string entryIcon
        required property string route
        property bool featured: false
        readonly property Item motionTitle: label
        readonly property string motionIcon: entryIcon
        readonly property string motionDescription: entryDescription
        readonly property Item motionSurface: background
        objectName: "settings-" + route
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredHeight: Theme.dp(featured ? 100 : 82)
        padding: Theme.dp(featured ? 20 : 14)
        hoverEnabled: true
        motionScale: 1 - (1 - SwirlMotion.pressScale) * feedback.contact
        SwirlInteractionMotion { id: feedback; hovered: entry.hovered; pressed: entry.down; focused: entry.visualFocus; controlEnabled: entry.enabled }
        background: Rectangle {
            id: surface
            property bool surfaceHidden: false
            color: Theme.material("content")
            radius: entry.featured ? Theme.cardRadius : Theme.controlRadius
            opacity: surfaceHidden ? 0 : 1
            border.width: entry.visualFocus ? Theme.borderWidth : 0
            border.color: Theme.focusBorder
            Rectangle { anchors.fill: parent; radius: parent.radius; color: Theme.withAlpha(Theme.accent, (entry.featured ? 0.035 : 0) + feedback.light * 0.055) }
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.leftMargin: Theme.dp(14); anchors.rightMargin: Theme.dp(14); height: Theme.borderWidth; color: Theme.separator; visible: !entry.featured }
        }
        contentItem: RowLayout {
            spacing: Theme.dp(entry.featured ? 18 : 14)
            SwirlIcon { name: entry.entryIcon; size: Theme.dp(entry.featured ? 34 : 25); color: Theme.accent }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.dp(6)
                SwirlText { id: label; Layout.fillWidth: true; text: entry.entryTitle; color: Theme.text; font.pixelSize: Theme.fontSize(entry.featured ? 19 : 15); font.weight: Font.DemiBold; elide: Text.ElideRight }
                SwirlText { Layout.fillWidth: true; text: entry.entryDescription; color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
            }
            SwirlIcon { name: "chevron-right"; size: Theme.dp(14); color: Theme.muted; transform: Translate { x: Theme.dp(3) * feedback.light } }
        }
        onClicked: page.Window.window.openSettings(route, entry)
        Accessible.name: entryTitle
        Accessible.description: entryDescription
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.pagePadding
        spacing: Theme.sectionGap
        SwirlPageHeader { Layout.fillWidth: true; title: qsTr("设置"); description: qsTr("管理界面偏好、网络资源与本地配置。") }
        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: SwirlScrollBar {}
            ColumnLayout {
                width: scroll.availableWidth
                spacing: Theme.dp(24)
                Entry { featured: true; entryTitle: qsTr("通用设置"); entryDescription: qsTr("主题、字体、动画与本机偏好"); entryIcon: "settings"; route: "settings" }
                GridLayout {
                    Layout.fillWidth: true
                    columns: width < Theme.dp(560) ? 1 : 2
                    columnSpacing: Theme.dp(28)
                    rowSpacing: Theme.dp(24)
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: Theme.dp(4)
                        SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("连接资源"); description: qsTr("解析、节点与来源。") }
                        Entry { entryTitle: "DNS"; entryDescription: qsTr("解析服务与本地映射"); entryIcon: "dns"; route: "dns" }
                        Entry { entryTitle: qsTr("订阅管理"); entryDescription: qsTr("来源、更新与自动更新周期"); entryIcon: "subscriptions"; route: "subscriptions" }
                        Entry { entryTitle: qsTr("节点管理"); entryDescription: qsTr("浏览、测速与编辑节点"); entryIcon: "proxies"; route: "proxies" }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: Theme.dp(4)
                        SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("配置工具"); description: qsTr("配置文件与扩展能力。") }
                        Entry { entryTitle: qsTr("模块"); entryDescription: qsTr("管理配置扩展模块"); entryIcon: "modules"; route: "modules" }
                        Entry { entryTitle: qsTr("配置"); entryDescription: qsTr("管理与切换本地配置"); entryIcon: "profiles"; route: "profiles" }
                        Entry { entryTitle: qsTr("脚本"); entryDescription: qsTr("脚本草稿与能力状态"); entryIcon: "scripts"; route: "scripts" }
                    }
                }
                Item { Layout.preferredHeight: Theme.dp(12) }
            }
        }
    }
}
