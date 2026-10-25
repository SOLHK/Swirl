pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

SwirlDialog {
    id:editor
    objectName:"servicePolicyDialog"
    title:newRecord?qsTr("添加策略"):qsTr("编辑策略")
    property bool newRecord:true
    property var original:({})
    property var targetOptions:[]
    property var domains:[]
    property var selectedTarget:({kind:"unconfigured"})
    property bool pending:false
    property bool recoveryAvailable:false
    signal recoveryRequested()
    property string pendingRequestId:""
    property string message:""
    property bool messageIsError:false
    property string conflictReviewDigest:""
    onDomainsChanged:conflictReviewDigest=""
    onSelectedTargetChanged:conflictReviewDigest=""
    signal saveRequested(var record)
    signal validationRequested(var record)
    function begin(record,source,isNew) {
        newRecord=Boolean(isNew)
        original=Policy.copy(record);domains=Policy.copy(record.domains||[]);selectedTarget=Policy.copy(record.target||{kind:"unconfigured"})
        nameField.text=record.name||"";priorityField.text=String(record.priority===undefined?0:record.priority);enabledField.checked=record.enabled!==false
        domainField.text="";domainType.currentIndex=0;pending=false;pendingRequestId="";message="";conflictReviewDigest="";heroSource=source;open()
    }
    function record() {
        const next=Policy.copy(original);next.name=nameField.text.trim();next.enabled=enabledField.checked;next.priority=Number(priorityField.text)
        next.domains=Policy.copy(domains);next.target=Policy.copy(selectedTarget);return next
    }
    function showError(text) {message=String(text);messageIsError=true;errorSummary.forceActiveFocus()}
    stateFingerprint:Qt.md5(JSON.stringify({domains:domains,target:selectedTarget}))
    dismissBlocked:pending
    width:Math.floor(Math.min(Theme.dp(650),parent?parent.width-Theme.dp(36):Theme.dp(650)))
    height:Math.floor(Math.min(Theme.dp(650),parent?parent.height-Theme.dp(36):Theme.dp(650)))
    contentItem:ColumnLayout {
        spacing:Theme.dp(12)
        PolicyFormScroll {
            id:form;objectName:"servicePolicyForm";Layout.fillWidth:true;Layout.fillHeight:true;ownerItem:editor.ownerItem;formBody:formBody
            ColumnLayout {
                id:formBody
                width:Math.floor(form.availableWidth);spacing:Theme.dp(10)
                SwirlText {text:qsTr("策略名称");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                SwirlTextField {id:nameField;objectName:"servicePolicyName";Layout.fillWidth:true;enabled:!editor.pending;placeholderText:qsTr("例如 GitHub 或工作服务");Accessible.name:qsTr("策略名称");onTextEdited:editor.conflictReviewDigest=""}
                SwirlText {text:qsTr("匹配方式");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                SwirlComboBox {objectName:"serviceMatchType";Layout.fillWidth:true;model:[qsTr("网站域名")];enabled:!editor.pending;Accessible.name:qsTr("匹配方式")}
                SwirlText {Layout.fillWidth:true;text:qsTr("应用程序及应用与网站组合：当前模式无法可靠识别应用，请使用网站域名。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
                SwirlText {text:qsTr("匹配内容");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                RowLayout {Layout.fillWidth:true;spacing:Theme.dp(8)
                    SwirlComboBox {id:domainType;objectName:"serviceDomainType";Layout.preferredWidth:Theme.dp(132);model:[qsTr("包含子域名"),qsTr("仅此域名")];enabled:!editor.pending;Accessible.name:qsTr("域名匹配范围")}
                    SwirlTextField {id:domainField;objectName:"serviceDomainValue";Layout.fillWidth:true;placeholderText:"example.com";enabled:!editor.pending;Accessible.name:qsTr("域名")}
                    SwirlButton {objectName:"addServiceDomain";text:qsTr("添加");enabled:domainField.text.trim().length>0&&!editor.pending;onClicked:{editor.domains=editor.domains.concat([{type:domainType.currentIndex===0?"domain_suffix":"domain",value:domainField.text.trim()}]);domainField.clear();domainField.forceActiveFocus()}}
                }
                ListView {
                    id:domainList;objectName:"serviceDomainList";Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(132),Math.max(Theme.dp(42),contentHeight));clip:true;reuseItems:true;model:editor.domains
                    ScrollBar.vertical:SwirlScrollBar {}
                    delegate:RowLayout {
                        id:domainRow;required property var modelData;required property int index;width:Math.floor(ListView.view.width);height:Theme.dp(42);spacing:Theme.dp(8)
                        SwirlText {Layout.fillWidth:true;text:(domainRow.modelData.type==="domain_suffix"?"*.":"")+domainRow.modelData.value;color:Theme.text;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
                        SwirlText {text:domainRow.modelData.type==="domain_suffix"?qsTr("包含子域名"):qsTr("仅此域名");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                        SwirlButton {text:qsTr("移除");quiet:true;enabled:!editor.pending;onClicked:editor.domains=editor.domains.filter((item,index)=>index!==domainRow.index);Accessible.name:qsTr("移除域名 %1").arg(domainRow.modelData.value)}
                    }
                    SwirlText {anchors.centerIn:parent;visible:domainList.count===0;text:qsTr("添加至少一个域名；任一条匹配即使用此策略。");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                }
                SwirlText {text:qsTr("出口");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                SwirlButton {id:targetButton;objectName:"servicePolicyTarget";Layout.fillWidth:true;text:Policy.targetName(editor.selectedTarget,editor.targetOptions);outlined:true;enabled:!editor.pending;onClicked:targetPicker.begin(editor.selectedTarget,targetButton);Accessible.name:qsTr("策略出口：%1").arg(text)}
                RowLayout {Layout.fillWidth:true;spacing:Theme.dp(12)
                    SwirlText {text:qsTr("优先级");color:Theme.text;font.pixelSize:Theme.fontSize(12)}
                    SwirlTextField {id:priorityField;objectName:"servicePolicyPriority";Layout.preferredWidth:Theme.dp(90);validator:IntValidator {bottom:0;top:1000000}enabled:!editor.pending;Accessible.name:qsTr("策略优先级，数值越小越优先");onTextEdited:editor.conflictReviewDigest=""}
                    SwirlText {Layout.fillWidth:true;text:qsTr("数值越小越优先");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                    ReferenceCheckBox {id:enabledField;objectName:"servicePolicyEnabled";text:qsTr("启用");enabled:!editor.pending;onToggled:editor.conflictReviewDigest=""}
                }
            }
        }
        SwirlText {id:errorSummary;objectName:"servicePolicyMessage";Layout.fillWidth:true;visible:editor.message.length>0;text:editor.message;textFormat:Text.PlainText;color:editor.messageIsError?Theme.orange:Theme.muted;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12);activeFocusOnTab:true;Accessible.name:text}
        RowLayout {Layout.fillWidth:true
            SwirlButton {text:qsTr("恢复已保存的操作");visible:editor.pending&&editor.recoveryAvailable;onClicked:editor.recoveryRequested()}
            SwirlButton {objectName:"validateServicePolicy";text:qsTr("检查规则");quiet:true;enabled:!editor.pending&&priorityField.acceptableInput;onClicked:editor.validationRequested(editor.record())}
            Item {Layout.fillWidth:true}
            SwirlButton {objectName:"cancelServicePolicy";text:qsTr("取消");enabled:!editor.pending;onClicked:editor.close()}
            SwirlButton {objectName:"saveServicePolicy";text:editor.pending?qsTr("正在保存…"):editor.conflictReviewDigest.length?qsTr("确认保存"):qsTr("保存");primary:true;enabled:!editor.pending&&nameField.text.trim().length>0&&editor.domains.length>0&&priorityField.acceptableInput&&editor.selectedTarget.kind!=="unconfigured";onClicked:editor.saveRequested(editor.record())}
        }
    }
    PolicyTargetPicker {id:targetPicker;ownerItem:editor.ownerItem;options:editor.targetOptions;allowDirect:true;onTargetChosen:target=>{editor.selectedTarget=Policy.copy(target);targetPicker.markSaved();targetPicker.close()}}
}
