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
  contentItem:Text{text:parent.text;leftPadding:Theme.dp(8);rightPadding:Theme.dp(8);font:parent.font;color:parent.highlighted?"white":parent.enabled?Theme.text:Theme.muted;verticalAlignment:Text.AlignVCenter;elide:Text.ElideRight}
 }
 id:page;property string selectedId:"";property int sortIndex:3
 readonly property var records:{let rows=gatewayProvider.devices.map(r=>Object.assign({},r));if(sortIndex===0)rows.sort((a,b)=>b.total-a.total);else if(sortIndex===1)rows.sort((a,b)=>b.speed-a.speed);else if(sortIndex===2)rows.sort((a,b)=>a.name.localeCompare(b.name));else if(sortIndex===3)rows.sort((a,b)=>ipNumber(a.ip)-ipNumber(b.ip));else if(sortIndex===4)rows.sort((a,b)=>b.lastSeen-a.lastSeen);return rows}
 readonly property var selected:records.find(r=>r.id===selectedId)||null
 function ipNumber(ip){return ip.split(".").reduce((n,v)=>n*256+Number(v),0)}
 function configureGateway(){gatewayDialog.open()}
 function preparePreviewState(state){if(state==="device-sort")deviceSort.popup.open();else if(state==="device-settings")page.openGatewayMenu()}
 function openGatewayMenu(){gatewayMenu.popup(gearButton,Theme.dp(12),Theme.dp(10))}
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"设备";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlComboBox{id:deviceSort;objectName:"deviceSortPicker";anchors.right:parent.right;anchors.rightMargin:Theme.dp(20);y:Theme.dp(34);width:Theme.dp(208);height:Theme.dp(24);model:["按流量排序","按速度排序","按名称排序","按 IP 排序","按 DHCP 最后出现时间排序"];currentIndex:page.sortIndex;onActivated:page.sortIndex=currentIndex}
 Item{x:Theme.dp(24);y:Theme.dp(90);width:(parent.width-Theme.dp(70))/2;height:parent.height-y-Theme.dp(72)
  Text{visible:page.records.length===0;anchors.centerIn:parent;text:"无设备";color:Theme.muted;font.pixelSize:Theme.fontSize(17);font.weight:Font.DemiBold}
  SwirlDataTable{visible:page.records.length>0;anchors.fill:parent;rows:page.records;selectedId:page.selectedId;columns:[{key:"name",label:"设备",w:160},{key:"ip",label:"IP 地址",w:153}];onRowSelected:r=>page.selectedId=r.id}
 }
 ReferenceOutline{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(90);width:(parent.width-Theme.dp(90))/2;height:parent.height-y-Theme.dp(24)
  Column{visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(14)
   Text{text:page.selected?page.selected.name:"";textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(18)}
   Text{text:page.selected?"IP 地址："+page.selected.ip+"\n上传："+page.selected.upload+"\n下载："+page.selected.download+"\n速度："+page.selected.speedText+"\nMAC："+page.selected.mac+"\n状态："+page.selected.status+"\n租约到期："+new Date(page.selected.expires*1000).toLocaleString():"";textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);width:parent.width;wrapMode:Text.WrapAnywhere}
  }
 }
 Item{x:Theme.dp(24);anchors.bottom:parent.bottom;anchors.bottomMargin:Theme.dp(10);width:(parent.width-Theme.dp(70))/2;height:Theme.dp(64)
  Rectangle{width:parent.width;height:Theme.dp(1);color:Theme.border}
  Text{y:Theme.dp(15);text:"网关模式";color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold}
  SwirlToggle{objectName:"gatewayToggle";x:Theme.dp(68);y:Theme.dp(15);enabled:!gatewayProvider.busy;checked:gatewayProvider.running;onToggled:{const wanted=checked;if(wanted){if(!gatewayProvider.configured)page.configureGateway();else if(!gatewayProvider.start())AppState.notice(gatewayProvider.error)}else gatewayProvider.stop();checked=Qt.binding(()=>gatewayProvider.running)}Accessible.name:"网关模式"}
  SwirlIconButton{id:gearButton;objectName:"gatewaySettings";quiet:true;anchors.right:parent.right;y:Theme.dp(10);width:Theme.dp(26);height:width;iconName:"settings";onClicked:page.openGatewayMenu()}
  Text{y:Theme.dp(41);width:parent.width;text:gatewayProvider.error||"使用自研 DHCP 和 Mihomo TUN 接管专用局域网设备。需要管理员权限和独立 LAN 接口。";color:Theme.muted;font.pixelSize:Theme.fontSize(10);lineHeightMode:Text.FixedHeight;lineHeight:Theme.dp(13);wrapMode:Text.WordWrap;maximumLineCount:2;elide:Text.ElideRight}
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
   Text{text:"选择已设置静态 IPv4 地址的专用 LAN 接口。网关通过 Mihomo TUN 转发；不能选择系统当前的默认上网接口。";Layout.fillWidth:true;color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   SwirlComboBox{id:lanInterface;objectName:"gatewayInterface";Layout.fillWidth:true;model:gatewayProvider.interfaces;textRole:"label";onActivated:{const entry=gatewayProvider.interfaces[currentIndex];gatewayIp.text=entry.ip;prefix.text=String(entry.prefix)}}
   Text{visible:gatewayProvider.interfaces.length===0;text:"当前没有可用的专用 LAN 接口。请接入网卡并设置静态 IPv4 地址。";Layout.fillWidth:true;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   RowLayout{Text{text:"网关 IP";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:gatewayIp;Layout.fillWidth:true;text:gatewayProvider.configuration.gateway||""}}
   RowLayout{Text{text:"子网前缀";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:prefix;Layout.fillWidth:true;text:String(gatewayProvider.configuration.prefix||24);validator:IntValidator{bottom:8;top:30}}}
   RowLayout{Text{text:"地址池开始";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:firstAddress;Layout.fillWidth:true;text:gatewayProvider.configuration.first||"";placeholderText:"例如 192.168.137.100"}}
   RowLayout{Text{text:"地址池结束";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:lastAddress;Layout.fillWidth:true;text:gatewayProvider.configuration.last||"";placeholderText:"例如 192.168.137.200"}}
   RowLayout{Text{text:"DNS";color:Theme.text;Layout.preferredWidth:Theme.dp(82)}SwirlTextField{id:gatewayDns;Layout.fillWidth:true;text:gatewayProvider.configuration.dns||"1.1.1.1"}}
   ReferenceCheckBox{id:dedicatedLan;text:"该接口用于专用 LAN，且已关闭该网络的其他 DHCP 服务"}
   Text{text:gatewayProvider.error;Layout.fillWidth:true;color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WordWrap}
   RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:gatewayDialog.close()}SwirlButton{text:"保存";primary:true;enabled:dedicatedLan.checked&&lanInterface.currentIndex>=0&&gatewayProvider.interfaces.length>0;onClicked:{if(gatewayProvider.configure({interfaceIndex:gatewayProvider.interfaces[lanInterface.currentIndex].index,gateway:gatewayIp.text,prefix:Number(prefix.text),first:firstAddress.text,last:lastAddress.text,dns:gatewayDns.text,leaseSeconds:3600,dedicatedLan:true}))gatewayDialog.close()}}}
  }
 }
 FileDialog{id:clientExport;title:"导出客户端配置";fileMode:FileDialog.SaveFile;nameFilters:["CSV 文件 (*.csv)"];defaultSuffix:"csv";onAccepted:if(!gatewayProvider.exportClients(selectedFile))AppState.notice(gatewayProvider.error)}
 FileDialog{id:clientImport;title:"导入客户端配置";nameFilters:["CSV 文件 (*.csv)"];onAccepted:if(!gatewayProvider.importClients(selectedFile))AppState.notice(gatewayProvider.error)}
}
