pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var engineController
    required property var systemProvider
    readonly property var telemetry: engineController.telemetry
    readonly property bool wide: scroll.width - 2 * Theme.pagePadding >= Theme.dp(620)
    property int period: 0
    property int trafficKind: 0
    property int rankingKind: 0
    property var network: systemProvider.currentNetwork()
    property var totals: ({sampled: false})
    property var distribution: []
    property var ranks: []
    property bool proxyRanksAvailable: false
    property bool snapshotDirty: true
    readonly property bool connected: engineController.processAlive && engineController.apiHealthy
    readonly property string internetLatency: telemetry.latencies.internet || ""
    readonly property bool internetMeasured: /^\d+ ms$/.test(internetLatency)
    readonly property string emptyRanksText: trafficKind === 1 && !proxyRanksAvailable
        ? "此时段的代理来源尚无可核验的分类记录" : "暂无已采集的流量来源"
    readonly property int activeDeviceCount: {
        const addresses = new Set()
        for (const row of telemetry.connections) {
            if (row.status !== "活动" || !row.sourceIp || row.sourceIp === "127.0.0.1" || row.sourceIp === "::1") continue
            addresses.add(row.sourceIp)
        }
        return addresses.size
    }
    readonly property int dhcpDeviceCount: gatewayProvider.devices.filter(row => row.status === "租用中").length

    function refreshSnapshot() {
        if (!visible) return
        const range = period === 0 ? 0 : 3
        totals = telemetry.summary(range)
        distribution = telemetry.distribution(range)
        proxyRanksAvailable = telemetry.proxyRankingAvailable(range)
        let rows = []
        if (trafficKind === 0 || proxyRanksAvailable) {
            const proxyOnly = trafficKind === 1
            if (rankingKind === 0) rows = telemetry.ranking("apps", range, 4, proxyOnly)
                .concat(telemetry.ranking("devices", range, 4, proxyOnly))
            else rows = telemetry.ranking(rankingKind === 1 ? "domains" : "nodes", range, 4, proxyOnly)
            rows.sort((a, b) => b.total - a.total)
            rows = rows.slice(0, 3)
        }
        if (JSON.stringify(rows) !== JSON.stringify(ranks)) ranks = rows
        snapshotDirty = false
    }
    function bytes(value, known) { return known ? telemetry.formatBytes(value) : "—" }
    function latency(key) {
        const value = telemetry.latencies[key] || ""
        return /^\d+ ms$/.test(value) ? value : "—"
    }
    function goTraffic(item, key) {
        AppState.trafficPeriod = period === 0 ? 0 : 3
        SwirlMotion.navigateFrom(item, "traffic", key)
    }
    function openRank(row) {
        AppState.trafficPeriod = period === 0 ? 0 : 3
        if (row.kind === "apps") {
            AppState.trafficSelectedProcess = row.name
            AppState.openDetail("processes")
        } else if (row.kind === "devices") {
            AppState.trafficSelectedDevice = row.name
            AppState.openDetail("gateway")
        } else {
            AppState.connectionSearchQuery = row.name
            AppState.openDetail("connections")
        }
    }
    function scrollToBottom() { scroll.contentY = Math.max(0, scroll.contentHeight - scroll.height) }
    onPeriodChanged: { snapshotDirty = true; refreshSnapshot() }
    onTrafficKindChanged: { snapshotDirty = true; refreshSnapshot() }
    onRankingKindChanged: { snapshotDirty = true; refreshSnapshot() }
    onVisibleChanged: if (visible) refreshSnapshot()
    Component.onCompleted: refreshSnapshot()
    Connections { target: page.telemetry; function onChanged() { page.snapshotDirty = true } }
    Timer { interval: 300; running: page.visible && page.snapshotDirty; repeat: true; onTriggered: page.refreshSnapshot() }
    Timer { interval: 10000; running: page.visible; repeat: true; onTriggered: page.network = page.systemProvider.currentNetwork() }

    component Fact: ColumnLayout {
        property string caption: ""
        property string value: "—"
        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(2)
        SwirlText { text: parent.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
        SwirlText { text: parent.value; color: Theme.text; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
    }
    component StatRow: Item {
        id: statRow
        property string caption: ""
        property string value: "—"
        property color marker: "transparent"
        readonly property Item valueItem: valueText
        width: parent ? parent.width : 0; height: Theme.dp(40)
        Rectangle { anchors.top: parent.top; width: parent.width; height: 1 / Screen.devicePixelRatio; color: Theme.separator }
        Rectangle { visible: statRow.marker.a > 0; x: Theme.dp(3); y: Theme.dp(15); width: Theme.dp(5); height: Theme.dp(13); radius: width / 2; color: statRow.marker }
        SwirlText { x: statRow.marker.a > 0 ? Theme.dp(22) : Theme.dp(8); anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.67 - x; text: statRow.caption; color: Theme.text; font.pixelSize: Theme.fontSize(12); elide: Text.ElideRight }
        SwirlText { id: valueText; anchors.right: parent.right; anchors.rightMargin: Theme.dp(5); anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.34; text: statRow.value; color: Theme.text; font.pixelSize: Theme.fontSize(12); horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
    }
    component SectionTitle: SwirlMotionButton {
        id: titleControl
        property string caption: ""
        signal navigate()
        implicitHeight: Theme.dp(34); hoverEnabled: true
        topInset: 0; bottomInset: 0
        topPadding: Theme.dp(6); bottomPadding: Theme.dp(6); leftPadding: Theme.dp(9); rightPadding: Theme.dp(9)
        background: SwirlClearGlassSurface { radius: height / 2; focused: titleControl.activeFocus; pressed: titleControl.down; hovered: titleControl.hovered }
        contentItem: RowLayout {
            spacing: Theme.dp(5)
            SwirlText { Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter; text: titleControl.caption; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold }
            SwirlIcon { Layout.alignment: Qt.AlignVCenter; name: "chevron-right"; size: Theme.dp(15); color: Theme.text }
        }
        Accessible.name: caption + "详情"
        onClicked: navigate()
    }

    Flickable {
        id: scroll
        objectName: "activityScroll"
        anchors.fill: parent; anchors.topMargin: Theme.dp(52)
        contentWidth: width; contentHeight: content.implicitHeight + Theme.dp(12)
        flickableDirection: Flickable.VerticalFlick; boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: SwirlScrollBar {}

        ColumnLayout {
            id: content
            x: Theme.pagePadding; width: scroll.width - 2 * Theme.pagePadding
            spacing: 0

            Item {
                Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(45)
                Fact { x: parent.width * 0.02; width: parent.width * 0.22; caption: "网络"; value: page.network.type || "未连接" }
                Fact { x: parent.width * 0.255; width: parent.width * 0.23; caption: "配置"; value: extensionsProvider.profileName || "—" }
                ColumnLayout {
                    x: parent.width * 0.506; width: parent.width * 0.27; spacing: Theme.dp(2)
                    SwirlText { text: qsTr("出站模式"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
                    OutboundModeControl { Layout.alignment: Qt.AlignLeft; engineController: page.engineController }
                }
                Fact { x: parent.width * 0.8; width: parent.width * 0.2; caption: "外部 IP"; value: page.telemetry.externalIp || "—" }
            }
            Item { Layout.preferredHeight: Theme.dp(10) }

            GridLayout {
                id: cards
                Layout.fillWidth: true
                columns: page.wide ? 2 : 1
                columnSpacing: Theme.dp(10); rowSpacing: Theme.dp(10)

                SwirlGlassPanel {
                    id: diagnosticCard
                    objectName: "internetDiagnosticCard"
                    Layout.row: 0; Layout.column: 0
                    Layout.preferredWidth: page.wide ? (content.width - cards.columnSpacing) * 0.474 : content.width
                    Layout.preferredHeight: Theme.dp(276)
                    cornerRadius: Theme.dp(9); interactive: true

                    SwirlText { x: Theme.dp(18); y: Theme.dp(19); text: "INTERNET 延迟"; color: Theme.muted; font.pixelSize: Theme.fontSize(13) }
                    SwirlIconButton {
                        objectName: "networkDiagnosticButton"
                        x: Theme.dp(122); y: Theme.dp(12); implicitWidth: Theme.dp(28); implicitHeight: Theme.dp(28)
                        iconName: "refresh"; quiet: true
                        enabled: page.telemetry.measurementState !== "正在测量"
                        Accessible.name: "刷新 INTERNET 延迟"
                        onClicked: page.telemetry.measureNetwork()
                    }
                    SwirlButton {
                        id: diagnosticsLink
                        objectName: "networkDiagnosticDetails"
                        anchors.right: parent.right; anchors.rightMargin: Theme.dp(11); y: Theme.dp(14)
                        width: Theme.dp(94); implicitHeight: Theme.dp(28); text: "网络诊断"
                        onClicked: { page.telemetry.measureNetwork(); AppState.openDetail("toolbox") }
                    }
                    Row {
                        x: Theme.dp(18); y: Theme.dp(66); spacing: Theme.dp(5)
                        SwirlText { text: page.internetMeasured ? String(parseInt(page.internetLatency)) : "—"; color: Theme.dark ? Theme.text : "#08132C"; font.pixelSize: Theme.fontSize(page.internetMeasured ? 48 : 36); font.weight: Font.DemiBold }
                        SwirlText { anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.dp(6); text: page.internetMeasured ? "ms" : ""; color: Theme.dark ? Theme.text : "#08132C"; font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold }
                    }
                    SwirlText {
                        x: Theme.dp(19); y: Theme.dp(123); width: parent.width - Theme.dp(38)
                        text: page.internetMeasured ? "" : (page.telemetry.measurementState || "尚未检测")
                        color: Theme.muted; font.pixelSize: Theme.fontSize(11); elide: Text.ElideRight
                    }
                    Rectangle { x: Theme.dp(18); y: Theme.dp(150); width: parent.width - Theme.dp(36); height: 1 / Screen.devicePixelRatio; color: Theme.separator }
                    Item {
                        id: latencyMetrics
                        x: Theme.dp(18); y: Theme.dp(172); width: parent.width - Theme.dp(36); height: Theme.dp(45)
                        Repeater {
                            model: [
                                {caption: "路由", value: page.latency("router")},
                                {caption: "DNS", value: page.latency("dns")},
                                {caption: "代理", value: page.connected ? page.latency("proxy") : "不适用"}
                            ]
                            Column {
                                required property var modelData
                                required property int index
                                x: latencyMetrics.width * [0, 0.385, 0.735][index]
                                width: latencyMetrics.width * [0.28, 0.25, 0.26][index]
                                spacing: Theme.dp(5)
                                SwirlText { width: parent.width; text: parent.modelData.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                SwirlText { width: parent.width; text: parent.modelData.value; color: Theme.text; font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold; elide: Text.ElideRight }
                            }
                        }
                        Repeater {
                            model: 2
                            Rectangle { required property int index; x: latencyMetrics.width * [0.325, 0.675][index]; width: 1 / Screen.devicePixelRatio; height: Theme.dp(40); color: Theme.separator }
                        }
                    }
                }

                SwirlGlassPanel {
                    id: trafficCard
                    objectName: "activityTrafficCard"
                    Layout.row: page.wide ? 0 : 1; Layout.column: page.wide ? 1 : 0
                    Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(276)
                    cornerRadius: diagnosticCard.cornerRadius; interactive: true

                    SwirlText { x: Theme.dp(18); y: Theme.dp(19); text: "流量"; color: Theme.muted; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold }
                    SwirlSegmentedControl {
                        id: trafficFilter
                        objectName: "activityTrafficFilter"
                        anchors.right: parent.right; anchors.rightMargin: Theme.dp(36); y: Theme.dp(14)
                        width: Theme.dp(139); height: Theme.dp(28)
                        options: ["全部", "仅代理"]; currentIndex: page.trafficKind
                        onActivated: index => page.trafficKind = index
                    }
                    SwirlDailyTrafficChart {
                        id: trafficChart
                        objectName: "activityTrafficChart"
                        x: Theme.dp(17); y: Theme.dp(51)
                        width: parent.width - Theme.dp(34); height: Theme.dp(73)
                        proxyOnly: page.trafficKind === 1
                    }
                    SwirlSegmentedControl {
                        id: sourceFilter
                        objectName: "activitySourceFilter"
                        x: Theme.dp(17); y: Theme.dp(135)
                        width: parent.width - Theme.dp(34); height: Theme.dp(28)
                        options: ["进程与设备", "域名", "策略"]; currentIndex: page.rankingKind
                        onActivated: index => page.rankingKind = index
                    }
                    Column {
                        x: Theme.dp(17); y: Theme.dp(168); width: parent.width - Theme.dp(34)
                        Repeater {
                            model: page.ranks
                            SwirlMotionButton {
                                id: rank
                                required property var modelData
                                width: parent.width; height: Theme.dp(33); padding: 0; hoverEnabled: true
                                background: Rectangle { color: rank.down ? Theme.pressed : rank.hovered ? Theme.hover : "transparent"; radius: Theme.dp(5) }
                                contentItem: Item {
                                    SwirlIcon { x: Theme.dp(1); anchors.verticalCenter: parent.verticalCenter; size: Theme.dp(20); name: rank.modelData.kind === "apps" ? "terminal" : rank.modelData.kind === "devices" ? "router" : rank.modelData.kind === "domains" ? "globe" : "route"; color: Theme.muted }
                                    SwirlText { x: Theme.dp(31); anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.37; text: rank.modelData.name; color: Theme.text; font.pixelSize: Theme.fontSize(11); elide: Text.ElideRight }
                                    SwirlText { x: parent.width * 0.48; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.12; text: rank.modelData.kind === "apps" ? "进程" : rank.modelData.kind === "devices" ? "设备" : rank.modelData.kind === "domains" ? "域名" : "策略"; color: Theme.muted; font.pixelSize: Theme.fontSize(10); elide: Text.ElideRight }
                                    SwirlText { x: parent.width * 0.61; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.17; text: rank.modelData.value; color: Theme.muted; font.pixelSize: Theme.fontSize(10); horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
                                    SwirlText { x: parent.width * 0.79; anchors.verticalCenter: parent.verticalCenter; width: parent.width * 0.15; text: rank.modelData.connections + " 连接"; color: Theme.muted; font.pixelSize: Theme.fontSize(10); horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
                                    SwirlIcon { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; size: Theme.dp(13); name: "chevron-right"; color: Theme.muted }
                                    Rectangle { anchors.bottom: parent.bottom; x: Theme.dp(31); width: parent.width - x; height: 1 / Screen.devicePixelRatio; color: Theme.separator }
                                }
                                Accessible.name: modelData.name + "详情"
                                onClicked: page.openRank(modelData)
                            }
                        }
                    }
                    SwirlText { visible: page.ranks.length === 0; anchors.centerIn: parent; anchors.verticalCenterOffset: Theme.dp(63); width: parent.width - Theme.dp(44); text: page.emptyRanksText; color: Theme.muted; font.pixelSize: Theme.fontSize(11); horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap }
                }
            }

            Item { Layout.preferredHeight: Theme.dp(26) }
            GridLayout {
                id: bottomSections
                Layout.fillWidth: true
                columns: page.wide ? 3 : 1
                columnSpacing: Theme.dp(22); rowSpacing: Theme.dp(16)

                Column {
                    id: uploadSection
                    objectName: "activityUpload"
                    readonly property Item motionTitle: uploadRateRow.valueItem
                    readonly property Item motionSurface: uploadSection
                    Layout.preferredWidth: page.wide ? (content.width - 2 * bottomSections.columnSpacing) * 0.35 : content.width
                    Layout.preferredHeight: Theme.dp(204)
                    SectionTitle { caption: "上传和下载"; onNavigate: page.goTraffic(uploadSection, "uploadRate") }
                    Item { width: parent.width; height: Theme.dp(10) }
                    StatRow { id: uploadRateRow; caption: "当前上传速度"; value: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.uploadRate) + "/s" : "—"; marker: Theme.magenta }
                    StatRow { caption: "上传累计流量"; value: page.bytes(page.totals.up, page.totals.sampled) }
                    StatRow { caption: "当前下载速度"; value: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.downloadRate) + "/s" : "—"; marker: Theme.cyan }
                    StatRow { caption: "下载累计流量"; value: page.bytes(page.totals.down, page.totals.sampled) }
                }
                Column {
                    id: connectionsSection
                    objectName: "activityConnections"
                    readonly property Item motionTitle: connectionCountRow.valueItem
                    readonly property Item motionSurface: connectionsSection
                    Layout.preferredWidth: page.wide ? (content.width - 2 * bottomSections.columnSpacing) * 0.29 : content.width
                    Layout.preferredHeight: Theme.dp(204)
                    SectionTitle { caption: "活动连接"; onNavigate: SwirlMotion.navigateFrom(connectionsSection, "connections", "activeConnections") }
                    Item { width: parent.width; height: Theme.dp(10) }
                    StatRow { id: connectionCountRow; caption: "活动连接数量"; value: page.telemetry.connectionsSampled ? String(page.telemetry.activeConnections) : "—" }
                    StatRow { caption: "进程"; value: page.telemetry.connectionsSampled ? String(page.telemetry.activeProcesses) : "—" }
                    StatRow { caption: "设备"; value: page.telemetry.connectionsSampled ? String(page.activeDeviceCount) : "—" }
                    StatRow { caption: "DHCP 设备"; value: gatewayProvider.running ? String(page.dhcpDeviceCount) : "—" }
                }
                Column {
                    id: totalSection
                    objectName: "activityTotal"
                    readonly property Item motionTitle: totalTrafficRow.valueItem
                    readonly property Item motionSurface: totalSection
                    Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(204)
                    Item {
                        width: parent.width; height: Theme.dp(44)
                        SectionTitle { caption: "总计"; onNavigate: page.goTraffic(totalSection, "totalTraffic") }
                        SwirlSegmentedControl {
                            objectName: "activityPeriodFilter"
                            anchors.right: parent.right; y: Theme.dp(3)
                            width: Theme.dp(117); height: Theme.dp(28)
                            clearGlass: true
                            options: ["今日", "本月"]; currentIndex: page.period
                            onActivated: index => page.period = index
                        }
                    }
                    StatRow { id: totalTrafficRow; caption: "总流量"; value: page.bytes(page.totals.total, page.totals.sampled) }
                    StatRow { caption: "DIRECT"; value: page.distribution[1] && page.totals.sampled ? page.distribution[1].value : "—" }
                    StatRow { caption: "代理"; value: page.distribution[0] && page.totals.sampled ? page.distribution[0].value : "—" }
                    StatRow { caption: "拦截请求"; value: "—" }
                }
            }
        }
    }
}
