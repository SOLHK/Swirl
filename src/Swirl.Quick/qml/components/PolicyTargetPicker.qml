pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

SwirlDialog {
    id:picker
    objectName:"policyTargetPicker"
    title:qsTr("选择出口")
    property var options:[]
    property bool allowDirect:false
    property string excludedGroupId:""
    property var currentTarget:({kind:"unconfigured"})
    property var selectedTarget:({kind:"unconfigured"})
    property string query:""
    property int targetKind:0
    property bool pending:false
    property bool recoveryAvailable:false
    signal recoveryRequested()
    property string pendingRequestId:""
    property string message:""
    readonly property var visibleOptions:options.filter(option=>option.kind===(targetKind===0?"node":"group")&&!(option.kind==="group"&&option.id===excludedGroupId)&&String(option.name).toLowerCase().indexOf(query.toLowerCase())>=0)
    readonly property bool selectionAvailable:Policy.targetAvailable(selectedTarget,options)&&!(selectedTarget.kind==="group"&&selectedTarget.id===excludedGroupId)&&(allowDirect||selectedTarget.kind!=="direct")
    signal targetChosen(var target)
    function selectOption(option,index) {if(option&&option.available&&!pending){targets.currentIndex=index;selectedTarget={kind:option.kind,id:option.id}}}
    function begin(target,source) {
        currentTarget=Policy.copy(target||{kind:"unconfigured"});selectedTarget=Policy.copy(currentTarget)
        targetKind=currentTarget.kind==="group"?1:0;targetTabs.currentIndex=targetKind;query="";search.text="";pending=false;pendingRequestId="";message="";heroSource=source;open()
    }
    function showError(text) {message=String(text);errorSummary.forceActiveFocus()}
    onClosed:search.clear()
    stateFingerprint:Qt.md5(JSON.stringify(selectedTarget))
    dismissBlocked:pending
    width:Math.floor(Math.min(Theme.dp(600),parent?parent.width-Theme.dp(36):Theme.dp(600)))
    height:Math.floor(Math.min(Theme.dp(580),parent?parent.height-Theme.dp(36):Theme.dp(580)))
    contentItem:ColumnLayout {
        spacing:Theme.dp(12)
        SwirlSearchField {id:search;objectName:"policyTargetSearch";Layout.fillWidth:true;placeholderText:qsTr("搜索出口名称");enabled:!picker.pending;onTextChanged:picker.query=text;Accessible.name:qsTr("搜索出口")}
        SwirlSegmentedControl {id:targetTabs;objectName:"policyTargetTabs";Layout.fillWidth:true;options:[qsTr("节点"),qsTr("策略组")];currentIndex:picker.targetKind;enabled:!picker.pending;onActivated:index=>picker.targetKind=index}
        ListView {
            id:targets;objectName:"policyTargetList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;reuseItems:true;pixelAligned:true
            model:picker.visibleOptions;spacing:Theme.dp(3);keyNavigationEnabled:true;activeFocusOnTab:true
            Keys.onReturnPressed:picker.selectOption(picker.visibleOptions[currentIndex],currentIndex)
            Keys.onEnterPressed:picker.selectOption(picker.visibleOptions[currentIndex],currentIndex)
            ScrollBar.vertical:SwirlScrollBar {}
            delegate:SwirlMotionButton {
                id:option;required property var modelData;required property int index
                objectName:modelData.kind==="node"?"policyNode-"+modelData.id:"policyTarget-group-"+modelData.id
                width:Math.floor(ListView.view.width);height:Theme.dp(48);padding:Theme.dp(10);hoverEnabled:true
                enabled:Boolean(modelData.available)&&!picker.pending
                Accessible.name:String(modelData.name)+(modelData.available?"":qsTr("，当前不可用"))
                background:Rectangle {radius:Theme.controlRadius;color:Policy.sameTarget(picker.selectedTarget,option.modelData)?Theme.selected:option.hovered?Theme.hover:Theme.field;border.width:option.activeFocus?Theme.dp(1):0;border.color:Theme.focusBorder}
                contentItem:RowLayout {
                    SwirlIcon {name:"checkmark";visible:Policy.sameTarget(picker.selectedTarget,option.modelData);size:Theme.dp(16);color:Theme.accent;Accessible.ignored:true}
                    SwirlText {Layout.fillWidth:true;text:String(option.modelData.name);color:option.enabled?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
                    SwirlText {visible:!option.modelData.available;text:qsTr("当前不可用");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                }
                onClicked:picker.selectOption(modelData,index)
            }
            SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:targets.count===0;headline:qsTr("没有匹配的出口");detail:picker.targetKind===0?qsTr("先在节点页添加或导入节点。"):qsTr("先在策略组标签中创建策略组。")}
        }
        SwirlButton {objectName:"policyDirectTarget";visible:picker.allowDirect;Layout.fillWidth:true;text:Policy.sameTarget(picker.selectedTarget,{kind:"direct"})?qsTr("DIRECT（已选）"):"DIRECT";outlined:Policy.sameTarget(picker.selectedTarget,{kind:"direct"});enabled:!picker.pending;onClicked:picker.selectedTarget={kind:"direct"};Accessible.name:qsTr("直连出口 DIRECT")}
        SwirlText {Layout.fillWidth:true;visible:picker.selectedTarget.kind!=="unconfigured";text:qsTr("已选：%1").arg(Policy.targetName(picker.selectedTarget,picker.options));color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
        SwirlText {id:errorSummary;Layout.fillWidth:true;visible:picker.message.length>0;text:picker.message;textFormat:Text.PlainText;color:Theme.orange;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12);activeFocusOnTab:true;Accessible.name:text}
        RowLayout {Layout.alignment:Qt.AlignRight
            SwirlButton {text:qsTr("恢复已保存的操作");visible:picker.pending&&picker.recoveryAvailable;onClicked:picker.recoveryRequested()}
            SwirlButton {objectName:"cancelPolicyTarget";text:qsTr("取消");enabled:!picker.pending;onClicked:picker.close()}
            SwirlButton {objectName:"confirmPolicyTarget";text:picker.pending?qsTr("正在保存…"):qsTr("确认出口");primary:true;enabled:picker.selectionAvailable&&!picker.pending;onClicked:picker.targetChosen(Policy.copy(picker.selectedTarget))}
        }
    }
}
