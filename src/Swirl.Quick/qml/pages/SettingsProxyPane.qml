import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

ColumnLayout {
    id: pane
    required property var settingsPage
    spacing: Theme.dp(12)
    SettingsRowPane {
        Layout.fillWidth: true
        title: engineController.systemProxy.owned ? (engineController.systemProxy.enabled ? qsTr("系统代理已接管") : qsTr("接管状态未确认")) : engineController.systemProxy.systemEnabled ? qsTr("系统代理由其他应用管理") : qsTr("系统代理未接管")
        description: qsTr("代理总开关在活动页。开启与恢复过程会在那里显示。")
        SwirlButton { text: qsTr("前往活动页"); primary: true; onClicked: AppState.navigate("activity") }
    }
    SwirlText { Layout.fillWidth: true; visible: engineController.systemProxy.error.length > 0; text: engineController.systemProxy.error; color: Theme.red; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SwirlText { Layout.fillWidth: true; text: qsTr("退出时恢复接管前的系统代理。其他应用更改代理后，Swirl 会让出控制权；恢复快照保存在本机。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    Item { Layout.preferredHeight: Theme.dp(12) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("连接诊断"); description: qsTr("只在你开始诊断后，向填写的目标发送请求。"); SwirlFlow { Layout.preferredWidth: Theme.dp(62); Layout.preferredHeight: Theme.dp(24); phase: engineController.diagnostics.busy ? "pending" : "idle" } }
    GridLayout {
        Layout.fillWidth: true
        columns: width < Theme.dp(430) ? 1 : 2
        rowSpacing: Theme.compactGap
        columnSpacing: Theme.compactGap
        SwirlTextField { id: diagnosticUrl; objectName: "diagnosticUrlField"; Layout.fillWidth: true; enabled: !engineController.diagnostics.busy; placeholderText: qsTr("https://目标地址 或 wss://目标路径"); Accessible.name: qsTr("用户指定的连接诊断地址") }
        SwirlButton { text: engineController.diagnostics.busy ? qsTr("取消") : qsTr("开始诊断"); enabled: engineController.diagnostics.busy || engineController.activeProxyPort > 0; onClicked: engineController.diagnostics.busy ? engineController.diagnostics.cancel() : engineController.diagnostics.run(diagnosticUrl.text) }
    }
    SwirlText { Layout.fillWidth: true; text: engineController.diagnostics.stateText; color: Theme.text; font.pixelSize: Theme.fontSize(13); wrapMode: Text.Wrap }
    SwirlText { Layout.fillWidth: true; text: qsTr("检查本机端口、CONNECT、TLS / HTTP，或 WebSocket Upgrade 与随机 Ping/Pong。目标可能需要登录或子协议。诊断失败不等于 Codex 服务故障，10 秒观察也不代替长期实测。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SwirlTextArea { Layout.fillWidth: true; Layout.preferredHeight: Theme.dp(180); visible: engineController.diagnostics.entries.length > 0; readOnly: true; selectByMouse: true; text: engineController.diagnostics.report; wrapMode: TextEdit.Wrap; Accessible.name: qsTr("连接诊断报告") }
    Flow {
        Layout.fillWidth: true
        spacing: Theme.compactGap
        SwirlButton { text: qsTr("保存诊断报告"); onClicked: { const path = engineController.diagnostics.saveReport(); AppState.notice(path.length > 0 ? qsTr("诊断报告已保存：%1").arg(path) : qsTr("无法保存诊断报告")) } }
        SwirlButton { text: qsTr("清空记录"); quiet: true; enabled: !engineController.diagnostics.busy; onClicked: engineController.diagnostics.clear() }
    }
    Item { Layout.preferredHeight: Theme.dp(16) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("代理引擎"); description: qsTr("随 Swirl 交付的 Rust Core，通过进程内接口通信。"); SwirlStatusBadge { objectName: "engineStatusBadge"; label: engineController.stateText; tone: engineController.apiHealthy ? "success" : "accent" } }
    SwirlText { objectName: "engineErrorText"; Layout.fillWidth: true; visible: engineController.error.length > 0; text: engineController.error; color: Theme.red; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SettingsRowPane { Layout.fillWidth: true; title: qsTr("Rust Core 代理内核"); description: qsTr("连接时校验节点、DNS 与规则能力；不支持的配置会保留原设置并显示原因。"); SwirlToggle { objectName: "nativeCoreStatus"; checked: true; enabled: false; Accessible.name: qsTr("Rust Core 代理内核") } }
    SettingsRowPane { Layout.fillWidth: true; title: qsTr("内核模块"); description: qsTr("启动时验证 ABI 和构建标识。"); SwirlTextField { objectName: "enginePathField"; Layout.preferredWidth: Theme.dp(224); text: "swirl_api.dll"; readOnly: true; selectByMouse: true; Accessible.name: qsTr("Swirl Rust Core 模块") } }
    SettingsRowPane { Layout.fillWidth: true; title: qsTr("控制接口"); description: engineController.controlEndpoint; SwirlTextField { objectName: "enginePortField"; Layout.preferredWidth: Theme.dp(224); text: qsTr("进程内，无需端口"); readOnly: true; selectByMouse: true; Accessible.name: qsTr("进程内控制接口") } }
    SwirlText { Layout.fillWidth: true; text: qsTr("当前引擎：%1").arg(engineController.engineKind === "rust" ? "Rust Core" : engineController.engineName) + (engineController.engineReason ? "\n" + engineController.engineReason : ""); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SwirlText { objectName: "engineProcessText"; Layout.fillWidth: true; text: qsTr("进程：%1　API：%2").arg(engineController.processAlive ? qsTr("运行中，PID %1").arg(engineController.processId) : qsTr("未运行")).arg(engineController.apiHealthy ? qsTr("健康") : qsTr("未就绪")); color: Theme.text; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    SwirlText { Layout.fillWidth: true; text: qsTr("运行版本：%1　运行时间：%2 秒").arg((engineController.version || qsTr("未读取")).replace("Swirl Core Rust", "Rust Core")).arg(engineController.uptimeSeconds); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
    Flow {
        Layout.fillWidth: true
        spacing: Theme.compactGap
        SwirlButton { objectName: "engineStartButton"; text: qsTr("启动引擎"); enabled: engineController.canStart; onClicked: engineController.start(); Accessible.name: text }
        SwirlButton { objectName: "engineStopButton"; text: qsTr("停止引擎"); enabled: engineController.processAlive || engineController.busy; onClicked: engineController.stop(); Accessible.name: text }
        SwirlButton { text: qsTr("检查状态"); quiet: true; enabled: engineController.processAlive && !engineController.busy; onClicked: engineController.refresh(); Accessible.name: text }
    }
    SwirlText { Layout.fillWidth: true; text: engineController.configPath.length > 0 ? qsTr("运行配置：%1").arg(engineController.configPath) : qsTr("运行配置在启动时传入 Rust Core。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.WrapAnywhere }
    SwirlText { Layout.fillWidth: true; visible: text.length > 0; text: engineController.configurationSummary.replace("Swirl Core Rust", "Rust Core"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.WrapAnywhere }
    Item { Layout.preferredHeight: Theme.dp(16) }
    SwirlSectionTitle { Layout.fillWidth: true; title: qsTr("应用兼容建议"); description: qsTr("供 Codex 与其他应用手动参考。") }
    SwirlTextArea { Layout.fillWidth: true; readOnly: true; selectByMouse: true; text: engineController.proxyEnvironmentAdvice; wrapMode: TextEdit.Wrap; background: null; Accessible.name: qsTr("代理环境兼容建议") }
    SwirlText { Layout.fillWidth: true; text: qsTr("当前版本尚未实现 TUN 数据通路与网关转发。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12); wrapMode: Text.Wrap }
}
