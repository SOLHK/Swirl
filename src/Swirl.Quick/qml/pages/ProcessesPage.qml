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
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"进程";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlComboBox{objectName:"processSortPicker";anchors.right:parent.right;anchors.rightMargin:Theme.dp(20);y:Theme.dp(34);width:Theme.dp(112);height:Theme.dp(24);model:["按流量排序","按速度排序","按名称排序"];onActivated:page.sortIndex=currentIndex}
 Item{x:Theme.dp(24);y:Theme.dp(90);width:(parent.width-Theme.dp(70))/2;height:parent.height-y-Theme.dp(72)
  Text{visible:page.processes.length===0;anchors.centerIn:parent;text:"无进程";color:Theme.muted;font.pixelSize:Theme.fontSize(17);font.weight:Font.DemiBold}
  SwirlDataTable{visible:page.processes.length>0;anchors.fill:parent;rows:page.processes;itemHeight:Theme.dp(40);columns:[{key:"name",label:"进程",w:210},{key:"value",label:"流量",w:110}];onRowSelected:r=>page.selectedId=r.id}
 }
 ReferenceOutline{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(90);width:(parent.width-Theme.dp(90))/2;height:parent.height-y-Theme.dp(24)
  Column{visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(12)
   Text{id:processDetailName;text:page.selected?page.selected.name:"";color:Theme.text;font.pixelSize:Theme.fontSize(18);width:parent.width;wrapMode:Text.WrapAnywhere}
   Text{text:page.selected?"上传  "+page.selected.upload+"\n下载  "+page.selected.download+"\n连接  "+page.selected.connections:"";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}
   SwirlButton{text:"查看连接";onClicked:page.Window.window.openDashboard()}
  }
 }
 Item{x:Theme.dp(24);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(10);width:(parent.width-Theme.dp(70))/2;height:Theme.dp(64)
  Rectangle{width:parent.width;height:Theme.dp(1);color:Theme.border}
  Text{y:Theme.dp(15);text:"计费网络模式";color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold}
  SwirlToggle{objectName:"meteredToggle";x:Theme.dp(96);y:Theme.dp(15);enabled:!page.engineController.busy;checked:page.engineController.meteredEnabled;onToggled:{if(!page.engineController.setMeteredEnabled(checked))AppState.notice(page.engineController.routingError);checked=Qt.binding(()=>page.engineController.meteredEnabled)}Accessible.name:"计费网络模式"}
  SwirlIconButton{quiet:true;anchors.right:parent.right;y:Theme.dp(10);width:Theme.dp(26);height:width;iconName:"settings";onClicked:{allowedProcesses.text=page.engineController.meteredAllowlist.join("\n");meteredDialog.open()}}
  Text{y:Theme.dp(41);width:parent.width;text:"启动后所有进程将默认禁止使用网络。适用于按流量计费的网络，如数据网络热点。";color:Theme.muted;font.pixelSize:Theme.fontSize(10);wrapMode:Text.WordWrap}
 }
 SwirlDialog{id:meteredDialog;title:"计费网络模式";ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  Text{text:"默认阻止所有程序的网络，仅允许下面的程序继续按分流规则访问。启用时自动开启增强模式，并保持规则判定。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  TextArea{id:allowedProcesses;objectName:"meteredAllowlistEditor";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(140);placeholderText:"每行一个程序名，例如 chrome.exe";font.pixelSize:Theme.fontSize(13);selectByMouse:true;wrapMode:TextEdit.NoWrap}
  Text{text:page.engineController.networkConfigurationError||page.engineController.routingError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:meteredDialog.close()}SwirlButton{text:"保存";primary:true;onClicked:{if(page.engineController.configureMeteredAllowlist(allowedProcesses.text.split(/\r?\n/).filter(s=>s.trim().length>0)))meteredDialog.close()}}}
 }}
}
