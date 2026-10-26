pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
 component GatewayMenuItem:MenuItem{
  implicitHeight:visible?Theme.dp(26):0;height:implicitHeight;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12)
  background:Rectangle{radius:Theme.dp(6);color:parent.highlighted?Theme.accent:"transparent"}
  contentItem:SwirlText {text:parent.text;leftPadding:Theme.dp(8);rightPadding:Theme.dp(8);font.family:parent.font.family;font.pixelSize:parent.font.pixelSize;font.weight:parent.font.weight;color:parent.highlighted?"white":parent.enabled?Theme.text:Theme.muted;verticalAlignment:Text.AlignVCenter;elide:Text.ElideRight}
 }
 id:page;property string selectedId:"";property int sortIndex:3
 readonly property var records:{if(!visible)return [];let rows=gatewayProvider.devices.map(r=>Object.assign({},r));if(sortIndex===0)rows.sort((a,b)=>b.total-a.total);else if(sortIndex===1)rows.sort((a,b)=>b.speed-a.speed);else if(sortIndex===2)rows.sort((a,b)=>a.name.localeCompare(b.name));else if(sortIndex===3)rows.sort((a,b)=>ipNumber(a.ip)-ipNumber(b.ip));else if(sortIndex===4)rows.sort((a,b)=>b.lastSeen-a.lastSeen);return rows}
 property bool detailHasSelection:selected!==null
 onDetailHasSelectionChanged:{if(visible)detailClock.moveTo(detailHasSelection?1:0);else{detailClock.destination=detailHasSelection?1:0;detailClock.finish()}}
 SwirlTransitionCoordinator {id:detailClock;duration:SwirlMotion.dialogDuration}
 readonly property var trafficDevice:engineController.telemetry.ranking("devices",AppState.trafficPeriod,100).find(r=>r.name===AppState.trafficSelectedDevice)||null
 readonly property var selected:records.find(r=>r.id===selectedId)||trafficDevice
 readonly property var heroTargets:({deviceName:deviceDetailName})
 readonly property var motionSurfaces:({deviceName:deviceDetailSurface.motionSurface})
 function selectRequested(){const row=records.find(r=>r.name===AppState.trafficSelectedDevice||r.ip===AppState.trafficSelectedDevice);selectedId=row?row.id:""}
 Component.onCompleted:selectRequested()
 Connections {target:AppState;function onTrafficSelectedDeviceChanged(){page.selectRequested()}}
 function ipNumber(ip){return ip.split(".").reduce((n,v)=>n*256+Number(v),0)}
 function configureGateway(){gatewayDialog.open()}
 function preparePreviewState(state){if(state==="device-sort")deviceSort.popup.open();else if(state==="device-settings")page.openGatewayMenu()}
 function openGatewayMenu(){gatewayMenu.showAt(gearButton,Theme.dp(12),Theme.dp(10))}
 SwirlText {textRole:"pageTitle";x:Theme.dp(24);y:Theme.dp(30);text:"设备";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlComboBox{id:deviceSort;objectName:"deviceSortPicker";anchors.right:parent.right;anchors.rightMargin:Theme.dp(20);y:Theme.dp(34);width:Theme.dp(208);height:Theme.dp(24);model:["按流量排序","按速度排序","按名称排序","按 IP 排序","按 DHCP 最后出现时间排序"];currentIndex:page.sortIndex;onActivated:page.sortIndex=currentIndex}
 Item{x:Theme.dp(24);y:Theme.dp(90);width:Math.floor((parent.width-Theme.dp(70))/2);height:parent.height-y-Theme.dp(72)
  SwirlText {visible:page.records.length===0;anchors.centerIn:parent;text:"无设备";color:Theme.muted;font.pixelSize:Theme.fontSize(17);font.weight:Font.DemiBold}
  SwirlDataTable{id:deviceTable;visible:page.records.length>0;anchors.fill:parent;incrementalRows:true;animateRowChanges:false;rows:page.records;selectedId:page.selectedId;columns:[{key:"name",label:"设备",w:160},{key:"ip",label:"IP 地址",w:153}];onRowSelected:r=>{page.selectedId=r.id;deviceDetailSurface.present(deviceTable.selectedItem)}}
 }
 SwirlLinkedDetail{id:deviceDetailSurface;animationLayer:page;sourceViewport:deviceTable;detailOpen:page.selected!==null;anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(90);width:Math.floor((parent.width-Theme.dp(90))/2);height:parent.height-y-Theme.dp(24)
  Column{visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(14)
   SwirlText {id:deviceDetailName;text:page.selected?page.selected.name:"";textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(18)}
   SwirlText {text:page.selected?"IP 地址："+(page.selected.ip||page.selected.name)+"\n上传："+page.selected.upload+"\n下载："+page.selected.download+"\n速度："+(page.selected.speedText||"—")+"\nMAC："+(page.selected.mac||"—")+"\n状态："+(page.selected.status||"已采集流量")+"\n租约到期："+(page.selected.expires?new Date(page.selected.expires*1000).toLocaleString():"—"):"";textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);width:parent.width;wrapMode:Text.WrapAnywhere}
  }
 }
 Item{x:Theme.dp(24);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(10);width:Math.floor((parent.width-Theme.dp(70))/2);height:Theme.dp(64)
  Rectangle{width:parent.width;height:Theme.dp(1);color:Theme.border}
  SwirlText {y:Theme.dp(15);text:"网关模式";color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold}
  SwirlToggle{objectName:"gatewayToggle";x:Theme.dp(68);y:Theme.dp(15);enabled:!gatewayProvider.busy&&gatewayProvider.running;checked:gatewayProvider.running;onToggled:{const wanted=checked;if(wanted){AppState.notice("Rust Core 暂不支持 TUN 网关转发")}else gatewayProvider.stop();checked=Qt.binding(()=>gatewayProvider.running)}Accessible.name:"网关模式"}
  SwirlIconButton{id:gearButton;objectName:"gatewaySettings";quiet:true;anchors.right:parent.right;y:Theme.dp(10);width:Theme.dp(26);height:width;iconName:"settings";onClicked:page.openGatewayMenu()}
  SwirlText {y:Theme.dp(41);width:parent.width;text:gatewayProvider.error||"Rust Core 暂不支持 TUN 网关转发；已保存配置保持不变。";color:Theme.muted;font.pixelSize:Theme.fontSize(10);lineHeightMode:Text.FixedHeight;lineHeight:Theme.dp(13);wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
  Menu{id:gatewayMenu;objectName:"gatewayMenu";popupType:Popup.Window;padding:Theme.dp(5);implicitWidth:Theme.dp(175);background:Rectangle{radius:Theme.popupRadius;color:Theme.dark?Theme.field:"#EAF2F8";border.color:Theme.border}
   GatewayMenuItem{text:"DHCP 服务器："+(gatewayProvider.running?"已启用":"未启用");enabled:false}
   GatewayMenuItem{text:"Swirl 网关："+(gatewayProvider.running?"已启用":"未启用");enabled:false}
   MenuSeparator{implicitHeight:Theme.dp(10);contentItem:Rectangle{implicitWidth:Theme.dp(165);implicitHeight:Theme.dp(1);color:Theme.border}}
   GatewayMenuItem{visible:gatewayProvider.configured;text:"配置网关…";onTriggered:page.configureGateway()}
   GatewayMenuItem{text:"恢复上次的接口转发状态";visible:gatewayProvider.recoveryNeeded&&!gatewayProvider.running;enabled:!gatewayProvider.busy;onTriggered:gatewayProvider.recover()}
   GatewayMenuItem{text:"导出客户端配置到 CSV…";onTriggered:clientExport.open()}
   GatewayMenuItem{text:"从 CSV 导入客户端配置";onTriggered:clientImport.open()}
  }
 }
 SwirlDialog{id:gatewayDialog;title:"网关模式";width:Theme.dp(560)
  ColumnLayout{width:parent.width;spacing:Theme.dp(12)
   SwirlText {text:"当前 Rust Core 构建尚不支持 TUN 网关转发。网关配置可以保留，但无法启用。";Layout.fillWidth:true;color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   SwirlComboBox{id:lanInterface;objectName:"gatewayInterface";Layout.fillWidth:true;model:gatewayProvider.interfaces;textRole:"label";onActivated:{const entry=gatewayProvider.interfaces[currentIndex];gatewayIp.text=entry.ip;prefix.text=String(entry.prefix)}}
   SwirlText {visible:gatewayProvider.interfaces.length===0;text:"当前没有可用的专用 LAN 接口。请接入网卡并设置静态 IPv4 地址。";Layout.fillWidth:true;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   RowLayout{SwirlText {text:"网关 IP";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:gatewayIp;Layout.fillWidth:true;text:gatewayProvider.configuration.gateway||""}}
   RowLayout{SwirlText {text:"子网前缀";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:prefix;Layout.fillWidth:true;text:String(gatewayProvider.configuration.prefix||24);validator:IntValidator{bottom:8;top:30}}}
   RowLayout{SwirlText {text:"地址池开始";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:firstAddress;Layout.fillWidth:true;text:gatewayProvider.configuration.first||"";placeholderText:"例如 192.168.137.100"}}
   RowLayout{SwirlText {text:"地址池结束";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:lastAddress;Layout.fillWidth:true;text:gatewayProvider.configuration.last||"";placeholderText:"例如 192.168.137.200"}}
   RowLayout{SwirlText {text:"DNS";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:gatewayDns;Layout.fillWidth:true;text:gatewayProvider.configuration.dns||"1.1.1.1"}}
   ReferenceCheckBox{id:dedicatedLan;text:"该接口用于专用 LAN，且已关闭该网络的其他 DHCP 服务"}
   SwirlText {text:gatewayProvider.error;Layout.fillWidth:true;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:gatewayDialog.close()}SwirlButton{text:"保存";primary:true;enabled:dedicatedLan.checked&&lanInterface.currentIndex>=0&&gatewayProvider.interfaces.length>0;onClicked:{if(gatewayProvider.configure({interfaceIndex:gatewayProvider.interfaces[lanInterface.currentIndex].index,gateway:gatewayIp.text,prefix:Number(prefix.text),first:firstAddress.text,last:lastAddress.text,dns:gatewayDns.text,leaseSeconds:3600,dedicatedLan:true}))gatewayDialog.close()}}}
  }
 }
 FileDialog{id:clientExport;title:"导出客户端配置";fileMode:FileDialog.SaveFile;nameFilters:["CSV 文件 (*.csv)"];defaultSuffix:"csv";onAccepted:if(!gatewayProvider.exportClients(selectedFile))AppState.notice(gatewayProvider.error)}
 FileDialog{id:clientImport;title:"导入客户端配置";nameFilters:["CSV 文件 (*.csv)"];onAccepted:if(!gatewayProvider.importClients(selectedFile))AppState.notice(gatewayProvider.error)}
}
