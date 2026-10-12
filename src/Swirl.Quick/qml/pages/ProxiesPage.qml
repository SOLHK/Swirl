import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string selectedId:engineController.selectedNodeId
    readonly property var selected:engineController.nodes.find(function(n){return n.id===page.selectedId})||null
    readonly property var viewRows:engineController.nodes.filter(function(n){return (n.name+" "+n.host).toLowerCase().indexOf(search.text.toLowerCase())>=0&&(protocolFilter.currentIndex===0||n.protocol===["","socks5","ss","trojan"][protocolFilter.currentIndex])}).sort(function(a,b){return a.name.localeCompare(b.name)})
    property string editingId:""
    function edit(node) {
        editingId=node?node.id:"";nodeName.text=node?node.name:"";nodeHost.text=node?node.host:"";nodePort.text=node?String(node.port):""
        nodeProtocol.currentIndex=node?["socks5","ss","trojan"].indexOf(node.protocol):0
        nodeCipher.currentIndex=node?Math.max(0,nodeCipher.model.indexOf(node.cipher)):0
        replaceCredentials.checked=false;nodeSni.text=node?node.serverName:"";nodeUsername.text="";nodePassword.text="";addDialog.open()
    }
    ColumnLayout {
        anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(15)
        SwirlGlassPanel {
            Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(110)
            RowLayout {
                anchors.fill:parent;anchors.margins:Theme.dp(20);spacing:Theme.dp(18)
                ColumnLayout {
                    Layout.fillWidth:true
                    Text {text:"所选节点";color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
                    Text {text:engineController.selectedNodeName;color:Theme.text;font.pixelSize:Theme.fontSize(22);font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight}
                    Text {text:engineController.stateText+" · "+engineController.nodeStateText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}
                }
                SwirlStatusBadge {label:engineController.activeProxyPort>0?"127.0.0.1:"+engineController.activeProxyPort:"未开放代理端口";tone:"accent"}
                SwirlButton {objectName:"nodeTestButton";text:"测试请求";iconName:"activity";enabled:engineController.apiHealthy&&engineController.activeNodeId.length>0&&!engineController.nodeBusy;onClicked:engineController.testNode(testUrl.text)}
                SwirlButton {objectName:"nodeAddButton";text:"添加节点";primary:true;enabled:engineController.canStart;onClicked:page.edit(null)}
            }
        }
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(9)
            SwirlSearchField {id:search;Layout.fillWidth:true;placeholderText:"搜索节点名称或服务器"}
            SwirlComboBox {id:protocolFilter;objectName:"proxyRegionCombo";model:["全部协议","SOCKS5","Shadowsocks","Trojan"]}
            SwirlComboBox {model:["名称排序"];enabled:false}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true;Layout.fillHeight:true;clip:true
                SwirlDataTable {
                    objectName:"realNodeTable";anchors.fill:parent;anchors.margins:Theme.dp(1);rows:page.viewRows;selectedId:page.selectedId
                    columns:[{key:"name",label:"节点名称",w:240},{key:"address",label:"地址 / 端口",w:180},{key:"protocol",label:"协议",w:122},{key:"latency",label:"检测耗时（ms）",w:115},{key:"status",label:"节点状态",w:132}]
                    onRowSelected:function(row){page.selectedId=row.id;engineController.chooseNode(row.id)}
                }
                SwirlEmptyState {anchors.centerIn:parent;visible:page.viewRows.length===0;headline:"没有保存的节点";detail:"手动添加 SOCKS5、Shadowsocks 或 Trojan 节点"}
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(280);Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent;anchors.margins:Theme.dp(19);spacing:Theme.dp(12)
                    ScrollView {
                        id:details;Layout.fillWidth:true;Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                            width:details.availableWidth;spacing:Theme.dp(16)
                            Text {text:"节点详情";color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
                            SwirlIcon {name:"globe";size:Theme.dp(45);color:Theme.accent;Layout.alignment:Qt.AlignHCenter}
                            Text {text:page.selected?page.selected.name:"未选择节点";color:Theme.text;font.pixelSize:Theme.fontSize(19);font.weight:Font.DemiBold;Layout.fillWidth:true;horizontalAlignment:Text.AlignHCenter;wrapMode:Text.Wrap}
                            Text {text:page.selected?page.selected.protocol+" · "+page.selected.address:"—";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WrapAnywhere}
                            Rectangle {Layout.fillWidth:true;height:Theme.dp(1);color:Theme.border}
                            Text {objectName:"nodeRequestState";text:engineController.requestStateText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                            Text {text:"测试 URL";color:Theme.muted}
                            SwirlTextField {id:testUrl;objectName:"nodeTestUrl";Layout.fillWidth:true;text:"https://www.gstatic.com/generate_204";enabled:!engineController.nodeBusy;Accessible.name:"真实请求测试地址"}
                            Text {text:"本机代理端口";color:Theme.muted}
                            SwirlTextField {objectName:"nodeProxyPort";Layout.fillWidth:true;text:String(engineController.proxyPort);enabled:engineController.canStart;validator:IntValidator {bottom:1;top:65535}onEditingFinished:engineController.proxyPort=Number(text);Accessible.name:"本机代理端口"}
                            Text {text:engineController.nodeError||engineController.error;color:Theme.orange;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        }
                    }
                    SwirlButton {objectName:"nodeConnectButton";Layout.fillWidth:true;text:engineController.activeNodeId===page.selectedId&&engineController.processAlive?"断开节点":"连接 / 切换节点";primary:true;enabled:page.selected!==null&&!engineController.nodeBusy;onClicked:{if(engineController.activeNodeId===page.selectedId&&engineController.processAlive)engineController.disconnectNode();else engineController.connectNode(page.selectedId)}}
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton {objectName:"nodeEditButton";Layout.fillWidth:true;text:"编辑";enabled:page.selected!==null&&engineController.canStart;onClicked:page.edit(page.selected)}
                        SwirlButton {objectName:"nodeDeleteButton";Layout.fillWidth:true;text:"删除";enabled:page.selected!==null&&engineController.canStart;onClicked:{if(engineController.deleteNode(page.selectedId))page.selectedId=""}}
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog;objectName:"proxyAddDialog";title:page.editingId.length?"编辑代理节点":"添加代理节点"
        onClosed:{nodePassword.text="";nodeUsername.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {
                id:form;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(380),page.height*0.6);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {
                    width:form.availableWidth;spacing:Theme.dp(10)
                    Text {text:"名称";color:Theme.muted}
                    SwirlTextField {id:nodeName;objectName:"nodeNameField";Layout.fillWidth:true;Accessible.name:"节点名称"}
                    SwirlComboBox {id:nodeProtocol;objectName:"nodeProtocolField";Layout.fillWidth:true;model:["SOCKS5","Shadowsocks","Trojan"];Accessible.name:"节点协议"}
                    Text {text:"服务器";color:Theme.muted}
                    SwirlTextField {id:nodeHost;objectName:"nodeHostField";Layout.fillWidth:true;placeholderText:"域名或 IP";Accessible.name:"节点服务器"}
                    Text {text:"端口";color:Theme.muted}
                    SwirlTextField {id:nodePort;objectName:"nodePortField";Layout.fillWidth:true;validator:IntValidator {bottom:1;top:65535}Accessible.name:"节点端口"}
                    SwirlTextField {id:nodeUsername;objectName:"nodeUsernameField";visible:nodeProtocol.currentIndex===0;Layout.fillWidth:true;placeholderText:page.editingId.length?"用户名留空保留原值":"SOCKS5 用户名（可选）";echoMode:TextInput.Password;Accessible.name:"SOCKS5 用户名"}
                    SwirlTextField {id:nodePassword;objectName:"nodePasswordField";Layout.fillWidth:true;placeholderText:page.editingId.length?"密码留空保留原值":"密码（无认证 SOCKS5 可留空）";echoMode:TextInput.Password;Accessible.name:"节点密码"}
                    RowLayout {visible:page.editingId.length>0;Layout.fillWidth:true
                        Text {text:"替换凭据（留空可清除 SOCKS5 认证）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlToggle {id:replaceCredentials;objectName:"nodeReplaceCredentials";checked:false}
                    }
                    SwirlComboBox {id:nodeCipher;visible:nodeProtocol.currentIndex===1;Layout.fillWidth:true;model:["aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305"];Accessible.name:"Shadowsocks 加密方式"}
                    SwirlTextField {id:nodeSni;visible:nodeProtocol.currentIndex===2;Layout.fillWidth:true;placeholderText:"TLS SNI（留空使用服务器）";Accessible.name:"Trojan SNI"}
                    Text {text:"凭据使用 Windows DPAPI 保存；Trojan 始终验证服务器证书。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                    Text {text:engineController.nodeError;color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton {text:"取消";onClicked:addDialog.close()}
                SwirlButton {objectName:"nodeSaveButton";text:"保存";primary:true;enabled:nodeName.text.trim().length>0&&nodePort.acceptableInput;onClicked:{if(engineController.saveNode({id:page.editingId,name:nodeName.text,protocol:["socks5","ss","trojan"][nodeProtocol.currentIndex],host:nodeHost.text,port:Number(nodePort.text),username:nodeUsername.text,password:nodePassword.text,replaceCredentials:replaceCredentials.checked,cipher:nodeCipher.currentText,serverName:nodeSni.text})){addDialog.close();page.selectedId=page.editingId||engineController.nodes[engineController.nodes.length-1].id}}}
            }
        }
    }
}
