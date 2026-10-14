pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;property string query:"";property var selectedRule:null
 property Item selectedRowItem:null
 property int editingIndex:-1
 function editRule(rule,source){
  if(!rule || rule.customIndex===undefined || engineController.processAlive)return
  editingIndex=rule.customIndex;ruleEditor.heroSource=source
  ruleType.currentIndex=ruleType.model.indexOf(rule.type==='FINAL'?'MATCH':rule.type)
  rulePattern.text=rule.pattern;rulePolicy.currentIndex=rulePolicy.model.indexOf(rule.policy)
  ruleEditor.open()
 }
 readonly property var displayRules:engineController.routingRules.filter(r=>(r.type+" "+r.pattern+" "+r.policy).toLowerCase().indexOf(query.toLowerCase())>=0)
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"规则";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlSearchField{objectName:"rulesSearch";anchors.right:parent.right;anchors.rightMargin:Theme.dp(20);y:Theme.dp(32);width:Theme.dp(245);height:Theme.dp(24);placeholderText:"搜索";font.pixelSize:Theme.fontSize(12);onTextChanged:page.query=text}
 Text{x:Theme.dp(24);y:Theme.dp(74);text:"规则按从上至下的顺序测试；双击自定义规则可编辑。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 Rectangle{x:Theme.dp(20);y:Theme.dp(102);width:parent.width-Theme.dp(40);height:parent.height-y-Theme.dp(20);radius:Theme.tableRadius;color:Theme.surface;border.color:Theme.border;clip:true
  SwirlDataTable{id:ruleTable;incrementalRows:true;animateRowChanges:page.query.length===0;objectName:"rulesTable";cellPadding:Theme.dp(6);anchors.fill:parent;anchors.bottomMargin:Theme.dp(38);rows:page.displayRules;selectedId:page.selectedRule?page.selectedRule.id:"";fillEmptyRows:true;headerHeight:Theme.dp(26);itemHeight:Theme.dp(32);emptyStripeHeight:Theme.dp(26);columns:[{key:"selector",label:"",w:36},{key:"order",label:"ID",w:32},{key:"type",label:"类型",w:134},{key:"pattern",label:"值",w:276},{key:"policy",label:"策略",w:153},{key:"hits",label:"使用",w:38}];onRowSelected:r=>page.selectedRule=r;onRowEdited:(r,source)=>page.editRule(r,source)}
  Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:Theme.dp(38);color:Theme.tableToolbar
   Row{x:Theme.dp(12);anchors.verticalCenter:parent.verticalCenter;spacing:Theme.dp(8);SwirlButton{objectName:"addRoutingRule";text:"+";implicitWidth:Theme.dp(40);implicitHeight:Theme.dp(24);onClicked:{page.editingIndex=-1;ruleEditor.heroSource=null;rulePattern.text="";ruleEditor.open()}}SwirlButton{objectName:"editRoutingRule";text:"编辑";implicitHeight:Theme.dp(24);enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&!page.engineController.processAlive;onClicked:page.editRule(page.selectedRule,ruleTable.selectedItem)}SwirlButton{objectName:"removeRoutingRule";text:"−";implicitWidth:Theme.dp(40);implicitHeight:Theme.dp(24);enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&!page.engineController.processAlive;onClicked:{if(page.engineController.removeRoutingRule(page.selectedRule.customIndex))page.selectedRule=null;else AppState.notice(page.engineController.networkConfigurationError)}}}
   SwirlButton{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);anchors.verticalCenter:parent.verticalCenter;text:"重置计数器";enabled:false;implicitHeight:Theme.dp(24)}
  }
 }

 SwirlDialog{id:ruleEditor;title:page.editingIndex>=0?"编辑规则":"新增规则";ColumnLayout{width:parent.width;spacing:Theme.dp(14)
  RowLayout{Layout.fillWidth:true;Text{text:"类型：";color:Theme.text}SwirlComboBox{id:ruleType;Layout.fillWidth:true;model:["DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","IP-CIDR6","PROCESS-NAME","DST-PORT","SRC-IP-CIDR","MATCH"]}}
  RowLayout{Layout.fillWidth:true;Text{text:"值：";color:Theme.text}SwirlTextField{id:rulePattern;objectName:"rulePattern";Layout.fillWidth:true;enabled:ruleType.currentText!=="MATCH";placeholderText:"example.com"}}
  RowLayout{Layout.fillWidth:true;Text{text:"策略：";color:Theme.text}SwirlComboBox{id:rulePolicy;Layout.fillWidth:true;model:["DIRECT","REJECT","SWIRL"].concat(page.engineController.policyGroups.map(g=>g.name))}}
  Text{text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:ruleEditor.close()}SwirlButton{objectName:"saveRoutingRule";text:page.editingIndex>=0?"保存":"添加";primary:true;onClicked:{if(page.engineController.saveRoutingRule(ruleType.currentText,rulePattern.text,rulePolicy.currentText,page.editingIndex)){page.selectedRule=null;ruleEditor.close()}}}}
 }}
}
