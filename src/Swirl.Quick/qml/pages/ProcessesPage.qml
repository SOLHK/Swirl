pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;property int sortIndex:0;property string selectedId:""
 readonly property Item motionTitle:heading.titleItem
 readonly property bool compact:width<Theme.dp(620)
 readonly property var telemetry:engineController.telemetry
 readonly property var heroTargets:({processName:processDetailName})
 readonly property var motionSurfaces:({processName:processDetailSurface.motionSurface})
 function selectRequested(){const row=processes.find(r=>r.name===AppState.trafficSelectedProcess);if(row)selectedId=row.id}
 Component.onCompleted:selectRequested()
 Connections {target:AppState;function onTrafficSelectedProcessChanged(){page.selectRequested()}function onTrafficPeriodChanged(){Qt.callLater(page.selectRequested)}}
 readonly property var processes:{if(!visible)return [];let rows=(telemetry.revision,telemetry.ranking("apps",AppState.trafficPeriod,100));if(sortIndex===1)rows.sort((a,b)=>b.speed-a.speed);else if(sortIndex===2)rows.sort((a,b)=>a.name.localeCompare(b.name));return rows}
 property bool detailHasSelection:selected!==null
 onDetailHasSelectionChanged:{if(visible)detailClock.moveTo(detailHasSelection?1:0);else{detailClock.destination=detailHasSelection?1:0;detailClock.finish()}}
 SwirlTransitionCoordinator {id:detailClock;duration:SwirlMotion.dialogDuration}
 readonly property var selected:processes.find(r=>r.id===selectedId)||null
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
  SwirlPageHeader {id:heading;Layout.fillWidth:true;title:qsTr("进程");description:qsTr("已采集连接归属的应用流量，不代表系统内所有进程。");metadata:qsTr("%1 个应用，按所选统计期间显示").arg(page.processes.length)
   SwirlComboBox {objectName:"processSortPicker";Layout.preferredWidth:Theme.dp(156);Accessible.name:qsTr("进程排序");model:[qsTr("按流量排序"),qsTr("按速度排序"),qsTr("按名称排序")];currentIndex:page.sortIndex;onActivated:page.sortIndex=currentIndex}
  }
  GridLayout {Layout.fillWidth:true;Layout.fillHeight:true;columns:page.compact?1:2;columnSpacing:Theme.sectionGap;rowSpacing:Theme.sectionGap
   Item {Layout.fillWidth:true;Layout.preferredWidth:3;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(100)
    SwirlDataTable {id:processTable;objectName:"processTable";anchors.fill:parent;visible:page.processes.length>0;incrementalRows:true;animateRowChanges:false;rows:page.processes;selectedId:page.selectedId;minimal:true;textPixelSize:13;headerPixelSize:12;itemHeight:Theme.dp(42);columns:[{key:"name",label:qsTr("进程"),w:240},{key:"value",label:qsTr("总流量"),w:120}];onRowSelected:r=>{page.selectedId=r.id;processDetailSurface.present(processTable.selectedItem)}}
    SwirlEmptyState {visible:page.processes.length===0;anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(24));headline:qsTr("尚无进程流量");detail:qsTr("经过 Swirl 的连接产生可归属流量后，应用会显示在这里。")}
   }
   SwirlLinkedDetail {id:processDetailSurface;animationLayer:page;sourceViewport:processTable;detailOpen:page.selected!==null;visible:!page.compact||page.selected!==null||moving;Layout.fillWidth:true;Layout.preferredWidth:2;Layout.fillHeight:!page.compact;Layout.preferredHeight:page.compact?Theme.dp(180):-1;Layout.minimumHeight:Theme.dp(120)
    ScrollView {id:processDetailScroll;visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.cardPadding;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
    ColumnLayout {width:processDetailScroll.availableWidth;spacing:Theme.dp(14)
     SwirlText {text:qsTr("进程详情");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
     SwirlText {id:processDetailName;textFormat:Text.PlainText;text:page.selected?page.selected.name:"";color:Theme.text;font.pixelSize:Theme.fontSize(20);font.weight:Font.DemiBold;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
     Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
     Repeater {model:page.selected?[{label:qsTr("上传"),value:page.selected.upload},{label:qsTr("下载"),value:page.selected.download},{label:qsTr("连接"),value:page.selected.connections}]:[]
      RowLayout {required property var modelData;Layout.fillWidth:true;SwirlText {text:modelData.label;color:Theme.muted;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true}SwirlText {text:String(modelData.value);color:Theme.text;font.pixelSize:Theme.fontSize(14)}}
     }
     Item {Layout.fillHeight:true}
     SwirlButton {text:qsTr("查看连接");Layout.fillWidth:true;onClicked:page.Window.window.openDashboard()}
    }
    }
    SwirlEmptyState {visible:page.selected===null;anchors.centerIn:parent;width:Math.max(0,parent.width-2*Theme.cardPadding);headline:qsTr("选择一个进程");detail:qsTr("从列表选择应用，查看实际上传、下载和连接摘要。")}
   }
  }
  Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
  RowLayout {Layout.fillWidth:true;spacing:Theme.dp(14)
   ColumnLayout {Layout.fillWidth:true;spacing:Theme.dp(5);SwirlText {text:qsTr("计费网络模式");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}SwirlText {text:page.engineController.routingError||qsTr("当前不支持计费网络接管。允许名单可保存，尚不执行流量阻止。");color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}}
   SwirlToggle {objectName:"meteredToggle";enabled:page.engineController.meteredEnabled&&!page.engineController.busy;checked:page.engineController.meteredEnabled;onToggled:{page.engineController.setMeteredEnabled(checked);checked=Qt.binding(()=>page.engineController.meteredEnabled)}Accessible.name:qsTr("计费网络模式")}
   SwirlIconButton {quiet:true;iconName:"settings";tooltip:qsTr("计费网络允许列表");onClicked:{allowedProcesses.text=page.engineController.meteredAllowlist.join("\n");meteredDialog.open()}}
  }
 }
 SwirlDialog{id:meteredDialog;objectName:"meteredDialog";title:"计费网络模式"
 height:Math.min(Theme.dp(430),parent?parent.height-Theme.dp(32):Theme.dp(430))
 contentItem:ScrollView {id:meteredScroll;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
 ColumnLayout{width:meteredScroll.availableWidth;spacing:Theme.dp(12)
  SwirlText {renderType:Text.NativeRendering;text:"当前尚未实现 TUN 与进程网络阻止。下面的允许名单仅保存为配置，不代表已限制任何程序的网络。";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  SwirlText {text:page.engineController.elevated?"已具备管理员权限；当前构建仍不支持计费网络接管。":"当前构建不支持计费网络接管；保存名单不会自动开启。";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  SwirlTextArea {id:allowedProcesses;objectName:"meteredAllowlistEditor";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(140);placeholderText:"每行一个程序名，例如 chrome.exe";font.pixelSize:Theme.fontSize(13);selectByMouse:true;wrapMode:TextEdit.NoWrap}
  SwirlText {renderType:Text.NativeRendering;text:page.engineController.networkConfigurationError||page.engineController.routingError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
 }}
 footer:RowLayout{spacing:Theme.dp(10);height:Theme.dp(58)
 Item {Layout.fillWidth:true}
 SwirlButton{text:"取消";onClicked:meteredDialog.close()}SwirlButton{text:"保存";primary:true;onClicked:{if(page.engineController.configureMeteredAllowlist(allowedProcesses.text.split(/\r?\n/).filter(s=>s.trim().length>0)))meteredDialog.close()}}
 Item {implicitWidth:Theme.dp(20)}
 }
 }
}
