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

    readonly property bool proxyOwned: engineController.systemProxy.owned && engineController.systemProxy.enabled && engineController.processAlive
    readonly property string proxyError: engineController.systemProxy.stateReadError || engineController.systemProxy.error || engineController.routingError || engineController.policyError || (engineController.errorCode !== "None" ? engineController.error : "")
    readonly property string proxyPhase: engineController.systemProxyBusy || engineController.systemProxyStopping ? "pending" : proxyError.length ? "failed" : proxyOwned ? "succeeded" : "idle"
    readonly property string proxySummary: engineController.systemProxyStopping ? qsTr("正在恢复系统设置") : engineController.systemProxyBusy ? qsTr("正在开启代理") : proxyOwned ? qsTr("Swirl 正在接管网络") : engineController.processAlive ? qsTr("内核运行中，系统代理未接管") : qsTr("代理未开启")
    readonly property string defaultTargetName: {
        const target = ((engineController.policyDocument || {}).default_policy || {}).target || {}
        if (target.kind === "direct") return "DIRECT"
        const entry = engineController.policyTargetOptions.find(option => option.kind === target.kind && option.id === target.id)
        return entry ? entry.name : qsTr("尚未分配")
    }

    component Fact: ColumnLayout {
        id: fact
        property string caption: ""
        property string value: "—"
        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(4)
        SwirlText { text: fact.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
        SwirlText { text: fact.value; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.Medium; Layout.fillWidth: true; elide: Text.ElideRight }
    }
    component StatRow: RowLayout {
        id: stat
        property string caption: ""
        property string value: "—"
        readonly property Item valueItem: valueText
        width: parent ? parent.width : 0; height: Theme.dp(30); spacing: Theme.dp(8)
        SwirlText { text: stat.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
        SwirlText { id: valueText; text: stat.value; color: Theme.text; font.pixelSize: Theme.fontSize(13); font.weight: Font.Medium; elide: Text.ElideRight }
    }
    component SectionTitle: SwirlMotionButton {
        id: titleControl
        property string caption: ""
        signal navigate()
        implicitHeight: Theme.dp(30); hoverEnabled: true; padding: 0; rightPadding: Theme.dp(5)
        background: Rectangle { radius: Theme.dp(6); color: titleControl.down ? Theme.pressed : titleControl.hovered ? Theme.hover : "transparent"; border.width: titleControl.visualFocus ? Theme.borderWidth : 0; border.color: Theme.accent }
        contentItem: RowLayout {
            spacing: Theme.dp(6)
            SwirlText { text: titleControl.caption; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold }
            SwirlIcon { name: "chevron-right"; size: Theme.dp(14); color: Theme.muted }
        }
        Accessible.name: qsTr("%1详情").arg(caption)
        onClicked: navigate()
    }

    Flickable {
        id: scroll; objectName: "activityScroll"
        anchors.fill: parent; anchors.topMargin: Theme.dp(52)
        contentWidth: width; contentHeight: content.implicitHeight + Theme.dp(20)
        flickableDirection: Flickable.VerticalFlick; boundsBehavior: Flickable.StopAtBounds
        clip: true; ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            id: content
            x: Theme.pagePadding; width: scroll.width - 2 * Theme.pagePadding; spacing: Theme.dp(18)
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(12)
                SwirlText { textRole: "pageTitle"; text: qsTr("活动"); font.pixelSize: Theme.fontSize(26); font.weight: Font.DemiBold; color: Theme.text; Layout.fillWidth: true }
                SwirlButton { id: policyShortcut; text: qsTr("查看策略"); iconName: "route"; quiet: true; onClicked: SwirlMotion.navigateFrom(policyShortcut, "policies", "") }
            }
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: statusBody.implicitHeight + Theme.dp(28)
                radius: Theme.dp(14); color: Theme.buttonBase
                ColumnLayout {
                    id: statusBody; anchors.fill: parent; anchors.margins: Theme.dp(14); spacing: Theme.dp(14)
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(10)
                        SwirlFlow { Layout.preferredWidth: Theme.dp(54); Layout.preferredHeight: Theme.dp(20); phase: page.proxyPhase }
                        SwirlText { text: page.proxySummary; font.pixelSize: Theme.fontSize(15); font.weight: Font.DemiBold; color: Theme.text; Layout.fillWidth: true; elide: Text.ElideRight }
                        OutboundModeControl { engineController: page.engineController }
                    }
                    SwirlText { visible: page.proxyError.length > 0; text: page.proxyError; textFormat: Text.PlainText; color: Theme.red; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(14)
                        Fact { caption: qsTr("网络"); value: page.network.type || qsTr("未连接") }
                        Fact { caption: qsTr("配置"); value: extensionsProvider.profileName || "—" }
                        Fact { caption: qsTr("默认策略"); value: page.defaultTargetName }
                        Fact { caption: qsTr("外部 IP"); value: page.telemetry.externalIp || "—" }
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true; columns: page.wide ? 2 : 1; columnSpacing: Theme.dp(20); rowSpacing: Theme.dp(18)
                SwirlGlassPanel {
                    id: trafficCard; objectName: "activityTrafficCard"
                    Layout.fillWidth: true; Layout.preferredWidth: 3; Layout.minimumWidth: 0; Layout.preferredHeight: Theme.dp(268)
                    cornerRadius: Theme.dp(16); color: Theme.surface; border.width: 0
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: Theme.dp(16); spacing: Theme.dp(10)
                        RowLayout {
                            Layout.fillWidth: true
                            SwirlText { text: qsTr("传输"); font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold; color: Theme.text; Layout.fillWidth: true }
                            SwirlSegmentedControl { id: trafficFilter; objectName: "activityTrafficFilter"; Layout.preferredWidth: Theme.dp(138); Layout.preferredHeight: Theme.dp(28); options: [qsTr("全部"), qsTr("仅代理")]; currentIndex: page.trafficKind; onActivated: index => page.trafficKind = index }
                        }
                        RowLayout {
                            id: uploadSection; objectName: "activityUpload"
                            readonly property Item motionTitle: uploadRateText
                            readonly property Item motionSurface: uploadSection
                            Layout.fillWidth: true; spacing: Theme.dp(24)
                            ColumnLayout {
                                Layout.fillWidth: true; spacing: Theme.dp(3)
                                SectionTitle { caption: qsTr("上传"); onNavigate: page.goTraffic(uploadSection, "uploadRate") }
                                SwirlText { id: uploadRateText; text: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.uploadRate) + "/s" : "—"; font.pixelSize: Theme.fontSize(25); font.weight: Font.DemiBold; color: Theme.text }
                            }
                            ColumnLayout {
                                id: downloadSection
                                readonly property Item motionTitle: downloadRateText
                                readonly property Item motionSurface: downloadSection
                                Layout.fillWidth: true; spacing: Theme.dp(3)
                                SectionTitle { caption: qsTr("下载"); onNavigate: page.goTraffic(downloadSection, "downloadRate") }
                                SwirlText { id: downloadRateText; text: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.downloadRate) + "/s" : "—"; font.pixelSize: Theme.fontSize(25); font.weight: Font.DemiBold; color: Theme.text }
                            }
                        }
                        SwirlDailyTrafficChart { id: trafficChart; objectName: "activityTrafficChart"; Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: Theme.dp(65); proxyOnly: page.trafficKind === 1 }
                        RowLayout {
                            id: totalSection; objectName: "activityTotal"
                            readonly property Item motionTitle: totalTrafficText
                            readonly property Item motionSurface: totalSection
                            Layout.fillWidth: true
                            SectionTitle { caption: qsTr("累计"); onNavigate: page.goTraffic(totalSection, "totalTraffic") }
                            SwirlText { id: totalTrafficText; Layout.fillWidth: true; text: page.bytes(page.totals.total, page.totals.sampled); color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; elide: Text.ElideRight }
                            SwirlSegmentedControl { objectName: "activityPeriodFilter"; Layout.preferredWidth: Theme.dp(112); Layout.preferredHeight: Theme.dp(28); options: [qsTr("今日"), qsTr("本月")]; currentIndex: page.period; onActivated: index => page.period = index }
                        }
                    }
                }
                ColumnLayout {
                    id: diagnosticCard; objectName: "internetDiagnosticCard"
                    Layout.fillWidth: true; Layout.preferredWidth: 2; Layout.minimumWidth: 0; Layout.preferredHeight: Theme.dp(268); spacing: Theme.dp(10)
                    RowLayout {
                        Layout.fillWidth: true
                        SwirlText { text: qsTr("网络诊断"); color: Theme.text; font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold; Layout.fillWidth: true }
                        SwirlIconButton { objectName: "networkDiagnosticButton"; iconName: "refresh"; quiet: true; enabled: page.telemetry.measurementState !== "正在测量"; Accessible.name: qsTr("刷新 INTERNET 耗时"); onClicked: page.telemetry.measureNetwork() }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(6)
                        SwirlText { text: page.internetMeasured ? String(parseInt(page.internetLatency)) : "—"; color: Theme.text; font.pixelSize: Theme.fontSize(42); font.weight: Font.DemiBold }
                        SwirlText { Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: Theme.dp(6); text: page.internetMeasured ? "ms" : ""; color: Theme.muted; font.pixelSize: Theme.fontSize(16) }
                        Item { Layout.fillWidth: true }
                        SwirlFlow { Layout.preferredWidth: Theme.dp(42); Layout.preferredHeight: Theme.dp(18); phase: page.telemetry.measurementState === "正在测量" ? "pending" : page.internetMeasured ? "succeeded" : page.telemetry.measurementState === "测量完成" ? "failed" : "idle" }
                    }
                    SwirlText { text: page.internetMeasured ? qsTr("INTERNET · HTTPS 完整请求") : page.telemetry.measurementState || qsTr("尚未检测"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.separator }
                    Column {
                        Layout.fillWidth: true
                        StatRow { caption: qsTr("默认网关"); value: page.latency("router") }
                        StatRow { caption: qsTr("DNS 查询"); value: page.latency("dns") }
                        StatRow { caption: qsTr("代理请求"); value: page.connected ? page.latency("proxy") : qsTr("未连接") }
                    }
                    Item { Layout.fillHeight: true }
                    SwirlButton { id: diagnosticShortcut; objectName: "networkDiagnosticDetails"; text: qsTr("诊断详情"); quiet: true; onClicked: SwirlMotion.navigateFrom(diagnosticShortcut, "toolbox", "") }
                }
            }
            GridLayout {
                Layout.fillWidth: true; columns: page.wide ? 2 : 1; columnSpacing: Theme.dp(28); rowSpacing: Theme.dp(20)
                ColumnLayout {
                    Layout.fillWidth: true; Layout.preferredWidth: 3; Layout.minimumWidth: 0; spacing: Theme.dp(8)
                    RowLayout {
                        Layout.fillWidth: true
                        SwirlText { text: qsTr("流量来源"); font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; color: Theme.text; Layout.fillWidth: true }
                        SwirlSegmentedControl { id: sourceFilter; objectName: "activitySourceFilter"; Layout.preferredWidth: Theme.dp(230); Layout.preferredHeight: Theme.dp(28); options: [qsTr("进程与设备"), qsTr("域名"), qsTr("策略")]; currentIndex: page.rankingKind; onActivated: index => page.rankingKind = index }
                    }
                    Repeater {
                        model: page.ranks
                        SwirlMotionButton {
                            id: rank; required property var modelData
                            Layout.fillWidth: true; implicitHeight: Theme.dp(35); padding: Theme.dp(5); hoverEnabled: true
                            background: Rectangle { color: rank.down ? Theme.pressed : rank.hovered ? Theme.hover : "transparent"; radius: Theme.dp(6); border.width: rank.visualFocus ? Theme.borderWidth : 0; border.color: Theme.accent }
                            contentItem: RowLayout {
                                spacing: Theme.dp(9)
                                SwirlIcon { name: rank.modelData.kind === "apps" ? "terminal" : rank.modelData.kind === "devices" ? "router" : rank.modelData.kind === "domains" ? "globe" : "route"; size: Theme.dp(17); color: Theme.muted }
                                SwirlText { text: rank.modelData.name; Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                                SwirlText { text: rank.modelData.value; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                SwirlIcon { name: "chevron-right"; size: Theme.dp(12); color: Theme.muted }
                            }
                            Accessible.name: qsTr("%1详情").arg(modelData.name)
                            onClicked: { SwirlMotion.noteTrigger(rank); page.openRank(modelData) }
                        }
                    }
                    SwirlText { visible: page.ranks.length === 0; text: page.emptyRanksText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(74); verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap }
                    RowLayout {
                        Layout.fillWidth: true
                        SwirlText { text: qsTr("直连 %1").arg(page.distribution[1] && page.totals.sampled ? page.distribution[1].value : "—"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true }
                        SwirlText { text: qsTr("代理 %1").arg(page.distribution[0] && page.totals.sampled ? page.distribution[0].value : "—"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                    }
                }
                Column {
                    id: connectionsSection; objectName: "activityConnections"
                    readonly property Item motionTitle: connectionCountRow.valueItem
                    readonly property Item motionSurface: connectionsSection
                    Layout.fillWidth: true; Layout.preferredWidth: 2; Layout.minimumWidth: 0; spacing: Theme.dp(2)
                    SectionTitle { caption: qsTr("活动连接"); onNavigate: SwirlMotion.navigateFrom(connectionsSection, "connections", "activeConnections") }
                    StatRow { id: connectionCountRow; caption: qsTr("连接数量"); value: page.telemetry.connectionsSampled ? String(page.telemetry.activeConnections) : "—" }
                    StatRow { caption: qsTr("进程"); value: page.telemetry.connectionsSampled ? String(page.telemetry.activeProcesses) : "—" }
                    StatRow { caption: qsTr("设备"); value: page.telemetry.connectionsSampled ? String(page.activeDeviceCount) : "—" }
                    StatRow { caption: qsTr("DHCP 设备"); value: gatewayProvider.running ? String(page.dhcpDeviceCount) : "—" }
                }
            }
        }
    }
}
