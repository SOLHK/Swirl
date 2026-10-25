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
  id:card;property string title;property string description;property string status;property bool active:false;property bool available:false;property bool configurable:false;property bool toggleVisible:true;property string configureLabel:"配置";signal toggled(bool on);signal configure()
  Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredHeight:Math.max(Theme.dp(160),body.implicitHeight+2*Theme.cardPadding)
  ColumnLayout {id:body;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
   RowLayout {Layout.fillWidth:true;SwirlText{text:card.title;color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold;Layout.fillWidth:true}SwirlToggle{visible:card.toggleVisible;checked:card.active;enabled:card.available;onToggled:{card.toggled(checked);checked=Qt.binding(()=>card.active)}Accessible.name:card.title}}
   SwirlText {text:card.description;color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;Layout.fillWidth:true}
   RowLayout {Layout.fillWidth:true;SwirlText {text:card.status;color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;Layout.fillWidth:true}SwirlButton {visible:card.configurable;quiet:true;text:card.configureLabel;onClicked:card.configure()}}
  }
 }
 Flickable {id:scroll;anchors.fill:parent;contentWidth:width;contentHeight:body.implicitHeight+2*Theme.pagePadding;clip:true;boundsBehavior:Flickable.StopAtBounds;flickableDirection:Flickable.VerticalFlick;ScrollBar.vertical:SwirlScrollBar{}
  ColumnLayout {id:body;x:Theme.pagePadding;width:scroll.width-2*Theme.pagePadding;spacing:Theme.sectionGap
   SwirlText {textRole:"pageTitle";text:"概览";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold}
   SwirlText {text:"配置与服务状态";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}
   SwirlText {text:"网络接管";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
   GridLayout {Layout.fillWidth:true;columns:width>=Theme.dp(650)?2:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
    AccessCard{title:"系统代理";description:"在活动页统一开启或关闭 Swirl 代理，使用已保存的策略分配流量。";status:page.engineController.systemProxy.error||page.engineController.routingError||(page.engineController.busy?"正在切换":active?"由 Swirl 接管":page.engineController.systemProxy.systemEnabled?"由其他应用启用":"未启用");active:page.engineController.systemProxy.enabled;toggleVisible:false;configurable:true;configureLabel:"前往活动";onConfigure:AppState.navigate("activity")}
    AccessCard{title:"增强模式";description:"部分应用可能不遵循系统代理设置。使用增强模式可以让所有应用由 Swirl 处理。";status:active?"启用":page.engineController.elevated?"禁用":"需要管理员权限";active:page.engineController.tunEnabled;available:!page.engineController.busy;onToggled:on=>{if(!page.engineController.setTunEnabled(!page.engineController.tunRequested))AppState.notice(page.engineController.routingError||page.engineController.networkConfigurationError)}}
   }
   SwirlText {text:"局域网设备接管";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
   GridLayout {Layout.fillWidth:true;columns:width>=Theme.dp(650)?2:1;columnSpacing:Theme.gap;rowSpacing:Theme.gap
    AccessCard{title:"HTTP & SOCKS5 代理";description:"Swirl 可以被其他设备用作标准的 HTTP 和 SOCKS5 代理服务器。";status:active?"启用 · "+page.engineController.activeProxyPort:"禁用";active:page.engineController.lanEnabled;available:!page.engineController.busy;configurable:true;onConfigure:lanDialog.open();onToggled:on=>{if(on&&!page.engineController.lanConfigured)lanDialog.open();else if(!page.engineController.setLanEnabled(on))AppState.notice(page.engineController.networkConfigurationError)}}
    AccessCard{title:"网关模式";description:"将 Swirl 用作局域网的 DHCP 服务器，并使用 Swirl 网关模式接管其他设备的网络。";status:gatewayProvider.busy?"正在配置":gatewayProvider.running?"启用":gatewayProvider.configured?"禁用":"未配置";active:gatewayProvider.running;available:!gatewayProvider.busy;configurable:true;onConfigure:AppState.navigate("gateway");onToggled:on=>{if(on&&!gatewayProvider.start())AppState.notice(gatewayProvider.error);else if(!on)gatewayProvider.stop()}}
   }
   SwirlText {text:"远程连接";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
   AccessCard{title:"Swirl 远程连接";description:"通过 WireGuard、EasyTier 等协议连接设备之间的私有网络。";status:"WireGuard / EasyTier";configurable:true;onConfigure:AppState.navigate("proxies")}
  }
 }
 SwirlDialog{id:lanDialog;title:"HTTP & SOCKS5 局域网代理";ColumnLayout{width:parent.width;spacing:Theme.dp(12)
  SwirlText {text:"其他设备使用本机 IP 和代理端口连接，并使用下面的账户认证。";Layout.fillWidth:true;wrapMode:Text.WordWrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  SwirlText {text:page.engineController.lanAddresses.join(" · ")+":"+page.engineController.proxyPort;color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  SwirlTextField{id:lanUsername;Layout.fillWidth:true;text:page.engineController.lanUsername||"swirl";placeholderText:"用户名"}
  SwirlTextField{id:lanPassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"密码（至少 8 字符）"}
  SwirlText {text:page.engineController.networkConfigurationError;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WordWrap;font.pixelSize:Theme.fontSize(12)}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:{lanPassword.clear();lanDialog.close()}}SwirlButton{text:"保存";primary:true;enabled:page.engineController.canStart;onClicked:{if(page.engineController.configureLan(lanUsername.text,lanPassword.text)){lanPassword.clear();lanDialog.close()}}}}
 }}
}
