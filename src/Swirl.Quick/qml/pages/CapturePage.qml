pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;required property var captureProvider
 property int listenerPort:8899
 function scrollToBottom(){scroll.contentItem.contentY=Math.max(0,scroll.contentItem.contentHeight-scroll.availableHeight)}
 function applyLimits(){captureProvider.setLimits([3,5,10,0][timeLimit.currentIndex],[50,100,500,0][sizeLimit.currentIndex],[100,500,1000][countLimit.currentIndex])}
 component Note:SwirlText {renderType:Text.NativeRendering;color:Theme.muted;font.pixelSize:Theme.fontSize(12);lineHeight:1.5;wrapMode:Text.Wrap;Layout.fillWidth:true}
 component SectionTitle:SwirlText {renderType:Text.NativeRendering;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
 ScrollView {
  id:scroll;anchors.fill:parent;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout {width:Math.floor(scroll.availableWidth);spacing:Theme.dp(14)
   RowLayout {Layout.fillWidth:true;Layout.leftMargin:Theme.dp(24);Layout.rightMargin:Theme.dp(24);Layout.topMargin:Theme.dp(24)
    SwirlText {textRole:"pageTitle";renderType:Text.NativeRendering;text:"捕获 HTTP 内容";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.fillWidth:true}
    SwirlToggle {objectName:"captureToggle";large:true;checked:page.captureProvider.running;onToggled:{if(checked){page.applyLimits();page.captureProvider.start(page.listenerPort)}else page.captureProvider.stop()}Accessible.name:"捕获 HTTP 内容"}
   }
   Note {Layout.leftMargin:Theme.dp(24);Layout.rightMargin:Theme.dp(24);text:page.captureProvider.error||"捕获 HTTP 请求与内容。开启后会增加内存和存储开销，请仅在需要时使用；HTTPS 内容需要配合 MITM。"}
   RowLayout {Layout.fillWidth:true;Layout.leftMargin:Theme.dp(24);Layout.rightMargin:Theme.dp(24);spacing:Theme.gap;Layout.alignment:Qt.AlignTop
    ColumnLayout {Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.alignment:Qt.AlignTop;spacing:Theme.gap
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:visibilityBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:visibilityBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       SectionTitle {text:"可见性"}
       Note {text:"内存记录保留最近请求的摘要，HTTP 捕获同时保存请求内容。"}
       SwirlButton {text:"设置内存记录过滤器…";Layout.fillWidth:true;onClicked:filterDialog.open()}
       SwirlButton {text:"设置 HTTP 捕获过滤器…";Layout.fillWidth:true;onClicked:filterDialog.open()}
      }
     }
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:diskBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:diskBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       SectionTitle {text:"磁盘 HTTP 捕获"}
       Note {text:page.captureProvider.running?"本地地址：127.0.0.1:"+page.captureProvider.port:"尚未启动捕获"}
       SwirlButton {text:"在面板中显示";Layout.fillWidth:true;onClicked:page.Window.window.openDashboard()}
       Note {text:"从请求面板导出 HAR。仅解密 MITM 主机列表中的 HTTPS 请求。"}
      }
     }
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:displayBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:displayBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(10)
       SectionTitle {text:"显示"}
       ReferenceCheckBox {text:"合并系统进程 · 研发中";checked:true;enabled:false}
       Note {text:"将系统进程的统计合并到单一项目。"}
       ReferenceCheckBox {text:"应用包合并 · 研发中";checked:true;enabled:false}
       Note {text:"将应用及其子进程合并统计。"}
      }
     }
    }
    ColumnLayout {Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.alignment:Qt.AlignTop;spacing:Theme.gap
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:limitsBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:limitsBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       SectionTitle {text:"捕获限制器"}
       GridLayout {Layout.fillWidth:true;columns:2;columnSpacing:Theme.dp(8);rowSpacing:Theme.dp(12)
        SwirlText {renderType:Text.NativeRendering;text:"时间限制";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
        SwirlComboBox {id:timeLimit;Layout.fillWidth:true;Layout.minimumWidth:0;onActivated:page.applyLimits();model:["3 分钟","5 分钟","10 分钟","无限制"]}
        SwirlText {renderType:Text.NativeRendering;text:"尺寸限制";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
        SwirlComboBox {id:sizeLimit;Layout.fillWidth:true;Layout.minimumWidth:0;onActivated:page.applyLimits();model:["50 MB","100 MB","500 MB","无限制"]}
        SwirlText {renderType:Text.NativeRendering;text:"数量限制";color:Theme.text;font.pixelSize:Theme.fontSize(13)}
        SwirlComboBox {id:countLimit;Layout.fillWidth:true;Layout.minimumWidth:0;onActivated:page.applyLimits();model:["100 请求","500 请求","1000 请求"]}
       }
       Note {text:"达到任一限制时，自动停止本次 HTTP 捕获。"}
      }
     }
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:mitmBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:mitmBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       SectionTitle {text:"捕获 MITM 覆写"}
       ReferenceCheckBox {text:"自动开启 MITM";checked:page.captureProvider.autoMitmEnabled;onToggled:page.captureProvider.autoMitmEnabled=checked}
       SwirlButton {text:"编辑 MITM 主机名…";Layout.fillWidth:true;onClicked:AppState.navigate("tls")}
       Note {text:"仅对已配置的主机名生效，使用前需配置 CA。"}
      }
     }
    }
   }
   Item {Layout.preferredHeight:Theme.dp(24)}
  }
 }
 SwirlDialog{id:filterDialog;title:"HTTP 捕获过滤器";ColumnLayout{width:parent.width;SwirlTextField{id:captureFilter;Layout.fillWidth:true;text:page.captureProvider.filter;placeholderText:"URL 包含文本 (留空捕获全部)"}SwirlButton{text:"应用过滤器";onClicked:{page.captureProvider.filter=captureFilter.text;filterDialog.close()}}SwirlText {renderType:Text.NativeRendering;text:"查看实际捕获的 HTTP 请求与 CONNECT 隧道。";color:Theme.text;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;wrapMode:Text.WordWrap}SwirlButton{text:"打开请求面板";onClicked:{filterDialog.close();page.Window.window.openDashboard()}}}}
}
