pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

ColumnLayout {
    id: groups
    property var records: []
    property var targetOptions: []
    property var connectionRecords: []
    property string appliedRevision: ""
    property string appliedGeneration: ""
    property bool editable: true
    property bool running: false
    property string query: ""
    readonly property var visibleRecords: records.filter(record => String(record.name).toLowerCase().indexOf(query.toLowerCase()) >= 0)
    readonly property var runtimeByGroup: {
        const result = {}
        if (!running || !appliedRevision.length || !appliedGeneration.length) return result
        for (const connection of connectionRecords) {
            const route = connection.route || {}
            if (connection.status !== "活动" || connection.closed || route.rejection_code || String(route.revision || "") !== appliedRevision || String(route.generation || "") !== appliedGeneration || !route.leaf_node_id) continue
            for (const id of route.group_chain || []) {
                if (!result[id]) result[id] = {leaves: [], connections: 0}
                const observed = result[id]
                if (observed.leaves.indexOf(String(route.leaf_node_id)) < 0) observed.leaves.push(String(route.leaf_node_id))
                ++observed.connections
            }
        }
        return result
    }
    signal editRequested(var record, Item source)
    signal memberRequested(var record, Item source)
    signal deleteRequested(var record, Item source)
    signal createRequested(string strategy, Item source)
    spacing: Theme.dp(12)

    function leafName(id) {
        if (id === "SWIRL_V2_DIRECT") return "DIRECT"
        const target = targetOptions.find(option => option.kind === "node" && option.id === id)
        return target ? String(target.name) : qsTr("节点已不在目录")
    }
    function actualExit(id) {
        if (!running) return qsTr("代理未开启")
        const observed = runtimeByGroup[id]
        if (!observed || !observed.leaves.length) return qsTr("等待流量")
        return observed.leaves.length === 1 ? leafName(observed.leaves[0]) : qsTr("%1 个实际出口").arg(observed.leaves.length)
    }
    function actualDetail(id) {
        const observed = runtimeByGroup[id]
        return observed ? observed.leaves.map(leaf => leafName(leaf)).join("\n") : qsTr("有活动连接时显示实际出口；不同服务可能使用不同节点。")
    }
    component PolicyMenuItem: MenuItem {
        id: action
        property string glyph: ""
        property bool danger: false
        implicitHeight: Theme.dp(38); leftPadding: Theme.dp(10); rightPadding: Theme.dp(12)
        contentItem: RowLayout {
            spacing: Theme.dp(10)
            SwirlIcon { name: action.glyph; size: Theme.dp(16); color: action.danger ? Theme.red : Theme.muted; Accessible.ignored: true }
            SwirlText { Layout.fillWidth: true; text: action.text; color: action.danger ? Theme.red : Theme.text; font.pixelSize: Theme.fontSize(12) }
        }
        background: Rectangle { radius: Theme.dp(8); color: action.highlighted ? Theme.hover : "transparent"; border.width: action.visualFocus ? Theme.borderWidth : 0; border.color: Theme.text }
    }
    RowLayout {
        Layout.fillWidth: true; spacing: Theme.dp(12)
        SwirlText { objectName: "policyGroupCountTitle"; Layout.alignment: Qt.AlignBaseline; text: qsTr("可复用出口"); color: Theme.text; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
        SwirlText { objectName: "policyGroupCount"; Layout.alignment: Qt.AlignBaseline; tabularFigures: true; text: String(groups.records.length); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        Item { Layout.fillWidth: true }
        SwirlSearchField {id:search;objectName:"policyGroupSearch";Layout.preferredWidth:Theme.dp(226);Layout.minimumWidth:Theme.dp(140);placeholderText:qsTr("搜索策略组");Accessible.name:placeholderText;onTextChanged:groups.query=text}
    }
    SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("把策略组分配给服务，统一管理出口。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
    RowLayout {
        Layout.fillWidth: true; visible: groups.records.length > 0; spacing: Theme.dp(8)
        SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; leftPadding: Theme.dp(8); text: qsTr("策略组 / 选择方式"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        SwirlText { Layout.preferredWidth: Theme.dp(220); leftPadding: Theme.dp(8); text: qsTr("实际出口 / 配置成员"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        Item { Layout.preferredWidth: Theme.dp(36) }
    }
    SwirlAnimatedModel { id: groupModel; source: groups.visibleRecords; keyRole: "id" }
    Item {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
        ListView {
            id: list; objectName: "policyGroupList"
            anchors.fill: parent; clip: true; reuseItems: true; pixelAligned: true; model: groupModel
            visible: groups.records.length > 0
            ScrollBar.vertical: SwirlScrollBar {}
            move: Transition { enabled: !SwirlMotion.reduced; NumberAnimation { property: "y"; duration: SwirlMotion.listDuration; easing.type: SwirlMotion.standardEasing } }
            displaced: Transition { enabled: !SwirlMotion.reduced; NumberAnimation { property: "y"; duration: SwirlMotion.listDuration; easing.type: SwirlMotion.standardEasing } }
            delegate: Item {
                id: row
                required property var entry
                readonly property var record: entry
                readonly property var observation: groups.runtimeByGroup[record.id] || ({leaves: [], connections: 0})
                width: Math.floor(ListView.view.width); height: Theme.dp(84)
                ListView.onPooled: { moreMenu.close(); visible = false }
                ListView.onReused: visible = true
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Theme.borderWidth; color: Theme.border }
                RowLayout {
                    anchors.fill: parent; spacing: Theme.dp(8)
                    SwirlMotionButton {
                        id: edit; objectName: "policyGroup-" + row.record.id
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; padding: Theme.dp(8); hoverEnabled: true; enabled: groups.editable
                        background: SwirlControlSurface { hovered: edit.hovered; pressed: edit.down; focused: edit.visualFocus; quiet: true; controlEnabled: edit.enabled }
                        contentItem: RowLayout {
                            spacing: Theme.dp(12)
                            SwirlIcon { name: row.record.strategy === "manual" ? "pin" : row.record.strategy === "url_test" ? "gauge" : row.record.strategy === "fallback" ? "shield" : "layers"; size: Theme.dp(20); color: Theme.muted; Accessible.ignored: true }
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(5)
                                SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: row.record.name; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold; elide: Text.ElideRight }
                                SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; tabularFigures: true; text: qsTr("%1，%2 个候选").arg(Policy.strategyName(row.record.strategy)).arg((row.record.members || []).length); color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                            }
                        }
                        Accessible.name: qsTr("编辑策略组 %1").arg(row.record.name)
                        onClicked: groups.editRequested(row.record, edit)
                    }
                    ColumnLayout {
                        Layout.preferredWidth: Theme.dp(220); Layout.minimumWidth: Theme.dp(160); spacing: Theme.dp(4)
                        SwirlText {
                            objectName: "policyGroupRuntime-" + row.record.id
                            Layout.fillWidth: true; Layout.minimumWidth: 0; leftPadding: Theme.dp(8)
                            text: groups.actualExit(row.record.id); textFormat: Text.PlainText
                            color: row.observation.connections ? Theme.text : Theme.muted; font.pixelSize: Theme.fontSize(13); font.weight: row.observation.connections ? Font.DemiBold : Font.Normal; elide: Text.ElideRight
                            HoverHandler { id: runtimeHover }
                            ToolTip.visible: runtimeHover.hovered; ToolTip.text: groups.actualDetail(row.record.id)
                        }
                        SubscriptionAction {
                            id: member; objectName: "policyGroupChoose-" + row.record.id
                            Layout.fillWidth: true; Layout.minimumWidth: 0; visible: row.record.strategy === "manual"; implicitHeight: Theme.dp(28)
                            text: qsTr("已选：%1").arg(Policy.targetName(row.record.selected, groups.targetOptions)); enabled: groups.editable
                            Accessible.name: qsTr("%1，%2，选择成员").arg(row.record.name).arg(text); tooltip: Accessible.name
                            contentItem: RowLayout {
                                spacing: Theme.dp(6)
                                SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: member.text; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                                SwirlIcon { name: "chevron-up-down"; size: Theme.dp(11); color: Theme.muted; Accessible.ignored: true }
                            }
                            onClicked: groups.memberRequested(row.record, member)
                        }
                        SwirlText { Layout.fillWidth: true; leftPadding: Theme.dp(8); tabularFigures: true; visible: row.record.strategy !== "manual"; text: row.observation.connections ? qsTr("%1 个活动连接").arg(row.observation.connections) : qsTr("按策略自动选择"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                    }
                    SubscriptionAction { id: more; objectName: "policyGroupMore-" + row.record.id; iconName: "ellipsis"; Layout.preferredWidth: Theme.dp(36); Layout.preferredHeight: Theme.dp(44); enabled: groups.editable; Accessible.name: qsTr("%1 的更多操作").arg(row.record.name); tooltip: Accessible.name; tooltipEnabled: !moreMenu.visible; onClicked: moreMenu.showAt() }
                }
                SwirlContextMenu {
                    id: moreMenu; popupType: Popup.Item; parent: more; x: more.width - width; y: more.height; transformOrigin: Item.TopRight
                    items: []; implicitWidth: Theme.dp(204)
                    PolicyMenuItem { objectName: "swirlContextOption-0"; text: qsTr("编辑策略组"); glyph: "edit"; enabled: groups.editable; onTriggered: groups.editRequested(row.record, more) }
                    MenuSeparator { contentItem: Rectangle { implicitHeight: Theme.borderWidth; color: Theme.border } topPadding: Theme.dp(5); bottomPadding: Theme.dp(5) }
                    PolicyMenuItem { objectName: "swirlContextOption-1"; text: qsTr("删除策略组"); glyph: "trash"; danger: true; enabled: groups.editable; onTriggered: groups.deleteRequested(row.record, more) }
                }
            }
            SwirlEmptyState { anchors.centerIn: parent; width: parent.width; visible: groups.records.length > 0 && list.count === 0; headline: qsTr("没有匹配的策略组"); detail: qsTr("尝试其他名称。") }
        }
        PolicyGroupTypes { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: Theme.dp(8); visible: groups.records.length === 0; editable: groups.editable; onCreateRequested: (strategy, source) => groups.createRequested(strategy, source) }
    }
}
