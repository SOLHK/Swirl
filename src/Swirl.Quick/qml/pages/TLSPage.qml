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
 component Note:Text{color:Theme.muted;font.pixelSize:Theme.fontSize(11);lineHeightMode:Text.FixedHeight;lineHeight:Theme.dp(14);wrapMode:Text.WordWrap;width:parent.width}
 Text{x:Theme.dp(24);y:Theme.dp(30);text:"HTTPS 解密";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.Bold}
 SwirlToggle{objectName:"tlsToggle";x:Theme.dp(186);y:Theme.dp(34);large:true;enabled:captureProvider.tls.ready;checked:captureProvider.tls.enabled;onToggled:captureProvider.tls.enabled=checked;Accessible.name:"HTTPS 解密"}
 Note{x:Theme.dp(24);y:Theme.dp(74);width:parent.width-Theme.dp(48);text:"通过中间人攻击 (MitM, man-in-the-middle) 的方式解密 HTTPS 流量。"}
 Column{x:Theme.dp(24);y:Theme.dp(108);width:(parent.width-Theme.dp(96))/2;spacing:Theme.dp(12)
  ReferenceSection{width:parent.width;title:"CA 证书";tint:Theme.orange}
  Row{x:Theme.dp(20);width:parent.width-Theme.dp(20);height:Theme.dp(54);spacing:Theme.dp(8)
   Image{source:"qrc:/swirl/icons/ui/reference-certificate.png";width:Theme.dp(48);height:Theme.dp(48);fillMode:Image.PreserveAspectFit}
   Column{width:parent.width-Theme.dp(56);spacing:Theme.dp(4);Text{text:captureProvider.tls.ready?"Swirl Local CA":"配置中没有 CA 证书";color:Theme.text;font.pixelSize:Theme.fontSize(13)}Note{text:captureProvider.tls.trusted?"CA 证书已被当前用户信任":"CA 证书不被系统信任"}}
  }
  Column{width:Theme.dp(180);x:Theme.dp(76);height:implicitHeight-Theme.dp(4);spacing:Theme.dp(8)
   Repeater{model:["生成新证书","将证书安装到系统","从 PKCS #12 文件导入证书","导出证书"]
    SwirlButton{objectName:"certificateAction-"+index;required property string modelData;required property int index;leftPadding:Theme.dp(6);rightPadding:Theme.dp(6);width:parent.width;height:Theme.dp(24);text:modelData;enabled:index===0||index===2||captureProvider.tls.ready;onClicked:{if(index===0){if(!captureProvider.tls.generate())AppState.notice(captureProvider.tls.error)}else if(index===1){if(!captureProvider.tls.installTrust())AppState.notice(captureProvider.tls.error)}else if(index===2)certificateImport.open();else certificateExport.open()}
Accessible.name:modelData;Text{visible:index===0;x:Theme.dp(-45);anchors.verticalCenter:parent.verticalCenter;text:"操作：";color:Theme.text;font.pixelSize:Theme.fontSize(13)}}
   }
  }
  Column{width:parent.width;spacing:Theme.dp(8)
  ReferenceSection{width:parent.width;title:"选项";tint:Theme.green}
  Column{width:parent.width;spacing:Theme.dp(2);ReferenceCheckBox{text:"进行 MitM 时跳过服务端证书验证";enabled:captureProvider.tls.ready;checked:captureProvider.tls.skipServerVerification;onToggled:captureProvider.tls.skipServerVerification=checked}
  Note{x:Theme.dp(22);width:parent.width-Theme.dp(22);text:"即使服务器证书无效也允许连接。"}}
  Column{width:parent.width;spacing:Theme.dp(2);ReferenceCheckBox{text:"自动屏蔽 QUIC";enabled:false}
  Note{x:Theme.dp(22);width:parent.width-Theme.dp(22);text:"当 QUIC 连接 (即 HTTP/3) 命中 MITM 主机名列表时，自动阻止该 QUIC 连接，使得连接回退至 HTTP/2 或 HTTP/1.1，以便使其可被 MITM。"}}
  Column{width:parent.width;spacing:Theme.dp(2);ReferenceCheckBox{text:"MitM over HTTP/2";checked:captureProvider.tls.http2Enabled;onToggled:captureProvider.tls.http2Enabled=checked}
  Note{x:Theme.dp(22);width:parent.width-Theme.dp(22);text:"使用 HTTP/2 协议进行 MITM 解密，可在高并发下优化性能。"}}
  }
 }
 Rectangle{anchors.right:parent.right;anchors.rightMargin:Theme.dp(24);y:Theme.dp(108);width:(parent.width-Theme.dp(48))/2;height:parent.height-y-Theme.dp(66);radius:Theme.tableRadius;color:"transparent";border.color:Theme.border
  Rectangle{width:parent.width;height:Theme.dp(30);color:Theme.tableToolbar;Text{x:Theme.dp(16);anchors.verticalCenter:parent.verticalCenter;text:"MitM 主机名";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}SwirlIconButton{quiet:true;anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter;iconName:"add-circle";width:Theme.dp(30);height:width;onClicked:hostDialog.open()}}
  ListView{x:Theme.dp(16);y:Theme.dp(40);width:parent.width-Theme.dp(32);height:parent.height-y-Theme.dp(8);spacing:Theme.dp(8);clip:true;model:page.domainRows;ScrollIndicator.vertical:ScrollIndicator{}
   delegate:Row{required property string modelData;width:ListView.view.width;height:Theme.dp(22);Text{width:parent.width-Theme.dp(24);text:parent.modelData;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}SwirlIconButton{quiet:true;iconName:"dismiss";width:Theme.dp(24);height:Theme.dp(22);Accessible.name:"删除 MitM 主机名";onClicked:captureProvider.tls.removeHostname(parent.modelData)}}
  }
  Note{anchors.top:parent.bottom;anchors.topMargin:Theme.dp(9);text:"只有该列表中的域名才会被 Swirl 进行解密，允许使用通配符。部分应用有严格的安全策略，仅允许特定的 CA 证书。支持通过 HTTP 捕获端口进行 HTTP/1.1 和 HTTP/2 解密。"}
 }
 SwirlDialog{id:hostDialog;title:"MitM 主机名";ColumnLayout{width:parent.width;SwirlTextField{id:hostname;Layout.fillWidth:true;placeholderText:"*.example.com"}Text{text:"仅在开启 HTTPS 解密后，对列表中的主机名生效。";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:hostDialog.close()}SwirlButton{text:"添加";primary:true;enabled:hostname.text.trim().length>0;onClicked:{if(captureProvider.tls.addHostname(hostname.text)){hostname.clear();hostDialog.close()}else AppState.notice(captureProvider.tls.error)}}}}}
 FileDialog{id:certificateImport;title:"导入 CA 证书";nameFilters:["PKCS #12 证书 (*.p12 *.pfx)"];onAccepted:importPasswordDialog.open()}
 SwirlDialog{id:importPasswordDialog;title:"CA 私钥密码";ColumnLayout{width:parent.width;SwirlTextField{id:certificatePassword;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"PKCS #12 密码（可为空）"}RowLayout{Layout.alignment:Qt.AlignRight;SwirlButton{text:"取消";onClicked:{certificatePassword.clear();importPasswordDialog.close()}}SwirlButton{text:"导入";primary:true;onClicked:{const success=captureProvider.tls.importPkcs12(certificateImport.selectedFile,certificatePassword.text);certificatePassword.clear();if(success)importPasswordDialog.close();else AppState.notice(captureProvider.tls.error)}}}}}
 FileDialog{id:certificateExport;title:"导出 CA 证书";fileMode:FileDialog.SaveFile;nameFilters:["PEM 证书 (*.pem)"];defaultSuffix:"pem";onAccepted:if(!captureProvider.tls.exportCertificate(selectedFile))AppState.notice(captureProvider.tls.error)}
}
