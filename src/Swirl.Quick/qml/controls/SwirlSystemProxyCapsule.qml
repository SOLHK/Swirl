import QtQuick
import SwirlQuick

SwirlStatusCapsule {
    id: control
    required property var controller
    readonly property bool proxyEnabled: controller.systemProxy.systemEnabled
    readonly property string operationError: controller.systemProxy.stateReadError || controller.routingError || controller.systemProxy.error || controller.error
    label: controller.systemProxyBusy ? qsTr("正在设置系统代理…") : proxyEnabled ? qsTr("关闭系统代理") : qsTr("开启系统代理")
    detail: operationError || (proxyEnabled ? qsTr("系统代理已开启，点击关闭") : qsTr("系统代理已关闭，点击通过 Swirl 开启"))
    tone: operationError.length ? "warning" : proxyEnabled ? "success" : "neutral"
    enabled: !controller.systemProxyBusy && (!controller.busy || proxyEnabled) && !controller.systemProxy.stateReadError.length
    onClicked: controller.toggleSystemProxy()
}
