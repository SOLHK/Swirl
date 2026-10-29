import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property bool embedded:false
    readonly property Item motionTitle:heading.titleItem
    readonly property bool compact:width<Theme.dp(620)
    property string selectedId:""
    property var connectionRows:[]
    property bool snapshotDirty:true
    property string protocolFilter:""
    readonly property var selected:connectionRows.find(record=>String(record.id)===selectedId)||null
    readonly property var observedRoute:selected&&selected.route?selected.route:({})
    function observed(value) {return value===undefined||value===null||value===""?qsTr("未提供"):String(value)}
    function nodeLabel(id) {
        if(id==="SWIRL_V2_DIRECT")return "DIRECT"
        if(id==="SWIRL_V2_REJECT")return "REJECT"
        const node=engineController.nodeCatalog.find(item=>item.id===id)
        return node?node.name+"\n"+id:observed(id)
    }
    function groupLabel(id) {const group=(engineController.policyDocument.groups||[]).find(item=>item.id===id);return group?group.name+" ("+id+")":String(id)}
    function serviceLabel(id) {const service=(engineController.policyDocument.service_policies||[]).find(item=>item.id===id);return service?service.name+"\n"+id:observed(id)}
    readonly property var routingDetailRows: {
        if(!selected)return []
        const route=observedRoute
        if(!Object.keys(route).length)return [[qsTr("匹配策略"),observed(selected.policy)],[qsTr("匹配规则"),observed(selected.rule)],[qsTr("最终出站"),observed(selected.outbound)],[qsTr("代理节点"),observed(selected.proxyNode)]]
        const modes={rule:qsTr("规则分流"),global:qsTr("全局代理"),direct:qsTr("直连模式")}
        return [[qsTr("实际模式"),modes[route.mode]||observed(route.mode)],
            [qsTr("命中规则 ID"),observed(route.rule_id)],[qsTr("规则层级"),observed(route.tier)],
            [qsTr("服务策略"),serviceLabel(route.service_policy_id)],
            [qsTr("策略组链"),route.group_chain===undefined?qsTr("未提供"):(route.group_chain.map(id=>page.groupLabel(id)).join(" → ")||qsTr("未使用策略组"))],
            [qsTr("实际节点"),nodeLabel(route.leaf_node_id)],
            [qsTr("节点来源"),observed(route.source_id)],[qsTr("实际目标 IP"),observed(route.chosen_ip)],
            [qsTr("DNS 路径"),observed(route.dns_path)],[qsTr("DNS 配置"),observed(route.dns_profile)],
            [qsTr("分类状态"),observed(route.classification_state)],[qsTr("拒绝原因"),observed(route.rejection_code)],
            [qsTr("出口保持原因"),observed(route.affinity_reason)],[qsTr("配置版本"),observed(route.revision)],[qsTr("运行代次"),observed(route.generation)]]
    }
    readonly property var connectionDetailRows:!selected?[]:[
        [qsTr("连接 ID"),observed(selected.id)],
        [qsTr("域名"),observed(selected.host)],[qsTr("目标"),observed(observedRoute.chosen_ip||selected.ip)],
        [qsTr("目标端口"),observed(selected.port)],
        [qsTr("来源地址"),observed(selected.sourceIp)],[qsTr("来源端口"),observed(selected.sourcePort)],
        [qsTr("应用程序"),observed(selected.process)],[qsTr("协议"),observed(selected.protocol)]].concat(routingDetailRows,[
        [qsTr("连接状态"),observed(selected.status)],
        [qsTr("传输状态"),observed(selected.transportState)],[qsTr("上传"),observed(selected.up)],
        [qsTr("下载"),observed(selected.down)],[qsTr("耗时"),observed(selected.latency)],[qsTr("建立时间"),observed(selected.time)]])
    SwirlTransitionCoordinator {id:detailClock;duration:SwirlMotion.dialogDuration;Component.onCompleted:{destination=AppState.detailOpen?1:0;finish()}}
    Connections {target:AppState;function onDetailOpenChanged(){detailClock.moveTo(AppState.detailOpen?1:0)}}
    readonly property var heroTargets:({activeConnections:activeCount})
    readonly property var motionSurfaces:({activeConnections:connectionSummary})
    readonly property var protocolOptions:[qsTr("全部协议")].concat(Array.from(new Set(connectionRows.map(row=>row.protocol||"").concat([protocolFilter]).filter(value=>value.length))).sort())
    function refreshSnapshot() {
        if(!visible)return
        connectionRows=engineController.connections
        snapshotDirty=false
    }
    onVisibleChanged:if(visible)refreshSnapshot()
    Component.onCompleted:refreshSnapshot()
    Connections {target:engineController.telemetry;function onChanged(){page.snapshotDirty=true}}
    Timer {interval:300;running:page.visible&&page.snapshotDirty;repeat:true;onTriggered:page.refreshSnapshot()}
    function latencyValue(record) {
        const value=String(record.latency||"")
        return /^\d+(\.\d+)?( ms)?$/.test(value)?parseFloat(value):Number.POSITIVE_INFINITY
    }
    property var visibleRows:{
        const q=search.text.trim().toLowerCase()
        const state=status.currentIndex
        const selectedProtocol=protocolFilter
        var rows=connectionRows.filter(function(r){
            const route=r.route||{}
            const searchable=[r.host,r.process,r.ip,r.port,r.sourceIp,r.sourcePort,r.protocol,r.status,r.transportState,r.policy,r.proxyNode,route.rule_id,route.service_policy_id,route.chosen_ip]
                .map(value=>value===undefined||value===null?"":String(value)).join(" ").toLowerCase()
            return searchable.indexOf(q)>=0 &&
                   (state===0||r.status===status.currentText) &&
                   (!selectedProtocol||r.protocol===selectedProtocol)
        })
        rows.sort(function(a,b){
            let order=0
            if(sort.currentIndex===1) {
                const av=page.latencyValue(a),bv=page.latencyValue(b)
                order=av===bv?0:av<bv?-1:1
            } else if(sort.currentIndex===2||sort.currentIndex===4) {
                const key=sort.currentIndex===2?"downloadBytes":"uploadBytes"
                order=Number(b[key]||0)-Number(a[key]||0)
            } else if(sort.currentIndex===5) order=Number(b.lastSeen||0)-Number(a.lastSeen||0)
            else {
                const key=sort.currentIndex===0?"host":"process"
                order=String(a[key]||"").localeCompare(String(b[key]||""),undefined,{numeric:true})
            }
            return order||String(a.id).localeCompare(String(b.id),undefined,{numeric:true})
        })
        return rows
    }
    ColumnLayout {
        anchors.fill:parent;anchors.margins:page.embedded?0:Theme.pagePadding;spacing:Theme.dp(16)
        Item {id:connectionSummary;visible:!page.embedded;property color color:Theme.material("content");Layout.fillWidth:true;implicitHeight:heading.implicitHeight
            SwirlPageHeader {id:heading;anchors.left:parent.left;anchors.right:parent.right;title:qsTr("活动连接");description:qsTr("查看连接与它实际命中的策略、节点和配置版本。")
                SwirlText {id:activeCount;textRole:"data";text:engineController.telemetry.connectionsSampled?String(engineController.telemetry.activeConnections):"—";color:Theme.text;font.pixelSize:Theme.fontSize(30);font.weight:Font.DemiBold}
                SwirlButton {text:qsTr("返回");visible:SwirlMotion.returnShared&&SwirlMotion.returnShared.route===AppState.currentPage;onClicked:SwirlMotion.returnToHub(activeCount)}
            }
        }
        SwirlSearchField {id:search;objectName:"activityConnectionSearch";Layout.fillWidth:true;text:AppState.connectionSearchQuery;placeholderText:qsTr("搜索进程、目标地址、来源、协议或策略");onTextEdited:AppState.connectionSearchQuery=text}
        GridLayout {Layout.fillWidth:true;columns:width<Theme.dp(570)?2:5;columnSpacing:Theme.compactGap;rowSpacing:Theme.compactGap
                SwirlComboBox {id:status;objectName:"activityConnectionStatus";Layout.fillWidth:true;model:[qsTr("全部状态"),qsTr("活动"),qsTr("已结束"),qsTr("采样中断")];Accessible.name:qsTr("连接状态筛选")}
                SwirlComboBox {id:protocol;objectName:"activityConnectionProtocol";Layout.fillWidth:true;model:page.protocolOptions;currentIndex:page.protocolFilter.length?model.indexOf(page.protocolFilter):0;onActivated:page.protocolFilter=currentIndex>0?currentText:"";Accessible.name:qsTr("连接协议筛选")}
                SwirlComboBox {id:sort;objectName:"activityConnectionSort";Layout.fillWidth:true;model:[qsTr("域名"),qsTr("耗时从短到长"),qsTr("下载从多到少"),qsTr("进程"),qsTr("上传从多到少"),qsTr("最近采集")];Accessible.name:qsTr("连接排序")}
                SwirlButton {development:true;enabled:false;text:qsTr("导出");iconName:"folder";onClicked:AppState.notice("导出连接记录")}
                SwirlButton {development:true;enabled:false;text:qsTr("清空");onClicked:{page.selectedId="";AppState.notice("清空连接记录")}}
        }
        RowLayout {Layout.fillWidth:true
            SwirlText {text:qsTr("%1 条记录").arg(page.visibleRows.length);color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
            SwirlButton {text:AppState.detailOpen?qsTr("隐藏详情"):qsTr("显示详情");enabled:page.selected!==null;quiet:true;onClicked:AppState.detailOpen=!AppState.detailOpen}
        }
        GridLayout {Layout.fillWidth:true;Layout.fillHeight:true;columns:page.compact?1:2;columnSpacing:Theme.sectionGap;rowSpacing:Theme.sectionGap
            Item {Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:Theme.dp(100)
                SwirlDataTable {id:connectionTable;objectName:"connectionTable";anchors.fill:parent;incrementalRows:true;animateRowChanges:false;rows:page.visibleRows;selectedId:page.selected?page.selected.id:"";minimal:true
                    columns:[{key:"host",label:qsTr("域名"),w:220},{key:"ip",label:qsTr("IP 地址"),w:125},{key:"process",label:qsTr("进程"),w:115},{key:"protocol",label:qsTr("协议"),w:80},{key:"policy",label:qsTr("策略"),w:119},{key:"up",label:qsTr("上传"),w:89},{key:"down",label:qsTr("下载"),w:100},{key:"latency",label:qsTr("耗时"),w:95},{key:"time",label:qsTr("建立时间"),w:108},{key:"status",label:qsTr("状态"),w:88}]
                    onRowSelected:function(record){page.selectedId=String(record.id);AppState.detailOpen=true;connectionDetail.present(connectionTable.selectedItem)}
                }
                SwirlEmptyState {visible:page.visibleRows.length===0;anchors.centerIn:parent;width:Math.max(0,parent.width-Theme.dp(24));headline:qsTr("没有匹配的连接");detail:qsTr("连接经过 Swirl 后会显示在这里，也可调整搜索或状态筛选。")}
            }
            SwirlLinkedDetail {id:connectionDetail;animationLayer:page;sourceViewport:connectionTable;detailOpen:AppState.detailOpen&&page.selected!==null;visible:detailOpen||moving;enabled:detailOpen;Layout.preferredWidth:page.compact?1:Theme.dp(300);Layout.fillWidth:page.compact;Layout.fillHeight:!page.compact;Layout.preferredHeight:page.compact?Theme.dp(180):-1
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(15)
                    SwirlText { text:AppState.zh("Connection details"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selected?page.selected.status.toUpperCase():"尚未选择"; tone:page.selected&&page.selected.status==="活动"?"success":"neutral" }
                    Repeater {
                        model:page.connectionDetailRows
                        ColumnLayout {
                            id:detailField
                            required property var modelData
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            SwirlText { text:AppState.zh(detailField.modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            SwirlText { text:String(detailField.modelData[1]);textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(13);wrapMode:Text.WrapAnywhere;Layout.fillWidth:true }
                        }
                    }

                        }
                    }

                    SwirlButton { development:true; enabled:false; Layout.fillWidth:true; text:AppState.zh("Terminate connection"); danger:true
                        onClicked:AppState.notice("Terminate connection")
                    }

                }
            }
        }
    }
}
