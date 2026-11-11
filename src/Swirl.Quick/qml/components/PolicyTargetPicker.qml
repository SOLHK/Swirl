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
    property bool latencySort:false
    property bool availableOnly:false
    property bool ownsProbe:false
    property bool autoProbePending:false
    readonly property var nodeOptions:options.filter(option=>option.kind==="node")
    readonly property var nodeIds:nodeOptions.map(option=>option.id)
    readonly property var nodeById:{const result={};for(const option of nodeOptions)result[option.id]=option;return result}
    NodeViewModel {id:pickerNodes;controller:picker.visible?engineController:null;query:picker.query;filters:({sort:picker.latencySort?"exitLatency":"name",available:picker.availableOnly})}
    Timer {id:autoProbe;interval:75;onTriggered:if(picker.opened&&!picker.pending&&picker.autoProbePending&&!engineController.tests.busy){picker.autoProbePending=false;picker.ownsProbe=engineController.testNodesIfStale(picker.nodeIds,engineController.defaultProbeUrl)||picker.ownsProbe}}
    Connections {target:engineController.tests;function onChanged(){if(picker.opened&&picker.autoProbePending&&!engineController.tests.busy)autoProbe.restart()}}
    onOpened:{autoProbePending=true;autoProbe.restart()}
    onNodeIdsChanged:if(opened){autoProbePending=true;autoProbe.restart()}
    onPendingChanged:if(opened&&!pending&&autoProbePending)autoProbe.restart()
    function optionAt(index){if(targetKind!==0)return visibleOptions[index];const row=pickerNodes.get(index);return nodeById[row.id]}
    readonly property var visibleOptions:options.filter(option=>option.kind===(targetKind===0?"node":"group")&&!(option.kind==="group"&&option.id===excludedGroupId)&&String(option.name).toLowerCase().indexOf(query.toLowerCase())>=0)
    readonly property bool selectionAvailable:Policy.targetAvailable(selectedTarget,options)&&!(selectedTarget.kind==="group"&&selectedTarget.id===excludedGroupId)&&(allowDirect||selectedTarget.kind!=="direct")
    signal targetChosen(var target)
    function selectOption(option,index) {if(option&&option.available&&!pending){(targetKind===0?targets:groupTargets).currentIndex=index;selectedTarget={kind:option.kind,id:option.id}}}
    function begin(target,source) {
        currentTarget=Policy.copy(target||{kind:"unconfigured"});selectedTarget=Policy.copy(currentTarget)
        targetKind=currentTarget.kind==="group"?1:0;targetTabs.currentIndex=targetKind;query="";search.text="";pending=false;pendingRequestId="";message="";heroSource=source;open()
    }
    function showError(text) {message=String(text);errorSummary.forceActiveFocus()}
    onClosed:{autoProbePending=false;search.clear();autoProbe.stop();if(ownsProbe)engineController.tests.cancel();ownsProbe=false}
    stateFingerprint:Qt.md5(JSON.stringify(selectedTarget))
    dismissBlocked:pending
    width:Math.floor(Math.min(Theme.dp(600),parent?parent.width-2*margins:Theme.dp(600)))
    height:Math.floor(Math.min(Theme.dp(580),parent?parent.height-2*margins:Theme.dp(580)))
    component TargetRow: SwirlMotionButton {
        id:option;required property var targetData;required property int index
        property var probeRow:({})
        objectName:targetData.kind==="node"?"policyNode-"+targetData.id:"policyTarget-group-"+targetData.id
        width:Math.floor(ListView.view.width);height:Theme.dp(targetData.kind==="node"?56:48);padding:Theme.dp(10);hoverEnabled:true
        enabled:Boolean(targetData.available)&&!picker.pending
        Accessible.name:String(targetData.name)+(targetData.available?"":qsTr("，当前不可用"))
        Accessible.description:String(targetData.sourceName||"")
        background:SwirlControlSurface {
            radius:Theme.pillRadius(height)
            quiet:true
            hovered:option.hovered
            pressed:option.down
            focused:option.visualFocus||(option.ListView.view.activeFocus&&option.ListView.view.currentIndex===option.index)
            controlEnabled:option.enabled
            color:Policy.sameTarget(picker.selectedTarget,option.targetData)?Theme.navigationSelected:option.enabled && option.down?Theme.pressed:option.enabled && option.hovered?Theme.hover:"transparent"
        }
        contentItem:RowLayout {
            spacing:Theme.dp(10)
            ColumnLayout {
                Layout.fillWidth:true;Layout.minimumWidth:0;spacing:Theme.dp(2)
                SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:String(option.targetData.name);textFormat:Text.PlainText;color:option.enabled?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
                SwirlText {Layout.fillWidth:true;visible:option.targetData.kind==="node";text:String(option.targetData.sourceName||"");textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(10);elide:Text.ElideRight}
            }
            SwirlText {visible:!option.targetData.available;Layout.alignment:Qt.AlignBaseline;text:qsTr("当前不可用");color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
            SwirlText {objectName:"policyNodeLatency";visible:option.targetData.kind==="node";Layout.preferredWidth:Theme.dp(100);horizontalAlignment:Text.AlignRight;text:String(option.probeRow.probeStatusText||"—");color:option.probeRow.testAvailable?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(11);elide:Text.ElideRight}
            SwirlIcon {name:"checkmark";opacity:Policy.sameTarget(picker.selectedTarget,option.targetData)?1:0;size:Theme.dp(16);color:Theme.text;Accessible.ignored:true}
        }
        onClicked:picker.selectOption(targetData,index)
    }
    contentItem:ColumnLayout {
        spacing:Theme.dp(12)
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            SwirlSearchField {
                id:search;objectName:"policyTargetSearch"
                Layout.fillWidth:true;Layout.minimumWidth:Theme.dp(100)
                implicitHeight:Theme.dp(34);placeholderText:qsTr("搜索出口名称");enabled:!picker.pending
                onTextChanged:picker.query=text;Accessible.name:qsTr("搜索出口")
            }
            SwirlSegmentedControl {id:targetTabs;objectName:"policyTargetTabs";Layout.preferredWidth:Theme.dp(180);Layout.preferredHeight:Theme.dp(34);options:[qsTr("节点"),qsTr("策略组")];currentIndex:picker.targetKind;enabled:!picker.pending;onActivated:index=>picker.targetKind=index}
        }
        RowLayout {
            Layout.fillWidth:true;visible:picker.targetKind===0;spacing:Theme.dp(8)
            SubscriptionAction {objectName:"policySortName";text:qsTr("名称");selected:!picker.latencySort;onClicked:picker.latencySort=false}
            SubscriptionAction {objectName:"policySortLatency";text:qsTr("延迟");selected:picker.latencySort;onClicked:picker.latencySort=true}
            SubscriptionAction {objectName:"policyAvailableOnly";text:qsTr("仅可用");selected:picker.availableOnly;onClicked:picker.availableOnly=!picker.availableOnly}
            Item {Layout.fillWidth:true}
            SubscriptionAction {objectName:"policyRetest";text:engineController.tests.busy?qsTr("取消检测"):qsTr("重新检测");enabled:!picker.pending;onClicked:{picker.autoProbePending=false;if(engineController.tests.busy){engineController.tests.cancel();picker.ownsProbe=false}else{picker.ownsProbe=true;engineController.testNodes(picker.nodeIds,engineController.defaultProbeUrl)}}}
        }
        SwirlText {Layout.fillWidth:true;visible:picker.targetKind===0;text:qsTr("HTTPS 出口响应时间 · 含 DNS、节点握手及目标 TLS");color:Theme.muted;font.pixelSize:Theme.fontSize(10);wrapMode:Text.Wrap}
        Item {
            Layout.fillWidth:true;Layout.fillHeight:true
            ListView {
                id:targets;objectName:"policyTargetList";anchors.fill:parent;visible:picker.targetKind===0
                clip:true;reuseItems:true;pixelAligned:true;model:pickerNodes;spacing:0;keyNavigationEnabled:true;activeFocusOnTab:true
                Keys.onReturnPressed:picker.selectOption(picker.optionAt(currentIndex),currentIndex)
                Keys.onEnterPressed:picker.selectOption(picker.optionAt(currentIndex),currentIndex)
                Keys.onSpacePressed:picker.selectOption(picker.optionAt(currentIndex),currentIndex)
                ScrollBar.vertical:SwirlScrollBar {}
                delegate:TargetRow {
                    required property var entry
                    targetData:picker.nodeById[entry.id]||{kind:"node",id:entry.id,name:entry.name,available:false}
                    probeRow:entry
                }
            }
            ListView {
                id:groupTargets;objectName:"policyTargetList";anchors.fill:parent;visible:picker.targetKind===1
                clip:true;reuseItems:true;pixelAligned:true;model:picker.visibleOptions;spacing:0;keyNavigationEnabled:true;activeFocusOnTab:true
                Keys.onReturnPressed:picker.selectOption(picker.visibleOptions[currentIndex],currentIndex)
                Keys.onEnterPressed:picker.selectOption(picker.visibleOptions[currentIndex],currentIndex)
                Keys.onSpacePressed:picker.selectOption(picker.visibleOptions[currentIndex],currentIndex)
                ScrollBar.vertical:SwirlScrollBar {}
                delegate:TargetRow {required property var modelData;targetData:modelData}
            }
            SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:(picker.targetKind===0?targets.count:groupTargets.count)===0;headline:qsTr("没有匹配的出口");detail:picker.targetKind===0?qsTr("先在节点页添加或导入节点。"):qsTr("先在策略组标签中创建策略组。")}
        }

        SubscriptionAction {
            id:directTarget;objectName:"policyDirectTarget"
            visible:picker.allowDirect;Layout.fillWidth:true;implicitWidth:Theme.dp(180)
            text:"DIRECT";selected:Policy.sameTarget(picker.selectedTarget,{kind:"direct"});enabled:!picker.pending
            contentItem:RowLayout {
                SwirlText {Layout.fillWidth:true;text:directTarget.text;color:directTarget.enabled?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(13)}
                SwirlIcon {name:"checkmark";opacity:directTarget.selected?1:0;size:Theme.dp(16);color:Theme.text;Accessible.ignored:true}
            }
            onClicked:picker.selectedTarget={kind:"direct"};Accessible.name:qsTr("直连出口 DIRECT")
        }
        SwirlText {Layout.fillWidth:true;visible:picker.selectedTarget.kind!=="unconfigured";text:qsTr("已选：%1").arg(Policy.targetName(picker.selectedTarget,picker.options));color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
        SwirlText {id:errorSummary;Layout.fillWidth:true;visible:picker.message.length>0;text:picker.message;textFormat:Text.PlainText;color:Theme.orange;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12);activeFocusOnTab:true;Accessible.name:text}
        ColumnLayout {
            Layout.fillWidth:true;spacing:Theme.dp(8)
            SubscriptionAction {Layout.alignment:Qt.AlignRight;text:qsTr("恢复已保存的操作");visible:picker.pending&&picker.recoveryAvailable;onClicked:picker.recoveryRequested()}
            RowLayout {
                Layout.fillWidth:true;spacing:Theme.dp(8)
                Item {Layout.fillWidth:true}
                SubscriptionAction {objectName:"cancelPolicyTarget";text:qsTr("取消");enabled:!picker.pending;onClicked:picker.close()}
                SubscriptionAction {objectName:"confirmPolicyTarget";text:picker.pending?qsTr("正在保存…"):qsTr("确认出口");solid:true;enabled:picker.selectionAvailable&&!picker.pending;onClicked:picker.targetChosen(Policy.copy(picker.selectedTarget))}
            }
        }
    }
}
