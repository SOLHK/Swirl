pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 function preparePreviewState(state){if(state==="rewrite-on")captureProvider.rewriteEnabled=true}
 component RewriteCard:SwirlGlassPanel {
  id:card;property string title;property string description;property string moduleId;property string buttonText
  width:Theme.dp(336);height:Theme.dp(134);cornerRadius:Theme.independentCardRadius
  Text{x:Theme.dp(16);y:Theme.dp(16);text:card.title;color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.DemiBold}
  Text{x:Theme.dp(16);y:Theme.dp(42);width:Theme.dp(304);text:card.description;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WordWrap}
  Text{x:Theme.dp(16);y:Theme.dp(101);text:captureProvider.rewriteRules.filter(r=>r.kind===card.moduleId).length+" 条规则"+(captureProvider.rewriteEnabled?"生效中":"已停用");color:Theme.text;font.pixelSize:Theme.fontSize(11)}
  SwirlButton{anchors.right:parent.right;anchors.rightMargin:Theme.dp(16);y:Theme.dp(96);implicitHeight:Theme.dp(24);text:card.buttonText;onClicked:page.Window.window.openRewriteEditor(card.moduleId,card.title)}
 }
 Flickable{anchors.fill:parent;contentWidth:Theme.dp(698);contentHeight:Theme.dp(574);clip:true
  Text{x:Theme.dp(4);y:Theme.dp(6);text:"重写 & 映射";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
  SwirlToggle{x:Theme.dp(156);y:Theme.dp(10);large:true;checked:captureProvider.rewriteEnabled;onToggled:captureProvider.rewriteEnabled=checked;Accessible.name:"重写与映射"}
  RewriteCard{x:Theme.dp(4);y:Theme.dp(80);title:"URL 重定向";description:"重定向 HTTP 请求。此功能也称为 Map Remote。Swirl 可以用 3 种不同的方法重写请求的 URL。有关更多信息，请查看手册。";buttonText:"编辑 URL 重定向规则…";moduleId:"redirect"}
  RewriteCard{x:Theme.dp(356);y:Theme.dp(80);title:"Header 重写";description:"Swirl 可以修改发送到服务器的 HTTP Header，以及修改返回响应的 Header。";buttonText:"编辑 Header 重写规则…";moduleId:"header"}
  RewriteCard{x:Theme.dp(4);y:Theme.dp(220);title:"Mock";description:"你可以模拟 API 服务器并返回静态响应。此功能也可称为 Map Local 或 API Mocking。如果你想动态返回响应，请使用脚本。";buttonText:"编辑 Mock 规则…";moduleId:"mock"}
  RewriteCard{x:Theme.dp(356);y:Theme.dp(220);title:"Body 重写";description:"Swirl 可以重写 HTTP 请求或响应的 Body，用正则表达式替换原始内容。如果你需要进行更灵活的修改，请使用脚本。";buttonText:"编辑 Body 重写规则…";moduleId:"body"}
  RewriteCard{x:Theme.dp(4);y:Theme.dp(360);title:"端口转发";description:"将传入的 TCP 连接从本地监听端口转发到指定的目标地址。";buttonText:"编辑端口转发规则…";moduleId:"forward"}
  Text{x:Theme.dp(18);y:Theme.dp(506);text:"以上计数包含了模块中的规则。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 }
}
