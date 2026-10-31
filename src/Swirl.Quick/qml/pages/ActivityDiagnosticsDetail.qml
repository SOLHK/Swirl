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
    property bool updatesEnabled: true
    readonly property var telemetry: engineController.telemetry
    property var network: ({})
    readonly property bool measuring: telemetry.measurementState === "正在测量"
    property bool componentReady: false
    property var diagnosticSnapshot: ({internet: {}, proxy: {}, latencies: {}})
    property string diagnosticSignature: ""
    readonly property var internet: diagnosticSnapshot.internet
    readonly property var proxy: diagnosticSnapshot.proxy
    readonly property var checks: [
        {name: qsTr("HTTPS 请求"), key: "internet", description: qsTr("包含连接、TLS 与目标响应的完整请求耗时")},
        {name: qsTr("默认网关"), key: "router", description: qsTr("网关 ICMP 响应耗时；未响应不等同于无法联网")},
        {name: qsTr("DNS 查询"), key: "dns", description: qsTr("系统解析器的实际 DNS 查询耗时")},
        {name: qsTr("代理请求"), key: "proxy", description: qsTr("当前 Rust 出站至响应首部；与完整 HTTPS 请求分别采样")}
    ]
    readonly property var detailFacts: {
        const rows = []
        for (const entry of [{name: qsTr("HTTPS"), data: internet}, {name: qsTr("代理"), data: proxy}]) {
            const fields = [
                ["route", qsTr("路径")], ["code", qsTr("结果代码")], ["http", qsTr("HTTP 状态")],
                ["networkError", qsTr("网络错误代码")], ["elapsedMs", qsTr("请求耗时（ms）")],
                ["outboundConnectMs", qsTr("出站连接耗时（ms）")], ["originTlsMs", qsTr("目标 TLS 耗时（ms）")],
                ["metricType", qsTr("测量范围")], ["routeVerified", qsTr("路径已验证")],
                ["engineRunning", qsTr("内核运行")], ["apiHealthy", qsTr("内核 API 健康")],
                ["proxyPort", qsTr("本地代理端口")], ["selectedNode", qsTr("已选择节点")],
                ["directSession", qsTr("直连会话")], ["state", qsTr("结果")],
                ["detail", qsTr("详情")], ["advice", qsTr("建议")]
            ]
            for (const field of fields) {
                if (entry.data[field[0]] !== undefined && entry.data[field[0]] !== "")
                    rows.push({label: qsTr("%1 · %2").arg(entry.name).arg(field[1]), value: diagnosticValue(field[0], entry.data[field[0]])})
            }
        }
        return rows
    }
    function diagnosticValue(key, value) {
        if (typeof value === "boolean") return value ? qsTr("是") : qsTr("否")
        if (key.endsWith("Ms") && value < 0) return qsTr("未提供")
        if (key === "metricType" && value === "http_headers") return qsTr("至 HTTP 响应首部")
        return String(value)
    }
    function valueFor(key) { return diagnosticSnapshot.latencies[key] || qsTr("尚未测量") }
    function phaseFor(key, result) {
        const value = valueFor(key)
        if (result.code === "measuring" || value === "测量中" || value === "正在检测" || value.includes("进行中")) return "pending"
        if (/^\d+ ms$/.test(value)) return "success"
        if (value === "未连接" || value === "尚未测量" || value === "尚未检测" || value === "未支持") return "neutral"
        return "warning"
    }
    function statusLabel(key, result) {
        const phase = phaseFor(key, result)
        if (phase === "success") return qsTr("正常")
        if (phase === "pending") return qsTr("检测中")
        if (phase === "warning") return qsTr("需检查")
        return valueFor(key)
    }
    function refreshNetwork() { if (visible && updatesEnabled) network = systemProvider.currentNetwork() }
    function refreshSnapshot() {
        if (!componentReady || !visible || !updatesEnabled) return
        const snapshot = {internet: telemetry.internetDiagnostic, proxy: telemetry.proxyDiagnostic, latencies: telemetry.latencies}
        const signature = JSON.stringify(snapshot)
        if (signature === diagnosticSignature) return
        diagnosticSignature = signature
        diagnosticSnapshot = snapshot
    }
    onVisibleChanged: if (visible) { refreshNetwork(); refreshSnapshot() }
    onUpdatesEnabledChanged: if (updatesEnabled) { refreshNetwork(); refreshSnapshot() }
    Component.onCompleted: { componentReady = true; refreshNetwork(); refreshSnapshot() }
    Connections { target: page.telemetry; function onChanged() { page.refreshSnapshot() } }
    Timer { interval: 10000; running: page.visible && page.updatesEnabled; repeat: true; onTriggered: page.refreshNetwork() }

    ScrollView {
        id: scroll
        objectName: "activityDiagnosticsScroll"
        anchors.fill: parent; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.dp(16)
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.dp(12)
                ColumnLayout {
                    Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(4)
                    SwirlText { text: page.network.type || qsTr("未连接"); color: Theme.text; font.pixelSize: Theme.fontSize(17); font.weight: Font.DemiBold }
                    SwirlText { text: page.network.name || ""; textFormat: Text.PlainText; color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; elide: Text.ElideRight }
                }
                SwirlButton {
                    objectName: "activityDiagnosticsMeasure"
                    text: page.measuring ? qsTr("检测中…") : qsTr("重新检测")
                    iconName: "refresh"; enabled: !page.measuring
                    onClicked: { page.refreshNetwork(); page.telemetry.measureNetwork() }
                }
            }
            SwirlText { Layout.fillWidth: true; text: qsTr("出口 IP：%1").arg(page.telemetry.externalIp || qsTr("尚未测量")); color: Theme.muted; font.pixelSize: Theme.fontSize(12); tabularFigures: true; wrapMode: Text.Wrap }
            SwirlText { Layout.fillWidth: true; text: qsTr("各项耗时来自独立检测，不能相加。网关与 DNS 地址暂未提供。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width < Theme.dp(620) ? 1 : 2
                columnSpacing: Theme.dp(14); rowSpacing: Theme.dp(14)
                Repeater {
                    model: page.checks
                    SwirlGlassPanel {
                        id: checkCard
                        required property var modelData
                        readonly property var result: modelData.key === "internet" ? page.internet : modelData.key === "proxy" ? page.proxy : ({})
                        readonly property string phase: page.phaseFor(modelData.key, result)
                        Layout.fillWidth: true; Layout.minimumWidth: 0
                        Layout.preferredHeight: checkContent.implicitHeight + Theme.dp(28)
                        cornerRadius: Theme.dp(22)
                        ColumnLayout {
                            id: checkContent
                            anchors.fill: parent; anchors.margins: Theme.dp(14); spacing: Theme.dp(8)
                            RowLayout {
                                Layout.fillWidth: true
                                SwirlText { text: checkCard.modelData.name; font.pixelSize: Theme.fontSize(14); font.weight: Font.DemiBold; color: Theme.text; Layout.fillWidth: true }
                                SwirlStatusBadge {
                                    label: page.statusLabel(checkCard.modelData.key, checkCard.result)
                                    tone: checkCard.phase === "pending" ? "accent" : checkCard.phase
                                    busy: checkCard.phase === "pending"
                                }
                            }
                            SwirlText {
                                objectName: "activityDiagnosticValue-" + checkCard.modelData.key
                                Layout.fillWidth: true
                                text: page.valueFor(checkCard.modelData.key)
                                color: checkCard.phase === "warning" ? Theme.warningText : Theme.text
                                font.pixelSize: Theme.fontSize(checkCard.phase === "success" ? 27 : 19)
                                font.weight: Font.DemiBold; tabularFigures: true; wrapMode: Text.Wrap
                            }
                            SwirlText { Layout.fillWidth: true; text: checkCard.modelData.description; color: Theme.muted; font.pixelSize: Theme.fontSize(11); wrapMode: Text.Wrap }
                        }
                    }
                }
            }
            ColumnLayout {
                visible: page.detailFacts.length > 0
                Layout.fillWidth: true; spacing: Theme.dp(10)
                SwirlText { text: qsTr("诊断详情"); color: Theme.text; font.pixelSize: Theme.fontSize(16); font.weight: Font.DemiBold }
                Repeater {
                    model: page.detailFacts
                    ColumnLayout {
                        id: diagnosticFact
                        required property var modelData
                        Layout.fillWidth: true; spacing: Theme.dp(3)
                        SwirlText { text: diagnosticFact.modelData.label; color: Theme.muted; font.pixelSize: Theme.fontSize(11) }
                        SwirlText { text: diagnosticFact.modelData.value; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(13); Layout.fillWidth: true; wrapMode: Text.WrapAnywhere; tabularFigures: true }
                    }
                }
            }
            SwirlText { visible: page.detailFacts.length === 0; text: qsTr("尚未运行诊断。开始检测后显示实际耗时及可用的错误详情。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
            SwirlText { text: page.telemetry.storageError; visible: text.length > 0; color: Theme.red; font.pixelSize: Theme.fontSize(12); Layout.fillWidth: true; wrapMode: Text.Wrap }
            Item { Layout.preferredHeight: Theme.dp(6) }
        }
    }
}
