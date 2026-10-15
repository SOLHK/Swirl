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
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.gap
  RowLayout {Layout.fillWidth:true
   SwirlText {renderType:Text.NativeRendering;text:"规则";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.fillWidth:true}
  }
  SwirlText {renderType:Text.NativeRendering;text:"规则按从上至下的顺序测试；双击自定义规则可编辑。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
  SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:Math.min(ruleArea.implicitHeight+2*Theme.cardPadding,Math.max(Theme.dp(240),page.height-Theme.dp(150)));Layout.maximumHeight:Math.max(Theme.dp(200),page.height-Theme.dp(150))
   ColumnLayout {id:ruleArea;anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
    RowLayout {Layout.fillWidth:true
     SwirlText {renderType:Text.NativeRendering;text:"路由规则";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
     SwirlText {renderType:Text.NativeRendering;text:page.displayRules.length+" 条规则";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
     SwirlSearchField {objectName:"rulesSearch";Layout.preferredWidth:Math.min(Theme.dp(240),page.width*0.36);placeholderText:"搜索类型、值或策略";onTextChanged:page.query=text}
    }
    SwirlDataTable {id:ruleTable;objectName:"rulesTable";textPixelSize:13;headerPixelSize:12;Layout.fillWidth:true;Layout.fillHeight:true;Layout.preferredHeight:Theme.tableHeaderHeight+Math.max(1,page.displayRules.length)*Theme.tableRowHeight;visible:page.displayRules.length>0;incrementalRows:true;animateRowChanges:page.query.length===0;rows:page.displayRules;selectedId:page.selectedRule?page.selectedRule.id:"";fillEmptyRows:false;columns:[{key:"order",label:"ID",w:40},{key:"type",label:"类型",w:125},{key:"pattern",label:"值",w:230},{key:"policy",label:"策略",w:100},{key:"hits",label:"使用",w:50}];onRowSelected:r=>page.selectedRule=r;onRowEdited:(r,source)=>page.editRule(r,source)}
    SwirlEmptyState {visible:page.displayRules.length===0;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(130);headline:page.query.length?"没有匹配的规则":"尚无路由规则";detail:page.query.length?"尝试其他关键词，或清空搜索。":"添加自定义规则以控制流量的处理方式。"}
    RowLayout {Layout.fillWidth:true;spacing:Theme.dp(8)
     SwirlButton {objectName:"addRoutingRule";text:"添加";iconName:"plus";onClicked:{page.editingIndex=-1;ruleEditor.heroSource=null;rulePattern.text="";ruleEditor.open()}}
     SwirlButton {objectName:"editRoutingRule";text:"编辑";enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&!page.engineController.processAlive;onClicked:page.editRule(page.selectedRule,ruleTable.selectedItem)}
     SwirlButton {objectName:"removeRoutingRule";text:"删除";enabled:page.selectedRule!==null&&page.selectedRule.customIndex!==undefined&&!page.engineController.processAlive;onClicked:{if(page.engineController.removeRoutingRule(page.selectedRule.customIndex))page.selectedRule=null;else AppState.notice(page.engineController.networkConfigurationError)}}
     Item {Layout.fillWidth:true}
     SwirlButton {text:"重置计数器";development:true;enabled:false}
    }
   }
  }
  Item {Layout.fillHeight:true}
 }

 SwirlDialog{id:ruleEditor;title:page.editingIndex>=0?"编辑规则":"新增规则";ColumnLayout{width:parent.width;spacing:Theme.dp(14)
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"类型：";color:Theme.text}SwirlComboBox{id:ruleType;Layout.fillWidth:true;model:["DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","IP-CIDR6","PROCESS-NAME","DST-PORT","SRC-IP-CIDR","MATCH"]}}
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"值：";color:Theme.text}SwirlTextField{id:rulePattern;objectName:"rulePattern";Layout.fillWidth:true;enabled:ruleType.currentText!=="MATCH";placeholderText:"example.com"}}
  RowLayout{Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"策略：";color:Theme.text}SwirlComboBox{id:rulePolicy;Layout.fillWidth:true;model:["DIRECT","REJECT","SWIRL"].concat(page.engineController.policyGroups.map(g=>g.name))}}
  SwirlText {renderType:Text.NativeRendering;text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:ruleEditor.close()}SwirlButton{objectName:"saveRoutingRule";text:page.editingIndex>=0?"保存":"添加";primary:true;onClicked:{if(page.engineController.saveRoutingRule(ruleType.currentText,rulePattern.text,rulePolicy.currentText,page.editingIndex)){page.selectedRule=null;ruleEditor.close()}}}}
 }}
}
