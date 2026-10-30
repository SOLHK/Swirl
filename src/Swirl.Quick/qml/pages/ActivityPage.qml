pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    required property var engineController
    required property var systemProvider
    readonly property var telemetry: engineController.telemetry
    readonly property bool wide: scroll.width - 2 * Theme.pagePadding >= Theme.dp(480)
    readonly property bool compact: scroll.width - 2 * Theme.pagePadding < Theme.dp(620)
    property int period: 0
    property int trafficKind: 0
    property int rankingKind: 0
    property var network: systemProvider.currentNetwork()
    property var totals: ({sampled: false})
    property var distribution: []
    property var ranks: []
    property bool proxyRanksAvailable: false
    property bool snapshotDirty: true
    property bool errorDetailsRequested: false
    property string errorDetailsText: ""
    readonly property bool detailOpen: details.activeDetail
    readonly property bool overviewActive: visible && !detailOpen
    onOverviewActiveChanged: if (overviewActive) {
        snapshotDirty = true
        refreshSnapshot()
        network = systemProvider.currentNetwork()
    }
    property var visitedDetails: ({})
    property var pendingSourceRow: null
    function dismissDetail() { return details.closeDetail() }
    function openCard(card, key, title) {
        if (details.activeDetail) return
        const next = Object.assign({}, visitedDetails)
        next[key] = true
        visitedDetails = next
        details.openFrom(card, key, title)
    }
    onWidthChanged: Qt.callLater(details.updateOrigin)
    onHeightChanged: Qt.callLater(details.updateOrigin)
    onVisibleChanged: {
        if (visible) refreshSnapshot()
        else if (details.activeDetail) { details.opened = false; details.reset() }
    }
    readonly property bool connected: engineController.processAlive && engineController.apiHealthy
    readonly property string internetLatency: telemetry.latencies.internet || ""
    readonly property bool internetMeasured: /^\d+ ms$/.test(internetLatency)
    readonly property string emptyRanksText: trafficKind === 1 && !proxyRanksAvailable
        ? "此时段的代理来源尚无可核验的分类记录" : "暂无已采集的流量来源"
    readonly property int activeDeviceCount: telemetry.activeDevices
    readonly property int dhcpDeviceCount: gatewayProvider.devices.filter(row => row.status === "租用中").length

    function refreshSnapshot() {
        if (!overviewActive) return
        const range = period === 0 ? 0 : 3
        totals = telemetry.summary(range)
        distribution = telemetry.distribution(range)
        proxyRanksAvailable = telemetry.proxyRankingAvailable(range)
        let rows = []
        if (trafficKind === 0 || proxyRanksAvailable) {
            const proxyOnly = trafficKind === 1
            if (rankingKind === 0) rows = telemetry.ranking("apps", range, 8, proxyOnly)
                .concat(telemetry.ranking("devices", range, 8, proxyOnly))
            else rows = telemetry.ranking(rankingKind === 1 ? "domains" : "nodes", range, 8, proxyOnly)
            rows.sort((a, b) => b.total - a.total)
            rows = rows.slice(0, 8)
        }
        if (JSON.stringify(rows) !== JSON.stringify(ranks)) ranks = rows
        snapshotDirty = false
    }
    function bytes(value, known) { return known ? telemetry.formatBytes(value) : "—" }
    function sourceName(row) {
        if (row.kind !== "nodes") return row.name
        if (row.name === "SWIRL_V2_DIRECT" || row.name === "DIRECT") return qsTr("直连")
        if (row.name === "SWIRL_V2_REJECT" || row.name === "REJECT") return qsTr("阻止")
        const target = engineController.policyTargetOptions.find(option => option.id === row.name)
        return target ? target.name : row.name
    }
    function latency(key) {
        const value = telemetry.latencies[key] || ""
        return value || qsTr("尚未测量")
    }
    readonly property bool diagnosticWarning: ["internet", "router", "dns", "proxy"].some(key => {
        const value = telemetry.latencies[key] || ""
        return value.length > 0 && !/^\d+ ms$/.test(value)
            && ["未连接", "尚未测量", "尚未检测", "未支持", "测量中", "正在测量", "节点检测进行中"].indexOf(value) < 0
    })
    function goTraffic(item, key) {
        openCard(trafficCard, "traffic", qsTr("传输"))
    }
    function openRank(row) {
        pendingSourceRow = row
        openCard(sourcesCard, "sources", qsTr("流量来源"))
        if (sourcesDetail.status === Loader.Ready) {
            sourcesDetail.item.selectSource(row)
            pendingSourceRow = null
        }
    }
    function scrollToBottom() { scroll.contentY = Math.max(0, scroll.contentHeight - scroll.height) }
    onPeriodChanged: { snapshotDirty = true; refreshSnapshot() }
    onTrafficKindChanged: { snapshotDirty = true; refreshSnapshot() }
    onRankingKindChanged: { snapshotDirty = true; refreshSnapshot() }
    Component.onCompleted: refreshSnapshot()
    Connections { target: page.telemetry; function onChanged() { page.snapshotDirty = true } }
    Timer { interval: 300; running: page.overviewActive && page.snapshotDirty; repeat: true; onTriggered: page.refreshSnapshot() }
    Timer { interval: 10000; running: page.overviewActive; repeat: true; onTriggered: page.network = page.systemProvider.currentNetwork() }

    readonly property bool proxyOwned: engineController.systemProxy.owned && engineController.systemProxy.enabled && engineController.processAlive
    readonly property string proxyError: engineController.systemProxy.stateReadError || engineController.systemProxy.error || engineController.routingError || engineController.policyError || (engineController.errorCode !== "None" ? engineController.error : "")
    readonly property string proxyPhase: engineController.systemProxyBusy || engineController.systemProxyStopping ? "pending" : proxyError.length ? "failed" : proxyOwned ? "succeeded" : "idle"
    readonly property string proxySummary: engineController.systemProxyStopping ? qsTr("正在恢复系统设置") : engineController.systemProxyBusy ? qsTr("正在开启代理") : proxyOwned ? qsTr("系统代理运行中") : engineController.processAlive ? qsTr("内核运行中，系统代理未接管") : qsTr("代理未开启")
    readonly property string runtimeLabel: proxyPhase === "pending" ? qsTr("切换中") : proxyError.length ? qsTr("需检查") : connected ? qsTr("运行中") : engineController.processAlive ? qsTr("等待内核") : qsTr("未启动")
    readonly property bool runtimeHealthy: connected && proxyPhase !== "pending" && !proxyError.length
    readonly property var defaultTarget: ((engineController.policyDocument || {}).default_policy || {}).target || ({})
    readonly property var defaultNode: defaultTarget.kind === "node"
        ? engineController.nodeCatalog.find(node => node.id === defaultTarget.id) || ({}) : ({})
    readonly property string nodeRegionCode: defaultNode.regionCode && defaultNode.regionCode !== "unknown" ? defaultNode.regionCode : ""
    readonly property string nodeRegionDetail: nodeRegionCode.length
        ? qsTr("节点标注地区：%1；来自节点名称，并非出口 IP 定位。").arg(defaultNode.regionName)
        : defaultTarget.kind === "group" ? qsTr("默认出口使用策略组")
        : defaultTarget.kind === "direct" ? qsTr("默认出口为直连") : qsTr("节点未标注地区")
    readonly property string defaultTargetName: {
        const target = defaultTarget
        if (target.kind === "direct") return "DIRECT"
        const entry = engineController.policyTargetOptions.find(option => option.kind === target.kind && option.id === target.id)
        return entry ? entry.name : qsTr("尚未分配")
    }

    component Fact: RowLayout {
        id: fact
        property string caption: ""
        property string value: "—"
        Layout.fillWidth: false; Layout.minimumWidth: 0; spacing: Theme.dp(5)
        SwirlText { text: fact.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
        SwirlText {
            id: factValue
            objectName: fact.objectName + "Value"
            text: fact.value; textFormat: Text.PlainText; tabularFigures: true; color: Theme.text
            font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium
            Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight
        }
        HoverHandler { id: factHover }
        SwirlToolTip { parent: fact; visible: factHover.hovered && factValue.truncated; text: fact.value }
    }
    component PolicyFact: Item {
        id: policySlot
        Layout.fillWidth: true; Layout.minimumWidth: Theme.dp(80); Layout.preferredWidth: Theme.dp(220)
        implicitHeight: Theme.dp(16)
        SwirlMotionButton {
            id: policy
            readonly property Item motionTitle: policyCaption
            readonly property Item motionSurface: policy
            objectName: "activityPolicyShortcut"
            x: -Theme.dp(8); y: (policySlot.height - height) / 2 + Theme.dp(2)
            width: policySlot.width + Theme.dp(16); height: Theme.dp(28)
            padding: 0; leftPadding: Theme.dp(8); rightPadding: Theme.dp(8); topPadding: Theme.dp(4); bottomPadding: Theme.dp(8)
            hoverEnabled: true; focusPolicy: Qt.StrongFocus
            Accessible.name: qsTr("策略：%1").arg(page.defaultTargetName)
            Accessible.description: qsTr("打开策略页面。%1").arg(page.nodeRegionDetail)
            onClicked: SwirlMotion.navigateFrom(policy, "policies", "")
            background: SwirlControlSurface { objectName: "activityPolicySurface"; radius: height / 2; quiet: true; hovered: policy.hovered; pressed: policy.down; focused: policy.visualFocus; controlEnabled: policy.enabled }
            SwirlArcMotion {
                id: policyCurve
                objectName: "activityPolicyMotion"
                targetX: policy.hovered || policy.visualFocus ? Theme.dp(4) : 0
                bend: Theme.dp(3); duration: SwirlMotion.hoverDuration; motionEnabled: page.visible
            }
            contentItem: RowLayout {
                id: policyContents
                spacing: Theme.dp(6)
                SwirlText { id: policyCaption; text: qsTr("策略"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
                SwirlText { id: policyValue; objectName: "activityPolicyValue"; text: page.defaultTargetName; textFormat: Text.PlainText; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight }
                Item {
                    Layout.preferredWidth: Theme.dp(12); Layout.fillHeight: true
                    // Center anchors also use the target item's rounding policy.
                    anchors.alignWhenCentered: false
                    SwirlIcon { objectName: "activityPolicyArrow"; name: "chevron-right"; size: Theme.dp(12); anchors.centerIn: parent; anchors.alignWhenCentered: false; color: policy.hovered || policy.visualFocus ? Theme.accent : Theme.muted; transform: Translate { x: policyCurve.position.x; y: policyCurve.position.y } }
                }
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            SwirlToolTip { parent: policy; width: Math.min(implicitWidth, Theme.dp(420), page.width - Theme.dp(32)); visible: policy.hovered || policy.visualFocus; text: qsTr("%1 · 打开策略\n%2").arg(page.defaultTargetName).arg(page.nodeRegionDetail) }
        }
    }
    component StatRow: RowLayout {
        id: stat
        property string caption: ""
        property string value: "—"
        readonly property Item valueItem: valueText
        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredHeight: implicitHeight
        implicitHeight: Theme.dp(26); spacing: Theme.dp(8)
        SwirlText { text: stat.caption; color: Theme.artworkText; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight }
        SwirlText { id: valueText; text: stat.value; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(13); font.weight: Font.Medium; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight }
    }
    component SectionTitle: SwirlMotionButton {
        id: titleControl
        property string caption: ""
        readonly property Item motionTitle: titleCaption
        signal navigate()
        implicitHeight: Theme.controlHeight; hoverEnabled: true
        leftPadding: Theme.dp(8); rightPadding: Theme.dp(12); topPadding: Theme.dp(4); bottomPadding: Theme.dp(4)
        Layout.leftMargin: -leftPadding
        baselineOffset: titleContents.y + titleCaption.y + titleCaption.baselineOffset
        background: SwirlControlSurface { quiet: true; hovered: titleControl.hovered; pressed: titleControl.down; focused: titleControl.visualFocus; controlEnabled: titleControl.enabled }
        contentItem: RowLayout {
            id: titleContents
            spacing: Theme.dp(8)
            SwirlText { id: titleCaption; text: titleControl.caption; color: Theme.text; font.pixelSize: Theme.fontSize(18); font.weight: Font.DemiBold }
            SwirlIcon { name: "chevron-right"; size: Theme.dp(14); color: Theme.muted }
        }
        Accessible.name: qsTr("%1详情").arg(caption)
        onClicked: navigate()
    }

    Flickable {
        id: scroll; objectName: "activityScroll"
        anchors.fill: parent; anchors.topMargin: Theme.dp(52)
        opacity: 1 - details.progress
        visible: details.progress < 1
        enabled: !details.activeDetail
        contentWidth: width; contentHeight: content.height + Theme.dp(16)
        interactive: contentHeight > height + 1
        flickableDirection: Flickable.VerticalFlick; boundsBehavior: Flickable.StopAtBounds
        clip: true; ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            id: content
            x: Theme.pagePadding; width: scroll.width - 2 * Theme.pagePadding
            height: Math.max(scroll.height - Theme.dp(16), Layout.minimumHeight); spacing: Theme.dp(16)
            SwirlGlassPanel {
                id: statusCard
                objectName: "activityStatusCard"
                Layout.fillWidth: true; Layout.minimumHeight: statusBody.implicitHeight + Theme.dp(24); Layout.preferredHeight: Layout.minimumHeight
                cornerRadius: Theme.cardRadius; color: Theme.surface
                Item {
                    id: statusEmblem
                    objectName: "activityStatusEmblem"
                    x: statusCard.width - width - Theme.dp(18); y: (statusCard.height - height) / 2
                    width: Theme.dp(128); height: Theme.dp(88)
                    Accessible.ignored: true
                }
                SwirlCloudKnotWeave {
                    objectName: "activityCloudKnotWeave"
                    anchors.fill: parent
                    active: page.proxyOwned && !page.engineController.systemProxyStopping
                    knotRect: Qt.rect(statusEmblem.x, statusEmblem.y, statusEmblem.width, statusEmblem.height)
                }
                ColumnLayout {
                    id: statusBody; anchors.fill: parent; anchors.margins: Theme.dp(12); anchors.leftMargin: Theme.dp(18); anchors.rightMargin: statusEmblem.width + Theme.dp(34); spacing: Theme.dp(5)
                    RowLayout {
                        id: statusHeader
                        objectName: "activityStatusHeader"
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.maximumWidth: statusBody.width
                        Layout.minimumHeight: Theme.dp(32); Layout.preferredHeight: Theme.dp(32); Layout.maximumHeight: Theme.dp(32); spacing: Theme.dp(10)
                        Rectangle {
                            id: runtimeCapsule
                            objectName: "activityRuntimeCapsule"
                            implicitWidth: runtimeContents.implicitWidth + Theme.dp(18)
                            Layout.preferredWidth: implicitWidth; Layout.minimumWidth: implicitWidth; Layout.preferredHeight: Theme.dp(24)
                            radius: height / 2; antialiasing: true
                            color: page.runtimeHealthy ? Theme.successSurface : page.proxyError.length ? Theme.warningSurface : Theme.raised
                            RowLayout {
                                id: runtimeContents; anchors.centerIn: parent; spacing: Theme.dp(6)
                                Rectangle { Layout.preferredWidth: Theme.dp(5); Layout.preferredHeight: Theme.dp(5); radius: width / 2; color: page.runtimeHealthy ? Theme.statusGreen : page.proxyError.length ? Theme.warningText : Theme.muted }
                                SwirlText { text: page.runtimeLabel; textRole: "smallLabel"; font.pixelSize: Theme.fontSize(11); font.weight: Font.Medium; color: page.runtimeHealthy ? Theme.successText : page.proxyError.length ? Theme.warningText : Theme.muted }
                            }
                            Accessible.role: Accessible.StaticText; Accessible.name: page.runtimeLabel; Accessible.description: page.proxySummary
                            HoverHandler { id: runtimeHover }
                            SwirlToolTip { parent: runtimeCapsule; visible: runtimeHover.hovered; text: page.proxySummary }
                        }
                        Item { Layout.fillWidth: true; Layout.minimumWidth: 0 }
                        SwirlIconButton {
                            id: proxyErrorDetails
                            objectName: "activityProxyErrorDetails"
                            visible: page.proxyError.length > 0
                            Layout.preferredWidth: Theme.dp(28); Layout.preferredHeight: Theme.dp(28)
                            iconName: "warning"; iconColor: Theme.red; quiet: true
                            tooltip: qsTr("查看代理错误详情"); Accessible.description: page.proxyError
                            onClicked: { page.errorDetailsText = page.proxyError; page.errorDetailsRequested = true }
                        }
                        OutboundModeControl { id: outboundMode; engineController: page.engineController; Layout.minimumWidth: implicitWidth }
                    }
                    RowLayout {
                        objectName: "activityExitIp"
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.maximumWidth: statusBody.width
                        Layout.minimumHeight: Theme.dp(26); Layout.preferredHeight: Theme.dp(26); Layout.maximumHeight: Theme.dp(26); spacing: Theme.dp(8)
                        SwirlText { text: qsTr("出口 IP"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
                        SwirlText {
                            id: exitIp
                            objectName: "activityExitIpValue"
                            text: page.telemetry.externalIp || "—"; textFormat: Text.PlainText; tabularFigures: true
                            font.pixelSize: Theme.fontSize(page.compact ? 18 : 20); font.weight: Font.DemiBold; color: Theme.text
                            Layout.preferredWidth: implicitWidth; Layout.minimumWidth: Theme.dp(page.compact ? 150 : 172); Layout.alignment: Qt.AlignBaseline
                            elide: Text.ElideRight
                            HoverHandler { id: exitIpHover }
                            SwirlToolTip { parent: exitIp; visible: exitIpHover.hovered && exitIp.truncated; text: exitIp.text }
                        }
                        SwirlText {
                            objectName: "activityNodeRegionTag"
                            visible: page.nodeRegionCode.length > 0; text: qsTr("节点 %1").arg(page.nodeRegionCode)
                            color: Theme.muted; font.pixelSize: Theme.fontSize(11); Layout.alignment: Qt.AlignBaseline
                            Accessible.name: page.nodeRegionDetail
                        }
                        Item { Layout.fillWidth: true }
                    }
                    RowLayout {
                        objectName: "activityStatusFooter"
                        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.maximumWidth: statusBody.width
                        Layout.minimumHeight: Theme.dp(16); Layout.preferredHeight: Theme.dp(16); Layout.maximumHeight: Theme.dp(16); spacing: Theme.dp(12)
                        Fact { objectName: "activityNetworkFact"; caption: qsTr("网络"); value: page.network.type || qsTr("未连接"); Layout.preferredWidth: Theme.dp(72) }
                        Fact { objectName: "activityProfileFact"; caption: qsTr("配置"); value: extensionsProvider.profileName || "—"; Layout.preferredWidth: Theme.dp(96) }
                        PolicyFact {}
                    }
                }
            }
            GridLayout {
                Layout.fillWidth: true; Layout.fillHeight: true
                columns: page.wide ? 2 : 1; columnSpacing: Theme.dp(20); rowSpacing: Theme.dp(16)
                SwirlActivityCard {
                    id: sourcesCard; objectName: "activitySourcesCard"
                    title: qsTr("流量来源"); titleItem: sourcesHeading.motionTitle
                    opacity: details.activeDetail && details.sourceCard === sourcesCard ? 0 : 1
                    onActivated: page.openCard(sourcesCard, "sources", title)
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 3; Layout.minimumWidth: 0
                    Layout.minimumHeight: Theme.dp(202); Layout.preferredHeight: Theme.dp(258)
                    cornerRadius: Theme.cardRadius
                    ColumnLayout {
                        id: sourcesSection; objectName: "activitySourceSection"
                        anchors.fill: parent; anchors.margins: Theme.dp(14); spacing: Theme.dp(8)
                        GridLayout {
                            z: 1
                            Layout.fillWidth: true; columns: page.compact ? 1 : 2; columnSpacing: Theme.dp(8); rowSpacing: Theme.dp(6)
                            Item {
                                Layout.fillWidth: true; Layout.minimumWidth: sourcesHeading.implicitWidth
                                Layout.preferredHeight: sourcesHeading.implicitHeight
                                SectionTitle { id: sourcesHeading; objectName: "activitySourcesDetails"; caption: qsTr("流量来源"); x: -leftPadding; height: parent.height; onNavigate: page.openCard(sourcesCard, "sources", caption) }
                            }
                            SwirlSegmentedControl { id: sourceFilter; objectName: "activitySourceFilter"; Layout.alignment: Qt.AlignRight; Layout.preferredWidth: Theme.dp(230); Layout.preferredHeight: Theme.dp(28); options: [qsTr("进程与设备"), qsTr("域名"), qsTr("策略")]; currentIndex: page.rankingKind; onActivated: index => page.rankingKind = index }
                        }
                        Flickable {
                            id: rankViewport; objectName: "activitySourceList"
                            visible: page.ranks.length > 0
                            Layout.fillWidth: true; Layout.minimumWidth: 0
                            Layout.fillHeight: true; Layout.minimumHeight: Theme.dp(96)
                            contentWidth: width; contentHeight: rankRows.implicitHeight
                            interactive: contentHeight > height + 1; clip: interactive
                            boundsBehavior: Flickable.StopAtBounds; flickableDirection: Flickable.VerticalFlick
                            ScrollBar.vertical: SwirlScrollBar {}
                            ColumnLayout {
                                id: rankRows
                                width: rankViewport.width - (rankViewport.interactive ? Theme.dp(8) : 0); spacing: Theme.dp(2)
                                Repeater {
                                    model: page.ranks
                                    SwirlMotionButton {
                                        id: rank; required property var modelData; required property int index
                                        objectName: "activitySourceRow-" + index
                                        readonly property string displayName: page.sourceName(modelData)
                                        Layout.fillWidth: true; Layout.minimumWidth: 0; implicitHeight: Theme.dp(34); padding: Theme.dp(4); hoverEnabled: true
                                        background: SwirlControlSurface { quiet: true; hovered: rank.hovered; pressed: rank.down; focused: rank.visualFocus; controlEnabled: rank.enabled }
                                        contentItem: RowLayout {
                                            spacing: Theme.dp(9)
                                            SwirlIcon { name: rank.modelData.kind === "apps" ? "terminal" : rank.modelData.kind === "devices" ? "router" : rank.modelData.kind === "domains" ? "globe" : "route"; size: Theme.dp(17); color: Theme.artworkText }
                                            SwirlText { text: rank.displayName; tabularFigures: true; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                                            SwirlText { text: rank.modelData.value; tabularFigures: true; Layout.alignment: Qt.AlignBaseline; color: Theme.artworkText; font.pixelSize: Theme.fontSize(12) }
                                            SwirlIcon { name: "chevron-right"; size: Theme.dp(12); color: Theme.artworkText }
                                        }
                                        Accessible.name: qsTr("%1，%2，查看详情").arg(displayName).arg(modelData.value)
                                        SwirlToolTip { parent: rank; width: Math.min(implicitWidth, Theme.dp(420)); visible: rank.hovered || rank.visualFocus; text: rank.displayName + " · " + rank.modelData.value + (rank.modelData.upload ? qsTr("\n上传 %1 · 下载 %2").arg(rank.modelData.upload).arg(rank.modelData.download) : "") }
                                        onClicked: { SwirlMotion.noteTrigger(rank); page.openRank(modelData) }
                                    }
                                }
                            }
                        }
                        SwirlText { visible: page.ranks.length === 0; text: page.emptyRanksText; color: Theme.artworkText; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: Theme.dp(96); verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap }
                        RowLayout {
                            Layout.fillWidth: true
                            SwirlText { text: qsTr("直连 %1").arg(page.distribution[1] && page.totals.sampled ? page.distribution[1].value : "—"); tabularFigures: true; Layout.alignment: Qt.AlignBaseline; color: Theme.artworkText; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true }
                            SwirlText { text: qsTr("代理 %1").arg(page.distribution[0] && page.totals.sampled ? page.distribution[0].value : "—"); tabularFigures: true; Layout.alignment: Qt.AlignBaseline; color: Theme.artworkText; font.pixelSize: Theme.fontSize(12) }
                        }
                    }
                }
                SwirlActivityCard {
                    id: diagnosticSurface; objectName: "activityDiagnosticCard"
                    title: qsTr("网络诊断"); titleItem: diagnosticShortcut.motionTitle
                    opacity: details.activeDetail && details.sourceCard === diagnosticSurface ? 0 : 1
                    onActivated: page.openCard(diagnosticSurface, "diagnostics", title)
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 2; Layout.minimumWidth: 0
                    Layout.minimumHeight: Theme.dp(202); Layout.preferredHeight: Theme.dp(258)
                ColumnLayout {
                    id: diagnosticCard; objectName: "internetDiagnosticCard"
                    anchors.fill: parent; anchors.margins: Theme.dp(16); spacing: Theme.dp(6)
                    RowLayout {
                        Layout.fillWidth: true
                        SectionTitle { id: diagnosticShortcut; objectName: "networkDiagnosticDetails"; caption: qsTr("网络诊断"); onNavigate: page.openCard(diagnosticSurface, "diagnostics", caption) }
                        Item { Layout.fillWidth: true }
                        SwirlIconButton { objectName: "networkDiagnosticButton"; Layout.preferredWidth: Theme.dp(30); Layout.preferredHeight: Theme.dp(30); iconName: "refresh"; quiet: true; enabled: page.telemetry.measurementState !== "正在测量"; Accessible.name: qsTr("刷新 INTERNET 耗时"); onClicked: page.telemetry.measureNetwork() }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(6)
                        SwirlText { objectName: "activityInternetValue"; Layout.alignment: Qt.AlignBaseline; text: page.internetMeasured ? String(parseInt(page.internetLatency)) : "—"; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(42); font.weight: Font.DemiBold }
                        SwirlText { objectName: "activityInternetUnit"; Layout.alignment: Qt.AlignBaseline; text: page.internetMeasured ? "ms" : ""; color: Theme.muted; font.pixelSize: Theme.fontSize(16) }
                        Item { Layout.fillWidth: true }
                        SwirlFlow { objectName: "diagnosticProxyWing"; Layout.preferredWidth: Theme.dp(42); Layout.preferredHeight: Theme.dp(18); phase: page.proxyPhase; proxyWing: true }
                    }
                    SwirlText { objectName: "activityInternetCaption"; text: page.diagnosticWarning ? qsTr("诊断需检查 · 查看详情") : page.internetMeasured ? qsTr("INTERNET · HTTPS 完整请求") : page.telemetry.measurementState || qsTr("尚未检测"); color: page.diagnosticWarning ? Theme.warningText : Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap }
                    Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.separator }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 0
                        StatRow { caption: qsTr("默认网关"); value: page.latency("router") }
                        StatRow { caption: qsTr("DNS 查询"); value: page.latency("dns") }
                        StatRow { caption: qsTr("代理请求"); value: page.connected ? page.latency("proxy") : qsTr("未连接") }
                    }
                    Item { Layout.fillHeight: true }
                }
                }
                SwirlActivityCard {
                    id: trafficCard; objectName: "activityTrafficCard"
                    title: qsTr("传输"); titleItem: trafficHeading.motionTitle
                    opacity: details.activeDetail && details.sourceCard === trafficCard ? 0 : 1
                    onActivated: page.openCard(trafficCard, "traffic", title)
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 3; Layout.minimumWidth: 0
                    Layout.minimumHeight: trafficBody.implicitHeight + Theme.dp(24); Layout.preferredHeight: Layout.minimumHeight
                    cornerRadius: Theme.cardRadius
                    ColumnLayout {
                        id: trafficBody
                        anchors.fill: parent; anchors.margins: Theme.dp(12); spacing: Theme.dp(4)
                        RowLayout {
                            Layout.fillWidth: true
                            SectionTitle { id: trafficHeading; objectName: "activityTrafficDetails"; caption: qsTr("传输"); Layout.fillWidth: false; onNavigate: page.openCard(trafficCard, "traffic", caption) }
                            Item { Layout.fillWidth: true }
                            SwirlSegmentedControl { id: trafficFilter; objectName: "activityTrafficFilter"; Layout.preferredWidth: Theme.dp(138); Layout.preferredHeight: Theme.dp(28); options: [qsTr("全部"), qsTr("仅代理")]; currentIndex: page.trafficKind; onActivated: index => page.trafficKind = index }
                        }
                        RowLayout {
                            id: uploadSection; objectName: "activityUpload"
                            readonly property Item motionTitle: uploadRateText
                            readonly property Item motionSurface: uploadSection
                            Layout.fillWidth: true; spacing: Theme.dp(16)
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(3)
                                SectionTitle { caption: qsTr("上传"); onNavigate: page.goTraffic(uploadSection, "uploadRate") }
                                SwirlText { id: uploadRateText; objectName: "activityUploadRate"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.uploadRate) + "/s" : "—"; tabularFigures: true; font.pixelSize: Theme.fontSize(24); font.weight: Font.DemiBold; color: Theme.text; elide: Text.ElideRight }
                            }
                            ColumnLayout {
                                id: downloadSection
                                readonly property Item motionTitle: downloadRateText
                                readonly property Item motionSurface: downloadSection
                                Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(3)
                                SectionTitle { caption: qsTr("下载"); onNavigate: page.goTraffic(downloadSection, "downloadRate") }
                                SwirlText { id: downloadRateText; objectName: "activityDownloadRate"; Layout.fillWidth: true; Layout.minimumWidth: 0; text: page.telemetry.sampled ? page.telemetry.formatBytes(page.telemetry.downloadRate) + "/s" : "—"; tabularFigures: true; font.pixelSize: Theme.fontSize(24); font.weight: Font.DemiBold; color: Theme.text; elide: Text.ElideRight }
                            }
                        }
                        SwirlDailyTrafficChart { id: trafficChart; objectName: "activityTrafficChart"; Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(52); Layout.minimumHeight: Theme.dp(52); proxyOnly: page.trafficKind === 1 }
                        RowLayout {
                            id: totalSection; objectName: "activityTotal"
                            readonly property Item motionTitle: totalTrafficText
                            readonly property Item motionSurface: totalSection
                            Layout.fillWidth: true
                            SectionTitle { Layout.alignment: Qt.AlignBaseline; caption: qsTr("累计"); onNavigate: page.goTraffic(totalSection, "totalTraffic") }
                            SwirlText { id: totalTrafficText; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; text: page.bytes(page.totals.total, page.totals.sampled); tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(20); font.weight: Font.DemiBold; elide: Text.ElideRight }
                            SwirlSegmentedControl { objectName: "activityPeriodFilter"; Layout.preferredWidth: Theme.dp(112); Layout.preferredHeight: Theme.dp(28); options: [qsTr("今日"), qsTr("本月")]; currentIndex: page.period; onActivated: index => page.period = index }
                        }
                    }
                }
                SwirlActivityCard {
                    id: connectionsCard; objectName: "activityConnectionsCard"
                    title: qsTr("活动连接"); titleItem: connectionsHeading.motionTitle
                    opacity: details.activeDetail && details.sourceCard === connectionsCard ? 0 : 1
                    onActivated: page.openCard(connectionsCard, "connections", title)
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 2; Layout.minimumWidth: 0
                    Layout.minimumHeight: connectionsSection.implicitHeight + Theme.dp(32)
                ColumnLayout {
                    id: connectionsSection; objectName: "activityConnections"
                    readonly property Item motionTitle: connectionCountValue
                    readonly property Item motionSurface: connectionsSection
                    anchors.fill: parent; anchors.margins: Theme.dp(16); spacing: Theme.dp(2)
                    SectionTitle { id: connectionsHeading; objectName: "activityConnectionsDetails"; caption: qsTr("活动连接"); onNavigate: page.openCard(connectionsCard, "connections", caption) }
                    RowLayout {
                        Layout.fillWidth: true; spacing: Theme.dp(6)
                        SwirlText { id: connectionCountValue; text: page.telemetry.connectionsSampled ? String(page.telemetry.activeConnections) : "—"; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(32); font.weight: Font.DemiBold }
                        SwirlText { text: qsTr("当前连接"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
                        Item { Layout.fillWidth: true }
                    }
                    StatRow { caption: qsTr("进程"); value: page.telemetry.connectionsSampled ? String(page.telemetry.activeProcesses) : "—" }
                    StatRow { caption: qsTr("设备"); value: page.telemetry.connectionsSampled ? String(page.activeDeviceCount) : "—" }
                    StatRow { caption: qsTr("DHCP 设备"); value: gatewayProvider.running ? String(page.dhcpDeviceCount) : "—" }
                }
                }
            }
        }
    }
    ActivityDetailTransition {
        id: details
        anchors.fill: parent
        Loader {
            id: sourcesDetail; anchors.fill: parent
            asynchronous: true
            active: page.visitedDetails.sources === true
            visible: details.detailKey === "sources"
            sourceComponent: ActivitySourcesDetail {
                engineController: page.engineController
                period: page.period === 0 ? 0 : 3
                kindIndex: page.rankingKind === 0 ? 0 : page.rankingKind === 1 ? 2 : 3
                proxyOnly: page.trafficKind === 1
            }
            onLoaded: if (page.pendingSourceRow) { item.selectSource(page.pendingSourceRow); page.pendingSourceRow = null }
        }
        Loader {
            anchors.fill: parent; asynchronous: true; active: page.visitedDetails.connections === true
            visible: details.detailKey === "connections"
            sourceComponent: ConnectionsPage { embedded: true }
        }
        Loader {
            anchors.fill: parent; asynchronous: true; active: page.visitedDetails.traffic === true
            visible: details.detailKey === "traffic"
            sourceComponent: TrafficAnalyticsPage { embedded: true; period: page.period === 0 ? 0 : 3 }
        }
        Loader {
            anchors.fill: parent; asynchronous: true; active: page.visitedDetails.diagnostics === true
            visible: details.detailKey === "diagnostics"
            sourceComponent: ActivityDiagnosticsDetail { engineController: page.engineController; systemProvider: page.systemProvider }
        }
    }
    Loader {
        active: page.errorDetailsRequested
        sourceComponent: SwirlDialog {
            id: errorDialog
            objectName: "activityProxyErrorDialog"
            ownerItem: page; guardChanges: false
            title: qsTr("代理错误详情")
            height: Math.min(Theme.dp(360), parent ? parent.height - Theme.dp(48) : Theme.dp(360))
            Component.onCompleted: open()
            onClosed: page.errorDetailsRequested = false
            contentItem: ColumnLayout {
                spacing: Theme.dp(12)
                ScrollView {
                    id: errorScroll
                    Layout.fillWidth: true; Layout.fillHeight: true
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical: SwirlScrollBar {}
                    SwirlText {
                        width: errorScroll.availableWidth
                        text: page.errorDetailsText; textFormat: Text.PlainText
                        color: Theme.red; font.pixelSize: Theme.fontSize(13); wrapMode: Text.Wrap
                    }
                }
                SwirlButton { Layout.alignment: Qt.AlignRight; text: qsTr("关闭"); onClicked: errorDialog.close() }
            }
        }
    }
}
