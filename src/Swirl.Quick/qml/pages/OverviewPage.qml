pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var engineController;required property var systemProvider
 component AccessCard:SwirlGlassPanel {
  id:card;property string title;property string description;property string status;property bool active:false;property bool available:false;property bool configurable:false;signal toggled(bool on);signal configure()
  cornerRadius:Theme.independentCardRadius;width:Theme.dp(336);height:Theme.dp(120)
  Text{x:Theme.dp(16);y:Theme.dp(16);text:card.title;color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold}
  SwirlToggle{x:Theme.dp(284);y:Theme.dp(16);checked:card.active;enabled:card.available;onToggled:{card.toggled(checked);checked=Qt.binding(()=>card.active)}
Accessible.name:card.title}
  Text{x:Theme.dp(16);y:Theme.dp(42);width:Theme.dp(304);text:card.description;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WordWrap}
  SwirlButton{visible:card.configurable;anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(88);quiet:true;implicitWidth:Theme.dp(24);text:"⋯";onClicked:card.configure()}
  Row{x:Theme.dp(16);y:Theme.dp(94);spacing:Theme.dp(6);Rectangle{width:Theme.dp(8);height:width;radius:width/2;color:card.active?Theme.green:Theme.orange;anchors.verticalCenter:parent.verticalCenter}Text{text:card.status;color:Theme.text;font.pixelSize:Theme.fontSize(11)}}
 }
 Flickable{anchors.fill:parent;contentWidth:Theme.dp(698);contentHeight:Theme.dp(618);clip:true;boundsBehavior:Flickable.StopAtBounds
  Text{x:Theme.dp(4);y:Theme.dp(6);text:"概览";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
  Text{x:Theme.dp(4);y:Theme.dp(60);text:"网络接管";color:Theme.magenta;font.pixelSize:Theme.fontSize(13)}
  AccessCard{x:Theme.dp(4);y:Theme.dp(94);title:"系统代理";description:"大多数应用的流量可以通过将 Swirl 设置为系统代理接管，具有最佳的兼容性和性能。";status:page.engineController.systemProxy.error||page.engineController.routingError||(active?"已接管":"未设置");active:page.engineController.systemProxy.enabled;available:!page.engineController.busy;onToggled:on=>page.engineController.setSystemProxy(on)}
  AccessCard{x:Theme.dp(356);y:Theme.dp(94);title:"增强模式";description:"部分应用可能不遵循系统代理设置。使用增强模式可以让所有应用由 Swirl 处理。";status:active?"启用":page.engineController.elevated?"禁用":"需要管理员权限";active:page.engineController.tunEnabled;available:!page.engineController.busy;onToggled:on=>{if(!page.engineController.setTunEnabled(!page.engineController.tunRequested))AppState.notice(page.engineController.routingError||page.engineController.networkConfigurationError)}}
  Text{x:Theme.dp(4);y:Theme.dp(246);text:"局域网设备接管";color:"#8764FF";font.pixelSize:Theme.fontSize(13)}
  AccessCard{x:Theme.dp(4);y:Theme.dp(280);title:"HTTP & SOCKS5 代理";description:"Swirl 可以被其他设备用作标准的 HTTP 和 SOCKS5 代理服务器。";status:active?"启用 · "+page.engineController.activeProxyPort:"禁用";active:page.engineController.lanEnabled;available:!page.engineController.busy;configurable:true;onConfigure:lanDialog.open();onToggled:on=>{if(on&&!page.engineController.lanConfigured)lanDialog.open();else if(!page.engineController.setLanEnabled(on))AppState.notice(page.engineController.networkConfigurationError)}}
  AccessCard{x:Theme.dp(356);y:Theme.dp(280);title:"网关模式";description:"将 Swirl 用作局域网的 DHCP 服务器，并使用 Swirl 网关模式接管其他设备的网络。";status:gatewayProvider.busy?"正在配置":gatewayProvider.running?"启用":gatewayProvider.configured?"禁用":"未配置";active:gatewayProvider.running;available:!gatewayProvider.busy;configurable:true;onConfigure:AppState.navigate("gateway");onToggled:on=>{if(on&&!gatewayProvider.start())AppState.notice(gatewayProvider.error);else if(!on)gatewayProvider.stop()}}
  Text{x:Theme.dp(4);y:Theme.dp(432);text:"远程连接";color:Theme.accent;font.pixelSize:Theme.fontSize(13)}
  AccessCard{x:Theme.dp(4);y:Theme.dp(466);title:"Swirl 远程连接";description:"通过 WireGuard、EasyTier 等协议连接设备之间的私有网络。";status:"WireGuard / EasyTier";configurable:true;onConfigure:AppState.navigate("proxies")}
 }
 SwirlDialog{id:lanDialog;title:"HTTP & SOCKS5 局域网代理";ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  Text{text:"其他设备使用本机 IP 和代理端口连接，并使用下面的账户认证。";Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  Text{text:page.engineController.lanAddresses.join(" · ")+":"+page.engineController.proxyPort;color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  SwirlTextField{id:lanUsername;Layout.fillWidth:true;text:page.engineController.lanUsername||"swirl";placeholderText:"用户名"}
  SwirlTextField{id:lanPassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"密码（至少 8 字符）"}
  Text{text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:{lanPassword.clear();lanDialog.close()}}SwirlButton{text:"保存";primary:true;enabled:page.engineController.canStart;onClicked:{if(page.engineController.configureLan(lanUsername.text,lanPassword.text)){lanPassword.clear();lanDialog.close()}}}}
 }}
}
