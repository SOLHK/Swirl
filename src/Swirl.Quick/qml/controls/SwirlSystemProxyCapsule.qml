import QtQuick
import SwirlQuick

SwirlStatusCapsule {
    proxyWing: true
    id: control
    required property var controller
    readonly property bool proxyEnabled: controller.proxyRequested || controller.systemProxy.owned
    readonly property bool proxyOwned: controller.systemProxy.owned && controller.systemProxy.enabled && controller.processAlive
    readonly property string operationError: controller.systemProxy.stateReadError || (controller.systemProxy.owned ? controller.systemProxy.error : "") || controller.routingError || controller.policyError || controller.systemProxy.error || (controller.errorCode !== "None" ? controller.error : "")
    label: controller.systemProxyStopping ? qsTr("正在关闭代理…") : controller.systemProxyBusy ? qsTr("正在开启代理…") : qsTr("系统代理")
    detail: operationError || (controller.systemProxyStopping ? qsTr("正在恢复已接管的系统设置") : controller.systemProxyBusy ? qsTr("正在检查代理端口和出口，点击取消") : proxyEnabled ? controller.tunEnabled ? qsTr("Swirl 已接管系统代理，点击恢复原设置；TUN 继续运行。") : qsTr("Swirl 已接管系统代理，点击恢复原设置并停止内核。") : controller.systemProxy.systemEnabled ? qsTr("其他应用的系统代理已开启；点击通过 Swirl 接管并保存原设置") : qsTr("点击通过 Swirl 开启系统代理"))
    tone: operationError.length ? "warning" : proxyOwned ? "success" : "neutral"
    activityPhase:controller.systemProxyBusy || controller.systemProxyStopping?"pending":operationError.length?"failed":controller.systemProxy.owned && controller.systemProxy.enabled && controller.processAlive?"succeeded":"idle"
    Accessible.description: detail
    enabled: !controller.systemProxyStopping && (proxyEnabled || (!controller.busy && !controller.policyBusy && !controller.imports.busy && !controller.systemProxy.stateReadError.length))
    onClicked: controller.toggleSystemProxy()
}
