import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    id: pane
    required property var settingsPage
    property real viewportHeight: 0
    readonly property bool compact: viewportHeight > 0 && viewportHeight < Theme.dp(520)
    spacing: Theme.dp(compact ? 12 : 16)

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.dp(18)
        SwirlBrandIcon {
            Layout.preferredWidth: Theme.dp(pane.compact ? 64 : 76)
            Layout.preferredHeight: Layout.preferredWidth
        }
        SwirlText {
            Layout.fillWidth: true
            text: "Swirl"
            textRole: "largeTitle"
            color: Theme.text
            font.pixelSize: Theme.fontSize(30)
            font.weight: Font.DemiBold
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 0
        Repeater {
            model: [
                {name: qsTr("版本"), value: Qt.application.version.replace("-preview", qsTr(" · 开发版"))},
                {name: qsTr("开发者"), value: "SOLHK"},
                {name: qsTr("界面框架"), value: "Qt 6 Quick"},
                {name: qsTr("平台"), value: qsTr("Windows 64 位")}
            ]
            Item {
                id: field
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: fieldRow.implicitHeight + Theme.dp(pane.compact ? 12 : 16)
                RowLayout {
                    id: fieldRow
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.dp(20)
                    SwirlText {
                        text: field.modelData.name
                        color: Theme.muted
                        font.pixelSize: Theme.fontSize(14)
                    }
                    SwirlText {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: field.modelData.value
                        color: Theme.text
                        font.pixelSize: Theme.fontSize(14)
                        horizontalAlignment: Text.AlignRight
                        wrapMode: Text.Wrap
                    }
                }
                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: Theme.borderWidth
                    color: Theme.separator
                }
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.dp(6)
        SwirlSectionTitle {
            Layout.fillWidth: true
            title: qsTr("项目与社区")
            description: qsTr("通过默认浏览器打开。问题反馈请使用项目主页的 GitHub Issues。")
        }
        Flow {
            Layout.fillWidth: true
            spacing: Theme.compactGap
            SwirlButton { text: qsTr("项目主页"); onClicked: Qt.openUrlExternally("https://github.com/SOLHK/Swirl") }
            SwirlButton { id: officialChannelButton; objectName: "officialChannelButton"; text: qsTr("官方频道"); Accessible.description: qsTr("通过默认浏览器打开 Swirl 官方频道（Telegram）"); onClicked: Qt.openUrlExternally("https://t.me/SwirlUpdates") }
            SwirlButton { id: communityGroupButton; objectName: "communityGroupButton"; text: qsTr("用户交流群"); Accessible.description: qsTr("通过默认浏览器打开 Swirl 交流群（Telegram）"); onClicked: Qt.openUrlExternally("https://t.me/SwirlHQ") }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.dp(6)
        SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("字体与许可") }
        SwirlText {
            Layout.fillWidth: true
            text: qsTr("Swirl 使用 HarmonyOS Sans 字体。Copyright 2021 Huawei Device Co., Ltd.\n第三方组件包括 Qt、Rust 网络与密码库、C++ 运行库及 HarmonyOS Sans。")
            color: Theme.muted
            font.pixelSize: Theme.fontSize(12)
            wrapMode: Text.Wrap
        }
        SwirlButton {
            id: fontLicenseButton
            Layout.alignment: Qt.AlignLeft
            text: qsTr("字体与完整许可")
            quiet: true
            onClicked: pane.settingsPage.selectSection("字体", fontLicenseButton)
        }
    }
}
