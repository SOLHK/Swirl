pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

SwirlDialog {
    id: dialog
    property var review: ({})
    property bool pending: false
    property string errorMessage: ""
    property bool canSubmit: true
    property bool recoveryRequired: false
    signal applyRequested()
    signal cancelRequested()
    signal recoveryRequested()
    signal reviewAgainRequested()
    objectName: "configurationReviewDialog"
    title: qsTr("审阅完整配置")
    guardChanges: false
    dismissBlocked: pending
    width: Math.min(Theme.dp(520), parent ? parent.width - Theme.dp(40) : Theme.dp(520))
    height: Math.min(implicitHeight, parent ? parent.height - Theme.dp(30) : implicitHeight)
    onClosed: { if (!pending) cancelRequested() }

    function showReview(value) {
        review = value
        errorMessage = ""
        pending = false
        if (!visible) open()
    }
    contentItem: ColumnLayout {
        spacing: Theme.dp(14)
        SwirlText {
            Layout.fillWidth: true; wrapMode: Text.Wrap
            text: qsTr("%1 的本机缓存配置").arg(dialog.review.sourceName || qsTr("订阅"))
            textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold
        }
        SwirlText {
            Layout.fillWidth: true; wrapMode: Text.Wrap
            text: qsTr("此次确认会替换以下设置。自动更新仍只管理节点；本次确认不会成为后续更新的授权。")
            color: Theme.muted; font.pixelSize: Theme.fontSize(12)
        }
        PolicyFormScroll {
            id: form
            ownerItem: dialog.ownerItem; formBody: reviewBody
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            Layout.preferredHeight: Math.min(reviewBody.implicitHeight, Theme.dp(270))
            ColumnLayout {
                id: reviewBody
                width: form.availableWidth; spacing: Theme.dp(10)
                Repeater {
                    model: dialog.review.changes || []
                    delegate: ColumnLayout {
                        id: change
                        required property var modelData
                        Layout.fillWidth: true; spacing: Theme.dp(5)
                        SwirlText { text: change.modelData.name || ""; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold }
                        SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("当前：%1").arg(change.modelData.before || qsTr("无")); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                        SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("本次：%1").arg(change.modelData.after || qsTr("无")); textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.border }
                    }
                }
                SwirlText { Layout.fillWidth: true; visible: text.length > 0; wrapMode: Text.Wrap; text: dialog.review.impact || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                SwirlText { objectName: "configurationReviewError"; Layout.fillWidth: true; visible: text.length > 0; wrapMode: Text.Wrap; text: dialog.errorMessage || dialog.review.error || ""; textFormat: Text.PlainText; color: Theme.red; font.pixelSize: Theme.fontSize(12); activeFocusOnTab: true }
            }
        }
        SwirlText { Layout.fillWidth: true; visible: !!dialog.review.canApply; wrapMode: Text.Wrap; text: qsTr("预览在 10 分钟内有效。来源或现有配置变化后，必须重新审阅。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(8)
            SwirlButton { objectName: "recoverConfigurationReview"; text: qsTr("恢复已保存的操作"); visible: dialog.pending && dialog.recoveryRequired; onClicked: dialog.recoveryRequested() }
            SwirlButton { objectName: "repeatConfigurationReview"; text: qsTr("重新审阅"); visible: !dialog.review.canApply && !dialog.pending; enabled: dialog.canSubmit; onClicked: dialog.reviewAgainRequested() }
            Item { Layout.fillWidth: true }
            SwirlButton { text: qsTr("取消"); enabled: !dialog.pending; onClicked: dialog.close() }
            SwirlButton { objectName: "applyReviewedConfiguration"; text: dialog.pending ? qsTr("正在应用…") : qsTr("本次应用"); primary: true; enabled: !!dialog.review.canApply && !dialog.pending && dialog.canSubmit; onClicked: dialog.applyRequested() }
        }
    }
}
