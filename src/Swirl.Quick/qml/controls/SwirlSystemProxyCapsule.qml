import QtQuick
import SwirlQuick

SwirlStatusCapsule {
    id: control
    required property var controller
    readonly property bool proxyEnabled: controller.proxyRequested || controller.systemProxy.owned || controller.processAlive
    readonly property bool proxyOwned: controller.systemProxy.owned && controller.systemProxy.enabled && controller.processAlive
    readonly property string operationError: controller.systemProxy.stateReadError || (controller.systemProxy.owned ? controller.systemProxy.error : "") || controller.routingError || controller.policyError || controller.systemProxy.error || (controller.errorCode !== "None" ? controller.error : "")
    label: controller.systemProxyStopping ? qsTr("正在关闭代理…") : controller.systemProxyBusy ? qsTr("正在开启代理…") : proxyOwned ? qsTr("系统代理 · 已开") : proxyEnabled ? qsTr("代理 · 仅内核") : controller.systemProxy.systemEnabled ? qsTr("系统代理 · 外部") : qsTr("系统代理 · 已关")
    detail: operationError || (controller.systemProxyStopping ? qsTr("正在结束配置操作、恢复已接管的系统设置并停止内核") : controller.systemProxyBusy ? qsTr("正在启动已保存策略并检查代理端口，点击取消") : proxyEnabled ? controller.systemProxy.enabled ? qsTr("Swirl 已接管系统代理，点击恢复原设置并停止内核") : qsTr("Swirl 内核正在运行，点击停止；其他应用的系统代理保持不变") : controller.systemProxy.systemEnabled ? qsTr("其他应用的系统代理已开启；点击启动 Swirl 并保存接管前的设置") : qsTr("点击启动已保存策略并通过 Swirl 开启代理"))
    tone: operationError.length ? "warning" : proxyOwned ? "success" : "neutral"
    activityPhase:controller.systemProxyBusy || controller.systemProxyStopping?"pending":operationError.length?"failed":controller.systemProxy.owned && controller.systemProxy.enabled && controller.processAlive?"succeeded":"idle"
    enabled: !controller.systemProxyStopping && (proxyEnabled || (!controller.busy && !controller.policyBusy && !controller.imports.busy && !controller.systemProxy.stateReadError.length))
    onClicked: controller.toggleSystemProxy()
}
