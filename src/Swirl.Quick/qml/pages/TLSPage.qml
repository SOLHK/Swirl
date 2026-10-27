pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property var domainRows:captureProvider.tls.hostnames
    readonly property Item motionTitle:heading.titleItem
    component Note:SwirlText { color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.Wrap; lineHeight:1.4 }
    ScrollView {
        id:scroll; anchors.fill:parent; anchors.margins:Theme.pagePadding; clip:true
        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff; ScrollBar.vertical:SwirlScrollBar {}
        ColumnLayout {
            width:scroll.availableWidth; spacing:Theme.dp(22)
            SwirlPageHeader {
                id:heading; Layout.fillWidth:true; title:qsTr("HTTPS 解密")
                description:qsTr("通过 HTTP 捕获端口检查指定主机名的 HTTPS 请求。")
                SwirlFlow { objectName:"tlsStateFlow"; Layout.preferredWidth:Theme.dp(42); Layout.preferredHeight:Theme.dp(18); phase:captureProvider.tls.error.length?"failed":captureProvider.tls.enabled?"succeeded":"idle" }
                SwirlToggle { objectName:"tlsToggle"; large:true; enabled:captureProvider.tls.ready; checked:captureProvider.tls.enabled; onToggled:captureProvider.tls.enabled=checked; Accessible.name:qsTr("HTTPS 解密") }
            }
            Rectangle {
                Layout.fillWidth:true; Layout.preferredHeight:certificateBody.implicitHeight+Theme.dp(32); color:Theme.buttonBase; radius:Theme.dp(14)
                ColumnLayout {
                    id:certificateBody; anchors.fill:parent; anchors.margins:Theme.dp(16); spacing:Theme.dp(14)
                    RowLayout {
                        Layout.fillWidth:true; spacing:Theme.dp(14)
                        SwirlIcon { name:"certificate"; size:Theme.dp(32); color:Theme.accent }
                        ColumnLayout { Layout.fillWidth:true; spacing:Theme.dp(5); SwirlText { text:captureProvider.tls.ready?"Swirl Local CA":qsTr("尚未配置 CA 证书"); color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold; Layout.fillWidth:true; wrapMode:Text.Wrap } Note { text:captureProvider.tls.trusted?qsTr("当前用户已信任此证书"):qsTr("未添加系统信任。生成或导入证书后，可按需安装。") } }
                    }
                    GridLayout {
                        Layout.fillWidth:true; columns:page.width>=Theme.dp(650)?4:2; columnSpacing:Theme.dp(8); rowSpacing:Theme.dp(8)
                        Repeater {
                            model:[qsTr("生成新证书"),qsTr("安装到系统"),qsTr("导入 PKCS #12"),qsTr("导出证书")]
                            SwirlButton { required property string modelData; required property int index; objectName:"certificateAction-"+index; Layout.fillWidth:true; Layout.minimumWidth:0; text:modelData; enabled:index===0||index===2||captureProvider.tls.ready; onClicked:{if(index===0){if(!captureProvider.tls.generate())AppState.notice(captureProvider.tls.error)}else if(index===1){if(!captureProvider.tls.installTrust())AppState.notice(captureProvider.tls.error)}else if(index===2)certificateImport.open();else certificateExport.open()} }
                        }
                    }
                }
            }
            Note { visible:captureProvider.tls.error.length>0; text:captureProvider.tls.error; color:Theme.red }
            GridLayout {
                Layout.fillWidth:true; columns:page.width>=Theme.dp(650)?2:1; columnSpacing:Theme.dp(28); rowSpacing:Theme.dp(24)
                ColumnLayout {
                    Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(12)
                    RowLayout { Layout.fillWidth:true; SwirlSectionTitle { title:qsTr("解密主机名"); Layout.fillWidth:true } SwirlText { text:qsTr("%1 项").arg(page.domainRows.length); color:Theme.muted; font.pixelSize:Theme.fontSize(12) } }
                    Note { text:qsTr("仅处理列表内的域名，支持 *.example.com 等通配符。") }
                    SwirlButton { objectName:"addMitmHostname"; text:qsTr("添加主机名"); iconName:"plus"; onClicked:hostDialog.open() }
                    SwirlGlassPanel {
                        Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(248); color:Theme.surface; border.width:0; cornerRadius:Theme.dp(14)
                        ListView {
                            anchors.fill:parent; anchors.margins:Theme.dp(10); clip:true; model:page.domainRows; spacing:Theme.dp(4); pixelAligned:true
                            ScrollBar.vertical:SwirlScrollBar {}
                            delegate:RowLayout { required property string modelData; width:ListView.view.width; height:Theme.controlHeight; SwirlText { Layout.fillWidth:true; text:modelData; color:Theme.text; font.pixelSize:Theme.fontSize(13); elide:Text.ElideRight } SwirlIconButton { quiet:true; iconName:"dismiss"; tooltip:qsTr("删除主机名"); Accessible.name:qsTr("删除 %1").arg(modelData); onClicked:captureProvider.tls.removeHostname(modelData) } }
                        }
                        SwirlEmptyState { visible:page.domainRows.length===0; anchors.centerIn:parent; width:Math.min(parent.width-Theme.dp(24),Theme.dp(300)); headline:qsTr("添加需要检查的域名"); detail:qsTr("开启解密后，这些主机名才会使用本机 CA。") }
                    }
                    Note { text:qsTr("部分应用仅接受特定 CA。支持的请求类型为 HTTP/1.1 与 HTTP/2。") }
                }
                ColumnLayout {
                    Layout.fillWidth:true; Layout.minimumWidth:0; Layout.preferredWidth:1; Layout.alignment:Qt.AlignTop; spacing:Theme.dp(14)
                    SwirlSectionTitle { title:qsTr("解密行为"); Layout.fillWidth:true }
                    ReferenceCheckBox { Layout.fillWidth:true; text:qsTr("跳过服务端证书验证"); enabled:captureProvider.tls.ready; checked:captureProvider.tls.skipServerVerification; onToggled:captureProvider.tls.skipServerVerification=checked }
                    Note { text:qsTr("开启后允许连接证书无效的服务器。") }
                    Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                    ReferenceCheckBox { Layout.fillWidth:true; text:"MitM over HTTP/2"; checked:captureProvider.tls.http2Enabled; onToggled:captureProvider.tls.http2Enabled=checked }
                    Note { text:qsTr("在支持的连接中使用 HTTP/2 解密。") }
                    Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.borderWidth; color:Theme.separator }
                    ReferenceCheckBox { Layout.fillWidth:true; text:qsTr("自动屏蔽 QUIC · 研发中"); enabled:false }
                    Note { text:qsTr("HTTP/3 回退控制尚未接入。") }
                }
            }
            Item { Layout.preferredHeight:Theme.dp(6) }
        }
    }
    SwirlDialog { ownerItem:page; id:hostDialog; title:qsTr("添加解密主机名"); ColumnLayout { width:parent.width; spacing:Theme.dp(14); SwirlTextField { id:hostname; Layout.fillWidth:true; placeholderText:"*.example.com"; Accessible.name:qsTr("解密主机名") } Note { text:qsTr("添加后，仅在开启 HTTPS 解密时生效。") } RowLayout { Layout.alignment:Qt.AlignRight; SwirlButton { text:qsTr("取消"); onClicked:hostDialog.requestDismiss() } SwirlButton { text:qsTr("添加"); primary:true; enabled:hostname.text.trim().length>0; onClicked:{if(captureProvider.tls.addHostname(hostname.text)){hostname.clear();hostDialog.markSaved();hostDialog.close()}else AppState.notice(captureProvider.tls.error)} } } } }
    FileDialog { id:certificateImport; title:qsTr("导入 CA 证书"); nameFilters:[qsTr("PKCS #12 证书 (*.p12 *.pfx)")]; onAccepted:importPasswordDialog.open() }
    SwirlDialog { ownerItem:page; id:importPasswordDialog; title:qsTr("CA 私钥密码"); ColumnLayout { width:parent.width; spacing:Theme.dp(14); SwirlTextField { id:certificatePassword; Layout.fillWidth:true; echoMode:TextInput.Password; placeholderText:qsTr("PKCS #12 密码，可留空") } Note { visible:captureProvider.tls.error.length>0; text:captureProvider.tls.error; color:Theme.red } RowLayout { Layout.alignment:Qt.AlignRight; SwirlButton { text:qsTr("取消"); onClicked:{certificatePassword.clear();importPasswordDialog.close()} } SwirlButton { text:qsTr("导入"); primary:true; onClicked:{const success=captureProvider.tls.importPkcs12(certificateImport.selectedFile,certificatePassword.text);certificatePassword.clear();if(success)importPasswordDialog.close();else AppState.notice(captureProvider.tls.error)} } } } }
    FileDialog { id:certificateExport; title:qsTr("导出 CA 证书"); fileMode:FileDialog.SaveFile; nameFilters:[qsTr("PEM 证书 (*.pem)")]; defaultSuffix:"pem"; onAccepted:if(!captureProvider.tls.exportCertificate(selectedFile))AppState.notice(captureProvider.tls.error) }
}
