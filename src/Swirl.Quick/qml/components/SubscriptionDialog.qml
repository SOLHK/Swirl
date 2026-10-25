pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

SwirlDialog {
    id: dialog
    property string sourceId: ""
    property bool pending: false
    property bool advanced: false
    property string errorMessage: ""
    property bool canSave: true
    property bool recoveryRequired: false
    readonly property string sourceName: displayName.text
    readonly property string sourceUrl: urlField.text.trim()
    readonly property int intervalMinutes: [360, 720, 1440, 10080][interval.currentIndex]
    readonly property bool autoUpdate: autoEnabled.checked
    readonly property string formatHint: ["auto", "clash", "loon", "shadowrocket", "surge", "quantumult-x", "sing-box"][formatPreference.currentIndex]
    signal saveRequested()
    signal recoveryRequested()
    objectName: "subscriptionDialog"
    title: sourceId.length ? qsTr("编辑订阅") : qsTr("添加订阅")
    dismissBlocked: pending
    height: Math.min(implicitHeight, parent ? parent.height - Theme.dp(30) : implicitHeight)
    stateFingerprint: String(autoUpdate) + ":" + intervalMinutes + ":" + formatHint

    function edit(record, source) {
        sourceId = record ? record.id : ""
        displayName.text = record ? record.name : ""
        urlField.text = ""
        formatPreference.currentIndex = record ? Math.max(0, ["auto", "clash", "loon", "shadowrocket", "surge", "quantumult-x", "sing-box"].indexOf(record.formatHint)) : 0
        interval.currentIndex = record ? Math.max(0, [360, 720, 1440, 10080].indexOf(record.intervalMinutes)) : 2
        autoEnabled.checked = record ? record.enabled : true
        advanced = false
        errorMessage = ""
        pending = false
        if (source) SwirlMotion.noteTrigger(source)
        open()
        Qt.callLater(function() { if (form.viewport) form.viewport.contentY = 0; displayName.forceActiveFocus() })
    }
    onClosed: urlField.text = ""
    contentItem: ColumnLayout {
        spacing: Theme.dp(14)
        PolicyFormScroll {
            id: form
            objectName: "subscriptionFormViewport"
            ownerItem: dialog.ownerItem; formBody: body
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            Layout.preferredHeight: Math.min(body.implicitHeight, Theme.dp(400))
            ColumnLayout {
                id: body
                objectName: "subscriptionFormBody"
                width: form.availableWidth; spacing: Theme.dp(10)
                SwirlText { text: qsTr("名称"); color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                SwirlTextField {
                    id: displayName; objectName: "subscriptionName"
                    Layout.fillWidth: true; enabled: !dialog.pending
                    placeholderText: qsTr("我的订阅"); maximumLength: 128
                    Accessible.name: qsTr("订阅名称")
                }
                SwirlText { text: qsTr("HTTPS 订阅地址"); color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                SwirlTextField {
                    id: urlField; objectName: "subscriptionUrl"
                    Layout.fillWidth: true; enabled: !dialog.pending
                    echoMode: TextInput.Password
                    placeholderText: dialog.sourceId.length ? qsTr("留空保留已加密地址") : "https://…"
                    Accessible.name: qsTr("订阅地址")
                    inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhSensitiveData
                }
                SwirlText {
                    objectName: "subscriptionAutomaticImport"
                    Layout.fillWidth: true; wrapMode: Text.Wrap
                    text: qsTr("自动识别格式，只更新来源节点。完整配置须单独审阅并确认，才会改变 DNS、规则和策略。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12)
                }
                RowLayout {
                    Layout.fillWidth: true
                    SwirlText { text: qsTr("自动更新"); Layout.fillWidth: true; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                    SwirlToggle { id: autoEnabled; checked: true; enabled: !dialog.pending; Accessible.name: qsTr("自动更新订阅") }
                }
                SwirlComboBox {
                    id: interval; objectName: "subscriptionInterval"
                    Layout.fillWidth: true; visible: autoEnabled.checked; enabled: !dialog.pending
                    model: [qsTr("每 6 小时"), qsTr("每 12 小时"), qsTr("每天"), qsTr("每周")]
                    Accessible.name: qsTr("自动更新间隔")
                }
                SwirlButton {
                    objectName: "subscriptionAdvanced"
                    text: dialog.advanced ? qsTr("收起高级设置") : qsTr("高级设置")
                    quiet: true; enabled: !dialog.pending
                    onClicked: dialog.advanced = !dialog.advanced
                }
                ColumnLayout {
                    Layout.fillWidth: true; visible: dialog.advanced; spacing: Theme.dp(8)
                    SwirlText { text: qsTr("客户端格式"); color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                    SwirlComboBox {
                        id: formatPreference; objectName: "subscriptionFormat"
                        Layout.fillWidth: true; enabled: !dialog.pending
                        model: [qsTr("自动"), "Clash", "Loon", qsTr("Shadowrocket / 通用"), "Surge / Surfboard", "Quantumult X", "sing-box"]
                        Accessible.name: qsTr("订阅格式")
                    }
                    SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("仅影响向服务器请求的客户端格式，下载后仍检测实际内容。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                }
                SwirlText {
                    objectName: "subscriptionSaveError"
                    Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0
                    text: dialog.errorMessage; textFormat: Text.PlainText
                    color: Theme.red; font.pixelSize: Theme.fontSize(12)
                    activeFocusOnTab: true; Accessible.role: Accessible.AlertMessage
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(8)
            SwirlButton {
                objectName: "recoverSubscriptionSave"; text: qsTr("恢复已保存的操作")
                visible: dialog.pending && dialog.recoveryRequired
                onClicked: dialog.recoveryRequested()
            }
            Item { Layout.fillWidth: true }
            SwirlButton { text: qsTr("取消"); enabled: !dialog.pending; onClicked: dialog.requestDismiss() }
            SwirlButton {
                objectName: "saveSubscription"
                text: dialog.pending ? qsTr("正在保存…") : qsTr("保存并更新"); primary: true
                enabled: !dialog.pending && dialog.canSave && displayName.text.trim().length > 0 && (dialog.sourceId.length > 0 || urlField.text.trim().length > 0)
                onClicked: dialog.saveRequested()
            }
        }
    }
}
