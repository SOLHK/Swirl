pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

ColumnLayout {
    id: assignments
    property var defaultPolicy: ({target: {kind: "unconfigured"}})
    property var records: []
    property var targetOptions: []
    property var nodeCatalog: []
    property var groupRecords: []
    property string routingMode: "rule"
    property bool editable: true
    property string query: ""
    readonly property var visibleRecords: records.filter(record => (record.name + " " + Policy.domainSummary(record.domains)).toLowerCase().indexOf(query.toLowerCase()) >= 0).slice().sort((a, b) => a.priority - b.priority)
    readonly property var categories: [
        {key: "ai", name: qsTr("AI 服务")}, {key: "google", name: qsTr("Google 服务")},
        {key: "communication", name: qsTr("通信")}, {key: "media", name: qsTr("流媒体")}, {key: "custom", name: qsTr("自定义服务")}
    ]
    readonly property var visibleRows: {
        const rows = []
        for (const category of categories) {
            const members = visibleRecords.filter(record => categoryFor(record) === category.key)
            if (!members.length) continue
            rows.push({id: "category:" + category.key, rowKind: "header", name: category.name, count: members.length, record: {}})
            for (const record of members) rows.push({id: "service:" + record.id, rowKind: "service", record: record})
        }
        return rows
    }
    signal defaultTargetRequested(Item source)
    signal targetRequested(var record, Item source)
    signal editRequested(var record, Item source)
    signal enabledRequested(string id, bool enabled)
    signal moveRequested(string id, int direction)
    signal deleteRequested(var record, Item source)
    signal createRequested(Item source)
    spacing: Theme.dp(12)

    function categoryFor(record) {
        const domains = (record.domains || []).map(domain => String(domain.value).toLowerCase())
        const matches = suffixes => domains.some(domain => suffixes.some(suffix => domain === suffix || domain.endsWith("." + suffix)))
        if (matches(["openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com", "anthropic.com", "claude.ai", "perplexity.ai"])) return "ai"
        if (matches(["google.com", "googleapis.com", "gstatic.com", "googlevideo.com", "youtube.com", "ytimg.com"])) return "google"
        if (matches(["telegram.org", "t.me", "whatsapp.com", "discord.com", "discordapp.com"])) return "communication"
        if (matches(["netflix.com", "nflxvideo.net", "spotify.com", "twitch.tv", "disneyplus.com"])) return "media"
        return "custom"
    }
    function sourceFor(target) {
        if (!target || target.kind === "unconfigured") return qsTr("选择节点或策略组")
        if (target.kind === "direct") return qsTr("直接出站")
        if (target.kind === "group") {
            const group = groupRecords.find(item => item.id === target.id)
            return group ? qsTr("策略组，%1 个候选").arg((group.members || []).length) : qsTr("策略组已失效")
        }
        const node = nodeCatalog.find(item => item.id === target.id)
        return node ? String(node.sourceName || qsTr("节点资源库")) : qsTr("节点已失效")
    }
    component PolicyMenuItem: MenuItem {
        id: action
        property string glyph: ""
        property real glyphRotation: 0
        property bool danger: false
        implicitHeight: Theme.dp(38)
        leftPadding: Theme.dp(10); rightPadding: Theme.dp(12)
        contentItem: RowLayout {
            spacing: Theme.dp(10)
            SwirlIcon { name: action.glyph; rotation: action.glyphRotation; size: Theme.dp(16); color: action.danger ? Theme.red : Theme.muted; Accessible.ignored: true }
            SwirlText { Layout.fillWidth: true; text: action.text; color: action.danger ? Theme.red : Theme.text; font.pixelSize: Theme.fontSize(12) }
        }
        background: Rectangle { radius: Theme.dp(8); color: action.highlighted ? Theme.hover : "transparent"; border.width: action.visualFocus ? Theme.borderWidth : 0; border.color: Theme.text }
    }

    PolicyRouteStrip {
        Layout.fillWidth: true; Layout.preferredHeight: implicitHeight
        defaultPolicy: assignments.defaultPolicy; targetOptions: assignments.targetOptions
        sourceLabel: assignments.sourceFor(assignments.defaultPolicy.target)
        mode: assignments.routingMode; editable: assignments.editable
        onTargetRequested: source => assignments.defaultTargetRequested(source)
    }
    RowLayout {
        Layout.fillWidth: true; spacing: Theme.dp(10)
        SwirlText { objectName: "servicePolicyCountTitle"; Layout.alignment: Qt.AlignBaseline; text: qsTr("专属服务"); color: Theme.text; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold }
        SwirlText { objectName: "servicePolicyCount"; Layout.alignment: Qt.AlignBaseline; tabularFigures: true; text: String(assignments.records.length); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Accessible.name: qsTr("%1 项专属服务策略").arg(assignments.records.length) }
        Item { Layout.fillWidth: true }
        SwirlSearchField {id:search;objectName:"servicePolicySearch";Layout.preferredWidth:Theme.dp(226);Layout.minimumWidth:Theme.dp(140);placeholderText:qsTr("搜索服务或域名");Accessible.name:placeholderText;onTextChanged:assignments.query=text}
    }
    SwirlText {
        Layout.fillWidth: true; wrapMode: Text.Wrap; visible: assignments.records.length > 0
        text: assignments.routingMode === "rule" ? qsTr("分类仅用于浏览；匹配顺序由各策略的优先级决定。") : qsTr("专属分配已保存；切回规则分流后参与路由。")
        color: Theme.muted; font.pixelSize: Theme.fontSize(12)
    }
    SwirlAnimatedModel { id: services; source: assignments.visibleRows; keyRole: "id" }
    Item {
        Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
        ListView {
            id: list; objectName: "servicePolicyList"
            anchors.fill: parent; clip: true; reuseItems: true; pixelAligned: true; model: services
            ScrollBar.vertical: SwirlScrollBar {}
            move: Transition { enabled: !SwirlMotion.reduced; NumberAnimation { property: "y"; duration: SwirlMotion.listDuration; easing.type: SwirlMotion.standardEasing } }
            displaced: Transition { enabled: !SwirlMotion.reduced; NumberAnimation { property: "y"; duration: SwirlMotion.listDuration; easing.type: SwirlMotion.standardEasing } }
            delegate: Item {
                id: row
                required property var entry
                readonly property var record: entry.record || ({})
                readonly property bool headerRow: entry.rowKind === "header"
                readonly property string category: assignments.categoryFor(record)
                width: Math.floor(ListView.view.width); height: Theme.dp(headerRow ? 30 : 76)
                ListView.onPooled: { moreMenu.close(); visible = false }
                ListView.onReused: visible = true
                RowLayout {
                    visible: row.headerRow; anchors.fill: parent; spacing: Theme.dp(8)
                    SwirlText { Layout.alignment: Qt.AlignBaseline; text: row.entry.name || ""; color: Theme.muted; font.pixelSize: Theme.fontSize(12); font.weight: Font.DemiBold }
                    SwirlText { Layout.alignment: Qt.AlignBaseline; tabularFigures: true; text: String(row.entry.count || ""); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.border }
                }
                RowLayout {
                    visible: !row.headerRow; anchors.fill: parent; spacing: Theme.dp(6)
                    SwirlMotionButton {
                        id: edit; objectName: "servicePolicy-" + row.record.id
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true
                        padding: Theme.dp(8); leftPadding: Theme.dp(34); enabled: assignments.editable; hoverEnabled: true
                        background: SwirlControlSurface { hovered: edit.hovered; pressed: edit.down; focused: edit.visualFocus; quiet: true; controlEnabled: edit.enabled }
                        contentItem: ColumnLayout {
                            spacing: Theme.dp(4)
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.dp(8)
                                SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; text: row.record.name || ""; textFormat: Text.PlainText; color: row.record.enabled ? Theme.text : Theme.muted; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold; elide: Text.ElideRight }
                                SwirlText { Layout.alignment: Qt.AlignBaseline; tabularFigures: true; text: qsTr("优先级 %1").arg(row.record.priority === undefined ? "" : row.record.priority); color: Theme.muted; font.pixelSize: Theme.fontSize(11) }
                            }
                            SwirlText { Layout.fillWidth: true; Layout.minimumWidth: 0; text: Policy.domainSummary(row.record.domains); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                        }
                        Accessible.name: qsTr("编辑策略 %1").arg(row.record.name || "")
                        SwirlIcon { anchors.left: parent.left; anchors.leftMargin: Theme.dp(9); anchors.verticalCenter: parent.verticalCenter; name: ({ai: "bolt", google: "globe", communication: "network", media: "play", custom: "document"})[row.category]; size: Theme.dp(17); color: Theme.muted; Accessible.ignored: true }
                        onClicked: assignments.editRequested(row.record, edit)
                    }
                    SwirlIcon { name: "chevron-right"; size: Theme.dp(12); color: Theme.muted; Accessible.ignored: true }
                    SubscriptionAction {
                        id: target; objectName: "servicePolicyTarget-" + row.record.id
                        Layout.preferredWidth: Theme.dp(184); Layout.minimumWidth: Theme.dp(140); Layout.preferredHeight: Theme.dp(54)
                        text: Policy.targetName(row.record.target, assignments.targetOptions); enabled: assignments.editable; tooltip: text
                        Accessible.name: qsTr("%1 的出口：%2").arg(row.record.name || "").arg(text)
                        contentItem: ColumnLayout {
                            spacing: Theme.dp(4)
                            SwirlText { objectName: "servicePolicyTargetText-" + row.record.id; Layout.fillWidth: true; Layout.minimumWidth: 0; text: target.text; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(13); font.weight: Font.DemiBold; elide: Text.ElideRight }
                            SwirlText { objectName: "servicePolicySource-" + row.record.id; Layout.fillWidth: true; Layout.minimumWidth: 0; text: assignments.sourceFor(row.record.target); textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
                        }
                        onClicked: assignments.targetRequested(row.record, target)
                    }
                    ReferenceCheckBox {
                        id: enabledControl; objectName: "servicePolicyEnabled-" + row.record.id
                        Layout.preferredWidth: Theme.dp(30); Layout.preferredHeight: Theme.dp(44); padding: 0
                        checked: Boolean(row.record.enabled); enabled: assignments.editable
                        Accessible.name: qsTr("启用策略 %1").arg(row.record.name || "")
                        onToggled: { const requested = checked; checked = Qt.binding(function() { return Boolean(row.record.enabled) }); assignments.enabledRequested(row.record.id, requested) }
                        indicator.x: (width - indicator.width) / 2
                    }
                    SubscriptionAction { id: more; objectName: "servicePolicyMore-" + row.record.id; iconName: "ellipsis"; Layout.preferredWidth: Theme.dp(36); Layout.preferredHeight: Theme.dp(44); enabled: assignments.editable; Accessible.name: qsTr("%1 的更多操作").arg(row.record.name || ""); tooltip: Accessible.name; tooltipEnabled: !moreMenu.visible; onClicked: moreMenu.showAt() }
                }
                Rectangle { visible: !row.headerRow; anchors.bottom: parent.bottom; width: parent.width; height: Theme.borderWidth; color: Theme.border }
                SwirlContextMenu {
                    id: moreMenu; popupType: Popup.Item; parent: more; x: more.width - width; y: more.height; transformOrigin: Item.TopRight
                    items: []; implicitWidth: Theme.dp(204)
                    PolicyMenuItem { objectName: "swirlContextOption-0"; text: qsTr("编辑策略"); glyph: "edit"; enabled: assignments.editable; onTriggered: assignments.editRequested(row.record, more) }
                    PolicyMenuItem { objectName: "swirlContextOption-1"; text: qsTr("上移优先级"); glyph: "chevron-right"; glyphRotation: -90; enabled: assignments.editable; onTriggered: assignments.moveRequested(row.record.id, -1) }
                    PolicyMenuItem { objectName: "swirlContextOption-2"; text: qsTr("下移优先级"); glyph: "chevron-right"; glyphRotation: 90; enabled: assignments.editable; onTriggered: assignments.moveRequested(row.record.id, 1) }
                    MenuSeparator { contentItem: Rectangle { implicitHeight: Theme.borderWidth; color: Theme.border } topPadding: Theme.dp(5); bottomPadding: Theme.dp(5) }
                    PolicyMenuItem { objectName: "swirlContextOption-3"; text: qsTr("删除策略"); glyph: "trash"; danger: true; enabled: assignments.editable; onTriggered: assignments.deleteRequested(row.record, more) }
                }
            }
        }
        ColumnLayout {
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: Theme.dp(22)
            visible: list.count === 0; spacing: Theme.dp(10)
            SwirlText { text: assignments.records.length ? qsTr("没有匹配的服务") : qsTr("需要单独分配哪个服务？"); color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: assignments.records.length ? qsTr("尝试其他名称或域名。") : qsTr("为 OpenAI、Claude、Google 或自定义网站指定出口；未单独分配的流量继续使用默认策略。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SubscriptionAction { objectName: "createFirstServicePolicy"; text: assignments.records.length ? qsTr("清空搜索") : qsTr("添加专属服务"); iconName: assignments.records.length ? "search" : "plus"; solid: true; enabled: assignments.editable; onClicked: { if (assignments.records.length) search.clear(); else assignments.createRequested(this) } }
        }
    }
}
