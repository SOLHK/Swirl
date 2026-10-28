pragma ComponentBehavior: Bound
import QtQuick
import QtQml.Models
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

SwirlMotionButton {
    id: control
    required property var engineController
    readonly property var document: engineController.policyDocument || ({})
    readonly property var receipt: engineController.policyReceipt || ({})
    readonly property bool busy: engineController.policyBusy
    readonly property bool editable: !busy && !engineController.policyMigrationRequired
        && engineController.policyApplyState !== "reconciling" && Boolean(document.default_policy)
    readonly property string appliedMode: String(engineController.routingMode || "rule")
    readonly property bool pending: submitting || pendingRequestId.length > 0
    readonly property bool savedForNextConnection: !engineController.processAlive && receipt.scope === "saved-next-connect"
    readonly property var modes: [
        { key: "rule", label: qsTr("规则分流"), description: qsTr("国内直连，其余按专属或默认策略") },
        { key: "global", label: qsTr("全局代理"), description: qsTr("普通流量走默认出口，保留必要本地例外") },
        { key: "direct", label: qsTr("直连模式"), description: qsTr("受接管流量不经过代理节点") }
    ]
    property string settledMode: ""
    property string requestedMode: ""
    property string pendingRequestId: ""
    property bool submitting: false
    property string message: ""
    property var lastCompletion: ({ requestId: "", success: false })
    // Presentation reads the acknowledged snapshot only. Reading appliedMode
    // here can lazily emit its change handler, which writes settledMode while
    // this binding is evaluating and re-enters the same display binding.
    readonly property string displayMode: settledMode
    readonly property string statusText: {
        if (pending) return qsTr("正在切换到%1").arg(control.modeLabel(requestedMode))
        if (message.length) return message
        if (engineController.policyMigrationRequired) return qsTr("请先在策略页面确认旧配置迁移")
        if (engineController.policyApplyState === "reconciling") return qsTr("配置状态需要恢复，请前往策略页面")
        if (busy) return qsTr("正在处理配置，请稍候")
        if (savedForNextConnection) return qsTr("已保存，下次连接生效")
        if (!engineController.processAlive) return qsTr("当前未连接；修改后在下次连接生效")
        if (receipt.scope === "new-requests-applied"
                && String(engineController.appliedRevision) === String(engineController.savedRevision))
            return qsTr("已生效，新连接使用当前模式")
        return qsTr("当前运行模式；实际出口请查看连接详情")
    }
    objectName: "activityOutboundMode"
    implicitWidth: Math.ceil(modeCaption.implicitWidth) + Theme.dp(24)
    implicitHeight: Theme.dp(28)
    padding: 0
    leftPadding: Theme.dp(12)
    rightPadding: Theme.dp(12)
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    text: modeLabel(displayMode)
    Accessible.name: qsTr("出站模式：%1").arg(text)
    Accessible.description: statusText
    ToolTip.text: qsTr("点击更改出站模式。%1").arg(statusText)
    ToolTip.visible: (hovered || visualFocus) && !modeMenu.visible
    ToolTip.delay: 650

    function modeLabel(mode) {
        const option = modes.find(item => item.key === mode)
        return option ? option.label : qsTr("未知模式")
    }
    function finishCommand(requestId, success) {
        if (!pendingRequestId.length || String(requestId) !== pendingRequestId) return
        if (success && String(receipt.request_id) !== pendingRequestId) {
            message = qsTr("未收到匹配的配置回执，请前往策略页面检查。")
        } else if (success) {
            message = ""
            settledMode = appliedMode
            AppState.notice(savedForNextConnection ? qsTr("已保存，下次连接生效")
                : qsTr("已切换到%1，新连接使用此模式").arg(modeLabel(appliedMode)))
        } else {
            message = qsTr("切换失败，仍使用%1。%2").arg(modeLabel(appliedMode))
                .arg(engineController.policyError || qsTr("请稍后重试。"))
        }
        requestedMode = ""
        pendingRequestId = ""
        if (message.length) AppState.notice(message)
    }
    function requestMode(mode) {
        if (!editable || !modes.some(item => item.key === mode)) return false
        if (mode === String(document.mode || appliedMode)) return true
        const candidate = Policy.copy(document)
        candidate.mode = mode
        const validation = engineController.validatePolicyDocument(candidate)
        if (!validation.ok) {
            message = Policy.validationText(validation, candidate)
            AppState.notice(message)
            return false
        }
        message = ""
        requestedMode = mode
        submitting = true
        const accepted = engineController.applyPolicyDocument(candidate)
        if (accepted) pendingRequestId = String(engineController.policyRequestId)
        submitting = false
        if (!accepted || !pendingRequestId.length) {
            requestedMode = ""
            message = engineController.policyError || qsTr("当前无法切换模式，请稍后重试。")
            AppState.notice(message)
            return false
        }
        if (lastCompletion.requestId === pendingRequestId) finishCommand(pendingRequestId, lastCompletion.success)
        else if (!busy && String(receipt.request_id) === pendingRequestId) finishCommand(pendingRequestId, true)
        return true
    }
    onAppliedModeChanged: if (!busy && !pending) settledMode = appliedMode
    onBusyChanged: if (!busy && !pending) settledMode = appliedMode
    Component.onCompleted: settledMode = appliedMode
    onClicked: modeMenu.showAt()
    background: SwirlClearGlassSurface {
        objectName: "activityOutboundModeSurface"
        radius: Theme.pillRadius(height)
        hovered: control.hovered
        pressed: control.down
        focused: false
        border.width: Theme.increaseContrast ? 1 / Screen.devicePixelRatio : 0
        border.color: Theme.text
    }
    contentItem: SwirlText {
        id: modeCaption
        objectName: "activityOutboundModeText"
        text: control.text
        textFormat: Text.PlainText
        textRole: "smallLabel"
        color: control.pending ? Theme.muted : Theme.text
        font.pixelSize: Theme.fontSize(11)
        font.weight: Theme.bodyFontWeight
        font.underline: control.visualFocus
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    SwirlContextMenu {
        id: modeMenu
        items: []
        objectName: "activityOutboundModeMenu"
        x: 0
        y: control.height + Theme.dp(5)
        width: Theme.dp(310)
        margins: Theme.dp(8)
        padding: Theme.dp(6)
        popupType: Popup.Item
        transformOrigin: Item.TopLeft
        background: Rectangle {
            radius: Theme.popupRadius
            color: Theme.material("floating")
            border.width: Theme.dp(1)
            border.color: Theme.glassRim
        }
        Instantiator {
            model: control.modes
            onObjectAdded: (index, object) => modeMenu.insertItem(index, object)
            onObjectRemoved: (index, object) => modeMenu.removeItem(object)
            delegate: MenuItem {
                id: option
                required property var modelData
                objectName: "activityMode-" + modelData.key
                height: Theme.dp(59)
                text: modelData.label
                enabled: control.editable
                Accessible.name: text + ", " + modelData.description
                Accessible.checkable: true
                Accessible.checked: control.displayMode === modelData.key
                Accessible.description: control.displayMode === modelData.key ? qsTr("当前模式") : ""
                background: Rectangle {
                    radius: Theme.dp(5)
                    color: option.highlighted || option.activeFocus ? Theme.selected : "transparent"
                }
                contentItem: RowLayout {
                    spacing: Theme.dp(9)
                    SwirlIcon {
                        name: "checkmark"
                        size: Theme.dp(14)
                        opacity: control.displayMode === option.modelData.key ? 1 : 0
                        color: Theme.text
                        Accessible.ignored: true
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.dp(3)
                        SwirlText { Layout.fillWidth: true; text: option.text; color: option.enabled ? Theme.text : Theme.muted; font.pixelSize: Theme.fontSize(13) }
                        SwirlText { Layout.fillWidth: true; text: option.modelData.description; color: Theme.muted; font.pixelSize: Theme.fontSize(11); elide: Text.ElideRight }
                    }
                }
                onTriggered: control.requestMode(modelData.key)
            }
        }
        MenuSeparator { contentItem: Rectangle { implicitHeight: 1; color: Theme.separator } }
        MenuItem {
            enabled: false
            height: Math.max(Theme.dp(40), statusLabel.implicitHeight + Theme.dp(14))
            contentItem: SwirlText {
                id: statusLabel
                text: control.statusText
                textFormat: Text.PlainText
                color: control.message.length ? Theme.orange : Theme.muted
                font.pixelSize: Theme.fontSize(11)
                wrapMode: Text.Wrap
            }
        }
        MenuItem {
            id: strategyLink
            text: qsTr("前往策略")
            height: Theme.dp(34)
            contentItem: SwirlText { text: strategyLink.text; color: Theme.text; font.pixelSize: Theme.fontSize(12); verticalAlignment: Text.AlignVCenter }
            background: Rectangle { radius: Theme.dp(5); color: strategyLink.highlighted ? Theme.selected : "transparent" }
            onTriggered: AppState.navigate("policies")
        }
    }
    Connections {
        target: control.engineController
        function onPolicyApplyFinished(requestId, success) {
            control.lastCompletion = { requestId: String(requestId), success: success }
            control.finishCommand(requestId, success)
        }
    }
}
