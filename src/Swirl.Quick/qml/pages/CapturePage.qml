pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var captureProvider
 function applyLimits(){captureProvider.setLimits([3,5,10,0][timeLimit.currentIndex],[50,100,500,0][sizeLimit.currentIndex],[100,500,1000][countLimit.currentIndex])}
 component Note:Text{color:Theme.muted;font.pixelSize:Theme.fontSize(11);lineHeightMode:Text.FixedHeight;lineHeight:Theme.dp(14);wrapMode:Text.WordWrap;width:parent.width}
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"捕获 HTTP 内容";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlToggle{objectName:"captureToggle";x:Theme.dp(228);y:Theme.dp(34);large:true;checked:page.captureProvider.running;onToggled:{if(checked){page.applyLimits();page.captureProvider.start(8899);}else page.captureProvider.stop()}
Accessible.name:"捕获 HTTP 内容"}
 Note{x:Theme.dp(24);y:Theme.dp(74);width:parent.width-Theme.dp(48);text:page.captureProvider.error||"打开该选项后将捕获 HTTP 请求的内容数据。该选项会显著降低性能并可能耗尽存储空间，请仅在需要时开启。配合 MitM 功能使用可捕获 HTTPS 请求数据。"}
 Column{x:Theme.dp(24);y:Theme.dp(122);width:(parent.width-Theme.dp(96))/2;spacing:Theme.dp(12)
  ReferenceSection{width:parent.width;title:"可见性";tint:Theme.orange}
  SwirlButton{text:"设置内存记录过滤器…";onClicked:filterDialog.open()}
  Note{text:"内存记录：Swirl 在内存中保留最近的请求摘要，供随时查看。"}
  SwirlButton{text:"设置 HTTP 捕获过滤器…";onClicked:filterDialog.open()}
  Note{text:"HTTP 捕获：将请求摘要和 HTTP 请求的 Body 保存为 HAR。请仅在需要时开启。"}
  Item{height:Theme.dp(14);width:parent.width}
  ReferenceSection{width:parent.width;title:"磁盘 HTTP 捕获";tint:Theme.green}
  Text{text:page.captureProvider.running?"本地地址：127.0.0.1:"+page.captureProvider.port:"本地路径：不可用";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  SwirlButton{text:"在面板中显示";onClicked:page.Window.window.openDashboard()}
  Note{text:"捕获内容可从请求面板导出为 HAR；仅对 MITM 列表中的主机解密 HTTPS。"}
 }
 Column{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(122);width:(parent.width-Theme.dp(48))/2;spacing:Theme.dp(8)
  ReferenceSection{width:parent.width;title:"捕获限制器"}
  Row{spacing:Theme.dp(8);Text{text:"时间限制：";color:Theme.text;font.pixelSize:Theme.fontSize(13);anchors.verticalCenter:parent.verticalCenter}SwirlComboBox{id:timeLimit;onActivated:page.applyLimits();model:["3 分钟","5 分钟","10 分钟","无限制"];implicitWidth:Theme.dp(100);implicitHeight:Theme.dp(24)}}
  Row{spacing:Theme.dp(8);Text{text:"尺寸限制：";color:Theme.text;font.pixelSize:Theme.fontSize(13);anchors.verticalCenter:parent.verticalCenter}SwirlComboBox{id:sizeLimit;onActivated:page.applyLimits();model:["50 MB","100 MB","500 MB","无限制"];implicitWidth:Theme.dp(100);implicitHeight:Theme.dp(24)}}
  Row{spacing:Theme.dp(8);Text{text:"数量限制：";color:Theme.text;font.pixelSize:Theme.fontSize(13);anchors.verticalCenter:parent.verticalCenter}SwirlComboBox{id:countLimit;onActivated:page.applyLimits();model:["100 请求","500 请求","1000 请求"];implicitWidth:Theme.dp(112);implicitHeight:Theme.dp(24)}}
  Note{text:"在达到上述限制之一时，自动停止本次 HTTP 捕获会话。"}
  Item{height:Theme.dp(20);width:parent.width}
  ReferenceSection{width:parent.width;title:"捕获 MITM 覆写"}
  ReferenceCheckBox{text:"自动开启 MITM";checked:captureProvider.autoMitmEnabled;onToggled:captureProvider.autoMitmEnabled=checked}
  SwirlButton{text:"编辑 MITM 主机名…";onClicked:AppState.navigate("tls")}
  Note{text:"对额外的主机名开启 MITM 功能 (若已配置 CA)。仅对已配置的主机名生效。"}
  Item{height:Theme.dp(18);width:parent.width}
  ReferenceSection{width:parent.width;title:"显示";tint:Theme.magenta}
  ReferenceCheckBox{text:"合并系统进程";checked:true}
  Note{text:"将所有系统进程的统计合并到单一项目。"}
  ReferenceCheckBox{text:"应用包合并";checked:true}
  Note{text:"统计时将应用的子进程合并为单一应用。"}
 }
 SwirlDialog{id:filterDialog;title:"HTTP 捕获过滤器";ColumnLayout{width:parent.width;SwirlTextField{id:captureFilter;Layout.fillWidth:true;text:page.captureProvider.filter;placeholderText:"URL 包含文本 (留空捕获全部)"}SwirlButton{text:"应用过滤器";onClicked:{page.captureProvider.filter=captureFilter.text;filterDialog.close()}}Text{text:"查看实际捕获的 HTTP 请求与 CONNECT 隧道。";color:Theme.text;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;wrapMode:Text.WordWrap}SwirlButton{text:"打开请求面板";onClicked:{filterDialog.close();page.Window.window.openDashboard()}}}}
}
