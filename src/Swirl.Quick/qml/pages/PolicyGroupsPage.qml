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
 SwirlAnimatedModel {id:groupModel;source:page.groups;keyRole:"name"}
 function editGroup(record,source){groupEditor.heroSource=source;groupEditor.groupName=record?record.name:"";groupName.text=record?record.name:"";groupType.currentIndex=record?["select","url-test","fallback","load-balance"].indexOf(record.type):0;groupEditor.members=record?record.proxies.slice():[];groupEditor.open()}
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(16)
  Text {text:"策略";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
  SwirlSegmentedControl {Layout.fillWidth:true;Layout.maximumWidth:Theme.dp(600);rounded:true;objectName:"routingModePicker";optionIcons:["code","network","route"];options:["直接连接","全局代理","规则判定"];textPixelSize:13;accentSelection:true;currentIndex:page.modeIndex;enabled:!page.engineController.busy&&!page.engineController.routingBusy;onActivated:index=>page.engineController.setRoutingMode(["direct","global","rule"][index])}
  Text {text:["直接连接目标服务器。","所有流量通过代理处理。","根据规则系统判定处理方式。"][page.modeIndex];color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  RowLayout {Layout.fillWidth:true;Text {text:"代理";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {text:"节点管理";onClicked:page.Window.window.openSettings("proxies")}SwirlButton {text:"测试全部";enabled:page.engineController.nodes.length>0&&!page.engineController.tests.busy;onClicked:page.engineController.testAllNodes("https://www.gstatic.com/generate_204")}}
  ListView {
   Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(94);orientation:ListView.Horizontal;spacing:Theme.dp(12);clip:true;model:page.engineController.nodes
   ScrollBar.horizontal:SwirlScrollBar {}
   delegate:SwirlMotionButton {
    id:node;required property var modelData;width:Theme.dp(165);height:Theme.dp(80);padding:Theme.dp(12)
    background:SwirlContinuousSurface {radius:Theme.dp(16);color:node.modelData.id===page.engineController.selectedNodeId?Theme.selected:Theme.field;border.width:Theme.borderWidth;border.color:Theme.border}
    contentItem:Column {spacing:Theme.dp(8);Text {width:parent.width;text:node.modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}Text {text:node.modelData.protocol+" · "+node.modelData.latency;color:Theme.muted;font.pixelSize:Theme.fontSize(11)}}
    onClicked:page.engineController.chooseNode(modelData.id)
   }
  }
  RowLayout {Layout.fillWidth:true;Text {text:"策略组";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {objectName:"addPolicyGroup";text:"添加策略组";onClicked:page.editGroup(null,null)}}
  ListView {
   Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(12);clip:true;model:groupModel;ScrollBar.vertical:SwirlScrollBar {}
   delegate:SwirlMotionButton {
    id:group;required property var entry;readonly property var modelData:entry;objectName:"policyCard-"+modelData.name;width:ListView.view.width;height:Theme.dp(80);padding:Theme.dp(16)
    background:SwirlContinuousSurface {radius:Theme.dp(20);color:Theme.field;border.width:Theme.borderWidth;border.color:Theme.border}
    contentItem:RowLayout {SwirlIcon {name:"layers";color:Theme.accent;size:Theme.dp(28)}ColumnLayout {Layout.fillWidth:true;Text {text:group.modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}Text {text:group.modelData.type+" · "+group.modelData.proxies.length+" 个子策略";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}}SwirlIcon {name:"chevron-right";size:Theme.dp(18)}}
    onClicked:page.editGroup(modelData,group)
   }
  }
 }
 SwirlDialog {
  id:groupEditor;objectName:"policyGroupDialog";title:"策略组";property string groupName:"";property var members:[]
  ColumnLayout {width:parent.width;spacing:Theme.dp(12)
   SwirlTextField {id:groupName;objectName:"policyGroupName";Layout.fillWidth:true;placeholderText:"策略组名称";readOnly:groupEditor.groupName.length>0}
   SwirlComboBox {id:groupType;objectName:"policyGroupType";Layout.fillWidth:true;model:["手动选择","自动测试","故障转移","负载均衡"]}
   Text {text:"子策略";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
   ListView {
    Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(190);clip:true;model:[{id:"DIRECT",name:"DIRECT"},{id:"REJECT",name:"REJECT"}].concat(page.engineController.nodes);ScrollBar.vertical:SwirlScrollBar {}
    delegate:ReferenceCheckBox {required property var modelData;width:ListView.view.width;text:modelData.name;checked:groupEditor.members.indexOf(modelData.id)>=0;onToggled:{const id=modelData.id;groupEditor.members=checked?groupEditor.members.concat([id]):groupEditor.members.filter(member=>member!==id)}}
   }
   Text {text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
   RowLayout {Layout.alignment:Qt.AlignRight
    SwirlButton {text:"删除";enabled:groupEditor.groupName.length>0;onClicked:{if(page.engineController.removePolicyGroup(groupEditor.groupName))groupEditor.close()}}
    SwirlButton {text:"取消";onClicked:groupEditor.close()}
    SwirlButton {objectName:"savePolicyGroup";text:"保存";primary:true;onClicked:{if(page.engineController.savePolicyGroup(groupName.text,["select","url-test","fallback","load-balance"][groupType.currentIndex],groupEditor.members))groupEditor.close()}}
   }
  }
 }
}
