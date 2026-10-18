pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 function preparePreviewState(state){if(state==="dns-focus")serverAddress.forceActiveFocus()}
 id:page;
    readonly property Item motionTitle:routeTitle

 function persistExitDraft(){moduleDrafts.save("feature-dns-exit",{pending:true,mode:serverMode,servers:serverAddress.text,encrypted:encryptedUrl.text,hosts:hostRows,useHosts:readHosts.checked,respectRules:respectRules.checked})}
 function finishSettings(){moduleDrafts.save("feature-dns-exit",{});page.Window.window.closeSettings()}
 property int serverMode:0;property var hostRows:[];property string selectedId:""
 Component.onCompleted:{const saved=moduleDrafts.load("feature-dns-exit");const config=saved.pending?saved:engineController.dnsConfiguration;serverMode=config.mode||0;serverAddress.text=config.servers||"";encryptedUrl.text=config.encrypted||"";hostRows=config.hosts||[];readHosts.checked=config.useHosts!==false;respectRules.checked=config.respectRules===true}
 component Label:SwirlText {color:Theme.text;font.pixelSize:Theme.fontSize(13)}
 component Note:SwirlText {textRole:"auxiliary";color:Theme.muted;font.pixelSize:Theme.fontSize(11);lineHeightMode:Text.FixedHeight;lineHeight:Theme.dp(14);wrapMode:Text.WordWrap;width:parent.width}
 component Group:SwirlGlassPanel {}
 SwirlText {textRole:"pageTitle";id:routeTitle;x:Theme.pagePadding;y:Theme.pagePadding;text:"DNS";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold}
 Note{x:Theme.pagePadding;y:routeTitle.y+routeTitle.height+Theme.dp(8);text:"本地 DNS 映射和 DNS 相关设置。"}
 readonly property bool narrow:width<Theme.dp(600)
 readonly property real optionsHeight:Math.max(Theme.dp(305),dnsServerColumn.implicitHeight+Theme.dp(40))
 readonly property real mappingY:Theme.dp(14)+optionsHeight+(narrow?Theme.dp(330):Theme.dp(24))
 Flickable{id:dnsBody;objectName:"motion-dns-scroll";y:Theme.dp(88);width:parent.width;height:parent.height-y-Theme.dp(48);clip:true;contentWidth:width;contentHeight:Math.max(height,page.mappingY+Theme.dp(300));boundsBehavior:Flickable.StopAtBounds
 ScrollBar.vertical:ScrollBar{policy:dnsBody.contentHeight>dnsBody.height?ScrollBar.AsNeeded:ScrollBar.AlwaysOff}
 Item{width:dnsBody.width;height:dnsBody.contentHeight
 Item{x:Theme.pagePadding;y:Theme.dp(14);width:page.narrow?parent.width-2*Theme.pagePadding:Math.floor((parent.width-2*Theme.pagePadding-Theme.gap)/2);height:page.optionsHeight
  Label{x:Theme.dp(8);text:"DNS 服务器";font.weight:Font.DemiBold}
  Group{y:Theme.dp(24);width:parent.width;height:Theme.dp(118)
   Column{id:dnsServerColumn;x:Theme.dp(16);y:Theme.dp(8);spacing:0;width:parent.width-Theme.dp(32)
    Repeater{model:["使用系统 DNS 服务器","使用系统 DNS 服务器和额外的服务器","使用自定义的服务器"]
     RadioButton{objectName:"dnsMode-"+index;required property string modelData;required property int index;text:modelData;checked:page.serverMode===index;onClicked:page.serverMode=index;implicitHeight:Theme.dp(24);font.pixelSize:Theme.fontSize(13);padding:0;spacing:Theme.dp(6)
      indicator:Rectangle{Behavior on color{ColorAnimation{duration:SwirlMotion.switchDuration}}width:Theme.dp(16);height:width;radius:width/2;color:parent.checked?Theme.accent:"#DEDEDF";anchors.verticalCenter:parent.verticalCenter;Rectangle{opacity:parent.parent.checked?1:0;Behavior on opacity{NumberAnimation{duration:SwirlMotion.switchDuration}}anchors.centerIn:parent;width:Theme.dp(5);height:width;radius:width/2;color:"white"}}
      contentItem:SwirlText {text:parent.text;leftPadding:Theme.dp(22);color:Theme.text;font.pixelSize:Theme.fontSize(13);verticalAlignment:Text.AlignVCenter}}
    }
    SwirlTextField{id:serverAddress;objectName:"dnsServerAddress";width:parent.width;height:Theme.dp(26);placeholderText:"服务器地址 (逗号分隔)";font.pixelSize:Theme.fontSize(12)}
   }
  }
  Label{x:Theme.dp(8);y:Theme.dp(160);text:"加密 DNS";font.weight:Font.DemiBold}
  Group{y:Theme.dp(184);width:parent.width;height:Theme.dp(123)
   SwirlTextField{id:encryptedUrl;x:Theme.dp(16);y:Theme.dp(12);width:parent.width-Theme.dp(32);height:Theme.dp(26);placeholderText:"加密 DNS URL";font.pixelSize:Theme.fontSize(12)}
   Note{x:Theme.dp(16);y:Theme.dp(48);width:parent.width-Theme.dp(32);text:"如果在此配置了 DNS 服务器，传统 DNS 将仅用于连通性测试和解析服务器域名。\n支持：https://、tls:// 和 tcp://。"}
  }
 }
 Item{anchors.right:parent.right;anchors.rightMargin:Theme.pagePadding;y:page.narrow?Theme.dp(14)+page.optionsHeight+Theme.gap:Theme.dp(14);width:page.narrow?parent.width-2*Theme.pagePadding:Math.floor((parent.width-2*Theme.pagePadding-Theme.gap)/2);height:Theme.dp(305)
  Label{x:Theme.dp(8);text:"DNS 选项";font.weight:Font.DemiBold}
  Group{y:Theme.dp(24);width:parent.width;height:Theme.dp(150)
   Label{x:Theme.dp(16);y:Theme.dp(12);text:"从 hosts 中读取 DNS 记录"}
   SwirlToggle{id:readHosts;anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(10);checked:true}
   Rectangle{x:Theme.dp(16);y:Theme.dp(40);width:parent.width-Theme.dp(32);height:Theme.dp(1);color:Theme.border}
   Label{x:Theme.dp(16);y:Theme.dp(53);text:"对使用代理的请求强制使用本地 DNS 映射结果";font.pixelSize:Theme.fontSize(12)}
   SwirlToggle{id:respectRules;anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(49)}
   Note{x:Theme.dp(16);y:Theme.dp(78);width:parent.width-Theme.dp(32);text:"默认情况下，当使用代理策略时，DNS 解析永远在代理服务器进行。开启该选项后，匹配本地 DNS 映射的域名将使用本地映射结果的 IP 地址发起代理请求。"}
  }
  Label{x:Theme.dp(8);y:Theme.dp(189);text:"DDNS";font.weight:Font.DemiBold}
  Group{y:Theme.dp(212);width:parent.width;height:Theme.dp(38);Label{x:Theme.dp(16);anchors.verticalCenter:parent.verticalCenter;text:"Swirl 私有 DDNS"}SwirlButton{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);anchors.verticalCenter:parent.verticalCenter;text:"配置…";enabled:false}}
 }
 Label{x:Theme.pagePadding;y:page.mappingY;text:"本地 DNS 映射";font.weight:Font.DemiBold}
 SwirlGlassPanel{x:Theme.pagePadding;y:page.mappingY+Theme.dp(28);width:parent.width-2*Theme.pagePadding;height:parent.height-y-Theme.dp(18);clip:true
  SwirlDataTable{gridLines:true;cellPadding:Theme.dp(10);anchors.fill:parent;anchors.bottomMargin:Theme.dp(30);fillEmptyRows:true;itemHeight:Theme.dp(26);rows:page.hostRows;columns:[{key:"selector",label:"",w:52},{key:"name",label:"域名",w:236},{key:"value",label:"值",w:236},{key:"server",label:"DNS 服务器",w:160},{key:"comment",label:"注释",w:170}];onRowSelected:r=>page.selectedId=r.id}
  Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:Theme.dp(30);color:Theme.tableToolbar;Row{x:Theme.dp(12);anchors.verticalCenter:parent.verticalCenter;spacing:Theme.dp(6);SwirlButton{text:"+";implicitWidth:Theme.dp(40);implicitHeight:Theme.dp(22);onClicked:mappingDialog.open()}SwirlButton{text:"−";implicitWidth:Theme.dp(40);implicitHeight:Theme.dp(22);enabled:page.selectedId.length>0;onClicked:page.hostRows=page.hostRows.filter(r=>r.id!==page.selectedId)}}}
 }
 }}
 Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:Theme.dp(40);color:"transparent";Row{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);anchors.verticalCenter:parent.verticalCenter;spacing:Theme.dp(14);SwirlButton{objectName:"cancelDns";text:"取消";onClicked:{page.finishSettings()}}SwirlButton{objectName:"applyDns";text:"应用";primary:true;onClicked:{if(engineController.configureDns({mode:page.serverMode,servers:serverAddress.text,encrypted:encryptedUrl.text,hosts:page.hostRows,useHosts:readHosts.checked,respectRules:respectRules.checked})){AppState.notice("DNS 配置已保存，连接时应用到 Mihomo");page.finishSettings()}else AppState.notice(engineController.networkConfigurationError)}}}}
 SwirlDialog{ownerItem:page;id:mappingDialog;title:"新增本地 DNS 映射";ColumnLayout{width:parent.width;SwirlTextField{id:host;Layout.fillWidth:true;placeholderText:"域名"}SwirlTextField{id:address;Layout.fillWidth:true;placeholderText:"IP 地址"}RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:mappingDialog.close()}SwirlButton{text:"添加";primary:true;enabled:host.text.trim().length>0&&address.text.trim().length>0;onClicked:{page.hostRows=page.hostRows.concat([{id:String(Date.now()),name:host.text.trim(),value:address.text.trim(),server:"",comment:""}]);mappingDialog.close()}}}}}
}
