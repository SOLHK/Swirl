pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    readonly property Item motionTitle: subscriptionHeading.titleItem
    property string expandedId: ""
    property int filterIndex: 0
    property bool mutationSubmitting: false
    property string mutationRequestId: ""
    property string mutationKind: ""
    property string mutationSourceId: ""
    property var mutationOwner: null
    property var providerIdsBeforeSave: []
    property string mutationMessage: ""
    property var lastMutationCompletion: ({requestId: "", success: false})
    readonly property bool mutationPending: mutationSubmitting || mutationRequestId.length > 0
    readonly property bool editable: !mutationPending && !engineController.policyBusy && !engineController.imports.busy && !engineController.imports.hasPreview
    readonly property var providers: engineController.imports.providers
    readonly property string searchQuery: search.text.trim().toLowerCase()
    readonly property var listed: providers.filter(function(record) {
        return String(record.name).toLowerCase().indexOf(page.searchQuery) >= 0 && (page.filterIndex === 0 || (page.filterIndex === 1 ? record.status === "更新失败" : record.enabled))
    })
    readonly property int totalNodes: providers.reduce((total, record) => total + Number(record.nodes), 0)
    readonly property string operationMessage: mutationMessage || engineController.imports.message

    function edit(record, source) {
        if (!editable) return
        mutationMessage = ""
        addDialog.edit(record, source)
    }
    function finishMutation(success) {
        const owner = mutationOwner, kind = mutationKind, source = mutationSourceId, before = providerIdsBeforeSave
        mutationSubmitting = false; mutationRequestId = ""; mutationOwner = null; mutationKind = ""; mutationSourceId = ""; providerIdsBeforeSave = []
        if (owner) owner.pending = false
        if (!success) {
            mutationMessage = engineController.policyError || engineController.imports.message || qsTr("目录变更未能完成，请检查状态后重试。")
            if (owner && owner.errorMessage !== undefined) owner.errorMessage = mutationMessage
            return
        }
        let savedId = source
        if (kind === "save" && !savedId.length) {
            const added = providers.filter(provider => before.indexOf(provider.id) < 0)
            if (added.length !== 1) { mutationMessage = qsTr("来源已保存，但无法确认新增标识；请先检查列表再更新。"); return }
            savedId = String(added[0].id)
        }
        if (owner) { owner.markSaved(); owner.close() }
        if (kind === "save") engineController.imports.refreshSubscription(savedId)
    }
    function completeMutation(requestId, success) {
        if (!mutationRequestId.length || String(requestId) !== mutationRequestId) return
        if (success && String((engineController.policyReceipt || {}).request_id) !== mutationRequestId) success = false
        finishMutation(success)
    }
    function trackMutation(accepted, v2) {
        if (!accepted) { finishMutation(false); return }
        if (!v2) { finishMutation(true); return }
        mutationRequestId = String(engineController.policyRequestId); mutationSubmitting = false
        if (!mutationRequestId.length) { finishMutation(false); return }
        if (lastMutationCompletion.requestId === mutationRequestId) completeMutation(mutationRequestId, lastMutationCompletion.success)
        else if (!engineController.policyBusy && String((engineController.policyReceipt || {}).request_id) === mutationRequestId) completeMutation(mutationRequestId, true)
    }
    function beginMutation(kind, source, owner) {
        mutationMessage = ""; mutationKind = kind; mutationSourceId = String(source || ""); mutationOwner = owner
        providerIdsBeforeSave = providers.map(provider => provider.id); mutationSubmitting = true
        if (owner) owner.pending = true
    }
    function saveSource() {
        const v2 = engineController.policyV2Active
        beginMutation("save", addDialog.sourceId, addDialog)
        trackMutation(engineController.imports.saveSubscription(addDialog.sourceId, addDialog.sourceName, addDialog.sourceUrl, addDialog.intervalMinutes, addDialog.autoUpdate, addDialog.formatHint), v2)
    }
    function confirmDelete(record, source) {
        if (!editable) return
        mutationMessage = ""; deleteDialog.recordId = record.id; deleteDialog.recordName = record.name; deleteDialog.nodeCount = record.nodes
        if (source) SwirlMotion.noteTrigger(source)
        deleteDialog.open()
    }
    function removeSource() {
        const v2 = engineController.policyV2Active
        beginMutation("delete", deleteDialog.recordId, deleteDialog)
        trackMutation(engineController.imports.removeSubscription(deleteDialog.recordId), v2)
    }
    function removeLegacy() {
        const v2 = engineController.policyV2Active
        beginMutation("legacy", "", legacyDialog)
        trackMutation(engineController.imports.cleanLegacyNodes(), v2)
    }
    function reviewSource(record, source) {
        if (!editable) return
        if (source) SwirlMotion.noteTrigger(source)
        engineController.imports.reviewConfiguration(record.id)
        if (engineController.imports.hasConfigurationReview) reviewDialog.showReview(engineController.imports.configurationReview)
    }
    function applyReview() {
        const v2 = engineController.policyV2Active
        beginMutation("review", String(reviewDialog.review.sourceId || ""), reviewDialog)
        trackMutation(engineController.imports.applyReviewedConfiguration(), v2)
    }

    Shortcut { sequences: [StandardKey.Find]; enabled: AppState.currentPage === "subscriptions" && !addDialog.visible && !deleteDialog.visible && !reviewDialog.visible && !operationDialog.visible && !legacyDialog.visible; onActivated: { search.forceActiveFocus(); search.selectAll() } }
    SwirlAnimatedModel { id: subscriptionModel; source: page.listed; keyRole: "id" }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: Theme.pagePadding; spacing: Theme.dp(14)
        SwirlPageHeader {
            id:subscriptionHeading;Layout.fillWidth:true;title:qsTr("订阅来源")
            description:qsTr("管理更新节奏与来源节点，保留每次操作的结果。")
            metadata:qsTr("%1 个来源，%2 个节点").arg(page.providers.length).arg(page.totalNodes)
            SubscriptionAction {objectName:"refreshAllSubscriptions";text:qsTr("更新全部");iconName:"refresh-source";enabled:page.editable&&page.providers.length>0;onClicked:engineController.imports.refreshAll()}
            SubscriptionAction {id:add;objectName:"addSubscription";text:qsTr("添加订阅");solid:true;iconName:"plus";enabled:page.editable;onClicked:page.edit(null,add)}
        }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(12)
            SwirlSearchField {id:search;objectName:"subscriptionSearch";Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(140);placeholderText:qsTr("搜索来源名称");Accessible.name:placeholderText}
            SwirlSegmentedControl {objectName:"subscriptionFilter";Layout.preferredWidth:Theme.dp(234);Layout.preferredHeight:Theme.dp(34);options:[qsTr("全部"),qsTr("更新失败"),qsTr("自动更新")];currentIndex:page.filterIndex;onActivated:index=>page.filterIndex=index}
        }
        RowLayout {
            Layout.fillWidth: true; visible: engineController.imports.legacyNodeCount > 0; spacing: Theme.dp(8)
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("%1 个历史节点归属待确认，已保留。").arg(engineController.imports.legacyNodeCount); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SubscriptionAction { objectName: "reviewLegacyNodes"; text: qsTr("查看"); onClicked: { AppState.navigate("proxies"); AppState.notice(qsTr("在节点来源中选择「历史未归属」查看。")) } }
            SubscriptionAction { objectName: "cleanLegacyNodes"; text: qsTr("清理"); danger: true; enabled: page.editable; onClicked: { page.mutationMessage = ""; legacyDialog.open() } }
        }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.dp(12)
            SwirlText { text: qsTr("订阅来源"); leftPadding: Theme.dp(8); Layout.fillWidth: true; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SwirlText { text: qsTr("节点"); Layout.preferredWidth: Theme.dp(48); horizontalAlignment: Text.AlignRight; color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SwirlText { text: qsTr("最近更新"); Layout.preferredWidth: Theme.dp(126); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            Item { Layout.preferredWidth: Theme.dp(88) }
        }
        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: Theme.borderWidth; color: Theme.border }
        Item {
            objectName: "subscriptionsSinglePanel"
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0
            ListView {
                id: subscriptionList; objectName: "subscriptionList"
                anchors.fill: parent; model: subscriptionModel; clip: true; reuseItems: true; pixelAligned: true
                ScrollBar.vertical: SwirlScrollBar {}
                add: Transition { enabled: !SwirlMotion.reduced; ParallelAnimation { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: SwirlMotion.releaseDuration } NumberAnimation { property: "insertionOffset"; from: Theme.dp(6); to: 0; duration: SwirlMotion.listDuration; easing.type: SwirlMotion.standardEasing } } }
                remove: Transition { enabled: !SwirlMotion.reduced; ParallelAnimation { NumberAnimation { property: "opacity"; to: 0; duration: SwirlMotion.exitDuration } NumberAnimation { property: "x"; to: Theme.dp(-8); duration: SwirlMotion.exitDuration; easing.type: Easing.InCubic } } }
                displaced: Transition { enabled: !SwirlMotion.reduced; NumberAnimation { property: "y"; duration: SwirlMotion.selectionDuration; easing.type: SwirlMotion.standardEasing } }
                delegate: SubscriptionRow {
                    id: provider
                    required property var entry
                    record: entry; width: Math.floor(subscriptionList.width)
                    expanded: page.expandedId === record.id
                    editable: page.editable; refreshable: page.editable
                    ListView.onPooled: { settle(); visible = false }
                    ListView.onReused: { visible = true; settle() }
                    onExpansionRequested: page.expandedId = expanded ? "" : record.id
                    onRefreshRequested: { if (record.canCancel) engineController.imports.cancelRefresh(record.id); else engineController.imports.refreshSubscription(record.id) }
                    onEditRequested: source => page.edit(record, source)
                    onDeleteRequested: source => page.confirmDelete(record, source)
                    onReviewRequested: source => page.reviewSource(record, source)
                    onNodesRequested: { AppState.navigate("proxies"); AppState.notice(qsTr("在节点来源中选择「%1」查看。").arg(record.name)) }
                }
            }
            ColumnLayout {
                objectName: "subscriptionsEmptyState"
                visible: subscriptionList.count === 0; anchors.centerIn: parent; width: Math.min(parent.width, Theme.dp(370)); spacing: Theme.dp(12)
                SwirlEmptyState { Layout.fillWidth: true; headline: page.providers.length ? qsTr("没有匹配的订阅") : qsTr("添加第一个订阅来源"); detail: page.providers.length ? qsTr("调整搜索或筛选条件，查看其他来源。") : qsTr("安全保存订阅地址，自动识别格式并管理来源节点。") }
                SubscriptionAction { Layout.alignment: Qt.AlignHCenter; solid: true; text: page.providers.length ? qsTr("清空筛选") : qsTr("添加订阅"); enabled: page.editable; onClicked: { if (page.providers.length) { search.clear(); page.filterIndex = 0 } else page.edit(null, this) } }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.minimumHeight:Theme.dp(30); spacing: Theme.dp(8)
            SwirlText { text: qsTr("最近操作"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SwirlText {
                objectName: "subscriptionOperationMessage"; Layout.fillWidth: true
                text: page.operationMessage || qsTr("自动更新只维护当前来源的节点；完整配置需要单独审阅。"); textFormat: Text.PlainText; elide: Text.ElideRight
                color: page.mutationMessage.length ? Theme.red : Theme.muted; font.pixelSize: Theme.fontSize(12)
            }
            SubscriptionAction { visible:page.operationMessage.length>0; text: qsTr("详情"); onClicked: operationDialog.open() }
        }
    }
    SwirlDialog {
        id: operationDialog; ownerItem: page; title: qsTr("最近操作详情"); guardChanges: false
        contentItem: ColumnLayout {
            spacing: Theme.dp(16)
            ScrollView {
                Layout.fillWidth: true; Layout.preferredHeight: Math.min(Theme.dp(280), operationText.implicitHeight)
                TextArea { id: operationText; text: page.operationMessage || qsTr("自动更新只维护当前来源的节点；完整配置需要单独审阅。"); textFormat: TextEdit.PlainText; readOnly: true; wrapMode: TextEdit.Wrap; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSize(12); background: null; selectByMouse: true }
            }
            SubscriptionAction { Layout.alignment: Qt.AlignRight; text: qsTr("关闭"); solid: true; onClicked: operationDialog.close() }
        }
    }
    SubscriptionDialog { id: addDialog; ownerItem: page; canSave: !engineController.policyBusy && !engineController.imports.busy; recoveryRequired: engineController.policyApplyState === "reconciling"; onSaveRequested: page.saveSource(); onRecoveryRequested: engineController.recoverPolicyConfiguration() }
    ConfigurationReviewDialog {
        id: reviewDialog; ownerItem: page
        canSubmit: !engineController.policyBusy && !engineController.imports.busy
        recoveryRequired: engineController.policyApplyState === "reconciling"
        onApplyRequested: page.applyReview()
        onCancelRequested: engineController.imports.cancelConfigurationReview()
        onRecoveryRequested: engineController.recoverPolicyConfiguration()
        onReviewAgainRequested: { engineController.imports.reviewConfiguration(String(review.sourceId || "")); showReview(engineController.imports.configurationReview) }
    }
    SwirlDialog {
        id: deleteDialog
        ownerItem: page; title: qsTr("删除订阅？"); property string recordId: ""; property string recordName: ""; property int nodeCount: 0; property bool pending: false
        guardChanges: false; dismissBlocked: pending
        ColumnLayout {
            width: parent.width; spacing: Theme.dp(12)
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("删除「%1」及其 %2 个所属节点。").arg(deleteDialog.recordName).arg(deleteDialog.nodeCount); textFormat: Text.PlainText; color: Theme.text }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("相关连接将断开。引用这些节点的策略将显示出口失效，需重新分配；不会自动改为直连。手动节点和历史未归属节点保留。"); color: Theme.muted; font.pixelSize: Theme.fontSize(12) }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0; text: page.mutationMessage || (deleteDialog.pending ? engineController.policyError : ""); textFormat: Text.PlainText; color: Theme.red }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                SubscriptionAction { objectName: "recoverSubscriptionDelete"; text: qsTr("恢复已保存的操作"); visible: deleteDialog.pending && engineController.policyApplyState === "reconciling"; onClicked: engineController.recoverPolicyConfiguration() }
                SubscriptionAction { text: qsTr("取消"); enabled: !deleteDialog.pending; onClicked: deleteDialog.close() }
                SubscriptionAction { objectName: "confirmSubscriptionDelete"; text: deleteDialog.pending ? qsTr("正在删除…") : qsTr("删除"); enabled: !deleteDialog.pending; danger: true; onClicked: page.removeSource() }
            }
        }
    }
    SwirlDialog {
        id: legacyDialog
        ownerItem: page; objectName: "legacyNodesDialog"; title: qsTr("清理历史未归属节点？"); property bool pending: false
        guardChanges: false; dismissBlocked: pending
        ColumnLayout {
            width: parent.width; spacing: Theme.dp(12)
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; text: qsTr("将删除来源缺失的 %1 个历史节点，其中可能包含旧版手动节点。请先检查并备份；此操作不能撤销。明确归属的手动节点和现有订阅保持不变。").arg(engineController.imports.legacyNodeCount); color: Theme.text }
            SwirlText { Layout.fillWidth: true; wrapMode: Text.Wrap; visible: text.length > 0; text: page.mutationMessage || (legacyDialog.pending ? engineController.policyError : ""); textFormat: Text.PlainText; color: Theme.red }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                SubscriptionAction { objectName: "recoverLegacyCleanup"; text: qsTr("恢复已保存的操作"); visible: legacyDialog.pending && engineController.policyApplyState === "reconciling"; onClicked: engineController.recoverPolicyConfiguration() }
                SubscriptionAction { text: qsTr("取消"); enabled: !legacyDialog.pending; onClicked: legacyDialog.close() }
                SubscriptionAction { objectName: "confirmLegacyNodesDelete"; text: legacyDialog.pending ? qsTr("正在清理…") : qsTr("确认清理"); enabled: !legacyDialog.pending; danger: true; onClicked: page.removeLegacy() }
            }
        }
    }
    Connections {
        target: engineController
        function onPolicyApplyFinished(requestId, success) { page.lastMutationCompletion = {requestId: String(requestId), success: success}; page.completeMutation(String(requestId), success) }
    }
    Connections {
        target: engineController.imports
        function onChanged() {
            if (reviewDialog.visible && engineController.imports.hasConfigurationReview) reviewDialog.review = engineController.imports.configurationReview
        }
    }
}
