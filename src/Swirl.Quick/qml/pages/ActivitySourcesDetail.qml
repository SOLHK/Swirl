pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var engineController
    property bool updatesEnabled: true
    readonly property var telemetry: engineController.telemetry
    property int kindIndex: 0
    property int period: 0
    property bool proxyOnly: false
    property string selectedId: ""
    property string pendingSelectionId: ""
    property var sourceRows: []
    property string sourceSignature: ""
    property bool snapshotDirty: true
    property bool componentReady: false
    readonly property string kind: ["apps", "devices", "domains", "nodes"][kindIndex]
    property bool proxyAvailable: false
    readonly property var selected: sourceRows.find(row => row.id === selectedId) || null
    readonly property var visibleRows: {
        const query = search.text.trim().toLocaleLowerCase()
        const rows = sourceRows.filter(row => (row.displayName + " " + row.name).toLocaleLowerCase().includes(query))
        const keys = ["total", "uploadBytes", "downloadBytes", "connections", "speed", "displayName"]
        const key = keys[sort.currentIndex]
        rows.sort((a, b) => key === "displayName"
            ? a.displayName.localeCompare(b.displayName, undefined, {numeric: true})
            : b[key] - a[key] || a.name.localeCompare(b.name))
        return rows
    }
    readonly property var selectedFacts: selected ? [
        {label: qsTr("累计流量"), value: selected.value},
        {label: qsTr("上传"), value: selected.upload},
        {label: qsTr("下载"), value: selected.download},
        {label: qsTr("连接次数"), value: String(selected.connections)},
        {label: qsTr("当前速率"), value: telemetry.connectionsSampled ? selected.speedText : qsTr("尚未采集")},
        {label: qsTr("流量占比"), value: selected.percent}
    ] : []

    function displayName(row) {
        if (row.kind !== "nodes") return row.name
        if (row.name === "SWIRL_V2_DIRECT" || row.name === "DIRECT") return qsTr("直连")
        if (row.name === "SWIRL_V2_REJECT" || row.name === "REJECT") return qsTr("阻止")
        const option = engineController.policyTargetOptions.find(target => target.id === row.name)
        return option ? option.name : row.name
    }
    function refreshSnapshot() {
        if (!componentReady || !visible || !updatesEnabled) return
        proxyAvailable = telemetry.proxyRankingAvailable(period)
        const rows = telemetry.ranking(kind, period, 0, proxyOnly).map(row => Object.assign({}, row, {
            id: kind + ":" + row.id,
            displayName: displayName(row)
        }))
        const signature = JSON.stringify(rows)
        if (signature !== sourceSignature) {
            sourceSignature = signature
            sourceRows = rows
        }
        snapshotDirty = false
        locateSelection()
    }
    function refresh() { snapshotDirty = true; refreshSnapshot() }
    function selectSource(row) {
        const index = ["apps", "devices", "domains", "nodes"].indexOf(row.kind)
        if (index < 0) return
        kindIndex = index
        selectedId = row.kind + ":" + (row.id || row.name)
        pendingSelectionId = selectedId
        search.text = ""
        refresh()
    }
    function locateSelection() {
        if (!pendingSelectionId.length) return
        const key = pendingSelectionId
        pendingSelectionId = ""
        Qt.callLater(function() { sourceTable.positionRow(key) })
    }
    onKindIndexChanged: refresh()
    onPeriodChanged: refresh()
    onProxyOnlyChanged: refresh()
    onVisibleChanged: if (visible) refresh()
    onUpdatesEnabledChanged: if (updatesEnabled) refresh()
    Component.onCompleted: { componentReady = true; refresh() }
    Connections { target: page.telemetry; function onChanged() { page.snapshotDirty = true } }
    Timer { interval: 300; running: page.visible && page.updatesEnabled && page.snapshotDirty; repeat: true; onTriggered: page.refreshSnapshot() }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.dp(12)
        GridLayout {
            Layout.fillWidth: true
            columns: page.width < Theme.dp(640) ? 1 : 2
            columnSpacing: Theme.dp(12); rowSpacing: Theme.dp(10)
            SwirlSegmentedControl {
                objectName: "activitySourcesKind"
                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: Theme.dp(340)
                options: [qsTr("进程"), qsTr("设备"), qsTr("域名"), qsTr("策略")]
                currentIndex: page.kindIndex
                onActivated: index => page.kindIndex = index
            }
            RowLayout {
                spacing: Theme.dp(8)
                SwirlComboBox {
                    objectName: "activitySourcesPeriod"
                    Layout.fillWidth: true; Layout.preferredWidth: Theme.dp(104)
                    model: [qsTr("今日"), qsTr("昨日"), qsTr("本周"), qsTr("本月")]
                    currentIndex: page.period; onActivated: page.period = currentIndex
                    Accessible.name: qsTr("流量来源统计期间")
                }
                SwirlSegmentedControl {
                    objectName: "activitySourcesTrafficFilter"
                    Layout.fillWidth: true; Layout.preferredWidth: Theme.dp(144)
                    options: [qsTr("全部"), qsTr("仅代理")]; currentIndex: page.proxyOnly ? 1 : 0
                    onActivated: index => page.proxyOnly = index === 1
                }
            }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: page.width < Theme.dp(540) ? 1 : 2
            columnSpacing: Theme.dp(10); rowSpacing: Theme.dp(8)
            SwirlSearchField { id: search; objectName: "activitySourcesSearch"; Layout.fillWidth: true; placeholderText: qsTr("搜索进程、设备、域名或策略") }
            SwirlComboBox {
                id: sort
                objectName: "activitySourcesSort"
                Layout.preferredWidth: Theme.dp(172)
                model: [qsTr("总流量优先"), qsTr("上传优先"), qsTr("下载优先"), qsTr("连接次数优先"), qsTr("当前速率优先"), qsTr("名称排序")]
                Accessible.name: qsTr("流量来源排序")
            }
        }
        SwirlText {
            Layout.fillWidth: true
            text: page.proxyOnly && !page.proxyAvailable
                ? qsTr("此时段的代理来源尚无可核验的分类记录")
                : qsTr("%1 项已归属来源 · 仅统计经过 Swirl 的流量").arg(page.visibleRows.length)
            color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap
        }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: Theme.dp(110)
            SwirlDataTable {
                id: sourceTable
                objectName: "activitySourcesTable"
                anchors.fill: parent
                rows: page.visibleRows; selectedId: page.selectedId
                incrementalRows: true; animateRowChanges: false; minimal: true
                columns: [
                    {key: "displayName", label: qsTr("来源"), w: 260, min: 160},
                    {key: "value", label: qsTr("总流量"), w: 120, min: 90},
                    {key: "upload", label: qsTr("上传"), w: 112, min: 90},
                    {key: "download", label: qsTr("下载"), w: 112, min: 90},
                    {key: "connections", label: qsTr("连接次数"), w: 100, min: 80},
                    {key: "percent", label: qsTr("占比"), w: 86, min: 70}
                ]
                onRowSelected: record => page.selectedId = record.id
            }
            SwirlEmptyState {
                visible: page.visibleRows.length === 0
                anchors.centerIn: parent; width: Math.max(0, parent.width - Theme.dp(24))
                headline: search.text.length ? qsTr("没有匹配的来源") : qsTr("尚无可归属流量")
                detail: search.text.length ? qsTr("调整搜索条件，查看其他来源。") : qsTr("连接产生可归属流量后，会显示实际上传、下载和连接次数。")
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.separator }
        ColumnLayout {
            visible: page.selected !== null
            Layout.fillWidth: true
            spacing: Theme.dp(9)
            SwirlText {
                objectName: "activitySourceSelectedName"
                Layout.fillWidth: true
                text: page.selected ? page.selected.displayName : ""
                textFormat: Text.PlainText; color: Theme.text
                font.pixelSize: Theme.fontSize(17); font.weight: Font.DemiBold; wrapMode: Text.WrapAnywhere
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width < Theme.dp(580) ? 3 : 6
                columnSpacing: Theme.dp(16); rowSpacing: Theme.dp(8)
                Repeater {
                    model: page.selectedFacts
                    ColumnLayout {
                        id: sourceFact
                        required property var modelData
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(4)
                        SwirlText { text: sourceFact.modelData.label; color: Theme.muted; font.pixelSize: Theme.fontSize(11) }
                        SwirlText { text: sourceFact.modelData.value; color: Theme.text; font.pixelSize: Theme.fontSize(13); tabularFigures: true; Layout.fillWidth: true; elide: Text.ElideRight }
                    }
                }
            }
        }
        SwirlText { visible: !page.selected; text: qsTr("选择一项来源查看完整流量摘要"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        SwirlText { visible: text.length > 0; text: page.telemetry.storageError; color: Theme.red; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
