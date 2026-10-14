pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "."
SwirlDialog {
 id:dialog;property string kind:"redirect";property string chosen:"";width:Math.min(Theme.dp(700),parent?parent.width-Theme.dp(40):Theme.dp(700));height:Theme.dp(510)
 ColumnLayout{anchors.fill:parent;spacing:Theme.dp(12)
  SwirlDataTable{Layout.fillWidth:true;Layout.fillHeight:true;rows:captureProvider.rewriteRules.filter(r=>r.kind===dialog.kind);fillEmptyRows:true;itemHeight:Theme.dp(30);columns:[{key:"pattern",label:"匹配表达式",w:280},{key:"replacement",label:"替换内容",w:260}];onRowSelected:r=>dialog.chosen=r.id}
  RowLayout{SwirlButton{text:"+";implicitWidth:Theme.dp(40);onClicked:addEditor.open()}SwirlButton{text:"−";implicitWidth:Theme.dp(40);enabled:dialog.chosen.length>0;onClicked:captureProvider.removeRewriteRule(dialog.chosen)}Item{Layout.fillWidth:true}SwirlButton{text:"完成";primary:true;onClicked:dialog.close()}}
  Text{text:"重写处理经过 HTTP 捕获端口的明文请求。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
 }
 SwirlDialog{id:addEditor;title:"新增规则";width:Theme.dp(510);ColumnLayout{width:parent.width;spacing:Theme.dp(10)
  Text{visible:dialog.kind!=="forward";text:"URL 正则表达式";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  SwirlTextField{id:pattern;visible:dialog.kind!=="forward";Layout.fillWidth:true;placeholderText:"^http://example\\.com/api"}
  RowLayout{visible:dialog.kind==="header"||dialog.kind==="body";Text{text:"方向";color:Theme.text}SwirlComboBox{id:direction;model:["响应","请求"];Layout.fillWidth:true}}
  SwirlTextField{id:headerName;visible:dialog.kind==="header";Layout.fillWidth:true;placeholderText:"Header 名称"}
  SwirlTextField{id:search;visible:dialog.kind==="body";Layout.fillWidth:true;placeholderText:"正文正则表达式"}
  RowLayout{visible:dialog.kind==="redirect"||dialog.kind==="mock";Text{text:"状态码";color:Theme.text}SwirlTextField{id:status;Layout.fillWidth:true;text:dialog.kind==="redirect"?"302":"200"}}
  SwirlTextField{id:listenPort;visible:dialog.kind==="forward";Layout.fillWidth:true;placeholderText:"本地监听端口"}
  SwirlTextField{id:targetHost;visible:dialog.kind==="forward";Layout.fillWidth:true;placeholderText:"目标主机名或 IP"}
  SwirlTextField{id:targetPort;visible:dialog.kind==="forward";Layout.fillWidth:true;placeholderText:"目标端口"}
  Text{visible:dialog.kind!=="forward";text:dialog.kind==="mock"?"响应正文":"替换内容";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
  ScrollView{visible:dialog.kind!=="forward";Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(100);TextArea{id:replacement;color:Theme.text;font.pixelSize:Theme.fontSize(13);wrapMode:TextEdit.Wrap;selectByMouse:true;background:Rectangle{color:Theme.field;radius:Theme.controlRadius}}}
  Text{text:captureProvider.error;color:Theme.orange;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WordWrap}
  RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:addEditor.close()}SwirlButton{text:"添加";primary:true;onClicked:{if(captureProvider.saveRewriteRule({kind:dialog.kind,pattern:pattern.text,name:headerName.text,search:search.text,replacement:replacement.text,direction:direction.currentIndex===0?"response":"request",status:Number(status.text),contentType:"application/json",listenPort:Number(listenPort.text),targetHost:targetHost.text,targetPort:Number(targetPort.text)}))addEditor.close()}}}
 }}
}
