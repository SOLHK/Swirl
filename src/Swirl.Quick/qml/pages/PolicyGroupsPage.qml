pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
import "../components/PolicyHelpers.js" as Policy

Item {
    id:page
    required property var engineController
    property int tabIndex:0
    property var pendingOwner:null
    property string pendingRequestId:""
    property var lastCompletion:({requestId:"",success:false})
    property string localMessage:""
    property var targetContext:({kind:"default"})
    readonly property var document:engineController.policyDocument||({})
    readonly property var targets:engineController.policyTargetOptions||[]
    readonly property var services:document.service_policies||[]
    readonly property var groups:document.groups||[]
    readonly property bool editable:!engineController.policyBusy&&!engineController.policyMigrationRequired&&engineController.policyApplyState!=="reconciling"&&Boolean(document.default_policy)
    readonly property string configuredMode:String(document.mode||engineController.routingMode)
    readonly property int modeIndex:["rule","global","direct"].indexOf(configuredMode)
    readonly property string statusText: {
        if(engineController.policyBusy)return ({preparing:qsTr("正在校验配置…"),persisting_intent:qsTr("正在保存变更…"),activating:qsTr("正在应用配置…"),committing:qsTr("正在完成保存…"),reconciling:qsTr("正在确认配置状态…")})[engineController.policyApplyState]||qsTr("正在处理配置…")
        if(engineController.policyMigrationRequired)return qsTr("需要确认旧配置迁移")
        const receipt=engineController.policyReceipt||({})
        if(receipt.scope==="new-requests-applied"&&engineController.processAlive&&String(engineController.appliedRevision)===String(engineController.savedRevision))return qsTr("已生效，新连接使用当前配置")
        if(receipt.scope==="saved-next-connect")return qsTr("已保存，下次连接生效")
        return engineController.processAlive?qsTr("查看连接详情以确认实际出口"):qsTr("配置保存后可连接")
    }
    function candidateWithRecord(collection,record) {
        const next=Policy.copy(document);const rows=next[collection]||[];const index=rows.findIndex(item=>item.id===record.id)
        if(index<0)rows.push(Policy.copy(record));else rows[index]=Policy.copy(record)
        next[collection]=rows;return next
    }
    function ownerError(owner,message) {
        if(owner){owner.pending=false;if(typeof owner.showError==="function")owner.showError(message);else owner.message=String(message)}
        else {localMessage=String(message);pageMessage.forceActiveFocus()}
    }
    function finishCommand(requestId,success) {
        if(String(requestId)!==pendingRequestId)return
        const owner=pendingOwner;const receipt=engineController.policyReceipt||({})
        if(success&&String(receipt.request_id)!==pendingRequestId){ownerError(owner,qsTr("未收到匹配的配置回执，请检查状态后重试。"));pendingOwner=null;pendingRequestId="";return}
        if(owner){owner.pending=false;if(success){owner.markSaved();owner.close()}else ownerError(owner,engineController.policyError||qsTr("配置未能应用，请修改后重试。"))}
        pendingOwner=null;pendingRequestId=""
    }
    function registerCommand(owner,accepted) {
        if(!accepted){ownerError(owner,engineController.policyError||qsTr("当前无法修改配置，请稍后重试。"));pendingOwner=null;return false}
        pendingOwner=owner;pendingRequestId=String(engineController.policyRequestId)
        if(owner){owner.pending=true;owner.pendingRequestId=pendingRequestId}
        if(lastCompletion.requestId===pendingRequestId){finishCommand(pendingRequestId,lastCompletion.success);return true}
        const receipt=engineController.policyReceipt||({})
        if(!engineController.policyBusy&&String(receipt.request_id)===pendingRequestId)finishCommand(pendingRequestId,true)
        return true
    }
    function submit(candidate,owner) {
        if(!editable){ownerError(owner,qsTr("请等待当前操作完成，或先确认旧配置迁移。"));return false}
        const validation=engineController.validatePolicyDocument(candidate)
        if(!validation.ok){ownerError(owner,Policy.validationText(validation,candidate));return false}
        if(owner&&owner.conflictReviewDigest!==undefined&&Policy.conflicts(validation).length){
            const digest=String(engineController.savedRevision)+":"+String(validation.plan_digest||Qt.md5(JSON.stringify(candidate)))
            if(owner.conflictReviewDigest!==digest){owner.conflictReviewDigest=digest;owner.message=Policy.validationText(validation,candidate);owner.messageIsError=false;return false}
        }
        if(owner)owner.pending=true
        localMessage="";return registerCommand(owner,engineController.applyPolicyDocument(candidate))
    }
    function validate(candidate,owner) {
        const result=engineController.validatePolicyDocument(candidate);owner.message=Policy.validationText(result,candidate);owner.messageIsError=!result.ok
        if(result.ok&&Policy.conflicts(result).length)owner.conflictReviewDigest=String(engineController.savedRevision)+":"+String(result.plan_digest||Qt.md5(JSON.stringify(candidate)))
    }
    function nextPriority() {return services.reduce((value,record)=>Math.max(value,Number(record.priority)+10),0)}
    function editService(record,source) {
        serviceEditor.begin(record||{id:engineController.newPolicyId(),name:"",enabled:true,priority:nextPriority(),domains:[],target:{kind:"unconfigured"}},source,!record)
    }
    function editGroup(record,source) {groupEditor.begin(record||{id:engineController.newPolicyId(),name:"",strategy:"manual",members:[]},source,!record)}
    function moveService(id,direction) {
        const rows=services.slice().sort((a,b)=>a.priority-b.priority);const index=rows.findIndex(record=>record.id===id);const destination=index+direction
        if(index<0||destination<0||destination>=rows.length)return
        const record=rows.splice(index,1)[0];rows.splice(destination,0,record)
        const next=Policy.copy(document);next.service_policies=rows.map((item,index)=>Object.assign({},item,{priority:index*10}));submit(next,null)
    }
    function openTarget(kind,record,source) {
        targetContext={kind:kind,id:record?record.id:""}
        targetPicker.allowDirect=kind==="service";targetPicker.excludedGroupId="";targetPicker.options=targets
        let current=kind==="default"?document.default_policy.target:record.target
        if(kind==="member"){
            current=record.selected||{kind:"unconfigured"};targetPicker.excludedGroupId=record.id
            targetPicker.options=(record.members||[]).map(member=>targets.find(option=>Policy.sameTarget(option,member))||{kind:member.kind,id:member.id||"",name:Policy.targetName(member,targets),available:false})
            targetPicker.allowDirect=record.members.some(member=>member.kind==="direct")
        }
        targetPicker.begin(current,source)
    }
    function chooseTarget(target) {
        const next=Policy.copy(document)
        if(targetContext.kind==="default")next.default_policy.target=target
        else {const rows=targetContext.kind==="service"?next.service_policies:next.groups;const record=rows.find(item=>item.id===targetContext.id);if(!record){ownerError(targetPicker,qsTr("此策略已不存在，请重新打开。"));return}if(targetContext.kind==="service")record.target=target;else record.selected=target}
        submit(next,targetPicker)
    }
    function requestDelete(kind,record,source) {deleteDialog.kind=kind;deleteDialog.recordId=record.id;deleteDialog.recordName=record.name;deleteDialog.message="";deleteDialog.pending=false;deleteDialog.heroSource=source;deleteDialog.open()}
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(12)
        RowLayout {Layout.fillWidth:true
            SwirlText {textRole:"pageTitle";text:qsTr("策略");color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold;Layout.fillWidth:true}
            SwirlButton {text:qsTr("查看规则");quiet:true;onClicked:AppState.navigate("rules")}
            SwirlButton {text:qsTr("节点库");quiet:true;onClicked:AppState.navigate("proxies")}
            SwirlButton {id:addButton;objectName:page.tabIndex===0?"addServicePolicy":"addPolicyGroup";text:page.tabIndex===0?qsTr("添加策略"):qsTr("添加策略组");primary:true;iconName:"plus";enabled:page.editable;onClicked:{if(page.tabIndex===0)page.editService(null,addButton);else page.editGroup(null,addButton)}}
        }
        SwirlSegmentedControl {id:tabs;objectName:"policyTabs";Layout.fillWidth:true;Layout.maximumWidth:Theme.dp(420);options:[qsTr("服务分配"),qsTr("策略组")];textPixelSize:13;currentIndex:page.tabIndex;onActivated:index=>page.tabIndex=index}
        RowLayout {Layout.fillWidth:true;spacing:Theme.dp(10)
            SwirlButton {objectName:"policyConnectButton";text:page.engineController.nodeBusy?qsTr("正在连接…"):page.engineController.processAlive?qsTr("断开出口"):qsTr("连接");enabled:!page.engineController.policyBusy&&!page.engineController.nodeBusy&&(page.engineController.processAlive||(page.editable&&(page.configuredMode==="direct"||["node","group"].indexOf(((page.document.default_policy||{}).target||{}).kind)>=0)));onClicked:{if(page.engineController.processAlive)page.engineController.disconnectNode();else page.engineController.connectConfiguredPolicy()}}
            SwirlComboBox {id:modePicker;objectName:"routingModePicker";Layout.preferredWidth:Theme.dp(142);model:[qsTr("规则分流"),qsTr("全局代理"),qsTr("直连模式")];currentIndex:Math.max(0,page.modeIndex);enabled:page.editable;Accessible.name:qsTr("出站模式");onActivated:index=>{const next=Policy.copy(page.document);next.mode=["rule","global","direct"][index];currentIndex=Qt.binding(function(){return Math.max(0,page.modeIndex)});page.submit(next,null)}}
            Item {Layout.fillWidth:true}
            SwirlText {text:qsTr("端口");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
            SwirlTextField {objectName:"policyProxyPort";Layout.preferredWidth:Theme.dp(76);text:String(page.engineController.proxyPort);enabled:page.engineController.canStart&&!page.engineController.policyBusy;validator:IntValidator {bottom:1;top:65535}horizontalAlignment:TextInput.AlignHCenter;Accessible.name:qsTr("本机代理端口");onEditingFinished:{if(acceptableInput)page.engineController.proxyPort=Number(text);text=Qt.binding(function(){return String(page.engineController.proxyPort)})}}
        }
        SwirlStatusBadge {label:page.statusText;busy:page.engineController.policyBusy;tone:page.engineController.policyError.length?"warning":"neutral"}
        SwirlText {id:pageMessage;objectName:"policyApplyMessage";Layout.fillWidth:true;visible:text.length>0;text:page.localMessage||page.engineController.policyError||page.engineController.nodeError||page.engineController.routingError;textFormat:Text.PlainText;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;activeFocusOnTab:true;Accessible.name:text}
        RowLayout {Layout.fillWidth:true;visible:page.engineController.policyMigrationRequired
            SwirlText {Layout.fillWidth:true;text:qsTr("旧配置需要迁移为稳定策略引用，确认后才能编辑。");color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
            SwirlButton {id:reviewMigration;objectName:"reviewPolicyMigration";text:qsTr("查看迁移说明");enabled:!page.engineController.policyBusy;onClicked:{migrationDialog.message="";migrationDialog.pending=false;migrationDialog.heroSource=reviewMigration;migrationDialog.open()}}
        }
        RowLayout {Layout.fillWidth:true;visible:page.engineController.policyApplyState==="reconciling"
            SwirlText {Layout.fillWidth:true;text:qsTr("配置操作需要恢复，完成前不会使用旧凭据重新连接。");color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
            SwirlButton {objectName:"recoverPolicyConfiguration";text:qsTr("恢复已保存的操作");enabled:page.engineController.policyApplyState==="reconciling";onClicked:{page.localMessage="";page.engineController.recoverPolicyConfiguration()}}
        }
        ServiceAssignments {Layout.fillWidth:true;Layout.fillHeight:true;visible:page.tabIndex===0;defaultPolicy:page.document.default_policy||{target:{kind:"unconfigured"}};records:page.services;targetOptions:page.targets;editable:page.editable;onDefaultTargetRequested:source=>page.openTarget("default",null,source);onTargetRequested:(record,source)=>page.openTarget("service",record,source);onEditRequested:(record,source)=>page.editService(record,source);onEnabledRequested:(id,enabled)=>{const next=Policy.copy(page.document);const record=next.service_policies.find(item=>item.id===id);if(record){record.enabled=enabled;page.submit(next,null)}} onMoveRequested:(id,direction)=>page.moveService(id,direction);onDeleteRequested:(record,source)=>page.requestDelete("service",record,source)}
        PolicyGroupList {Layout.fillWidth:true;Layout.fillHeight:true;visible:page.tabIndex===1;records:page.groups;targetOptions:page.targets;editable:page.editable;running:page.engineController.processAlive;onEditRequested:(record,source)=>page.editGroup(record,source);onMemberRequested:(record,source)=>page.openTarget("member",record,source);onDeleteRequested:(record,source)=>page.requestDelete("group",record,source)}
    }
    PolicyTargetPicker {id:targetPicker;ownerItem:page;recoveryAvailable:page.engineController.policyApplyState==="reconciling";onRecoveryRequested:page.engineController.recoverPolicyConfiguration();onTargetChosen:target=>page.chooseTarget(target)}
    ServicePolicyDialog {id:serviceEditor;ownerItem:page;targetOptions:page.targets;recoveryAvailable:page.engineController.policyApplyState==="reconciling";onRecoveryRequested:page.engineController.recoverPolicyConfiguration();onSaveRequested:record=>page.submit(page.candidateWithRecord("service_policies",record),serviceEditor);onValidationRequested:record=>page.validate(page.candidateWithRecord("service_policies",record),serviceEditor)}
    PolicyGroupDialog {id:groupEditor;ownerItem:page;targetOptions:page.targets;recoveryAvailable:page.engineController.policyApplyState==="reconciling";onRecoveryRequested:page.engineController.recoverPolicyConfiguration();onSaveRequested:record=>page.submit(page.candidateWithRecord("groups",record),groupEditor);onValidationRequested:record=>page.validate(page.candidateWithRecord("groups",record),groupEditor)}
    SwirlDialog {
        id:deleteDialog;objectName:"deletePolicyDialog";ownerItem:page;title:kind==="service"?qsTr("删除策略"):qsTr("删除策略组");guardChanges:false
        property string kind:"service";property string recordId:"";property string recordName:"";property bool pending:false;property string pendingRequestId:"";property string message:""
        dismissBlocked:pending
        ColumnLayout {width:parent.width;spacing:Theme.dp(14)
            SwirlText {Layout.fillWidth:true;text:qsTr("确定删除“%1”？").arg(deleteDialog.recordName);color:Theme.text;wrapMode:Text.Wrap}
            SwirlText {Layout.fillWidth:true;text:deleteDialog.kind==="group"?qsTr("被引用的策略组不能删除；请先修改相关策略的出口。"):qsTr("之后匹配的流量将按其他规则或默认策略处理。");color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
            SwirlText {Layout.fillWidth:true;visible:deleteDialog.message.length>0;text:deleteDialog.message;textFormat:Text.PlainText;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;Accessible.name:text}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:qsTr("恢复已保存的操作");visible:deleteDialog.pending&&page.engineController.policyApplyState==="reconciling";onClicked:page.engineController.recoverPolicyConfiguration()}
                SwirlButton {objectName:"cancelDeletePolicy";text:qsTr("取消");enabled:!deleteDialog.pending;onClicked:deleteDialog.close()}
                SwirlButton {objectName:"confirmDeletePolicy";text:deleteDialog.pending?qsTr("正在删除…"):qsTr("删除");danger:true;enabled:!deleteDialog.pending;onClicked:{const next=Policy.copy(page.document);const collection=deleteDialog.kind==="service"?"service_policies":"groups";next[collection]=next[collection].filter(item=>item.id!==deleteDialog.recordId);page.submit(next,deleteDialog)}}
            }
        }
    }
    SwirlDialog {
        id:migrationDialog;objectName:"policyMigrationDialog";ownerItem:page;title:qsTr("确认策略迁移");guardChanges:false
        property bool pending:false;property string pendingRequestId:"";property string message:"";dismissBlocked:pending
        width:Math.floor(Math.min(Theme.dp(600),parent?parent.width-Theme.dp(36):Theme.dp(600)));height:Math.floor(Math.min(Theme.dp(500),parent?parent.height-Theme.dp(36):Theme.dp(500)))
        contentItem:ColumnLayout {spacing:Theme.dp(14)
            ScrollView {id:migrationScroll;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
                SwirlText {width:Math.floor(migrationScroll.availableWidth);text:page.engineController.policyMigrationSummary;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
            }
            SwirlText {Layout.fillWidth:true;visible:migrationDialog.message.length>0;text:migrationDialog.message;textFormat:Text.PlainText;color:Theme.orange;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12)}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:qsTr("恢复已保存的操作");visible:migrationDialog.pending&&page.engineController.policyApplyState==="reconciling";onClicked:page.engineController.recoverPolicyConfiguration()}
                SwirlButton {objectName:"cancelPolicyMigration";text:qsTr("取消");enabled:!migrationDialog.pending;onClicked:migrationDialog.close()}
                SwirlButton {objectName:"confirmPolicyMigration";text:migrationDialog.pending?qsTr("正在迁移…"):qsTr("确认迁移");primary:true;enabled:!migrationDialog.pending&&page.engineController.policyMigrationSummary.length>0;onClicked:{migrationDialog.pending=true;page.registerCommand(migrationDialog,page.engineController.confirmPolicyMigration())}}
            }
        }
    }
    Connections {target:page.engineController;function onPolicyApplyFinished(requestId,success){page.lastCompletion={requestId:String(requestId),success:success};page.finishCommand(requestId,success)}}
}
