pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;property int tabIndex:0;property int filterIndex:0;property string query:""
 readonly property var records: {
  const q=query.toLowerCase();let rows=[];
  if(tabIndex===0)rows=captureProvider.sessions.map(r=>Object.assign({},r,{client:"本地程序",policy:r.policy||"—",rule:"—",up:r.upBytes+" B",down:r.downBytes+" B",address:r.url}));
  else if(tabIndex===1)rows=engineController.telemetry.connections;
  else if(tabIndex===2)rows=engineController.dnsConfiguration.hosts||[];
  else if(tabIndex===3)rows=gatewayProvider.devices.map(r=>Object.assign({},r,{up:r.upload,down:r.download}));
  else if(tabIndex===5)rows=(systemProvider.revision,systemProvider.logs());
  else if(tabIndex===4)rows=(engineController.telemetry.revision,engineController.telemetry.ranking("apps",0,100));
  return rows.filter(r=>JSON.stringify(r).toLowerCase().indexOf(q)>=0)
 }
 readonly property var columns:tabIndex===0?[{key:"id",label:"ID",w:50},{key:"time",label:"日期",w:93},{key:"client",label:"客户端",w:160},{key:"rule",label:"规则",w:163},{key:"policy",label:"策略",w:153},{key:"up",label:"上传",w:53},{key:"down",label:"下载",w:53},{key:"duration",label:"时长",w:60},{key:"method",label:"方法",w:75},{key:"address",label:"地址",w:190}]:tabIndex===1?[{key:"host",label:"主机名",w:220},{key:"process",label:"进程",w:170},{key:"policy",label:"策略",w:150},{key:"up",label:"上传",w:100},{key:"down",label:"下载",w:100}]:tabIndex===2?[{key:"type",label:"类型",w:80},{key:"name",label:"域名",w:220},{key:"value",label:"值",w:200},{key:"server",label:"DNS 服务器",w:160},{key:"comment",label:"注释",w:180}]:tabIndex===3?[{key:"ip",label:"IP 地址",w:150},{key:"name",label:"设备名",w:180},{key:"up",label:"上传",w:110},{key:"down",label:"下载",w:110}]:tabIndex===4?[{key:"name",label:"名称",w:230},{key:"upload",label:"上传",w:160},{key:"download",label:"下载",w:160},{key:"value",label:"今日",w:160}]:[{key:"time",label:"时间",w:180},{key:"source",label:"分类",w:120},{key:"code",label:"标题",w:160},{key:"message",label:"详情",w:520}]
 Rectangle{width:Theme.dp(220);height:parent.height;color:Theme.dark?Theme.sidebar:"#CEE0E6"
  SwirlSegmentedControl{x:Theme.dp(20);y:Theme.dp(62);width:Theme.dp(180);options:["按客户端","按主机名"];accentSelection:true;currentIndex:page.filterIndex;onActivated:index=>page.filterIndex=index}
  Text{x:Theme.dp(16);y:Theme.dp(95);text:"请求";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
  Rectangle{x:Theme.dp(10);y:Theme.dp(112);width:Theme.dp(200);height:Theme.dp(34);radius:Theme.tileRadius;color:Theme.navigationSelected;Text{x:Theme.dp(8);anchors.verticalCenter:parent.verticalCenter;text:page.filterIndex===0?"所有客户端":"所有主机名";color:Theme.accent;font.pixelSize:Theme.fontSize(13)}}
  Text{x:Theme.dp(16);y:Theme.dp(164);text:"本地程序";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
  Text{x:Theme.dp(16);y:Theme.dp(198);text:"远程客户端";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 }
 Item{x:Theme.dp(220);width:parent.width-x;height:parent.height
  SwirlSegmentedControl{x:Theme.dp(10);y:Theme.dp(12);width:Math.min(parent.width-Theme.dp(260),Theme.dp(670));height:Theme.dp(30);rounded:true;options:["最近的请求","活动连接","DNS","设备","流量统计","日志簿"];currentIndex:page.tabIndex;textPixelSize:13;onActivated:index=>page.tabIndex=index}
  SwirlSearchField{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(14);borderless:true;width:Theme.dp(270);height:Theme.dp(26);placeholderText:"搜索";onTextChanged:page.query=text}
  SwirlDataTable{objectName:"dashboardTable";stripeInset:Theme.dp(10);stripeRadius:Theme.dp(8);cellPadding:Theme.dp(6);x:0;y:Theme.dp(51);width:parent.width;height:parent.height-y-Theme.dp(38);fillEmptyRows:true;headerHeight:Theme.dp(26);itemHeight:Theme.dp(26);rows:page.records;columns:page.columns;onRowSelected:r=>{page.Window.window.openCaptureInspector()}}
  Rectangle{anchors.bottom:parent.bottom;width:parent.width;height:Theme.dp(38);color:Theme.tableToolbar
   Row{x:Theme.dp(16);anchors.verticalCenter:parent.verticalCenter;spacing:Theme.dp(10)
    SwirlButton{text:"清空";onClicked:{if(page.tabIndex===5)systemProvider.clearLogs();else captureProvider.clear()}}
    SwirlButton{text:"重新载入";onClicked:engineController.refresh()}
    SwirlButton{text:captureProvider.running?"停止流量捕获":"启动流量捕获";onClicked:{if(captureProvider.running)captureProvider.stop();else captureProvider.start(8899)}}
    SwirlButton{text:captureProvider.tls.enabled?"关闭 MitM":"开启 MitM";enabled:captureProvider.tls.ready;onClicked:captureProvider.tls.enabled=!captureProvider.tls.enabled}
    SwirlButton{text:"代理控制";onClicked:page.Window.window.openProxyControl()}
   }
  }
 }
}
