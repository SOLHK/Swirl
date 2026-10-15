pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;property int sortIndex:0;property string selectedId:""
 readonly property var telemetry:engineController.telemetry
 readonly property var heroTargets:({processName:processDetailName})
 function selectRequested(){const row=processes.find(r=>r.name===AppState.trafficSelectedProcess);if(row)selectedId=row.id}
 Component.onCompleted:selectRequested()
 Connections {target:AppState;function onTrafficSelectedProcessChanged(){page.selectRequested()}function onTrafficPeriodChanged(){Qt.callLater(page.selectRequested)}}
 readonly property var processes:{let rows=(telemetry.revision,telemetry.ranking("apps",AppState.trafficPeriod,100));if(sortIndex===1)rows.sort((a,b)=>b.speed-a.speed);else if(sortIndex===2)rows.sort((a,b)=>a.name.localeCompare(b.name));return rows}
 readonly property var selected:processes.find(r=>r.id===selectedId)||null
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.gap
  RowLayout {Layout.fillWidth:true
   Text {text:"进程";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.fillWidth:true}
   SwirlComboBox {objectName:"processSortPicker";Layout.preferredWidth:Theme.dp(146);model:["按流量排序","按速度排序","按名称排序"];onActivated:page.sortIndex=currentIndex}
  }
  Text {text:"按实际采集的流量查看应用，选择进程查看连接摘要。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
  RowLayout {Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.gap
   SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredWidth:3;Layout.fillHeight:true
    ColumnLayout {anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
     RowLayout {Layout.fillWidth:true
      Text {text:"应用流量";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
      Text {text:page.processes.length+" 个进程";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
     }
     SwirlDataTable {objectName:"processTable";Layout.fillWidth:true;Layout.fillHeight:true;visible:page.processes.length>0;rows:page.processes;selectedId:page.selectedId;minimal:true;columns:[{key:"name",label:"进程",w:220},{key:"value",label:"总流量",w:110}];onRowSelected:r=>page.selectedId=r.id}
     Item {visible:page.processes.length===0;Layout.fillWidth:true;Layout.fillHeight:true
      SwirlEmptyState {anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(16));headline:"尚无进程流量";detail:"连接节点并产生网络流量后，这里会显示实际采集的应用。"}
     }
    }
   }
   SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredWidth:2;Layout.fillHeight:true
    ColumnLayout {visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(16)
     Text {text:"进程详情";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
     Text {id:processDetailName;text:page.selected?page.selected.name:"";color:Theme.text;font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
     Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
     Repeater {model:page.selected?[{label:"上传",value:page.selected.upload},{label:"下载",value:page.selected.download},{label:"连接",value:page.selected.connections}]:[]
      RowLayout {required property var modelData;Layout.fillWidth:true;Text {text:modelData.label;color:Theme.muted;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true}Text {text:String(modelData.value);color:Theme.text;font.pixelSize:Theme.fontSize(13)}}
     }
     Item {Layout.fillHeight:true}
     SwirlButton {text:"查看连接";Layout.fillWidth:true;onClicked:page.Window.window.openDashboard()}
    }
    SwirlEmptyState {visible:page.selected===null;anchors.centerIn:parent;width:Math.max(0,parent.width-2*Theme.cardPadding);headline:"选择一个进程";detail:"从左侧选择应用，查看上传、下载和连接摘要。"}
   }
  }
  SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:meteredBody.implicitHeight+2*Theme.cardPadding
   ColumnLayout {id:meteredBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(8)
    RowLayout {Layout.fillWidth:true
     Text {text:"计费网络模式";color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold;Layout.fillWidth:true}
     SwirlToggle {objectName:"meteredToggle";enabled:!page.engineController.busy;checked:page.engineController.meteredEnabled;onToggled:{if(!page.engineController.setMeteredEnabled(checked))AppState.notice(page.engineController.routingError);checked=Qt.binding(()=>page.engineController.meteredEnabled)}Accessible.name:"计费网络模式"}
     SwirlIconButton {quiet:true;iconName:"settings";tooltip:"计费网络允许列表";onClicked:{allowedProcesses.text=page.engineController.meteredAllowlist.join("\n");meteredDialog.open()}}
    }
    Text {text:"启用后仅允许指定进程访问网络，适用于按流量计费的网络与热点。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
   }
  }
 }
 SwirlDialog{id:meteredDialog;title:"计费网络模式";ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  Text{text:"默认阻止所有程序的网络，仅允许下面的程序继续按分流规则访问。启用时自动开启增强模式，并保持规则判定。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  TextArea{id:allowedProcesses;objectName:"meteredAllowlistEditor";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(140);placeholderText:"每行一个程序名，例如 chrome.exe";font.pixelSize:Theme.fontSize(13);selectByMouse:true;wrapMode:TextEdit.NoWrap}
  Text{text:page.engineController.networkConfigurationError||page.engineController.routingError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:meteredDialog.close()}SwirlButton{text:"保存";primary:true;onClicked:{if(page.engineController.configureMeteredAllowlist(allowedProcesses.text.split(/\r?\n/).filter(s=>s.trim().length>0)))meteredDialog.close()}}}
 }}
}
