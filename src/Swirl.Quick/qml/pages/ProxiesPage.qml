import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    readonly property Item motionTitle:routeTitle

    readonly property string selectedId:engineController.selectedNodeId
    readonly property var allNodes:engineController.nodes
    readonly property var selected:allNodes.find(n=>n.id===page.selectedId)||null
    readonly property bool selectedActive:selected!==null&&engineController.processAlive&&engineController.activeNodeId===selectedId
    property string sourceId:""
    property string countryCode:""
    readonly property var sources:engineController.imports.providers
    readonly property var sourceRows:allNodes.filter(n=>!sourceId || n.sourceId===sourceId)
    // Region options/order depend only on metadata, never on latency telemetry.
    readonly property var catalogRows:engineController.nodeCatalog.filter(n=>!sourceId || n.sourceId===sourceId)
    readonly property var nodeById:{const rows={};for(const node of allNodes)rows[node.id]=node;return rows}
    readonly property var countries:{
        const names={}
        for(const node of catalogRows)names[node.regionCode]=node.regionName
        return Object.keys(names).sort((a,b)=>names[a].localeCompare(names[b])).map(code=>({code:code,name:names[code]}))
    }
    onSourcesChanged:if(sourceId && !sources.some(s=>s.id===sourceId))sourceId=""
    onCountriesChanged:if(countryCode && !countries.some(c=>c.code===countryCode))countryCode=""
    readonly property var sortedRows:catalogRows.slice().sort((a,b)=>a.name.localeCompare(b.name))
    readonly property string searchQuery:search.text.trim().toLowerCase()
    readonly property var viewRows:sortedRows.filter(n=>(n.name+" "+n.host).toLowerCase().indexOf(searchQuery)>=0 &&
        (protocolFilter.currentIndex===0||n.protocol===page.protocols[protocolFilter.currentIndex-1]) && (!countryCode||n.regionCode===countryCode)).map(n=>nodeById[n.id]||n)
    readonly property var protocols:engineController.supportedProtocols
    function selectRow(row) {
        // One mounted surface follows the selected row; interrupted motion starts here.
        if(engineController.chooseNode(row.id))nodeHero.start(nodeTable.selectedItem)
        else AppState.notice(engineController.nodeError)
    }
    property string editingId:""
    readonly property var tested:engineController.tests.results[selectedId]||({})
    readonly property bool rustRequestMetric:engineController.rustCoreBuild
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
            SwirlText {textRole:"pageTitle";id:routeTitle;renderType:Text.NativeRendering;text:"节点";color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold;Layout.fillWidth:true}
            SwirlButton {objectName:"allNodesTestButton";text:engineController.tests.busy?"取消测速":"测速";quiet:true;iconName:"activity";enabled:engineController.nodes.length>0;onClicked:engineController.tests.busy?engineController.tests.cancel():engineController.testAllNodes(testUrl.text)}
            SwirlButton {objectName:"nodeImportButton";text:"导入";quiet:true;iconName:"download";enabled:!engineController.imports.busy;onClicked:importDialog.open()}
            SwirlButton {objectName:"nodeAddButton";text:"添加节点";iconName:"plus";primary:true;enabled:engineController.canStart;onClicked:page.edit(null)}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            SwirlSearchField {id:search;objectName:"nodeSearchField";Layout.fillWidth:true;implicitHeight:Theme.controlHeight;placeholderText:"搜索节点名称或服务器";font.pixelSize:Theme.fontSize(13)}
            SwirlComboBox {id:protocolFilter;objectName:"proxyRegionCombo";implicitHeight:Theme.controlHeight;implicitWidth:Theme.dp(136);model:["全部协议"].concat(page.protocols);Accessible.name:"按协议筛选节点"}
            SwirlComboBox {id:countryFilter;objectName:"nodeCountryFilter";implicitWidth:Theme.dp(148);model:["全部地区"].concat(page.countries.map(c=>c.name));currentIndex:Math.max(0,page.countries.findIndex(c=>c.code===page.countryCode)+1);onActivated:page.countryCode=currentIndex>0?page.countries[currentIndex-1].code:"";Accessible.name:"按国家或地区筛选节点"}
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlComboBox {objectName:"nodeSourceFilter";visible:page.sources.length>0;implicitWidth:Theme.dp(170);model:["全部来源"].concat(page.sources.map(s=>s.name));currentIndex:Math.max(0,page.sources.findIndex(s=>s.id===page.sourceId)+1);onActivated:page.sourceId=currentIndex>0?page.sources[currentIndex-1].id:"";Accessible.name:"筛选订阅来源"}
            SwirlText {renderType:Text.NativeRendering;text:page.viewRows.length+" / "+page.sourceRows.length+" 个节点";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
            SwirlText {renderType:Text.NativeRendering;text:engineController.tests.message||engineController.stateText+" · "+engineController.nodeStateText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight;Layout.maximumWidth:Math.floor(page.width*0.55)}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;spacing:Theme.dp(16)
            SwirlGlassPanel {
                Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:Theme.dp(262);Layout.fillHeight:true;cornerRadius:Theme.independentCardRadius
                color:Theme.surface;border.width:0
                SwirlDataTable {
                    id:nodeTable;objectName:"realNodeTable";minimal:true;managedSelection:true;incrementalRows:true;animateRowChanges:false;animateLatency:true;itemHeight:Theme.dp(44);headerHeight:Theme.tableHeaderHeight;textPixelSize:13
                    anchors.fill:parent;anchors.margins:Theme.dp(16);rows:page.viewRows;selectedId:page.selectedId
                    cellPadding:Theme.dp(8)
                    columns:[{key:"name",label:"节点名称",w:235,min:76},{key:"protocol",label:"协议",w:82,min:44},{key:"latency",label:page.rustRequestMetric?"首部 ms":"延迟",w:76,min:52},{key:"status",label:"状态",w:92,min:58}]
                    onRowSelected:function(row){page.selectRow(row)}
                }
                SwirlEmptyState {anchors.centerIn:parent;visible:page.viewRows.length===0;headline:page.allNodes.length?"没有匹配的节点":"没有保存的节点";detail:page.allNodes.length?"调整搜索、协议或地区筛选。":"添加节点，或导入配置、URI 与订阅"}
            }
            ScrollView {
                id:detailScroll;Layout.preferredWidth:Math.min(Theme.dp(300),page.width*0.43);Layout.minimumWidth:Theme.dp(180);Layout.maximumWidth:Theme.dp(340);Layout.fillHeight:true;clip:true
                ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
                ColumnLayout {width:detailScroll.availableWidth;spacing:Theme.dp(14)
                Item {
                    id:summarySlot;Layout.fillWidth:true;Layout.preferredHeight:summaryBody.implicitHeight+2*Theme.cardPadding
                    SwirlText {renderType:Text.NativeRendering;anchors.centerIn:parent;visible:!nodeHero.opened&&!nodeHero.moving;text:"选择节点查看详情";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}
                }
                Item {
                    id:requestSlot
                    visible:nodeHero.opened||nodeHero.moving;Layout.fillWidth:true;Layout.preferredHeight:requestOptions.implicitHeight+2*Theme.cardPadding
                SwirlGlassPanel {
                    objectName:"nodeRequestSurface"
                    parent:requestSlot
                    x:0
                    y:0
                    width:requestSlot.width
                    height:requestSlot.height
                    z:1;clip:true
                    visible:nodeHero.opened||nodeHero.moving;opacity:nodeHero.progress
                    transform:Translate{x:Theme.dp(-24)*(1-nodeHero.progress)}
                    cornerRadius:Theme.independentCardRadius;color:Theme.surface;border.width:0
                    ColumnLayout {
                        id:requestOptions;x:Theme.cardPadding;y:Theme.cardPadding;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(9)
                        SwirlText {renderType:Text.NativeRendering;text:"请求与端口";color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.Medium}
                        SwirlText {renderType:Text.NativeRendering;text:"测试 URL";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
                        SwirlTextField {id:testUrl;objectName:"nodeTestUrl";Layout.fillWidth:true;text:"https://www.gstatic.com/generate_204";enabled:!engineController.nodeBusy&&!engineController.tests.busy;selectByMouse:true;Accessible.name:"真实请求测试地址"}
                        RowLayout {
                            Layout.fillWidth:true;spacing:Theme.dp(10)
                            SwirlText {renderType:Text.NativeRendering;text:"本机代理端口";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
                            SwirlTextField {objectName:"nodeProxyPort";Layout.preferredWidth:Theme.dp(88);text:String(engineController.proxyPort);enabled:engineController.canStart;validator:IntValidator {bottom:1;top:65535}horizontalAlignment:TextInput.AlignHCenter;onEditingFinished:{if(acceptableInput)engineController.proxyPort=Number(text);text=String(engineController.proxyPort)}Accessible.name:"本机代理端口"}
                        }
                        Rectangle {Layout.fillWidth:true;implicitHeight:Theme.dp(1);color:Theme.border}
                        SwirlText {renderType:Text.NativeRendering;objectName:"nodeRequestState";text:engineController.tests.busy?engineController.tests.message:page.tested.time?(page.tested.success?"独立测试成功（不代表已连接）":"独立测试失败")+" · HTTP "+page.tested.http+" · "+(page.tested.latency>=0?(page.rustRequestMetric?"响应首部 ":"完整请求 ")+page.tested.latency+" ms":"无请求耗时结果")+(page.rustRequestMetric&&page.tested.success&&page.tested.outboundConnectMs>=0?"\n出站建立（含 DNS 与节点握手） "+page.tested.outboundConnectMs+" ms"+(page.tested.originTlsMs>=0?" · 目标 TLS "+page.tested.originTlsMs+" ms":""):"")+(page.tested.error?"\n"+page.tested.error:""):engineController.requestStateText;color:engineController.tests.busy?Theme.muted:page.tested.time?(page.tested.success?Theme.green:Theme.orange):engineController.requestSucceeded?Theme.green:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlText {renderType:Text.NativeRendering;text:"测速类型：Rust Core 经所选节点发送 HEAD，计时至目标 HTTP 响应首部（HTTPS 含目标 TLS），不等待响应体。隔离测试不继承当前 DNS 设置，目标解析遵循出站协议；不是 TCP 往返延迟。";visible:page.rustRequestMetric;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlText {renderType:Text.NativeRendering;text:engineController.nodeError||engineController.error;visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    }
                }
                }
                }
            }
        }
    }
    SwirlNodeTransfer {
        id:nodeHero;objectName:"nodeHero";targetSlot:summarySlot;sourceViewport:nodeTable
    }
    SwirlGlassPanel {
        id:nodeIdentity;objectName:"nodeIdentitySurface"
        // While settled the real ScrollView owns clipping and scrolling.
        // Only the moving shared card escapes it for the flight.
        parent:nodeHero.moving?page:summarySlot
        x:nodeHero.moving?nodeHero.cardX:0;y:nodeHero.moving?nodeHero.cardY:0
        width:nodeHero.cardWidth;height:nodeHero.cardHeight
        visible:nodeHero.opened||nodeHero.moving;z:20;clip:true;opacity:SwirlMotion.reduced?nodeHero.progress:1
        cornerRadius:Theme.independentCardRadius;color:Theme.surface;border.width:0
        ColumnLayout {
            id:summaryBody;x:Theme.cardPadding;y:Theme.dp(6)+(Theme.cardPadding-Theme.dp(6))*nodeHero.reveal;width:summarySlot.width-2*Theme.cardPadding;opacity:Math.max(0,Math.min(1,(nodeHero.reveal-0.18)/0.65));spacing:Theme.dp(12)
            RowLayout {
                Layout.fillWidth:true;spacing:Theme.dp(8)*nodeHero.reveal
                SwirlIcon {name:"globe";size:Theme.dp(22);Layout.preferredWidth:Theme.dp(22)*nodeHero.reveal;opacity:nodeHero.reveal;color:Theme.accent}
                SwirlText {renderType:Text.NativeRendering;text:"节点详情";color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.Medium;Layout.fillWidth:true}
                SwirlIconButton {objectName:"nodeReturnButton";implicitWidth:Theme.dp(24);implicitHeight:Theme.dp(26);iconName:"chevron-left";quiet:true;opacity:nodeHero.reveal;tooltip:"返回节点列表";onClicked:nodeHero.returnTo(nodeTable.selectedItem)}
            }
            SwirlText {
                id:nodeDetailTitle;objectName:"nodeDetailTitle";renderType:Text.NativeRendering
                text:page.selected?page.selected.name:"未选择节点";textFormat:Text.PlainText;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(18);font.weight:Font.Medium
                Layout.fillWidth:true;wrapMode:Text.Wrap;activeFocusOnTab:true
                HoverHandler {id:nodeNameHover}
                SwirlToolTip {parent:nodeDetailTitle;visible:page.selected!==null&&(nodeNameHover.hovered||nodeDetailTitle.activeFocus);text:nodeDetailTitle.text;delay:600}
            }
            ColumnLayout {
                Layout.fillWidth:true;spacing:Theme.dp(10)
                RowLayout {
                    Layout.fillWidth:true;spacing:Theme.dp(8)
                    SwirlStatusBadge {label:page.selected?page.selected.protocol.toUpperCase():"未选择";tone:"neutral"}
                    SwirlStatusBadge {Layout.fillWidth:false;busy:engineController.nodeBusy;label:page.selectedActive?engineController.nodeStateText:"未连接";tone:page.selectedActive?(engineController.nodeError.length?"warning":"accent"):"neutral"}
                }
                SwirlText {renderType:Text.NativeRendering;text:page.selected?page.selected.address:"选择一个节点开始连接";textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selected?(page.selected.sourceFormat||"手动节点")+" · "+page.selected.capability.engine:"";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selected?page.selected.normalizationNotes||"":"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selected?((page.selected.conversionIssues||[]).join("\n")):"";visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selectedActive&&engineController.activeProxyPort>0?"本机入口  127.0.0.1:"+engineController.activeProxyPort:"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
                GridLayout {
                    Layout.fillWidth:true;columns:2;rowSpacing:Theme.dp(8);columnSpacing:Theme.dp(8)
                    SwirlButton {objectName:"nodeConnectButton";Layout.fillWidth:true;Layout.preferredWidth:1;implicitHeight:Theme.controlHeight;text:engineController.nodeBusy?"连接中…":page.selectedActive?"断开节点":"连接节点";primary:true;enabled:page.selected!==null&&!engineController.nodeBusy;onClicked:{if(page.selectedActive)engineController.disconnectNode();else engineController.connectNode(page.selectedId)}}
                    SwirlButton {objectName:"nodeTestButton";text:engineController.tests.busy?"测试中…":"测试请求";Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected!==null&&!engineController.tests.busy&&/^https?:\/\/\S+$/i.test(testUrl.text.trim());onClicked:engineController.testSelectedNode(page.selectedId,testUrl.text.trim())}
                    SwirlButton {objectName:"nodeEditButton";text:"编辑节点";Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected!==null&&engineController.canStart;onClicked:page.edit(page.selected)}
                    SwirlButton {objectName:"nodeDeleteButton";text:"删除节点";danger:true;Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected!==null&&engineController.canStart;onClicked:engineController.deleteNode(page.selectedId)}
                }
            }
        }
    }
    SwirlDialog {
        ownerItem:page
        id:addDialog;objectName:"proxyAddDialog";title:page.editingId.length?"编辑代理节点":"添加代理节点"
        width:Math.min(Theme.dp(890),parent?parent.width-Theme.dp(30):Theme.dp(890));height:Math.min(Theme.dp(713),parent?parent.height-Theme.dp(30):Theme.dp(713))
        onClosed:{nodePassword.text="";nodeUsername.text="";nodeUuid.text="";nodeOptions.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {
                id:form;Layout.fillWidth:true;Layout.preferredHeight:Math.floor(Math.min(Theme.dp(380),page.height*0.6));clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {
                    width:form.availableWidth;spacing:Theme.dp(10)
                    SwirlText {renderType:Text.NativeRendering;text:"名称";color:Theme.muted}
                    SwirlTextField {id:nodeName;objectName:"nodeNameField";Layout.fillWidth:true;Accessible.name:"节点名称"}
                    SwirlComboBox {id:nodeProtocol;objectName:"nodeProtocolField";Layout.fillWidth:true;model:page.protocols;Accessible.name:"节点协议"}
                    SwirlText {renderType:Text.NativeRendering;text:"服务器";color:Theme.muted}
                    SwirlTextField {id:nodeHost;objectName:"nodeHostField";Layout.fillWidth:true;placeholderText:"域名或 IP";Accessible.name:"节点服务器"}
                    SwirlText {renderType:Text.NativeRendering;text:"端口";color:Theme.muted}
                    SwirlTextField {id:nodePort;objectName:"nodePortField";Layout.fillWidth:true;validator:IntValidator {bottom:1;top:65535}Accessible.name:"节点端口"}
                    SwirlTextField {id:nodeUsername;objectName:"nodeUsernameField";visible:["socks5","http","ssh","mieru","gost-relay","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:page.editingId.length?"用户名留空保留原值":"SOCKS5 用户名（可选）";echoMode:TextInput.Password;Accessible.name:"SOCKS5 用户名"}
                    SwirlTextField {id:nodePassword;objectName:"nodePasswordField";Layout.fillWidth:true;placeholderText:page.editingId.length?"密码留空保留原值":"密码 / 密钥（按协议填写）";echoMode:TextInput.Password;Accessible.name:"节点密码"}
                    RowLayout {visible:page.editingId.length>0;Layout.fillWidth:true
                        SwirlText {renderType:Text.NativeRendering;text:"替换凭据（留空可清除 SOCKS5 认证）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlToggle {id:replaceCredentials;objectName:"nodeReplaceCredentials";checked:false}
                    }
                    SwirlComboBox {id:nodeCipher;visible:nodeProtocol.currentIndex===1;Layout.fillWidth:true;editable:true;model:["aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305","2022-blake3-aes-128-gcm","2022-blake3-aes-256-gcm","2022-blake3-chacha20-poly1305"];Accessible.name:"Shadowsocks 加密方式"}
                    SwirlTextField {id:nodeSni;visible:["trojan","vmess","vless","hysteria","hysteria2","tuic","anytls","masque","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:"TLS SNI（留空使用服务器）";Accessible.name:"Trojan SNI"}
                    SwirlTextField {id:nodeUuid;visible:["vmess","vless"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:page.editingId.length?"UUID 留空保留原值":"UUID";Accessible.name:"节点 UUID"}
                    SwirlText {renderType:Text.NativeRendering;text:"协议扩展选项（JSON，留空保留已保存选项）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    SwirlTextField {id:nodeOptions;objectName:"nodeOptionsField";Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:'{"network":"ws","ws-opts":{"path":"/"}}';Accessible.name:"协议扩展选项"}
                    SwirlText {renderType:Text.NativeRendering;text:"支持 Clash、Surge、Loon、Quantumult X、sing-box 与 URI。凭据由 Windows DPAPI 保护；未映射参数会保留并阻止执行。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                    SwirlText {renderType:Text.NativeRendering;text:engineController.nodeError;color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton {text:"取消";onClicked:addDialog.close()}
                SwirlButton {objectName:"nodeSaveButton";text:"保存";primary:true;enabled:nodeName.text.trim().length>0&&(nodePort.acceptableInput||["wireguard","tailscale","zerotier","easytier","openvpn"].indexOf(nodeProtocol.currentText)>=0);onClicked:{var input={id:page.editingId,name:nodeName.text,protocol:nodeProtocol.currentText,host:nodeHost.text,port:Number(nodePort.text),username:nodeUsername.text,password:nodePassword.text,replaceCredentials:replaceCredentials.checked,cipher:nodeProtocol.currentText==="ss"?(nodeCipher.editText||nodeCipher.currentText):"",serverName:nodeSni.text};try{if(nodeOptions.text.trim().length)input.options=JSON.parse(nodeOptions.text);if(nodeUuid.text.trim().length){if(!input.options)input.options={};input.options.uuid=nodeUuid.text.trim()}}catch(e){AppState.notice("扩展选项须为合法 JSON 对象");return}if(engineController.saveNode(input)){engineController.chooseNode(page.editingId||engineController.nodes[engineController.nodes.length-1].id);nodeHero.opened=true;addDialog.close()}}}
            }
        }
    }

    FileDialog {
        parentWindow:page.Window.window;objectName:"settingsNodeFileDialog"
        id:configFile;title:"导入节点配置";nameFilters:["节点配置 (*.yaml *.yml *.json *.conf *.txt)","所有文件 (*)"]
        onAccepted:{importDialog.open();engineController.imports.importFile(selectedFile)}
    }
    SwirlDialog {
        ownerItem:page
        id:importDialog;objectName:"nodeImportDialog";title:"一键导入节点";onClosed:{engineController.imports.cancelImport();importContent.text="";importAddress.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {id:importForm;Layout.fillWidth:true;Layout.preferredHeight:Math.floor(Math.min(Theme.dp(340),page.height*0.55));clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {width:importForm.availableWidth;spacing:Theme.dp(12)
            SwirlText {renderType:Text.NativeRendering;text:"配置 / Base64 / URI（仅导入节点）";color:Theme.text;Layout.fillWidth:true;wrapMode:Text.Wrap}
            RowLayout {
                Layout.fillWidth:true
                SwirlButton {objectName:"importClipboardButton";text:"从剪贴板导入";enabled:!engineController.imports.busy&&!engineController.imports.hasPreview;onClicked:engineController.imports.importClipboard()}
                SwirlButton {text:"选择文件";enabled:!engineController.imports.busy&&!engineController.imports.hasPreview;onClicked:configFile.open()}
            }
            ScrollView {visible:!engineController.imports.hasPreview;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(130);clip:true
                SwirlTextArea {id:importContent;objectName:"importContentField";placeholderText:"粘贴 Xray / V2Ray JSON、Clash、Surge、Loon、Quantumult X、sing-box 配置或节点 URI";enabled:!engineController.imports.busy;wrapMode:TextEdit.Wrap;font.family:importAddress.font.family;font.pixelSize:importAddress.font.pixelSize;color:Theme.text;selectByMouse:true;Accessible.name:"待导入的节点配置";background:Rectangle {color:Theme.field;radius:Theme.controlRadius;border.color:Theme.border;border.width:1}}
            }
            ListView {
                objectName:"jsonImportPreview";visible:engineController.imports.hasPreview
                Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(160);clip:true
                model:engineController.imports.preview
                delegate:Column {
                    required property var modelData
                    width:ListView.view.width;spacing:Theme.dp(3)
                    SwirlText {width:parent.width;text:modelData.name+" · "+modelData.protocol.toUpperCase();textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WrapAnywhere}
                    SwirlText {width:parent.width;text:modelData.host+":"+modelData.port+" · "+modelData.capability.engine;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WrapAnywhere}
                    Item {width:1;height:Theme.dp(8)}
                }
                ScrollBar.vertical:SwirlScrollBar {}
            }
            SwirlText {visible:engineController.imports.hasPreview;Layout.fillWidth:true;text:engineController.imports.previewDiagnostics.join("\n");textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WrapAnywhere}
            SwirlText {renderType:Text.NativeRendering;text:"HTTPS 订阅地址（本次导入）";color:Theme.text}
            SwirlTextField {id:importAddress;Layout.fillWidth:true;enabled:!engineController.imports.busy&&!engineController.imports.hasPreview;echoMode:TextInput.Password;placeholderText:"https://…";Accessible.name:"一次性导入地址"}
            SwirlText {objectName:"importResultMessage";renderType:Text.NativeRendering;text:engineController.imports.message;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WrapAnywhere;Accessible.name:text}
                }
            }
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"关闭";onClicked:importDialog.close()}
                SwirlButton {visible:engineController.imports.hasPreview;text:"取消本次导入";onClicked:engineController.imports.cancelImport()}
                SwirlButton {objectName:"importApplyButton";text:engineController.imports.busy?"正在校验…":engineController.imports.hasPreview?"确认导入":"导入";primary:true;enabled:!engineController.imports.busy&&(engineController.imports.hasPreview||importContent.text.trim().length>0||importAddress.text.trim().length>0);onClicked:{if(engineController.imports.hasPreview)engineController.imports.confirmImport();else if(importAddress.text.trim().length)engineController.imports.importUrl(importAddress.text.trim());else engineController.imports.importText(importContent.text);importContent.text="";importAddress.text=""}}
            }
            SwirlButton {text:"保存为自动更新订阅";enabled:!engineController.imports.busy;onClicked:{importDialog.close();AppState.navigate("subscriptions")}}
        }
    }
}
