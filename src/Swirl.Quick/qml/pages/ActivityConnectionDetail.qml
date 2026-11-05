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
    readonly property var actualNode: engineController.nodeCatalog.find(node => node.id === engineController.activeNodeId) || ({})
    readonly property var defaultTarget: ((engineController.policyDocument || {}).default_policy || {}).target || ({})
    readonly property string policyName: {
        if (defaultTarget.kind === "direct") return qsTr("直连")
        const option = engineController.policyTargetOptions.find(target => target.kind === defaultTarget.kind && target.id === defaultTarget.id)
        return option ? option.name : qsTr("未分配")
    }
    property var network: ({})
    readonly property string nodeName: actualNode.name || (engineController.activeNodeId.length ? qsTr("节点详情未提供") : engineController.processAlive ? qsTr("当前节点未提供；连接按规则选择出口") : qsTr("尚未连接"))
    readonly property string uptime: {
        if (!engineController.processAlive) return qsTr("未运行")
        const seconds = engineController.uptimeSeconds
        return qsTr("%1 小时 %2 分 %3 秒").arg(Math.floor(seconds / 3600)).arg(Math.floor(seconds / 60) % 60).arg(seconds % 60)
    }
    readonly property var facts: [
        {label: qsTr("运行状态"), value: engineController.stateText || qsTr("未提供")},
        {label: qsTr("当前节点"), value: nodeName},
        {label: qsTr("节点协议"), value: actualNode.protocol || qsTr("未提供")},
        {label: qsTr("节点地址"), value: actualNode.host ? (actualNode.host.includes(":") ? "[" + actualNode.host + "]" : actualNode.host) + (actualNode.port ? ":" + actualNode.port : "") : qsTr("未提供")},
        {label: qsTr("出口 IP"), value: telemetry.externalIp || qsTr("尚未测量")},
        {label: qsTr("当前网络"), value: network.type || qsTr("未连接")},
        {label: qsTr("网络名称"), value: network.name || qsTr("未提供")},
        {label: qsTr("当前配置"), value: extensionsProvider.profileName || qsTr("未提供")},
        {label: qsTr("默认策略出口"), value: policyName},
        {label: qsTr("内核运行时长"), value: uptime},
        {label: qsTr("系统代理"), value: engineController.systemProxy.enabled ? engineController.systemProxy.owned ? qsTr("由 Swirl 接管") : qsTr("由其他应用设置") : qsTr("未开启")},
        {label: qsTr("TUN"), value: engineController.tunEnabled ? qsTr("已开启") : qsTr("未开启")},
        {label: qsTr("内核 API"), value: engineController.apiHealthy ? qsTr("正常") : engineController.processAlive ? qsTr("尚未就绪") : qsTr("未运行")}
    ]
    function refreshNetwork() { if (visible && updatesEnabled) network = systemProvider.currentNetwork() }
    onVisibleChanged: if (visible) refreshNetwork()
    onUpdatesEnabledChanged: if (updatesEnabled) refreshNetwork()
    Component.onCompleted: refreshNetwork()
    Timer { interval: 10000; running: page.visible && page.updatesEnabled; repeat: true; onTriggered: page.refreshNetwork() }

    ScrollView {
        id: scroll
        objectName: "activityConnectionScroll"
        anchors.fill: parent; clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical: SwirlScrollBar {}
        ColumnLayout {
            width: scroll.availableWidth; spacing: Theme.dp(18)
            SwirlText { text: page.nodeName; textFormat: Text.PlainText; Layout.fillWidth: true; Layout.minimumWidth: 0; color: Theme.text; font.pixelSize: Theme.fontSize(24); font.weight: Font.DemiBold; wrapMode: Text.WrapAnywhere }
            SwirlText { text: qsTr("运行时长是内核会话的时间。出口 IP 为最近一次检测结果，规则可能为不同连接选择不同出口。"); Layout.fillWidth: true; color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
            GridLayout {
                Layout.fillWidth: true; columns: page.width < Theme.dp(620) ? 1 : 2
                columnSpacing: Theme.dp(28); rowSpacing: Theme.dp(18)
                Repeater {
                    model: page.facts
                    ColumnLayout {
                        id: fact
                        required property var modelData
                        Layout.fillWidth: true; Layout.minimumWidth: 0; spacing: Theme.dp(5)
                        SwirlText { text: fact.modelData.label; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
                        SwirlText { text: fact.modelData.value; textFormat: Text.PlainText; color: Theme.text; font.pixelSize: Theme.fontSize(14); Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WrapAnywhere; tabularFigures: true }
                    }
                }
            }
            SwirlText { text: page.engineController.errorCode !== "None" ? page.engineController.error : page.engineController.routingError || page.engineController.policyError; visible: text.length > 0; Layout.fillWidth: true; color: Theme.warningText; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
            Item { Layout.preferredHeight: Theme.dp(8) }
        }
    }
}
