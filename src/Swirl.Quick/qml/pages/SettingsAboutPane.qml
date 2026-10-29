import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    id: pane
    required property var settingsPage
    spacing: Theme.dp(12)
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.dp(24)
        SwirlBrandIcon { Layout.preferredWidth: Theme.dp(104); Layout.preferredHeight: Theme.dp(104) }
        ColumnLayout { Layout.fillWidth: true; spacing: Theme.dp(6); SwirlText { text: "Swirl"; textRole: "largeTitle"; color: Theme.text; font.pixelSize: Theme.fontSize(32); font.weight: Font.DemiBold } SwirlText { text: qsTr("连接，让世界更近。"); color: Theme.muted; font.pixelSize: Theme.fontSize(14) } }
    }
    Item { Layout.preferredHeight: Theme.dp(16) }
    Repeater {
        model: [{name: qsTr("版本"), value: Qt.application.version.replace("-preview", qsTr(" · 开发版"))}, {name: qsTr("开发者"), value: "SOLHK"}, {name: qsTr("界面框架"), value: "Qt 6 Quick"}, {name: qsTr("平台"), value: qsTr("Windows 64 位")}]
        SettingsRowPane { required property var modelData; Layout.fillWidth: true; title: modelData.name; SwirlText { text: modelData.value; color: Theme.text; font.pixelSize: Theme.fontSize(14) } }
    }
    Item { Layout.preferredHeight: Theme.dp(14) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("项目与社区"); description: qsTr("通过默认浏览器打开。问题反馈请使用项目主页的 GitHub Issues。") }
    Flow {
        Layout.fillWidth: true
        spacing: Theme.compactGap
        SwirlButton { text: qsTr("项目主页"); onClicked: Qt.openUrlExternally("https://github.com/SOLHK/Swirl") }
        SwirlButton { id: officialChannelButton; objectName: "officialChannelButton"; text: qsTr("官方频道"); Accessible.description: qsTr("通过默认浏览器打开 Swirl 官方频道（Telegram）"); onClicked: Qt.openUrlExternally("https://t.me/SwirlUpdates"); SwirlToolTip { parent: officialChannelButton; visible: officialChannelButton.hovered || officialChannelButton.activeFocus; delay: 500; text: qsTr("Swirl 官方频道 · https://t.me/SwirlUpdates") } }
        SwirlButton { id: communityGroupButton; objectName: "communityGroupButton"; text: qsTr("用户交流群"); Accessible.description: qsTr("通过默认浏览器打开 Swirl 交流群（Telegram）"); onClicked: Qt.openUrlExternally("https://t.me/SwirlHQ"); SwirlToolTip { parent: communityGroupButton; visible: communityGroupButton.hovered || communityGroupButton.activeFocus; delay: 500; text: qsTr("Swirl 交流群 · https://t.me/SwirlHQ") } }
    }
    Item { Layout.preferredHeight: Theme.dp(16) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("字体与许可") }
    SwirlText { Layout.fillWidth: true; text: qsTr("Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.\n第三方组件包括 Qt、Rust 网络与密码库、C++ 运行库及 HarmonyOS Sans。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SwirlButton { id: fontLicenseButton; text: qsTr("字体与完整许可"); quiet: true; onClicked: pane.settingsPage.selectSection("字体", fontLicenseButton) }
}
