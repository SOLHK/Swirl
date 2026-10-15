import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string selectedId:engineController.selectedNodeId
    readonly property var selected:engineController.nodes.find(function(n){return n.id===page.selectedId})||null
    readonly property var viewRows:engineController.nodes.filter(function(n){return (n.name+" "+n.host).toLowerCase().indexOf(search.text.toLowerCase())>=0&&(protocolFilter.currentIndex===0||n.protocol===page.protocols[protocolFilter.currentIndex-1])}).sort(function(a,b){return a.name.localeCompare(b.name)})
    readonly property var protocols:engineController.supportedProtocols
    property string editingId:""
    readonly property var tested:engineController.tests.results[selectedId]||({})
    function edit(node) {
        editingId=node?node.id:"";nodeName.text=node?node.name:"";nodeHost.text=node?node.host:"";nodePort.text=node?String(node.port):""
        nodeProtocol.currentIndex=node?page.protocols.indexOf(node.protocol):0
        nodeCipher.currentIndex=node?Math.max(0,nodeCipher.model.indexOf(node.cipher)):0
        nodeUuid.text="";nodeOptions.text="";replaceCredentials.checked=false;nodeSni.text=node?node.serverName:"";nodeUsername.text="";nodePassword.text="";addDialog.open()
    }
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(16)
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            Text {text:"节点";color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold;Layout.fillWidth:true}
            SwirlButton {objectName:"allNodesTestButton";text:engineController.tests.busy?"取消测速":"测速";quiet:true;iconName:"activity";enabled:engineController.nodes.length>0;onClicked:engineController.tests.busy?engineController.tests.cancel():engineController.testAllNodes(testUrl.text)}
            SwirlButton {objectName:"nodeImportButton";text:"导入";quiet:true;iconName:"download";enabled:!engineController.imports.busy;onClicked:importDialog.open()}
            SwirlButton {objectName:"nodeAddButton";text:"添加节点";iconName:"plus";primary:true;enabled:engineController.canStart;onClicked:page.edit(null)}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            SwirlSearchField {id:search;Layout.fillWidth:true;implicitHeight:Theme.dp(34);placeholderText:"搜索节点名称或服务器";font.pixelSize:Theme.fontSize(13)}
            SwirlComboBox {id:protocolFilter;objectName:"proxyRegionCombo";implicitHeight:Theme.dp(32);implicitWidth:Theme.dp(136);model:["全部协议"].concat(page.protocols)}
        }
        RowLayout {
            Layout.fillWidth:true
            Text {text:page.viewRows.length+" 个节点";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
            Text {text:engineController.tests.message||engineController.stateText+" · "+engineController.nodeStateText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight;Layout.maximumWidth:page.width*0.55}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(16)
            SwirlGlassPanel {
                Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:Theme.dp(250);Layout.fillHeight:true;cornerRadius:Theme.independentCardRadius
                color:Theme.surface;border.width:0
                SwirlDataTable {
                    id:nodeTable;objectName:"realNodeTable";minimal:true;incrementalRows:true;animateLatency:true;itemHeight:Theme.dp(40);headerHeight:Theme.dp(32);textPixelSize:13
                    anchors.fill:parent;anchors.margins:Theme.dp(10);rows:page.viewRows;selectedId:page.selectedId
                    columns:[{key:"name",label:"节点名称",w:235},{key:"protocol",label:"协议",w:82},{key:"latency",label:"延迟",w:76},{key:"status",label:"状态",w:92}]
                    onRowSelected:function(row){page.selectedId=row.id;engineController.chooseNode(row.id)}
                    onRowActivated:function(row,sourceRow){nodeHero.start(sourceRow)}
                }
                SwirlEmptyState {anchors.centerIn:parent;visible:page.viewRows.length===0;headline:"没有保存的节点";detail:"添加节点，或导入配置、URI 与订阅"}
            }
            ScrollView {
                id:detailScroll;Layout.preferredWidth:Theme.dp(280);Layout.minimumWidth:Theme.dp(280);Layout.maximumWidth:Theme.dp(280);Layout.fillHeight:true;clip:true
                ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
                ColumnLayout {width:detailScroll.availableWidth;spacing:Theme.dp(14)
                Item {
                    id:summarySlot;Layout.fillWidth:true;Layout.preferredHeight:summaryBody.implicitHeight+Theme.dp(32)
                    Text {anchors.centerIn:parent;visible:!nodeHero.opened&&!nodeHero.moving;text:"选择节点查看详情";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}
                }
                Item {
                    id:requestSlot
                    Layout.fillWidth:true;Layout.preferredHeight:requestOptions.implicitHeight+Theme.dp(32)
                SwirlGlassPanel {
                    objectName:"nodeRequestSurface"
                    parent:nodeHero.moving?page:requestSlot
                    x:nodeHero.moving?nodeHero.cardX:0
                    y:nodeHero.moving?nodeHero.cardY+nodeHero.cardHeight+Theme.dp(14)*nodeHero.reveal:0
                    width:nodeHero.moving?nodeHero.cardWidth:requestSlot.width
                    height:nodeHero.moving?requestSlot.height*nodeHero.reveal:requestSlot.height
                    z:nodeHero.moving?59:1;clip:true
                    visible:nodeHero.opened||nodeHero.moving;opacity:nodeHero.moving?nodeHero.reveal:1
                    cornerRadius:Theme.independentCardRadius;color:Theme.surface;border.width:0
                    ColumnLayout {
                        id:requestOptions;x:Theme.dp(16);y:Theme.dp(16);width:parent.width-Theme.dp(32);spacing:Theme.dp(10)
                        Text {text:"请求与端口";color:Theme.text;font.pixelSize:Theme.fontSize(13);font.weight:Font.Medium}
                        Text {text:"测试 URL";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
                        SwirlTextField {id:testUrl;objectName:"nodeTestUrl";Layout.fillWidth:true;text:"https://www.gstatic.com/generate_204";enabled:!engineController.nodeBusy;Accessible.name:"真实请求测试地址"}
                        Text {text:"本机代理端口";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
                        SwirlTextField {objectName:"nodeProxyPort";Layout.fillWidth:true;text:String(engineController.proxyPort);enabled:engineController.canStart;validator:IntValidator {bottom:1;top:65535}onEditingFinished:engineController.proxyPort=Number(text);Accessible.name:"本机代理端口"}
                        Text {objectName:"nodeRequestState";text:engineController.tests.busy?engineController.tests.message:page.tested.time?(page.tested.success?"请求成功":"请求失败")+" · HTTP "+page.tested.http+" · "+(page.tested.latency>=0?page.tested.latency+" ms":"无延迟结果")+(page.tested.error?"\n"+page.tested.error:""):engineController.requestStateText;color:engineController.tests.busy?Theme.muted:page.tested.time?(page.tested.success?Theme.green:Theme.orange):engineController.requestSucceeded?Theme.green:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        Text {text:engineController.nodeError||engineController.error;visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    }
                }
                }
                }
            }
        }
    }
    SwirlNodeTransfer {id:nodeHero;objectName:"nodeHero";targetSlot:summarySlot}
    SwirlGlassPanel {
        id:nodeIdentity;objectName:"nodeIdentitySurface"
        parent:nodeHero.moving?page:summarySlot
        x:nodeHero.moving?nodeHero.cardX:0;y:nodeHero.moving?nodeHero.cardY:0
        width:nodeHero.moving?nodeHero.cardWidth:summarySlot.width;height:nodeHero.moving?nodeHero.cardHeight:summarySlot.height
        visible:nodeHero.opened||nodeHero.moving;z:nodeHero.moving?60:1;clip:true
        cornerRadius:Theme.dp(10+10*nodeHero.reveal);color:Theme.surface;border.width:0
        ColumnLayout {
            id:summaryBody;x:Theme.dp(16);y:Theme.dp(6+10*nodeHero.reveal);width:parent.width-Theme.dp(32);spacing:Theme.dp(12)
            RowLayout {
                Layout.fillWidth:true;spacing:Theme.dp(10)*nodeHero.reveal
                SwirlIcon {name:"globe";size:Theme.dp(30);Layout.preferredWidth:Theme.dp(30)*nodeHero.reveal;opacity:nodeHero.reveal;color:Theme.accent}
                Text {id:nodeDetailTitle;objectName:"nodeDetailTitle";text:page.selected?page.selected.name:"未选择节点";textFormat:Text.PlainText;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(13+6*nodeHero.reveal);font.weight:Font.Medium;Layout.fillWidth:true;wrapMode:Text.Wrap;maximumLineCount:3;elide:Text.ElideRight}
                SwirlIconButton {objectName:"nodeReturnButton";implicitWidth:Theme.dp(24);implicitHeight:Theme.dp(26);iconName:"chevron-left";quiet:true;opacity:nodeHero.reveal;tooltip:"返回节点列表";onClicked:nodeHero.returnTo(nodeTable.selectedItem)}
            }
            ColumnLayout {
                Layout.fillWidth:true;spacing:Theme.dp(12);opacity:Math.max(0,Math.min(1,(nodeHero.reveal-0.25)/0.65))
                Text {text:page.selected?page.selected.protocol+" · "+page.selected.address:"选择一个节点开始连接";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
                Text {text:page.selected?(page.selected.sourceFormat||"手动节点")+" · "+page.selected.capability.engine:"";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                Text {text:page.selected?page.selected.normalizationNotes||"":"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                Text {text:page.selected?((page.selected.conversionIssues||[]).join("\n")):"";visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlStatusBadge {busy:engineController.nodeBusy||engineController.tests.busy;label:engineController.activeProxyPort>0?"127.0.0.1:"+engineController.activeProxyPort:engineController.nodeStateText;tone:engineController.nodeError.length?"warning":engineController.apiHealthy?"success":"neutral"}
                SwirlButton {objectName:"nodeConnectButton";Layout.fillWidth:true;implicitHeight:Theme.dp(36);text:engineController.nodeBusy?"连接中…":engineController.activeNodeId===page.selectedId&&engineController.processAlive?"断开节点":"连接节点";iconName:"link";primary:true;enabled:page.selected!==null&&!engineController.nodeBusy;onClicked:{if(engineController.activeNodeId===page.selectedId&&engineController.processAlive)engineController.disconnectNode();else engineController.connectNode(page.selectedId)}}
                RowLayout {
                    Layout.fillWidth:true;spacing:Theme.dp(6)
                    SwirlButton {objectName:"nodeTestButton";text:"测试请求";quiet:true;iconName:"activity";Layout.fillWidth:true;enabled:page.selected!==null&&!engineController.tests.busy;onClicked:engineController.testSelectedNode(page.selectedId,testUrl.text)}
                    SwirlIconButton {objectName:"nodeEditButton";iconName:"edit";quiet:true;implicitWidth:Theme.dp(30);implicitHeight:Theme.dp(30);tooltip:"编辑节点";enabled:page.selected!==null&&engineController.canStart;onClicked:page.edit(page.selected)}
                    SwirlIconButton {objectName:"nodeDeleteButton";iconName:"trash";iconColor:Theme.red;quiet:true;implicitWidth:Theme.dp(30);implicitHeight:Theme.dp(30);tooltip:"删除节点";enabled:page.selected!==null&&engineController.canStart;onClicked:{if(engineController.deleteNode(page.selectedId))page.selectedId=""}}
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog;objectName:"proxyAddDialog";title:page.editingId.length?"编辑代理节点":"添加代理节点"
        width:Math.min(Theme.dp(890),parent?parent.width-Theme.dp(30):Theme.dp(890));height:Math.min(Theme.dp(713),parent?parent.height-Theme.dp(30):Theme.dp(713))
        onClosed:{nodePassword.text="";nodeUsername.text="";nodeUuid.text="";nodeOptions.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {
                id:form;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(380),page.height*0.6);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {
                    width:form.availableWidth;spacing:Theme.dp(10)
                    Text {text:"名称";color:Theme.muted}
                    SwirlTextField {id:nodeName;objectName:"nodeNameField";Layout.fillWidth:true;Accessible.name:"节点名称"}
                    SwirlComboBox {id:nodeProtocol;objectName:"nodeProtocolField";Layout.fillWidth:true;model:page.protocols;Accessible.name:"节点协议"}
                    Text {text:"服务器";color:Theme.muted}
                    SwirlTextField {id:nodeHost;objectName:"nodeHostField";Layout.fillWidth:true;placeholderText:"域名或 IP";Accessible.name:"节点服务器"}
                    Text {text:"端口";color:Theme.muted}
                    SwirlTextField {id:nodePort;objectName:"nodePortField";Layout.fillWidth:true;validator:IntValidator {bottom:1;top:65535}Accessible.name:"节点端口"}
                    SwirlTextField {id:nodeUsername;objectName:"nodeUsernameField";visible:["socks5","http","ssh","mieru","gost-relay","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:page.editingId.length?"用户名留空保留原值":"SOCKS5 用户名（可选）";echoMode:TextInput.Password;Accessible.name:"SOCKS5 用户名"}
                    SwirlTextField {id:nodePassword;objectName:"nodePasswordField";Layout.fillWidth:true;placeholderText:page.editingId.length?"密码留空保留原值":"密码 / 密钥（按协议填写）";echoMode:TextInput.Password;Accessible.name:"节点密码"}
                    RowLayout {visible:page.editingId.length>0;Layout.fillWidth:true
                        Text {text:"替换凭据（留空可清除 SOCKS5 认证）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlToggle {id:replaceCredentials;objectName:"nodeReplaceCredentials";checked:false}
                    }
                    SwirlComboBox {id:nodeCipher;visible:nodeProtocol.currentIndex===1;Layout.fillWidth:true;editable:true;model:["aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305","2022-blake3-aes-128-gcm","2022-blake3-aes-256-gcm","2022-blake3-chacha20-poly1305"];Accessible.name:"Shadowsocks 加密方式"}
                    SwirlTextField {id:nodeSni;visible:["trojan","vmess","vless","hysteria","hysteria2","tuic","anytls","masque","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:"TLS SNI（留空使用服务器）";Accessible.name:"Trojan SNI"}
                    SwirlTextField {id:nodeUuid;visible:["vmess","vless"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:page.editingId.length?"UUID 留空保留原值":"UUID";Accessible.name:"节点 UUID"}
                    Text {text:"协议扩展选项（JSON，留空保留已保存选项）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    SwirlTextField {id:nodeOptions;objectName:"nodeOptionsField";Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:'{"network":"ws","ws-opts":{"path":"/"}}';Accessible.name:"协议扩展选项"}
                    Text {text:"支持 Clash、Surge、Loon、Quantumult X、sing-box 与 URI。凭据由 Windows DPAPI 保护；未映射参数会保留并阻止执行。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                    Text {text:engineController.nodeError;color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton {text:"取消";onClicked:addDialog.close()}
                SwirlButton {objectName:"nodeSaveButton";text:"保存";primary:true;enabled:nodeName.text.trim().length>0&&(nodePort.acceptableInput||["wireguard","tailscale","zerotier","easytier","openvpn"].indexOf(nodeProtocol.currentText)>=0);onClicked:{var input={id:page.editingId,name:nodeName.text,protocol:nodeProtocol.currentText,host:nodeHost.text,port:Number(nodePort.text),username:nodeUsername.text,password:nodePassword.text,replaceCredentials:replaceCredentials.checked,cipher:nodeProtocol.currentText==="ss"?(nodeCipher.editText||nodeCipher.currentText):"",serverName:nodeSni.text};try{if(nodeOptions.text.trim().length)input.options=JSON.parse(nodeOptions.text);if(nodeUuid.text.trim().length){if(!input.options)input.options={};input.options.uuid=nodeUuid.text.trim()}}catch(e){AppState.notice("扩展选项须为合法 JSON 对象");return}if(engineController.saveNode(input)){addDialog.close();page.selectedId=page.editingId||engineController.nodes[engineController.nodes.length-1].id}}}
            }
        }
    }

    FileDialog {
        id:configFile;title:"导入节点配置";nameFilters:["节点配置 (*.yaml *.yml *.json *.conf *.txt)","所有文件 (*)"]
        onAccepted:engineController.imports.importFile(selectedFile)
    }
    SwirlDialog {
        id:importDialog;objectName:"nodeImportDialog";title:"一键导入节点";onClosed:{importContent.text="";importAddress.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {id:importForm;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(340),page.height*0.55);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {width:importForm.availableWidth;spacing:Theme.dp(12)
            Text {text:"配置 / Base64 / URI（仅导入节点）";color:Theme.text;Layout.fillWidth:true;wrapMode:Text.Wrap}
            RowLayout {
                Layout.fillWidth:true
                SwirlButton {objectName:"importClipboardButton";text:"从剪贴板导入";enabled:!engineController.imports.busy;onClicked:engineController.imports.importClipboard()}
                SwirlButton {text:"选择文件";enabled:!engineController.imports.busy;onClicked:configFile.open()}
            }
            ScrollView {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(130);clip:true
                TextArea {id:importContent;objectName:"importContentField";placeholderText:"粘贴 Clash、Surge、Loon、Quantumult X、sing-box 配置或节点 URI";wrapMode:TextEdit.Wrap;font:importAddress.font;color:Theme.text;selectByMouse:true;Accessible.name:"待导入的节点配置";background:Rectangle {color:Theme.field;radius:Theme.controlRadius;border.color:Theme.border;border.width:1}}
            }
            Text {text:"HTTPS 订阅地址（本次导入）";color:Theme.text}
            SwirlTextField {id:importAddress;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:"https://…";Accessible.name:"一次性导入地址"}
            Text {text:engineController.imports.message;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                }
            }
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"关闭";onClicked:importDialog.close()}
                SwirlButton {objectName:"importApplyButton";text:engineController.imports.busy?"正在导入…":"导入";primary:true;enabled:!engineController.imports.busy&&(importContent.text.trim().length>0||importAddress.text.trim().length>0);onClicked:{if(importAddress.text.trim().length)engineController.imports.importUrl(importAddress.text.trim());else engineController.imports.importText(importContent.text);importContent.text="";importAddress.text=""}}
            }
            SwirlButton {text:"保存为自动更新订阅";enabled:!engineController.imports.busy;onClicked:{importDialog.close();AppState.navigate("subscriptions")}}
        }
    }
}
