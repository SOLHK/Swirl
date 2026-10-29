pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

SwirlDialog {
    id:editor
    objectName:"policyGroupDialog"
    title:newRecord?qsTr("添加策略组"):qsTr("编辑策略组")
    property bool newRecord:true
    property var original:({})
    property var targetOptions:[]
    property var members:[]
    property var selectedMember:({kind:"unconfigured"})
    property var probeDraft:({})
    property bool probeUserEdited:false
    property bool advanced:false
    property bool pending:false
    property bool recoveryAvailable:false
    signal recoveryRequested()
    property string pendingRequestId:""
    property string message:""
    property bool messageIsError:false
    property string conflictReviewDigest:""
    onMembersChanged:conflictReviewDigest=""
    onSelectedMemberChanged:conflictReviewDigest=""
    onProbeDraftChanged:conflictReviewDigest=""
    onStrategyChanged:conflictReviewDigest=""
    readonly property string strategy:["manual","url_test","fallback","load_balance"][typeField.currentIndex]||"manual"
    signal saveRequested(var record)
    signal validationRequested(var record)
    function defaults(strategy) {return {url:"https://www.gstatic.com/generate_204",interval_ms:300000,timeout_ms:5000,expected_status:204,tolerance_ms:strategy==="url_test"?50:0,success_threshold:1,failure_threshold:2,switch_cooldown_ms:30000}}
    function begin(record,source,isNew) {
        newRecord=Boolean(isNew);original=Policy.copy(record);members=Policy.copy(record.members||[]);selectedMember=Policy.copy(record.selected||{kind:"unconfigured"})
        nameField.text=record.name||"";typeField.currentIndex=Math.max(0,["manual","url_test","fallback","load_balance"].indexOf(record.strategy||"manual"))
        probeDraft=record.probe?Policy.copy(record.probe):defaults(strategy);probeUserEdited=false;advanced=false;pending=false;pendingRequestId="";message="";conflictReviewDigest="";heroSource=source;open()
    }
    function record() {
        const next=Policy.copy(original);next.name=nameField.text.trim();next.strategy=strategy;next.members=Policy.copy(members)
        if(strategy==="manual"){next.selected=Policy.copy(selectedMember);delete next.probe}
        else {delete next.selected;next.probe=Policy.copy(probeDraft);if(strategy!=="url_test")next.probe.tolerance_ms=0}
        return next
    }
    function showError(text) {message=String(text);messageIsError=true;errorSummary.forceActiveFocus()}
    stateFingerprint:Qt.md5(JSON.stringify({members:members,selected:selectedMember,probe:probeDraft}))
    dismissBlocked:pending
    width:Math.floor(Math.min(Theme.dp(650),parent?parent.width-Theme.dp(36):Theme.dp(650)))
    height:Math.floor(Math.min(Theme.dp(680),parent?parent.height-Theme.dp(36):Theme.dp(680)))
    contentItem:ColumnLayout {
        spacing:Theme.dp(12)
        PolicyFormScroll {
            id:form;objectName:"policyGroupForm";Layout.fillWidth:true;Layout.fillHeight:true;ownerItem:editor.ownerItem;formBody:formBody
            ColumnLayout {
                id:formBody
                width:Math.floor(form.availableWidth);spacing:Theme.dp(10)
                SwirlText {text:qsTr("策略组名称");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                SwirlTextField {id:nameField;objectName:"policyGroupName";Layout.fillWidth:true;text:"";enabled:!editor.pending;placeholderText:qsTr("例如 工作出口");Accessible.name:qsTr("策略组名称");onTextEdited:editor.conflictReviewDigest=""}
                SwirlText {text:qsTr("策略类型");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                SwirlComboBox {id:typeField;objectName:"policyGroupType";Layout.fillWidth:true;model:[qsTr("手动选择"),qsTr("自动测速"),qsTr("故障转移"),qsTr("负载均衡")];enabled:!editor.pending;Accessible.name:qsTr("策略类型");onActivated:index=>{if(index===1&&!editor.original.probe&&!editor.probeUserEdited){const probe=Policy.copy(editor.probeDraft);probe.tolerance_ms=50;editor.probeDraft=probe}}}
                RowLayout {Layout.fillWidth:true
                    SwirlText {text:qsTr("候选出口");color:Theme.text;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
                    SwirlButton {id:addMember;objectName:"addPolicyGroupMember";text:qsTr("添加候选");quiet:true;enabled:!editor.pending;onClicked:memberPicker.begin({kind:"unconfigured"},addMember)}
                }
                ListView {
                    id:memberList;objectName:"policyGroupMemberList";Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(180),Math.max(Theme.dp(48),contentHeight));clip:true;reuseItems:true;model:editor.members
                    ScrollBar.vertical:SwirlScrollBar {}
                    delegate:RowLayout {
                        id:member;required property var modelData;required property int index;width:Math.floor(ListView.view.width);height:Theme.dp(48);spacing:Theme.dp(6)
                        SwirlText {Layout.fillWidth:true;text:Policy.targetName(member.modelData,editor.targetOptions);color:Theme.text;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
                        SwirlButton {objectName:"selectPolicyGroupMember-"+member.index;visible:editor.strategy==="manual";text:Policy.sameTarget(editor.selectedMember,member.modelData)?qsTr("已选"):qsTr("使用");outlined:Policy.sameTarget(editor.selectedMember,member.modelData);enabled:!editor.pending;onClicked:editor.selectedMember=Policy.copy(member.modelData);Accessible.name:qsTr("使用候选 %1").arg(Policy.targetName(member.modelData,editor.targetOptions))}
                        SwirlButton {text:qsTr("上移");quiet:true;enabled:member.index>0&&!editor.pending;onClicked:{const next=editor.members.slice();const value=next.splice(member.index,1)[0];next.splice(member.index-1,0,value);editor.members=next}Accessible.name:qsTr("上移候选 %1").arg(Policy.targetName(member.modelData,editor.targetOptions))}
                        SwirlButton {text:qsTr("移除");quiet:true;enabled:!editor.pending;onClicked:editor.members=editor.members.filter((item,index)=>index!==member.index);Accessible.name:qsTr("移除候选 %1").arg(Policy.targetName(member.modelData,editor.targetOptions))}
                    }
                    SwirlText {anchors.centerIn:parent;visible:memberList.count===0;text:qsTr("添加节点或其他策略组。");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                }
                SwirlText {Layout.fillWidth:true;visible:editor.strategy==="manual";text:qsTr("点击“使用”明确选择一个成员；成员失效不会自动替换为直连。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
                SwirlText {Layout.fillWidth:true;visible:editor.strategy==="fallback";text:qsTr("按候选顺序使用健康出口。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
                SwirlText {Layout.fillWidth:true;visible:editor.strategy==="load_balance";text:qsTr("新连接按服务保持出口稳定；既有连接不会迁移。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
                SwirlButton {objectName:"policyGroupAdvanced";Layout.fillWidth:true;visible:editor.strategy!=="manual";text:editor.advanced?qsTr("收起健康检测和自动切换"):qsTr("健康检测和自动切换");iconName:"chevron-up-down";quiet:true;enabled:!editor.pending;onClicked:editor.advanced=!editor.advanced}
                Loader {Layout.fillWidth:true;active:editor.advanced&&editor.strategy!=="manual";sourceComponent:Component {PolicyProbeSettings {value:editor.probeDraft;editable:!editor.pending;toleranceVisible:editor.strategy==="url_test";onEdited:probe=>{editor.probeDraft=probe;editor.probeUserEdited=true}}}}
            }
        }
        SwirlText {id:errorSummary;objectName:"policyGroupMessage";Layout.fillWidth:true;visible:editor.message.length>0;text:editor.message;textFormat:Text.PlainText;color:editor.messageIsError?Theme.orange:Theme.muted;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12);activeFocusOnTab:true;Accessible.name:text}
        RowLayout {Layout.fillWidth:true
            SwirlButton {text:qsTr("恢复已保存的操作");visible:editor.pending&&editor.recoveryAvailable;onClicked:editor.recoveryRequested()}
            SwirlButton {objectName:"validatePolicyGroup";text:qsTr("检查引用");quiet:true;enabled:!editor.pending;onClicked:editor.validationRequested(editor.record())}
            Item {Layout.fillWidth:true}
            SwirlButton {objectName:"cancelPolicyGroup";text:qsTr("取消");enabled:!editor.pending;onClicked:editor.close()}
            SwirlButton {objectName:"savePolicyGroup";text:editor.pending?qsTr("正在保存…"):editor.conflictReviewDigest.length?qsTr("确认保存"):qsTr("保存");primary:true;enabled:!editor.pending&&nameField.text.trim().length>0&&editor.members.length>0&&(editor.strategy!=="manual"||editor.members.some(member=>Policy.sameTarget(member,editor.selectedMember)));onClicked:editor.saveRequested(editor.record())}
        }
    }
    PolicyTargetPicker {id:memberPicker;ownerItem:editor.ownerItem;options:editor.targetOptions;excludedGroupId:String(editor.original.id||"");onTargetChosen:target=>{if(!editor.members.some(member=>Policy.sameTarget(member,target)))editor.members=editor.members.concat([Policy.copy(target)]);memberPicker.markSaved();memberPicker.close()}}
}
