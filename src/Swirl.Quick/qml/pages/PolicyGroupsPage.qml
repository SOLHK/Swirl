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
 property int nodePage:0
 readonly property int nodeColumns:Math.max(1,Math.floor((width-Theme.dp(48)+Theme.dp(12))/Theme.dp(210)))
 readonly property int nodesPerPage:nodeColumns*2
 readonly property int nodePages:Math.max(1,Math.ceil(engineController.nodes.length/nodesPerPage))
 onNodePagesChanged:nodePage=Math.min(nodePage,nodePages-1)
 readonly property var groups:engineController.policyGroups
 SwirlAnimatedModel {id:groupModel;source:page.groups;keyRole:"name"}
 function editGroup(record,source){groupEditor.heroSource=source;groupEditor.groupName=record?record.name:"";groupName.text=record?record.name:"";groupType.currentIndex=record?["select","url-test","fallback","load-balance"].indexOf(record.type):0;groupEditor.members=record?record.proxies.slice():[];groupEditor.open()}
 ScrollView {
  id:scroll;anchors.fill:parent;anchors.margins:Theme.dp(24);clip:true
  ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
 ColumnLayout {
  width:Math.floor(scroll.availableWidth);spacing:Theme.dp(16)
  SwirlText {textRole:"pageTitle";renderType:Text.NativeRendering;text:"策略";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
  SwirlSegmentedControl {Layout.fillWidth:true;Layout.maximumWidth:Theme.dp(600);rounded:true;objectName:"routingModePicker";optionIcons:["code","network","route"];options:["直接连接","全局代理","规则判定"];textPixelSize:13;accentSelection:true;currentIndex:page.modeIndex;enabled:!page.engineController.busy&&!page.engineController.routingBusy;onActivated:index=>page.engineController.setRoutingMode(["direct","global","rule"][index])}
  SwirlText {renderType:Text.NativeRendering;text:["直接连接目标服务器。","所有流量通过代理处理。","根据规则系统判定处理方式。"][page.modeIndex];color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  RowLayout {
   Layout.fillWidth:true;spacing:Theme.dp(10)
   SwirlButton {objectName:"policyConnectButton";text:page.engineController.nodeBusy?qsTr("正在连接…"):page.engineController.processAlive?qsTr("断开出口"):qsTr("连接所选出口");primary:true;enabled:!page.engineController.nodeBusy&&(page.engineController.processAlive||page.engineController.selectedNodeId.length>0||page.engineController.routingMode==="direct");onClicked:{if(page.engineController.processAlive)page.engineController.disconnectNode();else page.engineController.connectNode(page.engineController.selectedNodeId)}}
   Item {Layout.fillWidth:true}
   SwirlText {text:qsTr("本机代理端口");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
   SwirlTextField {objectName:"policyProxyPort";Layout.preferredWidth:Theme.dp(88);text:String(page.engineController.proxyPort);enabled:page.engineController.canStart;validator:IntValidator {bottom:1;top:65535}horizontalAlignment:TextInput.AlignHCenter;onEditingFinished:{if(acceptableInput)page.engineController.proxyPort=Number(text);text=String(page.engineController.proxyPort)}Accessible.name:qsTr("本机代理端口")}
  }
  RowLayout {Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"代理";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {text:"节点管理";quiet:true;iconName:"server";onClicked:page.Window.window.openSettings("proxies")}SwirlButton {text:"测试全部";quiet:true;iconName:"activity";enabled:page.engineController.nodes.length>0&&!page.engineController.tests.busy;onClicked:page.engineController.testAllNodes("https://www.gstatic.com/generate_204")}}
  SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:nodeGrid.implicitHeight+Theme.dp(page.engineController.nodes.length?80:32)
   Grid {id:nodeGrid;x:Theme.dp(16);y:Theme.dp(16);width:parent.width-Theme.dp(32);columns:page.nodeColumns;spacing:Theme.dp(12)
    Repeater {model:page.engineController.nodes.slice(page.nodePage*page.nodesPerPage,(page.nodePage+1)*page.nodesPerPage)
     SwirlMotionButton {
      id:node;required property var modelData;objectName:"policyNode-"+modelData.id;width:Math.floor((nodeGrid.width-(nodeGrid.columns-1)*nodeGrid.spacing)/nodeGrid.columns);height:Theme.dp(94);padding:Theme.dp(12);hoverEnabled:true
      background:Rectangle {radius:Theme.controlRadius;color:node.down?Theme.pressed:node.hovered?Theme.hover:node.modelData.id===page.engineController.selectedNodeId?Theme.selected:Theme.field;border.width:node.activeFocus?2:1;border.color:node.activeFocus?Theme.focusBorder:Theme.border}
      contentItem:ColumnLayout {spacing:Theme.dp(8)
       SwirlText {renderType:Text.NativeRendering;Layout.fillWidth:true;Layout.fillHeight:true;text:node.modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(13);wrapMode:Text.Wrap;maximumLineCount:2;elide:Text.ElideRight}
       SwirlText {renderType:Text.NativeRendering;Layout.fillWidth:true;text:node.modelData.protocol+" · "+node.modelData.latency;color:Theme.muted;font.pixelSize:Theme.fontSize(11);elide:Text.ElideRight}
      }
      SwirlToolTip {parent:node;visible:node.hovered||node.activeFocus;text:node.modelData.name}
      Accessible.name:modelData.name;onClicked:page.engineController.chooseNode(modelData.id)
     }
    }
    SwirlText {renderType:Text.NativeRendering;visible:page.engineController.nodes.length===0;width:nodeGrid.width;text:"尚无代理节点，请通过节点管理添加或导入。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
   }
  RowLayout {visible:page.engineController.nodes.length>0;x:Theme.dp(16);y:nodeGrid.y+nodeGrid.height+Theme.dp(12);width:parent.width-Theme.dp(32);height:Theme.controlHeight
   SwirlText {renderType:Text.NativeRendering;text:page.engineController.nodes.length+" 个节点 · 第 "+(page.nodePage+1)+" / "+page.nodePages+" 页";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
   SwirlButton {objectName:"previousNodePage";visible:page.nodePages>1;text:"上一页";enabled:page.nodePage>0;onClicked:--page.nodePage}
   SwirlButton {objectName:"nextNodePage";visible:page.nodePages>1;text:"下一页";enabled:page.nodePage<page.nodePages-1;onClicked:++page.nodePage}
  }
  }
  RowLayout {Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;text:"策略组";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlButton {objectName:"addPolicyGroup";text:"添加策略组";onClicked:page.editGroup(null,null)}}
  ListView { pixelAligned: true;
   Layout.fillWidth:true;Layout.preferredHeight:page.groups.length===0?Theme.dp(130):Math.min(Theme.dp(400),contentHeight);spacing:Theme.dp(12);clip:true;model:groupModel;ScrollBar.vertical:SwirlScrollBar {}
   SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:page.groups.length===0;headline:"尚无策略组";detail:"添加策略组以组织节点与路由。"}
   delegate:SwirlMotionButton {
    id:group;required property var entry;readonly property var modelData:entry;objectName:"policyCard-"+modelData.name;width:Math.floor(ListView.view.width);height:Math.ceil(Math.max(Theme.dp(88),contentItem.implicitHeight+2*Theme.cardPadding));padding:Theme.cardPadding
    background:SwirlContinuousSurface {radius:Theme.cardRadius;color:Theme.field;border.width:Theme.borderWidth;border.color:Theme.border}
    contentItem:RowLayout {SwirlIcon {name:"layers";color:Theme.accent;size:Theme.dp(28)}ColumnLayout {Layout.fillWidth:true;SwirlText {renderType:Text.NativeRendering;Layout.fillWidth:true;wrapMode:Text.Wrap;text:group.modelData.name;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}SwirlText {renderType:Text.NativeRendering;text:group.modelData.type+" · "+group.modelData.proxies.length+" 个子策略";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}}SwirlIcon {name:"chevron-right";size:Theme.dp(18)}}
    onClicked:page.editGroup(modelData,group)
   }
  }
 }
 }
 SwirlDialog {
  id:groupEditor;objectName:"policyGroupDialog";title:"策略组";property string groupName:"";property var members:[]
  ColumnLayout {width:parent.width;spacing:Theme.dp(12)
   SwirlTextField {id:groupName;objectName:"policyGroupName";Layout.fillWidth:true;placeholderText:"策略组名称";readOnly:groupEditor.groupName.length>0}
   SwirlComboBox {id:groupType;objectName:"policyGroupType";Layout.fillWidth:true;model:["手动选择","自动测试","故障转移","负载均衡"]}
   SwirlText {renderType:Text.NativeRendering;text:"子策略";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
   ListView { pixelAligned: true;
    Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(190);clip:true;model:[{id:"DIRECT",name:"DIRECT"},{id:"REJECT",name:"REJECT"}].concat(page.engineController.nodes);ScrollBar.vertical:SwirlScrollBar {}
    delegate:ReferenceCheckBox {required property var modelData;width:Math.floor(ListView.view.width);text:modelData.name;checked:groupEditor.members.indexOf(modelData.id)>=0;onToggled:{const id=modelData.id;groupEditor.members=checked?groupEditor.members.concat([id]):groupEditor.members.filter(member=>member!==id)}}
   }
   SwirlText {renderType:Text.NativeRendering;text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
   RowLayout {Layout.alignment:Qt.AlignRight
    SwirlButton {text:"删除";enabled:groupEditor.groupName.length>0;onClicked:{if(page.engineController.removePolicyGroup(groupEditor.groupName))groupEditor.close()}}
    SwirlButton {text:"取消";onClicked:groupEditor.close()}
    SwirlButton {objectName:"savePolicyGroup";text:"保存";primary:true;onClicked:{if(page.engineController.savePolicyGroup(groupName.text,["select","url-test","fallback","load-balance"][groupType.currentIndex],groupEditor.members))groupEditor.close()}}
   }
  }
 }
}
