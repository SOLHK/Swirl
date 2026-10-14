pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController
 readonly property int modeIndex:engineController.routingMode==="direct"?0:engineController.routingMode==="global"?1:2
 readonly property var groups:engineController.policyGroups
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"策略";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlSegmentedControl{x:Theme.dp(24);y:Theme.dp(78);width:Theme.dp(512);height:Theme.dp(28);rounded:true;objectName:"routingModePicker";optionIcons:["code","network","route"];options:["直接连接","全局代理","规则判定"];textPixelSize:13;accentSelection:true;currentIndex:page.modeIndex;enabled:!page.engineController.busy&&!page.engineController.routingBusy;onActivated:index=>page.engineController.setRoutingMode(["direct","global","rule"][index])}
 Text{x:Theme.dp(24);y:Theme.dp(116);text:["直接连接目标服务器。","所有流量通过代理处理。","根据规则系统判定处理方式。"][page.modeIndex];color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 Text{x:Theme.dp(24);y:Theme.dp(153);text:"代理";color:Theme.magenta;font.pixelSize:Theme.fontSize(13)}
 SwirlButton{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(150);text:"测试全部";implicitHeight:Theme.dp(20);quiet:true;enabled:page.engineController.nodes.length>0&&!page.engineController.tests.busy;onClicked:page.engineController.testAllNodes("https://www.gstatic.com/generate_204")}
 Flow{x:Theme.dp(24);y:Theme.dp(184);width:parent.width-Theme.dp(48);spacing:Theme.dp(12)
  Repeater{model:page.engineController.nodes
   SwirlMotionButton{required property var modelData;required property int index;width:Theme.dp(150);height:Theme.dp(80);padding:Theme.dp(10)
    background:Rectangle{radius:Theme.tileRadius;color:modelData.id===page.engineController.selectedNodeId?Theme.selected:Theme.field;border.color:Theme.border}
    contentItem:Column{spacing:Theme.dp(7);Text{width:parent.width;text:modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}Text{text:modelData.protocol+" · "+modelData.latency;color:Theme.muted;font.pixelSize:Theme.fontSize(11)}}
    onClicked:page.engineController.chooseNode(modelData.id)
   }
  }
  SwirlMotionButton{width:Theme.dp(150);height:Theme.dp(80);background:ReferenceOutline{}
contentItem:Item{SwirlIcon{anchors.centerIn:parent;name:"add-square";size:Theme.dp(22);color:Theme.withAlpha(Theme.muted,0.35)}}
onClicked:AppState.navigate("proxies");Accessible.name:"添加代理"}
 }
 Text{x:Theme.dp(24);y:Theme.dp(299);text:"策略组";color:Theme.cyan;font.pixelSize:Theme.fontSize(13)}
 SwirlMotionButton{x:Theme.dp(24+page.groups.length*162);y:Theme.dp(328);width:Theme.dp(150);height:Theme.dp(80);background:ReferenceOutline{}
contentItem:Item{SwirlIcon{anchors.centerIn:parent;name:"add-square";size:Theme.dp(22);color:Theme.withAlpha(Theme.muted,0.35)}}
onClicked:groupEditor.open();Accessible.name:"添加策略组"}

 Repeater{model:page.groups;SwirlMotionButton{required property var modelData;required property int index;x:Theme.dp(24+index*162);y:Theme.dp(328);width:Theme.dp(150);height:Theme.dp(80);background:Rectangle{color:Theme.field;radius:Theme.tileRadius;border.color:Theme.border}contentItem:Column{Text{text:modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(13)}Text{text:modelData.type;color:Theme.muted;font.pixelSize:Theme.fontSize(11)}}onClicked:{groupEditor.groupName=modelData.name;groupName.text=modelData.name;groupEditor.open()}}}
 SwirlDialog{id:groupEditor;title:"策略组";property string groupName:"";property var members:[];ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  SwirlTextField{id:groupName;Layout.fillWidth:true;placeholderText:"策略组名称"}
  SwirlComboBox{id:groupType;Layout.fillWidth:true;model:["手动选择","自动测试","故障转移","负载均衡"]}
  Text{text:"子策略";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  Repeater{model:[{id:"DIRECT",name:"DIRECT"}].concat(page.engineController.nodes);ReferenceCheckBox{required property var modelData;required property int index;text:modelData.name;onToggled:{const id=modelData.id;groupEditor.members=checked?groupEditor.members.concat([id]):groupEditor.members.filter(member=>member!==id)}}}
  Text{text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"删除";enabled:groupEditor.groupName.length>0;onClicked:{if(page.engineController.removePolicyGroup(groupEditor.groupName))groupEditor.close()}}SwirlButton{text:"取消";onClicked:groupEditor.close()}SwirlButton{text:"保存";primary:true;onClicked:{if(page.engineController.savePolicyGroup(groupName.text,["select","url-test","fallback","load-balance"][groupType.currentIndex],groupEditor.members))groupEditor.close()}}}
 }}
}
