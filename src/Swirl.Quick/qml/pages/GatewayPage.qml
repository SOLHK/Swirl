pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
 component GatewayMenuItem:MenuItem{
  implicitHeight:visible?Theme.dp(26):0;height:implicitHeight;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12)
  background:Rectangle{radius:Theme.dp(6);color:parent.highlighted?Theme.accent:"transparent"}
  contentItem:SwirlText {text:parent.text;leftPadding:Theme.dp(8);rightPadding:Theme.dp(8);font.family:parent.font.family;font.pixelSize:parent.font.pixelSize;font.weight:parent.font.weight;color:parent.highlighted?Theme.primaryButtonText:parent.enabled?Theme.text:Theme.muted;verticalAlignment:Text.AlignVCenter;elide:Text.ElideRight}
 }
 id:page;readonly property Item motionTitle:heading.titleItem;readonly property bool compact:width<Theme.dp(620);property string selectedId:"";property int sortIndex:3
 readonly property var lanSnapshot:engineController.lanStatus
 function lanStateText(){if(engineController.lanBusy)return qsTr("正在启动、停止或恢复");if(lanSnapshot.error)return lanSnapshot.error;if(engineController.lanEnabled&&!lanSnapshot.status_confirmed)return qsTr("监听状态未确认，请重试停止并检查内核");if(engineController.lanEnabled)return qsTr("%1 · HTTP %2 / SOCKS5 %3 · %4 个连接").arg(lanSnapshot.listen_ip||"—").arg(lanSnapshot.http_port||0).arg(lanSnapshot.socks_port||0).arg(lanSnapshot.active_connections||0);if(!engineController.lanSupported)return qsTr("当前平台或内核未提供 LAN 安全集成");if(engineController.lanRecoveryNeeded)return qsTr("有待恢复的防火墙记录");return qsTr("已关闭")}
 readonly property var records:{if(!visible)return [];let rows=gatewayProvider.devices.map(r=>Object.assign({},r));for(const client of(lanSnapshot.clients||[])){let row=rows.find(r=>r.ip===client.ip);if(!row){row={id:"lan:"+client.ip,name:client.ip,ip:client.ip,mac:"",lastSeen:0,speed:0,speedText:"—"};rows.push(row)}row.upload=engineController.telemetry.formatBytes(client.uploaded||0);row.download=engineController.telemetry.formatBytes(client.downloaded||0);row.total=(client.uploaded||0)+(client.downloaded||0);row.status=qsTr("LAN · %1 个当前连接").arg(client.active_connections||0)}if(sortIndex===0)rows.sort((a,b)=>b.total-a.total);else if(sortIndex===1)rows.sort((a,b)=>b.speed-a.speed);else if(sortIndex===2)rows.sort((a,b)=>a.name.localeCompare(b.name));else if(sortIndex===3)rows.sort((a,b)=>ipNumber(a.ip)-ipNumber(b.ip));else if(sortIndex===4)rows.sort((a,b)=>b.lastSeen-a.lastSeen);return rows}
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
 ColumnLayout {
  anchors.fill:parent;anchors.margins:Theme.pagePadding;spacing:Theme.sectionGap
  SwirlPageHeader {id:heading;Layout.fillWidth:true;title:qsTr("设备");description:qsTr("原生局域网代理、设备记录与客户端配置。透明网关仍待验收。");metadata:qsTr("%1 台设备").arg(page.records.length)
   SwirlComboBox {id:deviceSort;objectName:"deviceSortPicker";Layout.preferredWidth:Theme.dp(208);model:["按流量排序","按速度排序","按名称排序","按 IP 排序","按 DHCP 最后出现时间排序"];currentIndex:page.sortIndex;onActivated:page.sortIndex=currentIndex;Accessible.name:qsTr("设备排序")}
   SwirlIconButton {id:gearButton;objectName:"gatewaySettings";quiet:true;iconName:"settings";tooltip:qsTr("网关与客户端配置");onClicked:page.openGatewayMenu()}
  }
  GridLayout {
   Layout.fillWidth:true;columns:page.compact?1:2;columnSpacing:Theme.sectionGap;rowSpacing:Theme.dp(8)
   ColumnLayout {Layout.fillWidth:true;spacing:Theme.dp(5)
    SwirlText {text:qsTr("原生局域网代理");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}
    SwirlText {objectName:"lanProxyState";text:page.lanStateText();textFormat:Text.PlainText;color:page.lanSnapshot.error?Theme.orange:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
    SwirlText {visible:engineController.lanEnabled;text:qsTr("上传 %1 · 下载 %2").arg(engineController.telemetry.formatBytes(page.lanSnapshot.uploaded||0)).arg(engineController.telemetry.formatBytes(page.lanSnapshot.downloaded||0));color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
   }
   RowLayout {Layout.alignment:Qt.AlignRight;spacing:Theme.dp(12)
    SwirlButton {objectName:"lanProxyConfigure";quiet:true;text:qsTr("配置 LAN");onClicked:lanDialog.open()}
    SwirlToggle {objectName:"lanProxyToggle";checked:engineController.lanEnabled;enabled:!engineController.lanBusy&&(engineController.lanEnabled||(engineController.lanSupported&&!engineController.busy&&!engineController.policyBusy));onToggled:{const wanted=checked;if(wanted&&!engineController.lanConfigured)lanDialog.open();else if(!engineController.setLanEnabled(wanted))AppState.notice(engineController.networkConfigurationError);checked=Qt.binding(()=>engineController.lanEnabled)}Accessible.name:qsTr("原生局域网代理")}
   }
  }
  SwirlText {text:qsTr("HTTP Basic 与 SOCKS5 认证不加密传输，请仅在可信局域网使用。");Layout.fillWidth:true;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
  Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
  GridLayout {Layout.fillWidth:true;Layout.fillHeight:true;columns:page.compact?1:2;columnSpacing:Theme.sectionGap;rowSpacing:Theme.sectionGap
   Item {Layout.fillWidth:true;Layout.preferredWidth:3;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(100)
    SwirlDataTable {id:deviceTable;objectName:"deviceTable";visible:page.records.length>0;anchors.fill:parent;incrementalRows:true;animateRowChanges:false;rows:page.records;selectedId:page.selectedId;minimal:true;itemHeight:Theme.dp(42);columns:[{key:"name",label:qsTr("设备"),w:210},{key:"ip",label:qsTr("IP 地址"),w:165}];onRowSelected:r=>{page.selectedId=r.id;deviceDetailSurface.present(deviceTable.selectedItem)}}
    SwirlEmptyState {visible:page.records.length===0;anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(24));headline:qsTr("尚无设备记录");detail:qsTr("已采集或已导入的客户端会显示在这里。可通过右上角菜单管理配置与 CSV。")}
   }
   SwirlLinkedDetail {id:deviceDetailSurface;animationLayer:page;sourceViewport:deviceTable;detailOpen:page.selected!==null;visible:!page.compact||page.selected!==null||moving;Layout.fillWidth:true;Layout.preferredWidth:2;Layout.fillHeight:!page.compact;Layout.preferredHeight:page.compact?Theme.dp(180):-1;Layout.minimumHeight:Theme.dp(120)
    ScrollView {id:deviceDetailScroll;visible:page.selected!==null;anchors.fill:parent;anchors.margins:Theme.cardPadding;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
     ColumnLayout {width:deviceDetailScroll.availableWidth;spacing:Theme.dp(14)
      SwirlText {text:qsTr("设备详情");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
      SwirlText {id:deviceDetailName;text:page.selected?page.selected.name:"";textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(20);font.weight:Font.DemiBold;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
      Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
      Repeater {model:page.selected?[
       {label:qsTr("IP 地址"),value:page.selected.ip||page.selected.name},{label:qsTr("上传"),value:page.selected.upload},{label:qsTr("下载"),value:page.selected.download},
       {label:qsTr("速度"),value:page.selected.speedText},{label:"MAC",value:page.selected.mac},{label:qsTr("状态"),value:page.selected.status||qsTr("已采集流量")},
       {label:qsTr("租约到期"),value:page.selected.expires?new Date(page.selected.expires*1000).toLocaleString():"—"}]:[]
       ColumnLayout {required property var modelData;Layout.fillWidth:true;spacing:Theme.dp(4);SwirlText {text:modelData.label;color:Theme.muted;font.pixelSize:Theme.fontSize(11)}SwirlText {text:modelData.value===undefined||modelData.value===null||modelData.value===""?"—":String(modelData.value);textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}}
      }
     }
    }
    SwirlEmptyState {visible:page.selected===null;anchors.centerIn:parent;width:Math.max(0,parent.width-2*Theme.cardPadding);headline:qsTr("选择一个设备");detail:qsTr("查看设备地址、已采集流量与客户端信息。")}
   }
  }
  Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.borderWidth;color:Theme.separator}
  RowLayout {Layout.fillWidth:true;spacing:Theme.dp(16)
   ColumnLayout {Layout.fillWidth:true;spacing:Theme.dp(5);SwirlText {text:qsTr("网关模式");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}SwirlText {text:gatewayProvider.error||qsTr("当前不支持 TUN 网关转发；配置与恢复记录保持保留。");color:gatewayProvider.error.length?Theme.red:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}}
   SwirlToggle {objectName:"gatewayToggle";enabled:!gatewayProvider.busy&&gatewayProvider.running;checked:gatewayProvider.running;onToggled:{const wanted=checked;if(wanted)AppState.notice("Rust Core 暂不支持 TUN 网关转发");else gatewayProvider.stop();checked=Qt.binding(()=>gatewayProvider.running)}Accessible.name:qsTr("网关模式")}
  }
 }
 SwirlContextMenu{id:gatewayMenu;objectName:"gatewayMenu";items:[];popupType:Popup.Item;padding:Theme.dp(5);implicitWidth:Theme.dp(215)
   GatewayMenuItem{text:"配置原生 LAN 代理…";onTriggered:lanDialog.open()}
   GatewayMenuItem{text:"恢复 LAN 防火墙规则";visible:engineController.lanRecoveryNeeded&&!engineController.lanEnabled;enabled:!engineController.lanBusy;onTriggered:engineController.recoverLan()}
   GatewayMenuItem{text:"DHCP 服务器："+(gatewayProvider.running?"已启用":"未启用");enabled:false}
   GatewayMenuItem{text:"Swirl 网关："+(gatewayProvider.running?"已启用":"未启用");enabled:false}
   MenuSeparator{implicitHeight:Theme.dp(10);contentItem:Rectangle{implicitWidth:Theme.dp(165);implicitHeight:Theme.dp(1);color:Theme.border}}
   GatewayMenuItem{text:"配置网关…";onTriggered:page.configureGateway()}
   GatewayMenuItem{text:"恢复上次的接口转发状态";visible:gatewayProvider.recoveryNeeded&&!gatewayProvider.running;enabled:!gatewayProvider.busy;onTriggered:gatewayProvider.recover()}
   GatewayMenuItem{text:"导出客户端配置到 CSV…";onTriggered:clientExport.open()}
   GatewayMenuItem{text:"从 CSV 导入客户端配置";onTriggered:clientImport.open()}
  }
 SwirlDialog{id:gatewayDialog;ownerItem:page;title:"网关模式";width:Theme.dp(560);height:Math.min(Theme.dp(600),parent?parent.height-Theme.dp(32):Theme.dp(600))
  contentItem:ScrollView {id:gatewayConfigScroll;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout{width:gatewayConfigScroll.availableWidth;spacing:Theme.dp(12)
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
 }
 SwirlDialog {
  id:lanDialog;objectName:"lanProxyDialog";dismissBlocked:awaitingSave;ownerItem:page;title:qsTr("局域网代理 · IPv4");width:Math.floor(Math.min(Theme.dp(560),parent?parent.width-Theme.dp(40):Theme.dp(560)))
  property bool awaitingSave:false
  function completeSave(){
   if(!awaitingSave||engineController.policyBusy)return
   awaitingSave=false
   if(engineController.policyError){AppState.notice(engineController.policyError);return}
   lanPassword.clear();markSaved();close()
  }
  Connections {target:engineController;function onPolicyChanged(){lanDialog.completeSave()}}
  height:Math.min(Theme.dp(690),parent?parent.height-Theme.dp(32):Theme.dp(690))
  onOpened:{
   const config=engineController.lanConfiguration
   const choices=engineController.lanInterfaces
   lanProxyInterface.currentIndex=choices.findIndex(r=>r.ip===config.listen_ip)
   lanHttp.text=String(config.http_port||7899);lanSocks.text=String(config.socks_port||7899)
   lanUdpFirst.text=String(config.udp_port_start||7900);lanUdpLast.text=String(config.udp_port_end||7915)
   lanAllowed.text=(config.allowed_cidrs||[]).join("\n")
   lanUsername.text=engineController.lanUsername||"swirl";lanPassword.clear();lanDialog.markSaved()
  }
  onClosed:lanPassword.clear()
  contentItem:ScrollView {
   id:lanScroll;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
   ColumnLayout {
    width:lanScroll.availableWidth;spacing:Theme.dp(12)
    SwirlText {text:qsTr("启用后，其他设备使用所选地址和端口连接。认证与客户端 CIDR 同时生效；IPv6 监听尚未开放。代理域名访问需要已配置 DoH/DoT，否则连接会被拒绝以保护本机服务。HTTP/SOCKS5 用户名密码不提供链路加密，请只在可信局域网使用。");Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
    SwirlText {visible:!engineController.elevated;text:qsTr("启用与恢复需要以管理员身份运行 Swirl，以管理精确的防火墙规则。");Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.orange;font.pixelSize:Theme.fontSize(12)}
    SwirlComboBox {id:lanProxyInterface;objectName:"lanProxyInterface";Layout.fillWidth:true;model:engineController.lanInterfaces;textRole:"label";enabled:!engineController.lanEnabled&&!engineController.lanBusy;onActivated:{const entry=engineController.lanInterfaces[currentIndex];if(entry)lanAllowed.text=entry.cidr}}
    SwirlText {visible:engineController.lanInterfaces.length===0;text:qsTr("没有可用的局域网 IPv4 地址。启用时还会核验 Windows 网络类别，公共网络将被拒绝。");Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.orange;font.pixelSize:Theme.fontSize(12)}
    GridLayout {columns:2;Layout.fillWidth:true;columnSpacing:Theme.dp(12);rowSpacing:Theme.dp(8);enabled:!engineController.lanEnabled&&!engineController.lanBusy
     SwirlText {text:qsTr("HTTP 端口");color:Theme.text}SwirlTextField{id:lanHttp;objectName:"lanProxyHttpPort";Layout.fillWidth:true;validator:IntValidator{bottom:1;top:65535}}
     SwirlText {text:qsTr("SOCKS5 端口");color:Theme.text}SwirlTextField{id:lanSocks;objectName:"lanProxySocksPort";Layout.fillWidth:true;validator:IntValidator{bottom:1;top:65535}}
     SwirlText {text:qsTr("UDP 端口范围");color:Theme.text}RowLayout{Layout.fillWidth:true;SwirlTextField{id:lanUdpFirst;Layout.fillWidth:true;validator:IntValidator{bottom:1;top:65535}}SwirlText{text:"—";color:Theme.muted}SwirlTextField{id:lanUdpLast;Layout.fillWidth:true;validator:IntValidator{bottom:1;top:65535}}}
    }
    SwirlText {text:qsTr("允许的客户端 CIDR（每行一项，必须位于所选接口子网）");Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
    SwirlTextArea{id:lanAllowed;objectName:"lanProxyAllowedCidrs";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(80);placeholderText:"192.168.1.0/24";enabled:!engineController.lanEnabled&&!engineController.lanBusy}
    SwirlTextField{id:lanUsername;objectName:"lanProxyUsername";Layout.fillWidth:true;placeholderText:qsTr("用户名");enabled:!engineController.lanEnabled&&!engineController.lanBusy}
    SwirlTextField{id:lanPassword;objectName:"lanProxyPassword";Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:engineController.lanConfigured?qsTr("留空保留已有密码"):qsTr("密码（至少 12 UTF-8 字节）");enabled:!engineController.lanEnabled&&!engineController.lanBusy}
    SwirlText {visible:engineController.lanEnabled;text:qsTr("活跃连接 %1 · 上传 %2 · 下载 %3").arg(engineController.lanStatus.active_connections||0).arg(engineController.telemetry.formatBytes(engineController.lanStatus.uploaded||0)).arg(engineController.telemetry.formatBytes(engineController.lanStatus.downloaded||0));Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.text;font.pixelSize:Theme.fontSize(12)}
    SwirlText {text:engineController.networkConfigurationError||engineController.lanStatus.error||engineController.policyError||"";color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
    RowLayout {Layout.fillWidth:true
     SwirlButton {text:qsTr("恢复防火墙");visible:engineController.lanRecoveryNeeded&&!engineController.lanEnabled;enabled:!engineController.lanBusy;onClicked:engineController.recoverLan()}
     Item {Layout.fillWidth:true}
     SwirlButton {text:qsTr("关闭");enabled:!lanDialog.awaitingSave;onClicked:lanDialog.requestDismiss()}
     SwirlButton {text:lanDialog.awaitingSave?qsTr("正在保存"):qsTr("保存");primary:true;enabled:!lanDialog.awaitingSave&&!engineController.lanEnabled&&!engineController.lanBusy&&!engineController.policyBusy&&lanProxyInterface.currentIndex>=0;onClicked:{
      const entry=engineController.lanInterfaces[lanProxyInterface.currentIndex];if(!entry)return
      const config=Object.assign({},engineController.lanConfiguration,{listen_ip:entry.ip,http_port:Number(lanHttp.text),socks_port:Number(lanSocks.text),udp_port_start:Number(lanUdpFirst.text),udp_port_end:Number(lanUdpLast.text),allowed_cidrs:lanAllowed.text.split(/[\n,]+/).map(v=>v.trim()).filter(v=>v.length>0),username:lanUsername.text,password:lanPassword.text})
      lanDialog.awaitingSave=true
      if(engineController.configureLanAccess(config))lanDialog.completeSave();else lanDialog.awaitingSave=false
     }}
    }
   }
  }
 }
 FileDialog{id:clientExport;parentWindow:page.Window.window;title:"导出客户端配置";fileMode:FileDialog.SaveFile;nameFilters:["CSV 文件 (*.csv)"];defaultSuffix:"csv";onAccepted:if(!gatewayProvider.exportClients(selectedFile))AppState.notice(gatewayProvider.error)}
 FileDialog{id:clientImport;parentWindow:page.Window.window;title:"导入客户端配置";nameFilters:["CSV 文件 (*.csv)"];onAccepted:if(!gatewayProvider.importClients(selectedFile))AppState.notice(gatewayProvider.error)}
}
