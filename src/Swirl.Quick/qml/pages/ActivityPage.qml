pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    objectName: "activityPage"
    required property var engineController
    required property var systemProvider
    property Item ribbonBack: page
    property Item ribbonFront: page
    property Item proxyAnchor: null
    property Item sidebarAnchor: null
    property var wingScene: null
    property bool sceneSettled: true
    property real sceneRevision: 0
    onSceneSettledChanged: if (sceneSettled) Qt.callLater(updateLayoutOrigin)
    readonly property real ribbonTourProgress: overviewActive && statusWeave.release < 1 ? statusWeave.progress : 1
    readonly property real ribbonTourStrength: overviewActive ? 1 - statusWeave.release : 0
    onSceneRevisionChanged: Qt.callLater(updateLayoutOrigin)
    readonly property var telemetry: engineController.telemetry
    readonly property real contentLogicalWidth: content.width
    readonly property real dualColumnMinimumWidth: Theme.dp(736)
    readonly property bool wide: contentLogicalWidth >= dualColumnMinimumWidth
    readonly property real cardInset: Theme.dp(14)
    readonly property real moduleGap: Theme.dp(5)
    readonly property real sourceRowHeight: Theme.dp(32)
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
    property var visitedDetails: ({})
    property var pendingSourceRow: null
    readonly property bool detailOpen: details.activeDetail
    readonly property bool overviewActive: visible && !detailOpen
    readonly property bool connected: engineController.processAlive && engineController.apiHealthy
    readonly property string internetLatency: telemetry.latencies.internet || ""
    readonly property bool internetMeasured: /^\d+ ms$/.test(internetLatency)
    readonly property bool measuring: telemetry.measurementState === "正在测量"
    readonly property string emptyRanksText: trafficKind === 1 && !proxyRanksAvailable ? qsTr("此时段的代理来源尚无可核验的分类记录") : qsTr("暂无已采集的流量来源")
    readonly property int previewRows: Math.max(5, Math.min(7, Math.floor((sourcesCard.height - Theme.dp(150)) / sourceRowHeight)))
    readonly property var visibleRanks: ranks.slice(0, previewRows)
    readonly property bool proxyOwned: engineController.systemProxy.owned && engineController.systemProxy.enabled && engineController.processAlive
    readonly property string proxyError: engineController.systemProxy.stateReadError || engineController.systemProxy.error || engineController.routingError || engineController.policyError || (engineController.errorCode !== "None" ? engineController.error : "")
    readonly property string proxyPhase: engineController.systemProxyBusy || engineController.systemProxyStopping ? "pending" : proxyError.length ? "failed" : proxyOwned ? "succeeded" : "idle"
    readonly property string proxySummary: engineController.systemProxyStopping ? qsTr("正在恢复系统设置") : engineController.systemProxyBusy ? qsTr("正在开启代理") : proxyOwned ? qsTr("系统代理运行中") : engineController.processAlive ? qsTr("内核运行中，系统代理未接管") : qsTr("代理未开启")
    readonly property string runtimeLabel: proxyPhase === "pending" ? qsTr("切换中") : proxyError.length ? qsTr("需检查") : connected ? qsTr("运行中") : engineController.processAlive ? qsTr("等待内核") : qsTr("未启动")
    readonly property bool runtimeHealthy: connected && proxyPhase !== "pending" && !proxyError.length
    readonly property var defaultTarget: ((engineController.policyDocument || {}).default_policy || {}).target || ({})
    readonly property string defaultTargetName: {
        if (defaultTarget.kind === "direct") return qsTr("直连")
        const entry = engineController.policyTargetOptions.find(option => option.kind === defaultTarget.kind && option.id === defaultTarget.id)
        return entry ? entry.name : qsTr("尚未分配")
    }
    readonly property var actualNode: engineController.nodeCatalog.find(node => node.id === engineController.activeNodeId) || ({})
    readonly property string currentNodeName: actualNode.name || (engineController.activeNodeId.length ? qsTr("节点详情未提供") : engineController.processAlive ? qsTr("由规则选择出口") : qsTr("尚未连接"))
    readonly property var diagnosticFailures: ["internet", "router", "dns", "proxy"].map(key => telemetry.latencies[key] || "").filter(value => value.length > 0 && !/^\d+ ms$/.test(value) && ["未连接", "尚未测量", "尚未检测", "未支持", "测量中", "正在测量", "节点检测进行中"].indexOf(value) < 0)
    readonly property bool diagnosticWarning: diagnosticFailures.length > 0
    readonly property string diagnosticSummary: diagnosticWarning ? diagnosticFailures[0] : internetMeasured ? qsTr("HTTPS 完整请求") : telemetry.measurementState || qsTr("尚未检测")

    function dismissDetail() { return details.closeDetail() }
    function openCard(card, key, title) {
        if (details.activeDetail) return
        const next = Object.assign({}, visitedDetails)
        next[key] = true; visitedDetails = next
        details.openFrom(card, key, title)
    }
    function refreshSnapshot() {
        if (!overviewActive) return
        const range = period === 0 ? 0 : 3
        totals = telemetry.summary(range); distribution = telemetry.distribution(range)
        proxyRanksAvailable = telemetry.proxyRankingAvailable(range)
        let rows = []
        if (trafficKind === 0 || proxyRanksAvailable) {
            const proxyOnly = trafficKind === 1
            if (rankingKind === 0) rows = telemetry.ranking("apps", range, 7, proxyOnly).concat(telemetry.ranking("devices", range, 7, proxyOnly))
            else rows = telemetry.ranking(rankingKind === 1 ? "domains" : "nodes", range, 7, proxyOnly)
            rows.sort((a, b) => b.total - a.total); rows = rows.slice(0, 7)
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
    function latency(key) { return telemetry.latencies[key] || qsTr("尚未测量") }
    function openRank(row) {
        if (details.activeDetail) return
        pendingSourceRow = row; openCard(sourcesCard, "sources", qsTr("流量来源"))
        if (sourcesDetail.status === Loader.Ready) { sourcesDetail.item.selectSource(row); pendingSourceRow = null }
    }
    function scrollToBottom() { scroll.contentY = Math.max(0, scroll.contentHeight - scroll.height) }
    function updateLayoutOrigin() {
        topRow.ensurePolished(); bottomRow.ensurePolished(); rightStack.ensurePolished(); narrowColumn.ensurePolished()
        details.updateOrigin()
        statusWeave.updateGeometry()
    }
    function ensureSourceVisible(card) {
        if (!card) return
        updateLayoutOrigin()
        const top = card.mapToItem(scroll.contentItem, 0, 0).y
        const bottom = top + card.height
        let target = scroll.contentY
        if (top < target || card.height > scroll.height) target = top
        else if (bottom > target + scroll.height) target = bottom - scroll.height
        scroll.contentY = Math.max(0, Math.min(target, scroll.contentHeight - scroll.height))
    }
    onOverviewActiveChanged: if (overviewActive) { snapshotDirty = true; refreshSnapshot(); network = systemProvider.currentNetwork() }
    onPeriodChanged: { snapshotDirty = true; refreshSnapshot() }
    onTrafficKindChanged: { snapshotDirty = true; refreshSnapshot() }
    onRankingKindChanged: { snapshotDirty = true; refreshSnapshot() }
    onWidthChanged: Qt.callLater(page.updateLayoutOrigin)
    onHeightChanged: Qt.callLater(page.updateLayoutOrigin)
    onWideChanged: Qt.callLater(page.updateLayoutOrigin)
    onVisibleChanged: { if (visible) refreshSnapshot(); else if (details.activeDetail) details.reset() }
    Component.onCompleted: refreshSnapshot()
    Connections { target: page.telemetry; function onChanged() { page.snapshotDirty = true } }
    Timer { interval: 300; running: page.overviewActive && page.snapshotDirty; repeat: true; onTriggered: page.refreshSnapshot() }
    Timer { interval: 10000; running: page.overviewActive; repeat: true; onTriggered: page.network = page.systemProvider.currentNetwork() }

    component CardTitle: SwirlText {
        color: Theme.text; font.pixelSize: Theme.fontSize(17); font.weight: Font.DemiBold
        Layout.minimumWidth: 0; elide: Text.ElideRight
    }
    component Fact: RowLayout {
        id: fact
        property string caption: ""
        property string value: "—"
        property int valueAlignment: Text.AlignLeft
        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(8)
        SwirlText { text: fact.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.preferredWidth: Theme.dp(64); Layout.alignment: Qt.AlignBaseline }
        SwirlText { id: factValue; objectName: fact.objectName + "Value"; text: fact.value; textFormat: Text.PlainText; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(12); font.weight: Font.Medium; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; horizontalAlignment: fact.valueAlignment; elide: Text.ElideRight }

    }
    component Rate: RowLayout {
        id: rate
        property string caption: ""
        property real value: 0
        readonly property var parts: page.telemetry.formatBytes(value).split(" ")
        Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 1; spacing: Theme.dp(4)
        SwirlText { id: rateCaption; text: rate.caption; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
        SwirlText { objectName: rate.objectName + "Value"; text: page.telemetry.sampled ? rate.parts[0] : "—"; Layout.minimumWidth: 0; Layout.maximumWidth: Math.max(0, rate.width - rateCaption.implicitWidth - rateUnit.implicitWidth - rate.spacing * 3); Layout.alignment: Qt.AlignBaseline; tabularFigures: true; font.pixelSize: Theme.fontSize(22); font.weight: Font.DemiBold; color: Theme.text; elide: Text.ElideRight }
        SwirlText { id: rateUnit; text: page.telemetry.sampled ? rate.parts[1] + "/s" : ""; Layout.alignment: Qt.AlignBaseline; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
        Item { Layout.fillWidth: true }
    }

    Flickable {
        id: scroll; objectName: "activityScroll"
        anchors.fill: parent; anchors.topMargin: Theme.dp(52)
        opacity: 1 - details.progress
        // Keep the existing knot instance and its weave position across navigation.
        enabled: !details.activeDetail
        contentWidth: width; contentHeight: content.height + Theme.dp(16)
        interactive: contentHeight > height + 1
        flickableDirection: Flickable.VerticalFlick; boundsBehavior: Flickable.StopAtBounds
        onContentYChanged: { if (details.activeDetail) Qt.callLater(details.updateOrigin); Qt.callLater(statusWeave.updateGeometry) }
        clip: true; ScrollBar.vertical: SwirlScrollBar {}
        Item {
            id: content
            objectName: "activityContent"
            readonly property real gap: Theme.dp(16)
            readonly property real smallWidth: (width - gap) * 5 / 12
            readonly property real largeWidth: (width - gap) * 7 / 12
            readonly property real availableRowsHeight: Math.max(Theme.dp(564), scroll.height - Theme.dp(16) - gap)
            readonly property real topHeight: page.wide ? Math.max(Theme.dp(238), availableRowsHeight * 0.38) : Theme.dp(238)
            readonly property real bottomHeight: page.wide ? availableRowsHeight - topHeight : Theme.dp(326)
            readonly property real auxiliaryHeight: (bottomHeight - gap) / 2
            x: Theme.pagePadding; width: scroll.width - 2 * Theme.pagePadding
            height: page.wide ? topHeight + gap + bottomHeight : narrowColumn.implicitHeight

            RowLayout {
                id: topRow
                objectName: "activityTopRow"
                x: 0; y: 0; width: content.width; height: content.topHeight; spacing: content.gap
                Item {
                    id: statusWideSlot
                    Layout.minimumWidth: content.smallWidth; Layout.preferredWidth: content.smallWidth; Layout.maximumWidth: content.smallWidth
                    Layout.minimumHeight: content.topHeight; Layout.preferredHeight: content.topHeight; Layout.maximumHeight: content.topHeight
                    SwirlActivityCard {
                        id: statusCard; objectName: "activityStatusCard"
                        anchors.fill: parent
                        title: qsTr("连接状态"); titleItem: statusTitle
                        opacity: details.activeDetail && details.sourceCard === statusCard ? 0 : 1
                        onActivated: page.openCard(statusCard, "connection", title)
                        Item {
                            id: statusEmblem; objectName: "activityStatusEmblem"
                            // The title spans the card; everything below shares a
                            // permanent text/art split, even while disconnected.
                            x: statusCard.width - width; y: Theme.dp(52)
                            width: Math.min(Theme.dp(160), statusCard.width * 0.44)
                            height: statusCard.height - y - page.cardInset
                            Accessible.ignored: true
                        }
                        ColumnLayout {
                            id: statusBody; objectName: "activityStatusBody"
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: page.cardInset; spacing: page.moduleGap
                            RowLayout {
                                objectName: "activityStatusHeader"; Layout.minimumHeight: Theme.dp(28); Layout.fillWidth: true; spacing: Theme.dp(8)
                                CardTitle { id: statusTitle; objectName: "activityConnectionDetails"; text: qsTr("连接状态"); Layout.fillWidth: true }
                                SwirlStatusBadge { objectName: "activityRuntimeCapsule"; label: page.runtimeLabel; tone: page.runtimeHealthy ? "success" : page.proxyError.length ? "warning" : "neutral"; busy: page.proxyPhase === "pending" }
                                SwirlIconButton { objectName: "activityProxyErrorDetails"; visible: page.proxyError.length > 0; Layout.preferredWidth: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); iconName: "warning"; iconColor: Theme.red; quiet: true; tooltip: qsTr("查看代理错误详情"); Accessible.description: page.proxyError; onClicked: { page.errorDetailsText = page.proxyError; page.errorDetailsRequested = true } }
                                SwirlIcon { name: "chevron-right"; size: Theme.dp(13); color: Theme.muted }
                            }
                            ColumnLayout {
                                objectName: "activityNodeSection"
                                Layout.fillWidth: true; Layout.minimumWidth: 0
                                Layout.rightMargin: statusEmblem.width - page.cardInset + Theme.dp(6)
                                Layout.minimumHeight: Theme.dp(64); Layout.preferredHeight: Theme.dp(64); Layout.maximumHeight: Theme.dp(64); spacing: Theme.dp(3)
                                SwirlText { text: page.engineController.activeNodeId.length ? qsTr("当前节点") : qsTr("当前出口"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                SwirlText { id: currentNode; objectName: "activityCurrentNode"; text: page.currentNodeName; textFormat: Text.PlainText; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight;  }
                            }
                            ColumnLayout {
                                objectName: "activityIpSection"; Layout.fillWidth: true; spacing: Theme.dp(2)
                                Layout.rightMargin: statusEmblem.width - page.cardInset + Theme.dp(6)
                                SwirlText { text: qsTr("出口 IP"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                SwirlText { id: exitIp; objectName: "activityExitIpValue"; text: page.telemetry.externalIp || qsTr("尚未测量"); textFormat: Text.PlainText; tabularFigures: true; Layout.fillWidth: true; Layout.minimumWidth: 0; color: Theme.text; font.pixelSize: Theme.fontSize(14); font.weight: Font.Medium; elide: Text.ElideRight;  }
                            }
                            Fact { objectName: "activityNetworkFact"; Layout.rightMargin: statusEmblem.width - page.cardInset + Theme.dp(6); caption: qsTr("网络"); value: page.network.type || qsTr("未连接") }
                            Fact { objectName: "activityProfileFact"; Layout.rightMargin: statusEmblem.width - page.cardInset + Theme.dp(6); caption: qsTr("配置"); value: extensionsProvider.profileName || qsTr("未提供") }
                            Fact { objectName: "activityPolicyFact"; Layout.rightMargin: statusEmblem.width - page.cardInset + Theme.dp(6); caption: qsTr("默认策略"); value: page.defaultTargetName }
                        }
                    }
                }
                Item {
                    id: trafficWideSlot
                    Layout.minimumWidth: content.largeWidth; Layout.preferredWidth: content.largeWidth; Layout.maximumWidth: content.largeWidth
                    Layout.minimumHeight: content.topHeight; Layout.preferredHeight: content.topHeight; Layout.maximumHeight: content.topHeight
                    SwirlActivityCard {
                        id: trafficCard; objectName: "activityTrafficCard"
                        anchors.fill: parent
                        title: qsTr("传输"); titleItem: trafficTitle
                        opacity: details.activeDetail && details.sourceCard === trafficCard ? 0 : 1
                        onActivated: page.openCard(trafficCard, "traffic", title)
                        ColumnLayout {
                            objectName: "activityTrafficBody"
                            anchors.fill: parent; anchors.margins: page.cardInset; spacing: page.moduleGap
                            RowLayout {
                                Layout.fillWidth: true; Layout.minimumHeight: Theme.dp(28)
                                CardTitle { id: trafficTitle; objectName: "activityTrafficDetails"; text: qsTr("传输"); Layout.fillWidth: true }
                                SwirlText { text: qsTr("合计 · 最近 1 分钟"); color: Theme.muted; font.pixelSize: Theme.fontSize(11) }
                                SwirlIcon { name: "chevron-right"; size: Theme.dp(13); color: Theme.muted }
                            }
                            RowLayout { objectName: "activityRateRow"; Layout.fillWidth: true; spacing: Theme.dp(12); Rate { objectName: "activityUploadRate"; caption: qsTr("上传"); value: page.telemetry.uploadRate } Rate { objectName: "activityDownloadRate"; caption: qsTr("下载"); value: page.telemetry.downloadRate } }
                            SwirlTrafficChart { subdued: true; axisFontSize: Theme.fontSize(11); id: trafficChart; objectName: "activityTrafficChart"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; Layout.minimumHeight: Theme.dp(110); Layout.preferredHeight: Theme.dp(110); rangeIndex: 0; series: "total"; enabled: false; updatesEnabled: page.overviewActive }
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.dp(8)
                                SwirlText { text: qsTr("累计"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
                                SwirlText { objectName: "activityTotal"; text: page.bytes(page.totals.total, page.totals.sampled); color: Theme.text; font.pixelSize: Theme.fontSize(17); font.weight: Font.DemiBold; tabularFigures: true; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight }
                                SwirlSegmentedControl { objectName: "activityPeriodFilter"; Layout.preferredWidth: Theme.dp(112); Layout.preferredHeight: Theme.dp(28); options: [qsTr("今日"), qsTr("本月")]; currentIndex: page.period; onActivated: index => page.period = index }
                            }
                        }
                    }
                }
            }
            RowLayout {
                id: bottomRow
                objectName: "activityBottomRow"
                x: 0; y: topRow.height + content.gap; width: content.width; height: content.bottomHeight; spacing: content.gap
                Item {
                    id: sourcesWideSlot
                    Layout.minimumWidth: content.largeWidth; Layout.preferredWidth: content.largeWidth; Layout.maximumWidth: content.largeWidth
                    Layout.minimumHeight: content.bottomHeight; Layout.preferredHeight: content.bottomHeight; Layout.maximumHeight: content.bottomHeight
                    SwirlActivityCard {
                        id: sourcesCard; objectName: "activitySourcesCard"
                        anchors.fill: parent
                        title: qsTr("流量来源"); titleItem: sourcesTitle
                        opacity: details.activeDetail && details.sourceCard === sourcesCard ? 0 : 1
                        onActivated: page.openCard(sourcesCard, "sources", title)
                        ColumnLayout {
                            objectName: "activitySourcesBody"
                            anchors.fill: parent; anchors.margins: page.cardInset; spacing: page.moduleGap
                            RowLayout { objectName: "activitySourcesHeader"; Layout.fillWidth: true; Layout.minimumHeight: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); Layout.maximumHeight: Theme.dp(28); CardTitle { id: sourcesTitle; objectName: "activitySourcesDetails"; text: qsTr("流量来源"); Layout.fillWidth: true } SwirlButton { text: qsTr("查看全部"); Layout.minimumHeight: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); Layout.maximumHeight: Theme.dp(28); quiet: true; onClicked: page.openCard(sourcesCard, "sources", sourcesCard.title) } }
                            RowLayout {
                                objectName: "activitySourcesFilters"; Layout.fillWidth: true; spacing: Theme.dp(6)
                                SwirlSegmentedControl { rounded: false; objectName: "activitySourceFilter"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); Layout.maximumHeight: Theme.dp(28); options: [qsTr("进程与设备"), qsTr("域名"), qsTr("策略")]; currentIndex: page.rankingKind; onActivated: index => page.rankingKind = index }
                                SwirlComboBox { objectName: "activityTrafficFilter"; Layout.preferredWidth: Theme.dp(92); Layout.minimumHeight: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); Layout.maximumHeight: Theme.dp(28); model: [qsTr("全部"), qsTr("仅代理")]; currentIndex: page.trafficKind; onActivated: page.trafficKind = currentIndex; Accessible.name: qsTr("流量来源范围") }
                            }
                            Item {
                                objectName: "activitySourceList"
                                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; Layout.minimumHeight: page.sourceRowHeight * 5
                                Column {
                                    anchors.left: parent.left; anchors.right: parent.right; spacing: 0
                                    Repeater {
                                        model: page.visibleRanks
                                        SwirlMotionButton {
                                            id: rank
                                            required property var modelData
                                            required property int index
                                            objectName: "activitySourceRow-" + index
                                            readonly property string displayName: page.sourceName(modelData)
                                            width: parent.width; height: page.sourceRowHeight; padding: Theme.dp(4); hoverEnabled: true
                                            background: SwirlControlSurface { quiet: true; hovered: rank.hovered; pressed: rank.down; focused: rank.visualFocus; controlEnabled: rank.enabled }
                                            contentItem: RowLayout {
                                                spacing: Theme.dp(8)
                                                SwirlIcon { name: rank.modelData.kind === "apps" ? "terminal" : rank.modelData.kind === "devices" ? "router" : rank.modelData.kind === "domains" ? "globe" : "route"; size: Theme.dp(16); color: Theme.muted }
                                                SwirlText { text: rank.displayName; textFormat: Text.PlainText; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.alignment: Qt.AlignBaseline; elide: Text.ElideRight; color: Theme.text; font.pixelSize: Theme.fontSize(12) }
                                                SwirlText { text: rank.modelData.value; horizontalAlignment: Text.AlignRight; Layout.preferredWidth: Theme.dp(80); tabularFigures: true; Layout.alignment: Qt.AlignBaseline; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                            }
                                            Accessible.name: qsTr("%1，%2，查看详情").arg(displayName).arg(modelData.value)

                                            onClicked: page.openRank(modelData)
                                        }
                                    }
                                }
                                SwirlText { visible: page.ranks.length === 0; anchors.fill: parent; text: page.emptyRanksText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); verticalAlignment: Text.AlignVCenter; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                            }
                            SwirlText { objectName: "activitySourceSummaryCaption"; text: page.rankingKind === 0 ? qsTr("进程与设备分别归属，同一流量不重复累计") : qsTr("仅展示重点来源，完整列表请查看全部"); color: Theme.muted; font.pixelSize: Theme.fontSize(10); Layout.fillWidth: true; elide: Text.ElideRight }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1 / Screen.devicePixelRatio; color: Theme.increaseContrast ? Theme.separator : Theme.withAlpha(Theme.text, 0.06) }
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.dp(12)
                                SwirlText { text: qsTr("直连 %1").arg(page.distribution[1] && page.totals.sampled ? page.distribution[1].value : "—"); tabularFigures: true; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                                SwirlText { text: qsTr("代理 %1").arg(page.distribution[0] && page.totals.sampled ? page.distribution[0].value : "—"); tabularFigures: true; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.minimumWidth: 0; elide: Text.ElideRight }
                            }
                        }
                    }
                }
                ColumnLayout {
                    id: rightStack
                    objectName: "activityRightStack"
                    Layout.minimumWidth: content.smallWidth; Layout.preferredWidth: content.smallWidth; Layout.maximumWidth: content.smallWidth
                    Layout.minimumHeight: content.bottomHeight; Layout.preferredHeight: content.bottomHeight; Layout.maximumHeight: content.bottomHeight
                    spacing: content.gap
                    Item {
                        id: diagnosticWideSlot
                        Layout.minimumWidth: content.smallWidth; Layout.preferredWidth: content.smallWidth; Layout.maximumWidth: content.smallWidth
                        Layout.minimumHeight: content.auxiliaryHeight; Layout.preferredHeight: content.auxiliaryHeight; Layout.maximumHeight: content.auxiliaryHeight
                        SwirlActivityCard {
                            id: diagnosticCard; objectName: "activityDiagnosticCard"
                            anchors.fill: parent
                            title: qsTr("网络诊断"); titleItem: diagnosticTitle
                            opacity: details.activeDetail && details.sourceCard === diagnosticCard ? 0 : 1
                            onActivated: page.openCard(diagnosticCard, "diagnostics", title)
                            ColumnLayout {
                                objectName: "activityDiagnosticBody"
                                anchors.fill: parent; anchors.margins: page.cardInset; spacing: page.moduleGap
                                RowLayout {
                                    Layout.fillWidth: true
                                    CardTitle { id: diagnosticTitle; objectName: "networkDiagnosticDetails"; text: qsTr("网络诊断"); Layout.fillWidth: true }
                                    SwirlIconButton { objectName: "networkDiagnosticButton"; Layout.preferredWidth: Theme.dp(28); Layout.preferredHeight: Theme.dp(28); iconName: "refresh"; quiet: true; enabled: page.telemetry.measurementState !== "正在测量"; tooltip: qsTr("重新检测网络"); onClicked: page.telemetry.measureNetwork() }
                                    SwirlIcon { name: "chevron-right"; size: Theme.dp(13); color: Theme.muted }
                                }
                                RowLayout {
                                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: Theme.dp(5)
                                    SwirlText { objectName: "activityInternetValue"; text: page.internetMeasured ? String(parseInt(page.internetLatency)) : "—"; Layout.alignment: Qt.AlignBaseline; color: Theme.text; font.pixelSize: Theme.fontSize(24); font.weight: Font.DemiBold; tabularFigures: true }
                                    SwirlText { objectName: "activityInternetUnit"; text: page.internetMeasured ? "ms" : ""; Layout.alignment: Qt.AlignBaseline; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                                    Item { Layout.fillWidth: true }
                                    SwirlStatusBadge { label: page.measuring ? qsTr("检测中") : page.diagnosticWarning ? qsTr("需检查") : page.internetMeasured ? qsTr("正常") : qsTr("未检测"); tone: page.measuring ? "accent" : page.diagnosticWarning ? "warning" : page.internetMeasured ? "success" : "neutral"; busy: page.measuring }
                                }
                                SwirlText { objectName: "activityInternetCaption"; text: page.diagnosticSummary; color: page.diagnosticWarning ? Theme.warningText : Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; Layout.minimumWidth: 0; maximumLineCount: 2; wrapMode: Text.Wrap; elide: Text.ElideRight }
                                RowLayout {
                                    Layout.fillWidth: true; spacing: Theme.dp(12)
                                    SwirlText { text: qsTr("网关 %1").arg(page.latency("router")); color: Theme.muted; font.pixelSize: Theme.fontSize(11); Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                                    SwirlText { text: qsTr("DNS %1").arg(page.latency("dns")); color: Theme.muted; font.pixelSize: Theme.fontSize(11); Layout.fillWidth: true; Layout.minimumWidth: 0; elide: Text.ElideRight }
                                }
                            }
                        }
                    }
                    Item {
                        id: connectionsWideSlot
                        Layout.minimumWidth: content.smallWidth; Layout.preferredWidth: content.smallWidth; Layout.maximumWidth: content.smallWidth
                        Layout.minimumHeight: content.auxiliaryHeight; Layout.preferredHeight: content.auxiliaryHeight; Layout.maximumHeight: content.auxiliaryHeight
                        SwirlActivityCard {
                            id: connectionsCard; objectName: "activityConnectionsCard"
                            anchors.fill: parent
                            title: qsTr("活动连接"); titleItem: connectionsTitle
                            opacity: details.activeDetail && details.sourceCard === connectionsCard ? 0 : 1
                            onActivated: page.openCard(connectionsCard, "connections", title)
                            ColumnLayout {
                                objectName: "activityConnectionsBody"
                                anchors.fill: parent; anchors.margins: page.cardInset; spacing: page.moduleGap
                                RowLayout { Layout.fillWidth: true; Layout.minimumHeight: Theme.dp(28); CardTitle { id: connectionsTitle; objectName: "activityConnectionsDetails"; text: qsTr("活动连接"); Layout.fillWidth: true } SwirlIcon { name: "chevron-right"; size: Theme.dp(13); color: Theme.muted } }
                                RowLayout {
                                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: Theme.dp(7)
                                    SwirlText { objectName: "activityConnectionCount"; text: page.telemetry.connectionsSampled ? String(page.telemetry.activeConnections) : "—"; tabularFigures: true; color: Theme.text; font.pixelSize: Theme.fontSize(28); font.weight: Font.DemiBold; Layout.alignment: Qt.AlignBaseline }
                                    SwirlText { text: page.telemetry.connectionsSampled ? qsTr("当前连接") : qsTr("尚未采集"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.alignment: Qt.AlignBaseline }
                                    Item { Layout.fillWidth: true }
                                }
                                Fact { valueAlignment: Text.AlignRight; caption: qsTr("已识别进程"); value: !page.telemetry.connectionsSampled ? qsTr("未知") : page.telemetry.activeConnections > 0 && page.telemetry.activeProcesses === 0 ? qsTr("未提供") : String(page.telemetry.activeProcesses) }
                                Fact { valueAlignment: Text.AlignRight; caption: qsTr("非本机来源"); value: page.telemetry.connectionsSampled ? String(page.telemetry.activeDevices) : qsTr("未知") }
                            }
                        }
                    }
                }
            }
            ColumnLayout {
                id: narrowColumn
                objectName: "activityNarrowColumn"
                x: 0; y: 0; width: content.width; height: implicitHeight; spacing: content.gap
                Item { id: statusNarrowSlot; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: content.topHeight; Layout.preferredHeight: content.topHeight; Layout.maximumHeight: content.topHeight }
                Item { id: trafficNarrowSlot; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: content.topHeight; Layout.preferredHeight: content.topHeight; Layout.maximumHeight: content.topHeight }
                Item { id: sourcesNarrowSlot; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: content.bottomHeight; Layout.preferredHeight: content.bottomHeight; Layout.maximumHeight: content.bottomHeight }
                Item { id: diagnosticNarrowSlot; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: content.auxiliaryHeight; Layout.preferredHeight: content.auxiliaryHeight; Layout.maximumHeight: content.auxiliaryHeight }
                Item { id: connectionsNarrowSlot; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.minimumHeight: content.auxiliaryHeight; Layout.preferredHeight: content.auxiliaryHeight; Layout.maximumHeight: content.auxiliaryHeight }
            }
            states: State {
                name: "single-column"
                when: !page.wide
                ParentChange { target: statusCard; parent: statusNarrowSlot }
                ParentChange { target: trafficCard; parent: trafficNarrowSlot }
                ParentChange { target: sourcesCard; parent: sourcesNarrowSlot }
                ParentChange { target: diagnosticCard; parent: diagnosticNarrowSlot }
                ParentChange { target: connectionsCard; parent: connectionsNarrowSlot }
            }
            SwirlCloudKnotWeave {
                id: statusWeave
                objectName: "activityCloudKnotWeave"
                anchors.fill: parent
                visible: page.sceneSettled
                z: 2
                connectionItem: statusCard; transferItem: trafficCard; sourcesItem: sourcesCard
                diagnosticItem: diagnosticCard; connectionsItem: connectionsCard
                knotTarget: statusEmblem
                cardViewport: scroll
                behindCards: page.ribbonBack; frontLayer: page.ribbonFront
                proxyAnchor: page.proxyAnchor; sidebarAnchor: page.sidebarAnchor; wingScene: page.wingScene
                wide: page.wide; gap: content.gap
                active: page.proxyOwned && page.runtimeHealthy && !page.engineController.systemProxyStopping
                presentationActive: page.overviewActive
                // Global decorative views follow the overview's detail fade.
                opacity: 1 - details.progress
            }
        }
    }

    ActivityDetailTransition {
        id: details
        anchors.fill: parent
        onReturning: page.ensureSourceVisible(details.sourceCard)
        Loader { anchors.fill: parent; asynchronous: true; active: page.visitedDetails.connection === true; visible: details.detailKey === "connection"; sourceComponent: ActivityConnectionDetail { engineController: page.engineController; systemProvider: page.systemProvider; updatesEnabled: !details.moving } }
        Loader {
            id: sourcesDetail
            anchors.fill: parent; asynchronous: true; active: page.visitedDetails.sources === true; visible: details.detailKey === "sources"
            sourceComponent: ActivitySourcesDetail { engineController: page.engineController; period: page.period === 0 ? 0 : 3; kindIndex: page.rankingKind === 0 ? 0 : page.rankingKind === 1 ? 2 : 3; proxyOnly: page.trafficKind === 1; updatesEnabled: !details.moving }
            onLoaded: if (page.pendingSourceRow) { item.selectSource(page.pendingSourceRow); page.pendingSourceRow = null }
        }
        Loader { anchors.fill: parent; asynchronous: true; active: page.visitedDetails.connections === true; visible: details.detailKey === "connections"; sourceComponent: ConnectionsPage { embedded: true; updatesEnabled: !details.moving } }
        Loader { anchors.fill: parent; asynchronous: true; active: page.visitedDetails.traffic === true; visible: details.detailKey === "traffic"; sourceComponent: TrafficAnalyticsPage { embedded: true; period: page.period === 0 ? 0 : 3; updatesEnabled: !details.moving } }
        Loader { anchors.fill: parent; asynchronous: true; active: page.visitedDetails.diagnostics === true; visible: details.detailKey === "diagnostics"; sourceComponent: ActivityDiagnosticsDetail { engineController: page.engineController; systemProvider: page.systemProvider; updatesEnabled: !details.moving } }
    }
    Loader {
        active: page.errorDetailsRequested
        sourceComponent: SwirlDialog {
            id: errorDialog; objectName: "activityProxyErrorDialog"
            ownerItem: page; guardChanges: false; title: qsTr("代理错误详情")
            height: Math.min(Theme.dp(360), parent ? parent.height - Theme.dp(48) : Theme.dp(360))
            Component.onCompleted: open()
            onClosed: page.errorDetailsRequested = false
            contentItem: ColumnLayout {
                spacing: Theme.dp(12)
                ScrollView {
                    id: errorScroll; Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff; ScrollBar.vertical: SwirlScrollBar {}
                    SwirlText { width: errorScroll.availableWidth; text: page.errorDetailsText; textFormat: Text.PlainText; color: Theme.red; font.pixelSize: Theme.fontSize(13); wrapMode: Text.Wrap }
                }
                SwirlButton { Layout.alignment: Qt.AlignRight; text: qsTr("关闭"); onClicked: errorDialog.close() }
            }
        }
    }
}
