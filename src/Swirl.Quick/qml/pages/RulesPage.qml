pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;property string query:"";property var selectedRule:null
 readonly property Item motionTitle:ruleHeading.titleItem
 property Item selectedRowItem:null
 property int editingIndex:-1
 readonly property bool v2:engineController.policyV2Active
 readonly property bool canEditPolicy:!engineController.policyBusy&&engineController.policyApplyState!=="reconciling"
 property bool ruleSubmitting:false
 property string ruleRequestId:""
 property string deleteRequestId:""
 property var lastCompletion:({requestId:"",success:false})
 function finishRule(requestId,success){
  const receipt=engineController.policyReceipt||({})
  if(success&&String(receipt.request_id)!==String(requestId))return
  if(requestId===ruleRequestId&&ruleSubmitting){ruleSubmitting=false;ruleRequestId="";if(success){selectedRule=null;ruleEditor.markSaved();ruleEditor.close()}}
  if(requestId===deleteRequestId){deleteRequestId="";if(success)selectedRule=null;else AppState.notice(engineController.policyError)}
 }
 readonly property var ruleTargets:v2?[{label:"DIRECT",value:"DIRECT"},{label:qsTr("拒绝连接"),value:"REJECT"}].concat(engineController.policyTargetOptions.filter(option=>option.kind==="node"||option.kind==="group").map(option=>({label:option.name,value:option.kind+":"+option.id}))):["DIRECT","REJECT","SWIRL"].concat(engineController.policyGroups.map(group=>group.name)).map(value=>({label:value,value:value}))
 readonly property var ruleTypes:["DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","IP-CIDR6","DST-PORT","SRC-IP-CIDR"].concat(v2?[]:["MATCH"])
 function targetIndex(value){return ruleTargets.findIndex(target=>target.value===value)}
 function saveRule(){
  if(rulePolicy.currentIndex<0)return
  if(!engineController.saveRoutingRule(ruleType.currentText,rulePattern.text,ruleTargets[rulePolicy.currentIndex].value,editingIndex))return
  if(v2){ruleSubmitting=true;ruleRequestId=engineController.policyRequestId;if(lastCompletion.requestId===ruleRequestId)finishRule(ruleRequestId,lastCompletion.success)}
  else{selectedRule=null;ruleEditor.markSaved();ruleEditor.close()}
 }
 function deleteRule(){
  if(engineController.removeRoutingRule(selectedRule.customIndex)){
   if(v2){deleteRequestId=engineController.policyRequestId;if(lastCompletion.requestId===deleteRequestId)finishRule(deleteRequestId,lastCompletion.success)}
   else selectedRule=null
  }else AppState.notice(engineController.policyError||engineController.networkConfigurationError)
 }
 function editRule(rule,source){
  if(!rule || rule.customIndex===undefined || !canEditPolicy||(!v2&&engineController.processAlive))return
  editingIndex=rule.customIndex;ruleEditor.heroSource=source
  ruleType.currentIndex=ruleType.model.indexOf(rule.type==='FINAL'?'MATCH':rule.type)
  rulePattern.text=rule.pattern;rulePolicy.currentIndex=targetIndex(rule.policyTarget||rule.policy)
  ruleEditor.open()
 }
 readonly property var displayRules:engineController.routingRules.filter(r=>(r.type+" "+r.pattern+" "+r.policy).toLowerCase().indexOf(query.toLowerCase())>=0)
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.gap
  SwirlPageHeader {
   id:ruleHeading;Layout.fillWidth:true;title:qsTr("路由规则")
   description:page.v2?qsTr("按本地直连、专属服务、中国规则库、自定义规则、默认策略依次匹配。双击自定义规则可编辑。"):qsTr("当前保留旧版顺序规则；在策略页审阅迁移后启用新的分流层级。")
   SwirlFlow {objectName:"rulesOperationFlow";Layout.preferredWidth:Theme.dp(42);Layout.preferredHeight:Theme.dp(18);phase:page.ruleSubmitting||page.deleteRequestId.length?"pending":page.engineController.policyError.length?"failed":"idle"}
   SwirlButton {text:qsTr("查看策略");iconName:"route";quiet:true;onClicked:AppState.navigate("policies")}
  }
  SwirlGlassPanel {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(200);cornerRadius:Theme.dp(16);color:Theme.surface;border.width:0
   ColumnLayout {id:ruleArea;anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
    RowLayout {Layout.fillWidth:true
     SwirlText {renderType:Text.NativeRendering;text:qsTr("规则列表");color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
     SwirlText {renderType:Text.NativeRendering;text:page.displayRules.length+" 条规则";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
     SwirlSearchField {objectName:"rulesSearch";Layout.preferredWidth:Math.floor(Math.min(Theme.dp(240),page.width*0.36));placeholderText:"搜索类型、值或策略";onTextChanged:page.query=text}
    }
    SwirlDataTable {id:ruleTable;objectName:"rulesTable";textPixelSize:13;headerPixelSize:12;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(150);visible:page.displayRules.length>0;incrementalRows:true;animateRowChanges:page.query.length===0;rows:page.displayRules;selectedId:page.selectedRule?page.selectedRule.id:"";fillEmptyRows:false;columns:[{key:"order",label:"ID",w:40},{key:"type",label:"类型",w:125},{key:"pattern",label:"值",w:230},{key:"policy",label:"策略",w:100},{key:"hits",label:"使用",w:50}];onRowSelected:r=>page.selectedRule=r;onRowEdited:(r,source)=>page.editRule(r,source)}
    SwirlEmptyState {visible:page.displayRules.length===0;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(130);headline:page.query.length?"没有匹配的规则":"尚无路由规则";detail:page.query.length?"尝试其他关键词，或清空搜索。":"添加自定义规则以控制流量的处理方式。"}
    RowLayout {Layout.fillWidth:true;spacing:Theme.dp(8)
     SwirlButton {objectName:"addRoutingRule";text:qsTr("添加规则");iconName:"plus";primary:true;enabled:page.canEditPolicy&&(page.v2||!page.engineController.processAlive);onClicked:{page.editingIndex=-1;ruleEditor.heroSource=null;ruleType.currentIndex=0;rulePattern.text="";rulePolicy.currentIndex=-1;ruleEditor.open()}}
     SwirlButton {objectName:"editRoutingRule";text:"编辑";enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&page.canEditPolicy&&(page.v2||!page.engineController.processAlive);onClicked:page.editRule(page.selectedRule,ruleTable.selectedItem)}
     SwirlButton {objectName:"removeRoutingRule";text:"删除";enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&page.canEditPolicy&&(page.v2||!page.engineController.processAlive);onClicked:page.deleteRule()}
     Item {Layout.fillWidth:true}
     SwirlButton {text:"重置计数器";development:true;enabled:false}
    }
   }
  }
 }

 SwirlDialog{id:ruleEditor;objectName:"ruleEditor";title:page.editingIndex>=0?"编辑规则":"新增规则";dismissBlocked:page.ruleSubmitting;ColumnLayout{width:parent.width;spacing:Theme.dp(14)
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"类型：";color:Theme.text}SwirlComboBox{id:ruleType;Layout.fillWidth:true;model:page.ruleTypes;enabled:!page.ruleSubmitting}}
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"值：";color:Theme.text}SwirlTextField{id:rulePattern;objectName:"rulePattern";Layout.fillWidth:true;enabled:ruleType.currentText!=="MATCH"&&!page.ruleSubmitting;placeholderText:"example.com"}}
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"策略：";color:Theme.text}SwirlComboBox{id:rulePolicy;objectName:"rulePolicy";Layout.fillWidth:true;model:page.ruleTargets.map(target=>target.label);enabled:!page.ruleSubmitting}}
  SwirlText {text:qsTr("当前系统代理无法可靠识别应用进程，应用规则不可用。");color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(11)}
  SwirlText {renderType:Text.NativeRendering;text:page.engineController.policyError||page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";enabled:!page.ruleSubmitting;onClicked:ruleEditor.requestDismiss()}SwirlButton{objectName:"saveRoutingRule";text:page.ruleSubmitting?qsTr("正在保存…"):page.editingIndex>=0?"保存":"添加";primary:true;enabled:page.canEditPolicy&&!page.ruleSubmitting&&ruleType.currentIndex>=0&&rulePolicy.currentIndex>=0;onClicked:page.saveRule()}}
 }}
 Connections {target:page.engineController;function onPolicyApplyFinished(requestId,success){
  page.lastCompletion={requestId:requestId,success:success};page.finishRule(requestId,success)
 }}
}
