pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id: row
    required property var record
    property bool expanded: false
    property bool editable: true
    property bool refreshable: true
    property real insertionOffset: 0
    readonly property bool updating: record.status === "正在更新"
    readonly property bool failed: record.status === "更新失败"
    readonly property real reveal: SwirlMotion.reduced ? (expanded ? 1 : 0) : detailClock.progress
    readonly property string stateLabel: record.status === "已保存真实节点" ? qsTr("已更新") : record.status
    signal expansionRequested()
    signal refreshRequested()
    signal editRequested(Item source)
    signal deleteRequested(Item source)
    signal reviewRequested(Item source)
    signal nodesRequested()
    objectName: "subscriptionCard-" + record.id
    implicitHeight: Theme.dp(76) + Math.round(details.implicitHeight * reveal)
    height: implicitHeight

    function closeMenu() { moreMenu.close() }
    transform: Translate { y: row.insertionOffset }
    function settle() { moreMenu.close(); detailClock.stop(); detailClock.progress = expanded ? 1 : 0; detailClock.destination = detailClock.progress; insertionOffset = 0; x = 0; opacity = 1 }
    onExpandedChanged: detailClock.moveTo(expanded ? 1 : 0)
    Component.onCompleted: detailClock.progress = expanded ? 1 : 0
    SwirlTransitionCoordinator { id: detailClock; duration: SwirlMotion.selectionDuration }

    Rectangle {
        anchors.fill: parent
        radius: Theme.controlRadius
        color: source.hovered || source.activeFocus ? Theme.navigationSelected : "transparent"
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.borderWidth; color: Theme.border }
    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; height: Theme.dp(76)
        spacing: Theme.dp(12)
        SwirlMotionButton {
            id: source
            objectName: "expandSubscription-" + row.record.id
            Layout.fillWidth: true; Layout.fillHeight: true
            hoverEnabled: true
            padding: Theme.dp(8)
            Accessible.name: qsTr("%1，%2 个节点，%3。%4详情").arg(row.record.name).arg(row.record.nodes).arg(row.stateLabel).arg(row.expanded ? qsTr("收起") : qsTr("展开"))
            background: Rectangle { color: "transparent"; radius: Theme.controlRadius; border.color: Theme.focusBorder; border.width: source.activeFocus ? Theme.borderWidth : 0 }
            contentItem: RowLayout {
                spacing: Theme.dp(10)
                SwirlIcon {
                    name: "chevron-right"; size: Theme.dp(12); color: Theme.muted
                    rotation: row.reveal * 90
                    Accessible.ignored: true
                }
                SwirlIcon { name: "subscriptions"; size: Theme.dp(20); color: Theme.muted; Accessible.ignored: true }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: Theme.dp(4)
                    SwirlText { objectName: "subscriptionTitle-" + row.record.id; text: row.record.name; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                    SwirlText {
                        Layout.fillWidth: true; elide: Text.ElideRight
                        text: row.failed ? qsTr("更新失败，已保留上次有效节点") : row.record.lastSuccess > 0 ? qsTr("更新于 %1").arg(row.record.update) : qsTr("尚无成功更新")
                        color: row.failed ? Theme.red : Theme.muted; font.pixelSize: Theme.fontSize(12)
                    }
                }
            }
            onClicked: row.expansionRequested()
        }
        SwirlText { text: String(row.record.nodes); Layout.preferredWidth: Theme.dp(38); horizontalAlignment: Text.AlignRight; color: Theme.text; font.pixelSize: Theme.fontSize(13); Accessible.name: qsTr("%1 个节点").arg(row.record.nodes) }
        SwirlStatusBadge {
            objectName: "subscriptionStatus-" + row.record.id
            label: row.stateLabel; busy: row.updating
            tone: row.record.status === "已保存真实节点" ? "success" : row.failed ? "warning" : "neutral"
        }
        SwirlMotionButton {
            id: refresh
            objectName: "refreshSubscription-" + row.record.id
            Layout.preferredWidth: Theme.controlHeight; Layout.preferredHeight: Theme.controlHeight
            hoverEnabled: true; enabled: row.record.canCancel || row.refreshable
            Accessible.name: row.record.canCancel ? (row.record.queued ? qsTr("取消排队 %1").arg(row.record.name) : qsTr("取消更新 %1").arg(row.record.name)) : qsTr("更新 %1").arg(row.record.name)
            ToolTip.visible: hovered || activeFocus; ToolTip.text: Accessible.name
            background: Rectangle { radius: Theme.controlRadius; color: refresh.down ? Theme.pressed : refresh.hovered ? Theme.hover : "transparent"; border.color: Theme.focusBorder; border.width: refresh.activeFocus ? Theme.borderWidth : 0 }
            contentItem: SwirlIcon { name: row.record.canCancel ? "dismiss" : "refresh"; color: refresh.enabled ? Theme.muted : Theme.withAlpha(Theme.muted, 0.5); size: Theme.dp(16); Accessible.ignored: true }
            onClicked: row.refreshRequested()
        }
        SwirlButton {
            id: more
            objectName: "moreSubscription-" + row.record.id
            text: qsTr("更多"); quiet: true; Layout.preferredWidth: Theme.dp(54); enabled: row.editable
            Accessible.name: qsTr("%1 的更多操作").arg(row.record.name)
            onClicked: { SwirlMotion.noteTrigger(more); moreMenu.open() }
        }
    }
    Item {
        x: Theme.dp(40); y: Theme.dp(76) - Theme.dp(4) * (1 - row.reveal); width: parent.width - x - Theme.dp(8)
        height: Math.round(details.implicitHeight * row.reveal); clip: true; enabled: row.expanded
        ColumnLayout {
            id: details
            width: parent.width; spacing: Theme.dp(8)
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: row.record.error || ""; visible: text.length > 0; textFormat: Text.PlainText; color: Theme.red; font.pixelSize: Theme.fontSize(12) }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: row.record.warning || ""; visible: text.length > 0; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(16)
                SwirlText { text: row.record.enabled ? qsTr("每 %1 分钟自动更新").arg(row.record.intervalMinutes) : qsTr("自动更新已关闭"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                SwirlText { Layout.fillWidth: true; elide: Text.ElideRight; text: row.record.enabled ? qsTr("下次 %1").arg(row.record.nextUpdate) : qsTr("手动更新可随时使用"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("自动识别格式，仅更新节点。地址已加密隐藏，DNS、规则和策略保持当前设置。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(6)
                SwirlButton { objectName: "viewSubscriptionNodes-" + row.record.id; text: qsTr("查看节点"); quiet: true; onClicked: row.nodesRequested() }
                SwirlButton { objectName: "editSubscription-" + row.record.id; text: qsTr("编辑"); quiet: true; enabled: row.editable; onClicked: row.editRequested(this) }
                SwirlButton { objectName: "reviewSubscription-" + row.record.id; text: qsTr("审阅完整配置"); quiet: true; enabled: row.editable; visible: !!row.record.hasConfiguration; onClicked: row.reviewRequested(this) }
                Item { Layout.fillWidth: true }
                SwirlButton { objectName: "deleteSubscription-" + row.record.id; text: qsTr("删除"); quiet: true; danger: true; enabled: row.editable; onClicked: row.deleteRequested(this) }
            }
            Item { Layout.preferredHeight: Theme.dp(8) }
        }
    }
    SwirlContextMenu {
        id: moreMenu
        popupType: Popup.Item; parent: more; x: more.width - width; y: more.height; transformOrigin: Item.TopRight
        items: row.record.hasConfiguration ? [qsTr("编辑来源"), qsTr("查看节点"), qsTr("审阅完整配置"), qsTr("删除来源")] : [qsTr("编辑来源"), qsTr("查看节点"), qsTr("删除来源")]
        handleItemsInternally: false
        onItemTriggered: index => {
            if (index === 0) row.editRequested(more)
            else if (index === 1) row.nodesRequested()
            else if (index === 2 && row.record.hasConfiguration) row.reviewRequested(more)
            else row.deleteRequested(more)
        }
    }
}
