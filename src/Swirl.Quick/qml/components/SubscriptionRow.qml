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
    readonly property string schedule: !record.enabled ? qsTr("手动更新") : Number(record.intervalMinutes) === 1440 ? qsTr("每天自动更新") : Number(record.intervalMinutes) === 10080 ? qsTr("每周自动更新") : qsTr("每 %1 小时自动更新").arg(Number(record.intervalMinutes) / 60)
    signal expansionRequested()
    signal refreshRequested()
    signal editRequested(Item source)
    signal deleteRequested(Item source)
    signal reviewRequested(Item source)
    signal nodesRequested()
    objectName: "subscriptionCard-" + record.id
    implicitHeight: Theme.dp(76) + Math.round(details.implicitHeight * reveal)
    height: implicitHeight
    transform: Translate { y: row.insertionOffset }
    function closeMenu() { moreMenu.close() }
    function settle() { moreMenu.close(); detailClock.stop(); detailClock.progress = expanded ? 1 : 0; detailClock.destination = detailClock.progress; insertionOffset = 0; x = 0; opacity = 1 }
    onExpandedChanged: detailClock.moveTo(expanded ? 1 : 0)
    Component.onCompleted: detailClock.progress = expanded ? 1 : 0
    SwirlTransitionCoordinator { id: detailClock; duration: SwirlMotion.selectionDuration }

    Rectangle {
        anchors.fill: parent; radius: Theme.controlRadius
        color: source.hovered || source.visualFocus ? Theme.navigationSelected : "transparent"
        Behavior on color { enabled: !SwirlMotion.reduced; ColorAnimation { duration: SwirlMotion.hoverDuration } }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.borderWidth; color: Theme.border }
    RowLayout {
        anchors.left: parent.left; anchors.right: parent.right; height: Theme.dp(76)
        spacing: Theme.dp(12)
        SwirlMotionButton {
            id: source
            objectName: "expandSubscription-" + row.record.id
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 0
            hoverEnabled: true; padding: Theme.dp(8)
            Accessible.name: qsTr("%1，%2 个节点，%3。%4详情").arg(row.record.name).arg(row.record.nodes).arg(row.stateLabel).arg(row.expanded ? qsTr("收起") : qsTr("展开"))
            background: Rectangle { color: "transparent"; radius: Theme.controlRadius; border.color: Theme.text; border.width: source.visualFocus ? Theme.borderWidth : 0 }
            contentItem: RowLayout {
                spacing: Theme.dp(10)
                SwirlIcon { name: "chevron-right"; size: Theme.dp(10); color: Theme.muted; rotation: row.reveal * 90; Accessible.ignored: true }
                SwirlIcon { name: "layers"; size: Theme.dp(18); color: Theme.muted; Accessible.ignored: true }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(5)
                    SwirlText { objectName: "subscriptionTitle-" + row.record.id; text: row.record.name; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                    SwirlText { Layout.fillWidth: true; elide: Text.ElideRight; text: row.schedule; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                }
            }
            onClicked: row.expansionRequested()
        }
        SwirlText { text: String(row.record.nodes); Layout.preferredWidth: Theme.dp(48); horizontalAlignment: Text.AlignRight; color: Theme.text; font.pixelSize: Theme.fontSize(14); Accessible.name: qsTr("%1 个节点").arg(row.record.nodes) }
        Item {
            objectName: "subscriptionStatus-" + row.record.id
            property string label: row.stateLabel
            property bool busy: row.updating
            property string tone: row.failed ? "warning" : row.record.status === "已保存真实节点" ? "success" : "neutral"
            Layout.preferredWidth: Theme.dp(126); Layout.fillHeight: true
            ColumnLayout {
                anchors.verticalCenter: parent.verticalCenter; width: parent.width; spacing: Theme.dp(5)
                RowLayout {
                    Layout.fillWidth: true; spacing: Theme.dp(5)
                    SwirlFlow {Layout.preferredWidth:Theme.dp(30);Layout.preferredHeight:Theme.dp(14);phase:row.updating?"pending":row.failed?"failed":row.record.status==="已保存真实节点"?"succeeded":"idle"}
                    SwirlText { text: row.stateLabel; color: row.failed ? Theme.red : Theme.text; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
                }
                SwirlText { text: row.record.lastSuccess > 0 ? row.record.update : qsTr("尚无成功更新"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
            }
        }
        RowLayout {
            Layout.preferredWidth: Theme.dp(88); spacing: 0
            SubscriptionAction {
                id: refresh
                objectName: "refreshSubscription-" + row.record.id
                Layout.preferredWidth: Theme.dp(44); Layout.preferredHeight: Theme.dp(44)
                iconName: row.record.canCancel ? "dismiss" : "refresh-source"
                enabled: row.record.canCancel || row.refreshable
                Accessible.name: row.record.canCancel ? (row.record.queued ? qsTr("取消排队 %1").arg(row.record.name) : qsTr("取消更新 %1").arg(row.record.name)) : qsTr("更新 %1").arg(row.record.name)
                tooltip: Accessible.name; tooltipEnabled: !moreMenu.visible
                onClicked: row.refreshRequested()
            }
            SubscriptionAction {
                id: more
                objectName: "moreSubscription-" + row.record.id
                iconName: "ellipsis"; enabled: row.editable
                Layout.preferredWidth: Theme.dp(44); Layout.preferredHeight: Theme.dp(44)
                Accessible.name: qsTr("%1 的更多操作").arg(row.record.name)
                tooltip: Accessible.name; tooltipEnabled: !moreMenu.visible
                onClicked: moreMenu.showAt()
            }
        }
    }
    Item {
        x: Theme.dp(46) + Theme.dp(7) * SwirlMotion.arch(row.reveal); y: Theme.dp(76) - Theme.dp(8) * (1 - row.reveal); width: parent.width - x - Theme.dp(12)
        height: Math.round(details.implicitHeight * row.reveal); clip: true; enabled: row.expanded
        opacity: row.reveal
        ColumnLayout {
            id: details
            width: parent.width; spacing: Theme.dp(8)
            SwirlText { Layout.fillWidth: true; text: row.record.enabled ? qsTr("下次更新  %1").arg(row.record.nextUpdate) : qsTr("自动更新已关闭，可随时手动更新。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
            SwirlText { Layout.fillWidth: true; text: qsTr("更新失败 · 已保留上次有效节点"); visible: row.failed; color: Theme.red; font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: row.record.error || ""; visible: text.length > 0; textFormat: Text.PlainText; color: Theme.red; font.pixelSize: Theme.fontSize(12) }
            SwirlText { Layout.fillWidth: true; text: qsTr("更新说明"); visible: String(row.record.warning || "").length > 0; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: row.record.warning || ""; visible: text.length > 0; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            Item { Layout.preferredHeight: Theme.dp(10) }
        }
    }
    component SourceMenuItem: MenuItem {
        id: menuAction
        property string glyph: ""
        property bool danger: false
        implicitHeight: Theme.dp(38)
        leftPadding: Theme.dp(10); rightPadding: Theme.dp(12)
        contentItem: RowLayout {
            spacing: Theme.dp(10)
            SwirlIcon { name: menuAction.glyph; size: Theme.dp(16); color: menuAction.danger ? Theme.red : Theme.muted; Accessible.ignored: true }
            SwirlText { text: menuAction.text; color: menuAction.danger ? Theme.red : Theme.text; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true }
        }
        background: Rectangle { radius: Theme.dp(8); color: menuAction.highlighted ? Theme.hover : "transparent"; border.width: menuAction.visualFocus ? Theme.borderWidth : 0; border.color: Theme.text }
    }
    SwirlContextMenu {
        id: moreMenu
        objectName: "subscriptionSourceMenu-" + row.record.id
        popupType: Popup.Item; parent: more; x: more.width - width; y: more.height - Theme.dp(2); transformOrigin: Item.TopRight
        items: []; implicitWidth: Theme.dp(204)
        SourceMenuItem { objectName: "editSubscription-" + row.record.id; text: qsTr("编辑来源"); glyph: "edit"; onTriggered: row.editRequested(more) }
        SourceMenuItem { objectName: "viewSubscriptionNodes-" + row.record.id; text: qsTr("查看节点"); glyph: "list"; onTriggered: row.nodesRequested() }
        SourceMenuItem { objectName: "reviewSubscription-" + row.record.id; text: qsTr("审阅完整配置"); glyph: "document"; visible: !!row.record.hasConfiguration; height: visible ? implicitHeight : 0; onTriggered: row.reviewRequested(more) }
        MenuSeparator { contentItem: Rectangle { implicitHeight: Theme.borderWidth; color: Theme.border } topPadding: Theme.dp(5); bottomPadding: Theme.dp(5) }
        SourceMenuItem { objectName: "deleteSubscription-" + row.record.id; text: qsTr("删除来源"); glyph: "trash"; danger: true; onTriggered: row.deleteRequested(more) }
    }
}
