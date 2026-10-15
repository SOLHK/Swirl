pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page;readonly property var domainRows:captureProvider.tls.hostnames
 component Note:SwirlText {renderType:Text.NativeRendering;color:Theme.muted;font.pixelSize:Theme.fontSize(12);lineHeight:1.5;wrapMode:Text.Wrap;Layout.fillWidth:true}
 component Title:SwirlText {renderType:Text.NativeRendering;color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold;Layout.fillWidth:true}
 ScrollView {
  id:scroll;anchors.fill:parent;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
  ColumnLayout {width:Math.floor(scroll.availableWidth);spacing:Theme.dp(14)
   RowLayout {Layout.fillWidth:true;Layout.margins:Theme.dp(24);Layout.bottomMargin:0
    SwirlText {renderType:Text.NativeRendering;text:"HTTPS 解密";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold;Layout.fillWidth:true}
    SwirlToggle {objectName:"tlsToggle";large:true;enabled:captureProvider.tls.ready;checked:captureProvider.tls.enabled;onToggled:captureProvider.tls.enabled=checked;Accessible.name:"HTTPS 解密"}
   }
   Note {Layout.leftMargin:Theme.dp(24);Layout.rightMargin:Theme.dp(24);text:"配置本机 CA 证书与需要解密的主机名，通过 MitM 查看 HTTPS 请求内容。"}
   RowLayout {Layout.fillWidth:true;Layout.leftMargin:Theme.dp(24);Layout.rightMargin:Theme.dp(24);spacing:Theme.gap;Layout.alignment:Qt.AlignTop
    ColumnLayout {Layout.fillWidth:true;Layout.preferredWidth:1.1;Layout.minimumWidth:0;Layout.alignment:Qt.AlignTop;spacing:Theme.gap
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:certificateBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:certificateBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       Title {text:"CA 证书"}
       RowLayout {Layout.fillWidth:true;spacing:Theme.dp(12)
        SwirlIcon {name:"certificate";size:Theme.dp(32);color:Theme.accent}
        ColumnLayout {Layout.fillWidth:true;spacing:Theme.dp(4)
         SwirlText {renderType:Text.NativeRendering;text:captureProvider.tls.ready?"Swirl Local CA":"尚未配置 CA 证书";color:Theme.text;font.pixelSize:Theme.fontSize(13);Layout.fillWidth:true;wrapMode:Text.Wrap}
         Note {text:captureProvider.tls.trusted?"已被当前用户信任":"生成或导入证书后，安装到当前用户。"}
        }
       }
       GridLayout {Layout.fillWidth:true;columns:2;columnSpacing:Theme.dp(8);rowSpacing:Theme.dp(8)
        Repeater {model:["生成新证书","安装到系统","导入 PKCS #12","导出证书"]
         SwirlButton {required property string modelData;required property int index;objectName:"certificateAction-"+index;Layout.fillWidth:true;Layout.minimumWidth:0;text:modelData;enabled:index===0||index===2||captureProvider.tls.ready;onClicked:{if(index===0){if(!captureProvider.tls.generate())AppState.notice(captureProvider.tls.error)}else if(index===1){if(!captureProvider.tls.installTrust())AppState.notice(captureProvider.tls.error)}else if(index===2)certificateImport.open();else certificateExport.open()}}
        }
       }
      }
     }
     SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredHeight:optionsBody.implicitHeight+2*Theme.cardPadding
      ColumnLayout {id:optionsBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(12)
       Title {text:"解密选项"}
       ReferenceCheckBox {Layout.fillWidth:true;text:"跳过服务端证书验证";enabled:captureProvider.tls.ready;checked:captureProvider.tls.skipServerVerification;onToggled:captureProvider.tls.skipServerVerification=checked}
       Note {text:"即使服务器证书无效也允许连接。"}
       ReferenceCheckBox {Layout.fillWidth:true;text:"自动屏蔽 QUIC · 研发中";enabled:false}
       Note {text:"阻止命中主机名列表的 HTTP/3 连接，使其回退到 HTTP/2 或 HTTP/1.1。"}
       ReferenceCheckBox {Layout.fillWidth:true;text:"MitM over HTTP/2";checked:captureProvider.tls.http2Enabled;onToggled:captureProvider.tls.http2Enabled=checked}
       Note {text:"使用 HTTP/2 解密，在高并发下减少连接开销。"}
      }
     }
    }
    SwirlGlassPanel {Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:0;Layout.alignment:Qt.AlignTop;Layout.preferredHeight:Math.max(Theme.dp(350),hostBody.implicitHeight+2*Theme.cardPadding)
     ColumnLayout {id:hostBody;anchors.left:parent.left;anchors.right:parent.right;anchors.top:parent.top;anchors.margins:Theme.cardPadding;spacing:Theme.dp(14)
      RowLayout {Layout.fillWidth:true;Title {text:"MitM 主机名"}SwirlText {renderType:Text.NativeRendering;text:page.domainRows.length+" 项";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}}
      Note {text:"仅解密列表中的域名，支持 *.example.com 等通配符。"}
      SwirlButton {objectName:"addMitmHostname";text:"添加主机名";iconName:"plus";Layout.fillWidth:true;onClicked:hostDialog.open()}
      ListView { pixelAligned: true;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(260),contentHeight);visible:page.domainRows.length>0;clip:true;model:page.domainRows;spacing:Theme.dp(4);ScrollBar.vertical:SwirlScrollBar {}
       delegate:RowLayout {required property string modelData;width:Math.floor(ListView.view.width);height:Theme.controlHeight
        SwirlText {renderType:Text.NativeRendering;Layout.fillWidth:true;text:modelData;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
        SwirlIconButton {quiet:true;iconName:"dismiss";tooltip:"删除主机名";Accessible.name:"删除 MitM 主机名";onClicked:captureProvider.tls.removeHostname(modelData)}
       }
      }
      Note {visible:page.domainRows.length===0;text:"尚未添加主机名。添加需要检查的域名后，再开启 HTTPS 解密。"}
      Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
      Note {text:"部分应用只接受特定 CA。这里的解密通过 HTTP 捕获端口生效，支持 HTTP/1.1 与 HTTP/2。"}
     }
    }
   }
   Item {Layout.preferredHeight:Theme.dp(24)}
  }
 }
 SwirlDialog{id:hostDialog;title:"MitM 主机名";ColumnLayout{width:parent.width;SwirlTextField{id:hostname;Layout.fillWidth:true;placeholderText:"*.example.com"}SwirlText {renderType:Text.NativeRendering;text:"仅在开启 HTTPS 解密后，对列表中的主机名生效。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:hostDialog.close()}SwirlButton{text:"添加";primary:true;enabled:hostname.text.trim().length>0;onClicked:{if(captureProvider.tls.addHostname(hostname.text)){hostname.clear();hostDialog.close()}else AppState.notice(captureProvider.tls.error)}}}}}
 FileDialog{id:certificateImport;title:"导入 CA 证书";nameFilters:["PKCS #12 证书 (*.p12 *.pfx)"];onAccepted:importPasswordDialog.open()}
 SwirlDialog{id:importPasswordDialog;title:"CA 私钥密码";ColumnLayout{width:parent.width;SwirlTextField{id:certificatePassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"PKCS #12 密码（可为空）"}RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:{certificatePassword.clear();importPasswordDialog.close()}}SwirlButton{text:"导入";primary:true;onClicked:{const success=captureProvider.tls.importPkcs12(certificateImport.selectedFile,certificatePassword.text);certificatePassword.clear();if(success)importPasswordDialog.close();else AppState.notice(captureProvider.tls.error)}}}}}
 FileDialog{id:certificateExport;title:"导出 CA 证书";fileMode:FileDialog.SaveFile;nameFilters:["PEM 证书 (*.pem)"];defaultSuffix:"pem";onAccepted:if(!captureProvider.tls.exportCertificate(selectedFile))AppState.notice(captureProvider.tls.error)}
}
