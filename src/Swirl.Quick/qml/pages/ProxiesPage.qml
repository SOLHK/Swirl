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
    readonly property bool detailOpen:nodeHero.opened

    property string inspectedId:""
    property string focusedId:""
    property string nodeSaveRequestId:""
    property string nodeDeleteRequestId:""
    property string nodeDeletedId:""
    property bool nodeSaveSubmitting:false
    property bool nodeDeleteSubmitting:false
    property bool nodeDeleteRecovery:false
    property string nodeMutationMessage:""
    property var lastNodeCompletion:({requestId:"",success:false})
    readonly property bool nodeSavePending:nodeSaveSubmitting||nodeSaveRequestId.length>0
    readonly property bool nodeDeletePending:nodeDeleteSubmitting||nodeDeleteRequestId.length>0
    readonly property string selectedId:inspectedId
    NodeViewModel { id:nodes;objectName:"nodeViewModel";controller:engineController }
    NodeSectionModel { id:sections;objectName:"nodeSectionModel";source:nodes;providers:page.sources }
    readonly property var selected:{nodes.revision;return nodes.find(page.selectedId)}
    readonly property var focused:{nodes.revision;return nodes.find(page.focusedId)}
    onSelectedChanged:if(selected.id===undefined&&!nodeDeletePending&&!nodeDeleteRecovery){inspectedId="";if(nodeHero.opened)nodeHero.returnTo(null)}
    onFocusedChanged:if(focused.id===undefined)focusedId=""
    readonly property bool selectedActive:selected.id!==undefined&&engineController.processAlive&&engineController.activeNodeId===selectedId
    property string sourceId:""
    property string sourceKind:""
    onSourceIdChanged:if(sourceId.length)sourceKind="subscription"
    property string countryCode:""
    property string protocol:""
    property string statusFilter:""
    property int maxLatency:-1
    property bool availableOnly:false
    property bool recentOnly:false
    property int groupIndex:0
    onGroupIndexChanged:if(groupIndex!==0)recentOnly=false
    readonly property var sources:engineController.imports.providers
    readonly property var sourceOptions:[{id:"",kind:"",name:qsTr("全部来源")},{id:"",kind:"manual",name:qsTr("手动添加")}].concat(page.sources.map(s=>({id:s.id,kind:"subscription",name:s.name}))).concat(engineController.imports.legacyNodeCount>0?[{id:"",kind:"legacy",name:qsTr("历史未归属")}]:[])
    readonly property int sourceIndex:Math.max(0,sourceOptions.findIndex(s=>s.id===page.sourceId&&s.kind===page.sourceKind))
    function selectSource(index){const entry=sourceOptions[index]||sourceOptions[0];sourceKind=entry.kind;sourceId=entry.id}
    readonly property var countries:{const names={};for(const n of engineController.nodeCatalog)if((!sourceId||n.sourceId===sourceId)&&(!sourceKind||n.sourceKind===sourceKind))names[n.regionCode]=n.regionName;return Object.keys(names).sort().map(code=>({code:code,name:names[code]}))}
    onCountriesChanged:if(countryCode&&!countries.some(c=>c.code===countryCode))countryCode=""
    readonly property int resultCount:nodes.count
    readonly property var protocols:engineController.supportedProtocols
    readonly property var filterState:({protocol:protocol,regionCode:countryCode,sourceId:sourceId,sourceKind:sourceKind,status:statusFilter,maxLatency:maxLatency,available:availableOnly||groupIndex===1,group:groupIndex===2?"favorites":recentOnly?"recent":"all",sort:["name","latency","regionName","protocol"][sortOrder.currentIndex]})
    onFilterStateChanged:nodes.filters=filterState
    onSourcesChanged:if(sourceId&&!sources.some(s=>s.id===sourceId)){sourceId="";sourceKind=""}
    onSourceOptionsChanged:if(sourceKind==="legacy"&&!sourceOptions.some(s=>s.kind==="legacy"))sourceKind=""
    Timer {id:searchDelay;interval:100;onTriggered:{nodes.query=search.text;nodeTable.scrollToBeginning()}}
    function dismissDetail(){if(!nodeHero.opened)return false;if(nodeDeletePending)return true;nodeHero.returnTo(nodeTable.selectedItem);if(nodeDeleteRecovery){nodeDeleteRecovery=false;inspectedId=""}return true}
    function selectRow(row) {if(row&&row.id)focusedId=row.id}
    function inspectRow(row) {
        if(!row||!row.id||nodeDeletePending)return
        nodeTable.focusRowAt(sections.indexOfNode(row.id))
        nodeDeleteRecovery=false;nodeMutationMessage=""
        focusedId=row.id;inspectedId=row.id;nodeHero.start(nodeTable.selectedItem)
    }
    function sectionIndexForNode(id){return sections.indexOfNode(id)}
    function resourceAt(index){return nodes.get(index)}
    function filteredNodeIds(){return sections.nodeIds()}
    Shortcut {sequences:[StandardKey.Find];enabled:page.visible&&!page.detailOpen;onActivated:search.forceActiveFocus()}
    property string editingId:""
    readonly property bool rustRequestMetric:engineController.rustCoreBuild
    property bool importPending:false
    property bool editingJson:false
    readonly property var tested:engineController.tests.results[selectedId]||({})
    function completeNodeMutation(requestId,success) {
        if(!requestId.length)return
        if(success&&String((engineController.policyReceipt||{}).request_id)!==requestId)success=false
        if(requestId===nodeSaveRequestId){nodeSaveRequestId="";nodeSaveSubmitting=false;if(success){addDialog.markSaved();addDialog.close()}else nodeMutationMessage=engineController.policyError||engineController.nodeError||qsTr("节点未能保存，请修改后重试。")}
        if(requestId===nodeDeleteRequestId){nodeDeleteRequestId="";nodeDeleteSubmitting=false;if(success){nodeDeleteRecovery=false;dismissDetail();inspectedId="";if(focusedId===nodeDeletedId)focusedId=""}else{nodeDeleteRecovery=selected.id===undefined;nodeMutationMessage=engineController.policyError||engineController.nodeError||qsTr("删除尚未确认，请检查恢复状态。")}}
    }
    function trackNodeMutation(kind,accepted,v2) {
        if(!accepted){nodeSaveSubmitting=false;nodeDeleteSubmitting=false;nodeMutationMessage=engineController.policyError||engineController.nodeError;return}
        if(!v2){nodeSaveSubmitting=false;nodeDeleteSubmitting=false;if(kind==="save"){addDialog.markSaved();addDialog.close()}else{dismissDetail();inspectedId="";if(focusedId===nodeDeletedId)focusedId=""}return}
        const requestId=String(engineController.policyRequestId)
        if(kind==="save"){nodeSaveRequestId=requestId;nodeSaveSubmitting=false}else{nodeDeleteRequestId=requestId;nodeDeleteSubmitting=false}
        if(lastNodeCompletion.requestId===requestId)completeNodeMutation(requestId,lastNodeCompletion.success)
        else if(!engineController.policyBusy&&String((engineController.policyReceipt||{}).request_id)===requestId)completeNodeMutation(requestId,true)
    }
    function saveResource(input) {nodeMutationMessage="";const v2=engineController.policyV2Active;nodeSaveSubmitting=true;trackNodeMutation("save",engineController.saveNode(input),v2)}
    function deleteResource(id) {nodeMutationMessage="";nodeDeleteRecovery=false;nodeDeletedId=id;const v2=engineController.policyV2Active;nodeDeleteSubmitting=true;trackNodeMutation("delete",engineController.deleteNode(id),v2)}
    function edit(node) {
        nodeMutationMessage=""
        editingJson=Boolean(node&&node.jsonParsed);editingId=node?node.id:"";nodeName.text=node?node.name:"";nodeHost.text=node?node.host:"";nodePort.text=node?String(node.port):""
        nodeProtocol.currentIndex=node?page.protocols.indexOf(node.protocol):0
        nodeCipher.currentIndex=node?Math.max(0,nodeCipher.model.indexOf(node.cipher)):0
        nodeUuid.text="";nodeOptions.text="";replaceCredentials.checked=false;nodeSni.text=node?node.serverName:"";nodeUsername.text="";nodePassword.text="";addDialog.open()
    }
    ColumnLayout {
        opacity:1-nodeHero.progress
        anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.dp(16)
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            SwirlText {textRole:"pageTitle";id:routeTitle;renderType:Text.NativeRendering;text:"节点";color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold}
            SwirlText {text:String(nodes.total);color:Theme.muted;font.pixelSize:Theme.fontSize(16);Accessible.name:qsTr("%1 个节点").arg(nodes.total)}
            Item {Layout.fillWidth:true}
            SwirlButton {id:allTestsButton;objectName:"allNodesTestButton";text:engineController.tests.busy?qsTr("取消测速"):qsTr("测速 ⌄");quiet:true;iconName:"activity";enabled:nodes.total>0||engineController.tests.busy;onClicked:{if(engineController.tests.busy)engineController.tests.cancel();else{SwirlMotion.noteTrigger(allTestsButton);batchTestMenu.showAt()}}}
            SwirlButton {objectName:"nodeImportButton";text:"导入";quiet:true;iconName:"download";enabled:!engineController.imports.busy;onClicked:importDialog.open()}
            SwirlButton {objectName:"nodeAddButton";text:"添加节点";iconName:"plus";primary:true;enabled:engineController.canStart;onClicked:page.edit(null)}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(8)
            SwirlSearchField {id:search;objectName:"nodeSearchField";Layout.fillWidth:true;Layout.minimumWidth:0;placeholderText:"搜索节点名称、地区、服务器或协议";onTextChanged:searchDelay.restart();Accessible.name:placeholderText}
            SwirlIconButton {iconName:"dismiss";tooltip:"清空搜索";enabled:search.text.length>0;opacity:enabled?1:0;onClicked:search.clear()}
            SwirlComboBox {objectName:"nodeSourceFilter";Layout.preferredWidth:Theme.dp(146);model:page.sourceOptions.map(s=>s.name);currentIndex:page.sourceIndex;onActivated:index=>page.selectSource(index);Accessible.name:qsTr("节点来源")}
            SwirlButton {objectName:"nodeFiltersButton";text:"筛选";quiet:true;onClicked:filtersDialog.open()}
            SwirlComboBox {id:sortOrder;objectName:"nodeSortOrder";Layout.preferredWidth:Theme.dp(110);model:[qsTr("名称排序"),qsTr("耗时排序"),qsTr("地区排序"),qsTr("协议排序")];Accessible.name:qsTr("来源内节点排序")}
        }
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(8)
            SwirlSegmentedControl {objectName:"nodeLibraryTabs";Layout.preferredWidth:Theme.dp(224);options:["全部","可用","收藏"];currentIndex:page.groupIndex;onActivated:index=>{page.recentOnly=false;page.groupIndex=index}}
            SwirlText {text:nodes.count+" / "+nodes.total+" 个节点";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}
        }
        RowLayout {
            Layout.fillWidth:true;visible:engineController.tests.busy||engineController.tests.message.length>0;spacing:Theme.dp(8)
            SwirlFlow {objectName:"nodeTestFlow";Layout.preferredWidth:Theme.dp(42);Layout.preferredHeight:Theme.dp(18);phase:engineController.tests.busy?"pending":"idle"}
            SwirlText {objectName:"nodeBatchProgress";text:engineController.tests.busy?qsTr("正在测速 %1 / %2").arg(engineController.tests.completed).arg(engineController.tests.total):engineController.tests.message;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;elide:Text.ElideRight}
        }
        RowLayout {
            Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;spacing:Theme.dp(16)
            SwirlGlassPanel {
                Layout.fillWidth:true;Layout.preferredWidth:1;Layout.minimumWidth:Theme.dp(262);Layout.fillHeight:true;Layout.minimumHeight:0;cornerRadius:Theme.independentCardRadius
                color:Theme.surface;border.width:0
                SwirlDataTable {
                    id:nodeTable;objectName:"realNodeTable";minimal:true;managedSelection:true;incrementalRows:false;animateRowChanges:true;animateLatency:true;itemHeight:Theme.dp(44);headerHeight:Theme.tableHeaderHeight;textPixelSize:13
                    sectioned:true;activateOnSingleClick:false
                    sectionDelegate:Component {NodeSourceHeader {record:parent.record}}
                    rowActionsWidth:Theme.dp(88)
                    rowActions:Component {
                        NodeRowActions {
                            record:parent.record
                            editable:!record.sourceId&&engineController.canStart&&!page.nodeSavePending&&!page.nodeDeletePending
                            testable:!engineController.tests.busy&&/^https?:\/\/\S+$/i.test(testUrl.text.trim())
                            onFavoriteRequested:nodes.toggleFavorite(record.id)
                            onDetailsRequested:page.inspectRow(record)
                            onEditRequested:page.edit(record)
                            onTestRequested:engineController.testSelectedNode(record.id,testUrl.text.trim())
                            onCopyRequested:nodes.copySafeInfo(record.id)
                        }
                    }
                    anchors.fill:parent;anchors.margins:Theme.dp(16);externalModel:sections;selectedId:page.focusedId
                    cellPadding:Theme.dp(8)
                    columns:[{key:"name",label:"节点名称",w:235,min:76},{key:"protocol",label:"协议",w:62,min:44},{key:"regionName",label:"地区提示",w:70,min:54},{key:"latency",label:page.rustRequestMetric?"出站 ms":"延迟",w:76,min:52},{key:"status",label:"状态",w:92,min:58}]
                    onRowSelected:function(row){page.selectRow(row)}
                    onRowActivated:function(row,titleItem){page.inspectRow(row)}
                    onSectionActivated:function(key){sections.toggleSection(key)}
                }
                SwirlEmptyState {anchors.centerIn:parent;visible:nodes.count===0;headline:nodes.total?"没有匹配的节点":"没有保存的节点";detail:nodes.total?"调整搜索、协议或地区筛选。":"添加节点，或导入配置、URI 与订阅"}
            }
        }
    }
    SwirlContextMenu {
        id:batchTestMenu;parent:allTestsButton;y:allTestsButton.height+Theme.dp(4);width:Theme.dp(230)
        handleItemsInternally:false
        items:[qsTr("当前筛选结果（%1）").arg(nodes.count),qsTr("全部节点（%1）").arg(nodes.total)]
        onItemTriggered:function(index){if(index===0)engineController.testNodes(sections.nodeIds(),testUrl.text.trim());else engineController.testAllNodes(testUrl.text.trim())}
    }
    Rectangle {objectName:"nodeDetailScrim";anchors.fill:parent;radius:Theme.cardRadius;antialiasing:true;z:10;visible:nodeHero.opened||nodeHero.moving;color:Theme.withAlpha("#000000",0.10*nodeHero.progress)
        MouseArea {anchors.fill:parent;onClicked:page.dismissDetail()}
    }
    Item {
        id:detailViewport;z:12;x:Theme.dp(24);y:Theme.dp(24);width:page.width-Theme.dp(48);height:page.height-Theme.dp(48)
        visible:nodeHero.opened||nodeHero.moving;opacity:nodeHero.progress
        Rectangle {anchors.fill:parent;radius:Theme.cardRadius;color:Theme.surface}
        RowLayout {
            x:Theme.dp(16);y:Theme.dp(10);width:parent.width-Theme.dp(32);height:Theme.dp(36)
            SwirlText {text:"节点详情";textRole:"pageTitle";font.pixelSize:Theme.fontSize(18);color:Theme.text;Layout.fillWidth:true}
            SwirlButton {objectName:"nodeReturnButton";text:"返回节点列表";iconName:"chevron-left";quiet:true;enabled:!page.nodeDeletePending;onClicked:page.dismissDetail()}
        }
        ScrollView {
                id:detailScroll;objectName:"nodeDetailScroll";x:Theme.dp(12);y:Theme.dp(56);width:parent.width-Theme.dp(24);height:parent.height-y-Theme.dp(12);clip:true
                ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {policy:detailScroll.contentHeight>detailScroll.height?ScrollBar.AlwaysOn:ScrollBar.AsNeeded}
                GridLayout {width:detailScroll.availableWidth;columns:width>=Theme.dp(580)?2:1;columnSpacing:Theme.dp(12);rowSpacing:Theme.dp(12)
                Item {
                    id:summarySlot;Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredWidth:1;Layout.alignment:Qt.AlignTop;Layout.preferredHeight:summaryBody.implicitHeight+2*Theme.cardPadding
                    SwirlText {renderType:Text.NativeRendering;anchors.centerIn:parent;visible:!nodeHero.opened&&!nodeHero.moving;text:"选择节点查看详情";color:Theme.muted;font.pixelSize:Theme.fontSize(13)}
                }
                Item {
                    id:requestSlot
                    visible:nodeHero.opened||nodeHero.moving;Layout.fillWidth:true;Layout.minimumWidth:0;Layout.preferredWidth:1;Layout.alignment:Qt.AlignTop;Layout.preferredHeight:requestOptions.implicitHeight+2*Theme.cardPadding
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
                        SwirlText {renderType:Text.NativeRendering;text:qsTr("独立节点测试");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.Medium}
                        SwirlText {renderType:Text.NativeRendering;text:"测试 URL";color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
                        SwirlTextField {id:testUrl;objectName:"nodeTestUrl";Layout.fillWidth:true;text:"https://www.gstatic.com/generate_204";enabled:!engineController.nodeBusy&&!engineController.tests.busy;selectByMouse:true;Accessible.name:"真实请求测试地址"}
                        Rectangle {Layout.fillWidth:true;implicitHeight:Theme.dp(1);color:Theme.border}
                        SwirlText {renderType:Text.NativeRendering;objectName:"nodeRequestState";text:engineController.tests.busy?engineController.tests.message:page.tested.time?(page.tested.success?"独立测试成功（不代表已连接）":"独立测试失败")+" · HTTP "+page.tested.http+" · "+(page.rustRequestMetric?(page.tested.success&&page.tested.outboundConnectMs>=0?"出站建立 "+page.tested.outboundConnectMs+" ms":"无出站耗时结果"):(page.tested.latency>=0?"完整请求 "+page.tested.latency+" ms":"无请求耗时结果"))+(page.tested.error?"\n"+page.tested.error:""):qsTr("尚未测试此节点");color:engineController.tests.busy?Theme.muted:page.tested.time?(page.tested.success?Theme.green:Theme.orange):Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlText {renderType:Text.NativeRendering;text:"出站建立耗时含 DNS 与节点握手；目标 HEAD 请求成功后才记录该值。此项不是 ICMP ping。";visible:page.rustRequestMetric;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlText {renderType:Text.NativeRendering;text:page.tested.error||(page.selectedActive?(engineController.nodeError||engineController.error):"");visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    }
                }
                }
                }
            }
    }
    SwirlDialog {
        id:filtersDialog;objectName:"nodeFiltersDialog";title:"筛选节点";guardChanges:false
        ColumnLayout {width:parent.width;spacing:Theme.dp(12)
            SwirlComboBox {id:protocolFilter;objectName:"proxyRegionCombo";Layout.fillWidth:true;model:["全部协议"].concat(page.protocols);onActivated:page.protocol=currentIndex?page.protocols[currentIndex-1]:"";Accessible.name:"协议"}
            SwirlComboBox {objectName:"nodeCountryFilter";Layout.fillWidth:true;model:["全部地区提示"].concat(page.countries.map(c=>c.name));onActivated:page.countryCode=currentIndex?page.countries[currentIndex-1].code:"";Accessible.name:"订阅名称中的地区提示"}
            SwirlComboBox {Layout.fillWidth:true;model:page.sourceOptions.map(s=>s.name);currentIndex:page.sourceIndex;onActivated:index=>page.selectSource(index);Accessible.name:qsTr("节点来源")}
            SwirlComboBox {Layout.fillWidth:true;model:["全部状态","未测试","测试中","可用","超时","测试失败","正在连接","已连接","连接失败","会话就绪 · 未验证"];onActivated:page.statusFilter=currentIndex?currentText:"";Accessible.name:"状态"}
            SwirlComboBox {Layout.fillWidth:true;model:["不限延迟","低于 100 ms","低于 300 ms","低于 1000 ms"];onActivated:page.maxLatency=[-1,99,299,999][currentIndex];Accessible.name:"延迟"}
            RowLayout {SwirlText {text:"只看实际测试可用";color:Theme.text;Layout.fillWidth:true} SwirlToggle {checked:page.availableOnly||page.groupIndex===1;onToggled:{page.availableOnly=checked;if(!checked&&page.groupIndex===1)page.groupIndex=0}}}
            RowLayout {SwirlText {text:"最近使用";color:Theme.text;Layout.fillWidth:true} SwirlToggle {checked:page.recentOnly;onToggled:{page.recentOnly=checked;if(checked)page.groupIndex=0}}}
            SwirlText {text:nodes.count+" 个匹配节点";color:Theme.muted}
            SwirlButton {text:"完成";onClicked:filtersDialog.close()}
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
            id:summaryBody;objectName:"nodeDetailBody";x:Theme.cardPadding;y:Theme.cardPadding;width:summarySlot.width-2*Theme.cardPadding;spacing:Theme.dp(12)
            SwirlText {
                id:nodeDetailTitle;objectName:"nodeDetailTitle";renderType:Text.NativeRendering
                text:page.selected.id!==undefined?page.selected.name:page.nodeDeletePending||page.nodeDeleteRecovery?qsTr("节点已从配置移除"):qsTr("未选择节点");textFormat:Text.PlainText;color:Theme.text;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(18);font.weight:Font.Medium
                Layout.fillWidth:true;wrapMode:Text.Wrap;activeFocusOnTab:true
                HoverHandler {id:nodeNameHover}
                SwirlToolTip {parent:nodeDetailTitle;visible:page.selected.id!==undefined&&(nodeNameHover.hovered||nodeDetailTitle.activeFocus);text:nodeDetailTitle.text;delay:600}
            }
            SwirlText {objectName:"nodeMutationMessage";Layout.fillWidth:true;visible:page.nodeMutationMessage.length>0||page.nodeDeletePending;text:page.nodeMutationMessage||(page.selected.id===undefined?qsTr("正在确认连接撤销，尚未报告删除成功。"):qsTr("正在保存删除并确认连接撤销…"));textFormat:Text.PlainText;color:page.nodeMutationMessage.length?Theme.orange:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap;Accessible.name:text}
            SwirlButton {objectName:"recoverNodeDelete";text:qsTr("恢复已保存的操作");visible:(page.nodeDeletePending||page.nodeDeleteRecovery)&&engineController.policyApplyState==="reconciling";onClicked:engineController.recoverPolicyConfiguration()}
            ColumnLayout {
                Layout.fillWidth:true;spacing:Theme.dp(10)
                RowLayout {
                    Layout.fillWidth:true;spacing:Theme.dp(8)
                    SwirlStatusBadge {label:page.selected.id!==undefined?page.selected.protocol.toUpperCase():"未选择";tone:"neutral"}
                    SwirlStatusBadge {objectName:"nodeConnectionState";Layout.fillWidth:false;busy:page.selectedActive&&engineController.nodeBusy;label:page.selected.connectionState||"未连接";tone:page.selectedActive?(engineController.nodeError.length?"warning":"accent"):"neutral"}
                }
                SwirlText {renderType:Text.NativeRendering;text:page.selected.id!==undefined?page.selected.address:qsTr("选择一个节点查看信息");textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {objectName:"nodeExecutionState";text:page.selected.id!==undefined?"已导入 · "+(page.selected.nativeExecutable?"可执行":"当前不可执行")+" · "+(page.tested.time?(page.tested.success?"测速成功":"测速失败"):"未测速")+" · "+(page.selected.networkVerified?"当前会话请求已验证":"当前会话联网待验证"):"未选择节点";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {objectName:"nodeDiagnosticReference";text:page.selected.nodeReference?"诊断编号 #"+page.selected.nodeReference:"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {text:qsTr("来源：%1").arg(page.selected.sourceName||((page.sources.find(s=>s.id===page.selected.sourceId)||{}).name)||(page.selected.sourceKind==="legacy"?qsTr("历史未归属"):qsTr("手动添加")));color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {text:"地区："+(page.selected.regionName||"未知")+"（订阅名称提示，未经地理验证）";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(11)}
                SwirlText {renderType:Text.NativeRendering;text:page.selected.id!==undefined?(page.selected.sourceFormat||"手动节点")+" · "+page.selected.capability.engine:"";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selected.id!==undefined?page.selected.normalizationNotes||"":"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selected.id!==undefined?((page.selected.conversionIssues||[]).join("\n")):"";visible:text.length>0;color:Theme.orange;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                SwirlText {renderType:Text.NativeRendering;text:page.selectedActive&&engineController.activeProxyPort>0?"本机入口  127.0.0.1:"+engineController.activeProxyPort:"";visible:text.length>0;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
                GridLayout {
                    Layout.fillWidth:true;columns:2;rowSpacing:Theme.dp(8);columnSpacing:Theme.dp(8)
                    SwirlButton {objectName:"nodePolicyButton";Layout.fillWidth:true;Layout.preferredWidth:1;text:qsTr("前往策略");quiet:true;onClicked:AppState.navigate("policies")}
                    SwirlButton {objectName:"nodeTestButton";text:engineController.tests.busy?"测试中…":"测试请求";Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected.id!==undefined&&!engineController.tests.busy&&/^https?:\/\/\S+$/i.test(testUrl.text.trim());onClicked:engineController.testSelectedNode(page.selectedId,testUrl.text.trim())}
                    SwirlButton {text:page.selected.favorite?"取消收藏":"收藏";Layout.fillWidth:true;enabled:page.selected.id!==undefined;onClicked:nodes.toggleFavorite(page.selectedId)}
                    SwirlButton {text:"复制安全信息";Layout.fillWidth:true;enabled:page.selected.id!==undefined;onClicked:nodes.copySafeInfo(page.selectedId)}
                    SwirlButton {objectName:"nodeEditButton";text:"编辑节点";Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected.id!==undefined&&!page.selected.sourceId&&engineController.canStart;onClicked:page.edit(page.selected)}
                    SwirlButton {objectName:"nodeDeleteButton";text:"删除节点";danger:true;Layout.fillWidth:true;Layout.preferredWidth:1;enabled:page.selected.id!==undefined&&!page.selected.sourceId&&engineController.canStart&&!page.nodeDeletePending;onClicked:page.deleteResource(page.selectedId)}
                }
            }
        }
    }
    SwirlDialog {
        ownerItem:page
        id:addDialog;objectName:"proxyAddDialog";title:page.editingId.length?"编辑代理节点":"添加代理节点"
        dismissBlocked:page.nodeSavePending
        width:Math.min(Theme.dp(890),parent?parent.width-Theme.dp(30):Theme.dp(890));height:Math.min(Theme.dp(713),parent?parent.height-Theme.dp(30):Theme.dp(713))
        onClosed:{nodePassword.text="";nodeUsername.text="";nodeUuid.text="";nodeOptions.text=""}
        ColumnLayout {
            width:parent.width;spacing:Theme.dp(12)
            ScrollView {
                id:form;Layout.fillWidth:true;Layout.preferredHeight:Math.floor(Math.min(Theme.dp(380),page.height*0.6));enabled:!page.nodeSavePending;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                ColumnLayout {
                    width:form.availableWidth;spacing:Theme.dp(10)
                    SwirlText {renderType:Text.NativeRendering;text:"名称";color:Theme.muted}
                    SwirlTextField {id:nodeName;objectName:"nodeNameField";Layout.fillWidth:true;Accessible.name:"节点名称"}
                    SwirlComboBox {id:nodeProtocol;objectName:"nodeProtocolField";enabled:!page.editingJson;Layout.fillWidth:true;model:page.protocols;Accessible.name:"节点协议"}
                    SwirlText {renderType:Text.NativeRendering;text:"服务器";color:Theme.muted}
                    SwirlTextField {id:nodeHost;enabled:!page.editingJson;objectName:"nodeHostField";Layout.fillWidth:true;placeholderText:"域名或 IP";Accessible.name:"节点服务器"}
                    SwirlText {renderType:Text.NativeRendering;text:"端口";color:Theme.muted}
                    SwirlTextField {id:nodePort;enabled:!page.editingJson;objectName:"nodePortField";Layout.fillWidth:true;validator:IntValidator {bottom:1;top:65535}Accessible.name:"节点端口"}
                    SwirlTextField {id:nodeUsername;enabled:!page.editingJson;objectName:"nodeUsernameField";visible:["socks5","http","ssh","mieru","gost-relay","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:page.editingId.length?"用户名留空保留原值":"SOCKS5 用户名（可选）";echoMode:TextInput.Password;Accessible.name:"SOCKS5 用户名"}
                    SwirlTextField {id:nodePassword;enabled:!page.editingJson;objectName:"nodePasswordField";Layout.fillWidth:true;placeholderText:page.editingId.length?"密码留空保留原值":"密码 / 密钥（按协议填写）";echoMode:TextInput.Password;Accessible.name:"节点密码"}
                    RowLayout {visible:page.editingId.length>0;Layout.fillWidth:true
                        SwirlText {renderType:Text.NativeRendering;text:"替换凭据（留空可清除 SOCKS5 认证）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                        SwirlToggle {id:replaceCredentials;enabled:!page.editingJson;objectName:"nodeReplaceCredentials";checked:false}
                    }
                    SwirlComboBox {id:nodeCipher;enabled:!page.editingJson;visible:nodeProtocol.currentIndex===1;Layout.fillWidth:true;editable:true;model:["aes-128-gcm","aes-256-gcm","chacha20-ietf-poly1305","2022-blake3-aes-128-gcm","2022-blake3-aes-256-gcm","2022-blake3-chacha20-poly1305"];Accessible.name:"Shadowsocks 加密方式"}
                    SwirlTextField {id:nodeSni;enabled:!page.editingJson;visible:["trojan","vmess","vless","hysteria","hysteria2","tuic","anytls","masque","trusttunnel"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;placeholderText:"TLS SNI（留空使用服务器）";Accessible.name:"Trojan SNI"}
                    SwirlTextField {id:nodeUuid;enabled:!page.editingJson;visible:["vmess","vless"].indexOf(nodeProtocol.currentText)>=0;Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:page.editingId.length?"UUID 留空保留原值":"UUID";Accessible.name:"节点 UUID"}
                    SwirlText {renderType:Text.NativeRendering;text:"协议扩展选项（JSON，留空保留已保存选项）";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
                    SwirlTextField {id:nodeOptions;enabled:!page.editingJson;objectName:"nodeOptionsField";Layout.fillWidth:true;echoMode:TextInput.Password;placeholderText:'{"network":"ws","ws-opts":{"path":"/"}}';Accessible.name:"协议扩展选项"}
                    SwirlText {renderType:Text.NativeRendering;text:page.editingJson?"JSON 节点可修改显示名称。连接参数与凭据从原配置完整保留；需要更新时请重新导入配置。":"支持 Xray / V2Ray JSON、Clash、Surge、Loon、Quantumult X、sing-box 与 URI。凭据由 Windows DPAPI 保护；未映射参数会保留并阻止执行。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                    SwirlText {renderType:Text.NativeRendering;text:page.nodeMutationMessage||engineController.nodeError;color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap;Layout.fillWidth:true}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton {objectName:"recoverNodeSave";text:qsTr("恢复已保存的操作");visible:page.nodeSavePending&&engineController.policyApplyState==="reconciling";onClicked:engineController.recoverPolicyConfiguration()}
                SwirlButton {text:"取消";enabled:!page.nodeSavePending;onClicked:addDialog.requestDismiss()}
                SwirlButton {objectName:"nodeSaveButton";text:page.nodeSavePending?qsTr("正在保存…"):qsTr("保存");primary:true;enabled:!page.nodeSavePending&&nodeName.text.trim().length>0&&(page.editingJson||nodePort.acceptableInput||["wireguard","tailscale","zerotier","easytier","openvpn"].indexOf(nodeProtocol.currentText)>=0);onClicked:{var input=page.editingJson?{id:page.editingId,name:nodeName.text}:{id:page.editingId,name:nodeName.text,protocol:nodeProtocol.currentText,host:nodeHost.text,port:Number(nodePort.text),username:nodeUsername.text,password:nodePassword.text,replaceCredentials:replaceCredentials.checked,cipher:nodeProtocol.currentText==="ss"?(nodeCipher.editText||nodeCipher.currentText):"",serverName:nodeSni.text};try{if(nodeOptions.text.trim().length)input.options=JSON.parse(nodeOptions.text);if(nodeUuid.text.trim().length){if(!input.options)input.options={};input.options.uuid=nodeUuid.text.trim()}}catch(e){AppState.notice("扩展选项须为合法 JSON 对象");return}page.saveResource(input)}}
            }
        }
    }

    FileDialog {
        parentWindow:page.Window.window;objectName:"settingsNodeFileDialog"
        id:configFile;title:"导入节点配置";nameFilters:["节点配置 (*.yaml *.yml *.json *.conf *.txt)","所有文件 (*)"]
        onAccepted:{importDialog.open();engineController.imports.importNodesOnlyFile(selectedFile)}
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
                SwirlButton {objectName:"importClipboardButton";text:"从剪贴板导入";enabled:!engineController.imports.busy&&!engineController.imports.hasPreview;onClicked:engineController.imports.importNodesOnlyClipboard()}
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
                    SwirlText {width:parent.width;text:modelData.name+" · "+modelData.protocolLabel;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(12);wrapMode:Text.WrapAnywhere}
                    SwirlText {width:parent.width;text:modelData.host+":"+modelData.port+" · "+modelData.capability.engine;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WrapAnywhere}
                    SwirlText {width:parent.width;text:modelData.transportLabel+" · "+modelData.securityLabel+" · "+modelData.parameterLabel;textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WrapAnywhere}
                    SwirlText {width:parent.width;visible:text.length>0;text:modelData.unsupportedReason;textFormat:Text.PlainText;color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.WrapAnywhere}
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
                SwirlButton {text:"关闭";onClicked:importDialog.requestDismiss()}
                SwirlButton {objectName:"importCancelPreviewButton";visible:engineController.imports.hasPreview;text:"取消本次导入";onClicked:engineController.imports.cancelImport()}
                SwirlButton {objectName:"importApplyButton";text:engineController.imports.busy?"正在校验…":engineController.imports.hasPreview?"确认导入":"导入";primary:true;enabled:!engineController.imports.busy&&(engineController.imports.hasPreview||importContent.text.trim().length>0||importAddress.text.trim().length>0);onClicked:{page.importPending=true;if(engineController.imports.hasPreview)engineController.imports.confirmImport();else if(importAddress.text.trim().length)engineController.imports.importNodesOnlyUrl(importAddress.text.trim());else engineController.imports.importNodesOnlyText(importContent.text)}}
            }
            SwirlButton {text:"保存为自动更新订阅";enabled:!engineController.imports.busy;onClicked:{importDialog.close();AppState.navigate("subscriptions")}}
        }
    }
    function clearHiddenFocus() {
        if(!page.detailOpen&&page.focusedId.length&&sections.indexOfNode(page.focusedId)<0)page.focusedId=""
    }
    onDetailOpenChanged:if(!detailOpen)clearHiddenFocus()
    Connections {target:sections;function onChanged(){page.clearHiddenFocus()}}
    Connections {
        target:engineController
        function onPolicyApplyFinished(requestId,success) {page.lastNodeCompletion={requestId:String(requestId),success:success};page.completeNodeMutation(String(requestId),success)}
    }
    Connections {
        target:engineController.imports
        function onNodesApplied() {
            if(!page.importPending)return
            importContent.text="";importAddress.text="";page.importPending=false
        }
        function onChanged() {
            if(!page.importPending||engineController.imports.busy||engineController.imports.hasPreview)return
            page.importPending=false
        }
    }
}
