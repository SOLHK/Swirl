pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;objectName:"dashboardPage"
 property int tabIndex:0
 property int filterIndex:0
 property string query:""
 property string selectedGroup:""
 property string feedback:""
 onTabIndexChanged:{selectedGroup="";feedback=""}
 onFilterIndexChanged:selectedGroup=""
 readonly property var sourceRows:{
  if(tabIndex===0)return captureProvider.sessions.map(r=>Object.assign({},r,{client:"本地程序",policy:r.policy||"—",rule:r.rule||"—",up:r.upBytes+" B",down:r.downBytes+" B",address:r.url,host:r.host||r.url}));
  if(tabIndex===1)return engineController.telemetry.connections;
  if(tabIndex===2)return (engineController.dnsConfiguration.hosts||[]).map(r=>({name:r.name,value:r.value,type:"Hosts 配置"}));
  if(tabIndex===3)return gatewayProvider.devices.map(r=>Object.assign({},r,{up:r.upload,down:r.download}));
  if(tabIndex===4)return (engineController.telemetry.revision,engineController.telemetry.ranking("apps",0,100));
  return (systemProvider.revision,systemProvider.logs());
 }
 function groupKey(r){return String(filterIndex===0?(r.process||r.client||r.source||r.name||"未分类"):(r.host||r.ip||r.name||"未分类"))}
 readonly property var groupNames:Array.from(new Set(sourceRows.map(r=>groupKey(r)))).sort()
 readonly property var records:sourceRows.filter(r=>(!selectedGroup||groupKey(r)===selectedGroup)&&JSON.stringify(r).toLowerCase().indexOf(query.toLowerCase())>=0)
 readonly property var columns:tabIndex===0?[{key:"id",label:"ID",w:60},{key:"time",label:"时间",w:110},{key:"method",label:"方法",w:70},{key:"policy",label:"策略",w:130},{key:"up",label:"上传",w:80},{key:"down",label:"下载",w:80},{key:"address",label:"地址",w:300}]:tabIndex===1?[{key:"host",label:"主机名",w:220},{key:"process",label:"进程",w:170},{key:"policy",label:"策略",w:150},{key:"up",label:"上传",w:100},{key:"down",label:"下载",w:100}]:tabIndex===2?[{key:"type",label:"来源",w:140},{key:"name",label:"域名",w:240},{key:"value",label:"映射地址",w:260}]:tabIndex===3?[{key:"ip",label:"IP 地址",w:170},{key:"name",label:"设备名",w:200},{key:"up",label:"上传",w:110},{key:"down",label:"下载",w:110}]:tabIndex===4?[{key:"name",label:"进程",w:250},{key:"upload",label:"上传",w:150},{key:"download",label:"下载",w:150},{key:"value",label:"今日总计",w:160}]:[{key:"time",label:"时间",w:180},{key:"source",label:"分类",w:120},{key:"code",label:"标题",w:160},{key:"message",label:"详情",w:520}]
 RowLayout{
  anchors.fill:parent;anchors.margins:Theme.dp(16);spacing:Theme.dp(16)
  ColumnLayout{
   Layout.preferredWidth:Theme.dp(190);Layout.fillHeight:true;spacing:Theme.dp(12)
   SwirlText {text:"网络控制与调试";color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(15);font.weight:Font.Medium}
   SwirlSegmentedControl{Layout.fillWidth:true;options:["按客户端","按主机名"];currentIndex:page.filterIndex;onActivated:index=>page.filterIndex=index}
   SwirlButton{Layout.fillWidth:true;text:"全部 · "+page.sourceRows.length;quiet:page.selectedGroup!=="";onClicked:page.selectedGroup=""}
   ListView { pixelAligned: true;
    Layout.fillWidth:true;Layout.fillHeight:true;clip:true;spacing:Theme.dp(4);model:page.groupNames
    delegate:SwirlButton{required property string modelData;width:Math.floor(ListView.view.width);text:modelData;quiet:page.selectedGroup!==modelData;onClicked:page.selectedGroup=modelData}
    ScrollBar.vertical:SwirlScrollBar{}
   }
   SwirlText {text:engineController.connected?"引擎已连接":"引擎未连接";color:engineController.connected?Theme.green:Theme.muted;font.pixelSize:Theme.fontSize(12)}
  }
  ColumnLayout{
   Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(10)
   SwirlSegmentedControl{objectName:"dashboardTabs";Layout.fillWidth:true;implicitHeight:Theme.dp(32);rounded:true;options:["最近请求","活动连接","DNS","设备","流量统计","日志"];currentIndex:page.tabIndex;textPixelSize:12;onActivated:index=>page.tabIndex=index}
   RowLayout{
    Layout.fillWidth:true
    SwirlSearchField{objectName:"dashboardSearch";Layout.fillWidth:true;placeholderText:"搜索当前记录";onTextChanged:page.query=text}
    SwirlText {text:page.records.length+" 项";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
   }
   SwirlText {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12);text:page.tabIndex===2?"当前显示已保存的 Hosts 配置 · DNS 查询历史研发中":page.feedback||captureProvider.error||engineController.error;visible:text.length>0;color:page.tabIndex===2?Theme.muted:Theme.orange}
   SwirlGlassPanel{
    Layout.fillWidth:true;Layout.fillHeight:true;cornerRadius:Theme.independentCardRadius;clip:true
    SwirlDataTable{objectName:"dashboardTable";anchors.fill:parent;anchors.margins:Theme.dp(16);stripeInset:Theme.dp(6);stripeRadius:Theme.tileRadius;cellPadding:Theme.controlPadding;fillEmptyRows:false;headerHeight:Theme.tableHeaderHeight;itemHeight:Theme.tableRowHeight;rows:page.records;columns:page.columns;onRowSelected:r=>{if(page.tabIndex===0)page.Window.window.openCaptureInspector();else page.feedback="已选择："+String(r.host||r.name||r.code||r.ip||"记录")}}
    SwirlEmptyState{anchors.centerIn:parent;visible:page.records.length===0;headline:page.query.length?"没有匹配的记录":"暂无记录";detail:page.tabIndex===0?"开启捕获并通过捕获端口发起真实请求。":page.tabIndex===2?"Hosts 可在 DNS 设置中配置；查询历史研发中。":"连接和流量仅在取得真实数据后显示。"}
   }
   Flow{
    Layout.fillWidth:true;spacing:Theme.dp(8)
    SwirlButton{objectName:"dashboardClear";text:"清空";enabled:page.tabIndex===0||page.tabIndex===5;onClicked:{if(page.tabIndex===5)systemProvider.clearLogs();else captureProvider.clear();page.feedback=page.tabIndex===5?"已清空日志视图":"已清空请求记录"}}
    SwirlButton{text:"重新载入";onClicked:{engineController.refresh();page.feedback="已请求刷新当前网络状态"}}
    SwirlButton{text:captureProvider.running?"停止捕获":"启动捕获";onClicked:{if(captureProvider.running)captureProvider.stop();else captureProvider.start(8899);page.feedback=captureProvider.error||(captureProvider.running?"捕获监听：127.0.0.1:"+captureProvider.port:"捕获已停止")}}
    SwirlButton{text:captureProvider.tls.enabled?"关闭 MitM":"开启 MitM";enabled:captureProvider.tls.ready;onClicked:{captureProvider.tls.enabled=!captureProvider.tls.enabled;page.feedback=captureProvider.tls.enabled?"MitM 已开启，需显式代理及受信任证书":"MitM 已关闭"}}
    SwirlButton{text:"代理控制";onClicked:page.Window.window.openProxyControl()}
    SwirlButton{visible:page.tabIndex===2;text:"DNS 查询历史";development:true;enabled:false}
   }
  }
 }
}
