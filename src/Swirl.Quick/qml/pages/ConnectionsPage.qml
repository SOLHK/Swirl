import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string selectedId:""
    readonly property var selected:engineController.connections.find(record=>String(record.id)===selectedId)||null
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
        [qsTr("域名"),observed(selected.host)],[qsTr("目标"),observed(observedRoute.chosen_ip||selected.ip)],
        [qsTr("应用程序"),observed(selected.process)],[qsTr("协议"),observed(selected.protocol)]].concat(routingDetailRows,[
        [qsTr("传输状态"),observed(selected.transportState)],[qsTr("上传"),observed(selected.up)],
        [qsTr("下载"),observed(selected.down)],[qsTr("耗时"),observed(selected.latency)],[qsTr("建立时间"),observed(selected.time)]])
    SwirlTransitionCoordinator {id:detailClock;duration:SwirlMotion.dialogDuration;Component.onCompleted:{destination=AppState.detailOpen?1:0;finish()}}
    Connections {target:AppState;function onDetailOpenChanged(){detailClock.moveTo(AppState.detailOpen?1:0)}}
    readonly property var heroTargets:({activeConnections:activeCount})
    readonly property var motionSurfaces:({activeConnections:connectionSummary})
    property var visibleRows:{
        if(!visible)return []
        var q=search.text.toLowerCase()
        var s=sort.currentText
        var state=status.currentText
        var rows=engineController.connections.filter(function(r){
            return (r.host+" "+r.process+" "+r.ip+" "+r.policy+" "+(r.route?String(r.route.rule_id||"")+" "+String(r.route.service_policy_id||"")+" "+String(r.route.chosen_ip||""):"")).toLowerCase().indexOf(q)>=0 &&
                   (state==="全部状态"||r.status===state)
        })
        rows.sort(function(a,b){
            var key=s==="域名"?"host":s==="延迟"?"latency":s==="下载"?"down":"process"
            return String(a[key]).localeCompare(String(b[key]),undefined,{numeric:true})
        })
        return rows
    }
    ColumnLayout {
        anchors.fill:parent
        anchors.leftMargin:Theme.dp(23); anchors.rightMargin:Theme.dp(23); anchors.bottomMargin:Theme.dp(14)
        spacing:Theme.dp(14)
        SwirlGlassPanel {id:connectionSummary;Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(72)
         RowLayout {anchors.fill:parent;anchors.margins:Theme.dp(16);SwirlText {textRole:"pageTitle";text:"活动连接";color:Theme.text;font.pixelSize:Theme.fontSize(22);Layout.fillWidth:true}SwirlText {textRole:"data";id:activeCount;text:engineController.telemetry.connectionsSampled?String(engineController.telemetry.activeConnections):"—";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold}SwirlButton {text:"返回";visible:SwirlMotion.returnShared && SwirlMotion.returnShared.route===AppState.currentPage;onClicked:SwirlMotion.returnToHub(activeCount)}}
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(10)
            SwirlSearchField { id:search; Layout.fillWidth:true; text:AppState.connectionSearchQuery; placeholderText:AppState.zh("搜索域名、IP、进程或策略"); onTextEdited:AppState.connectionSearchQuery=text }
            SwirlComboBox { id:status; model:["全部状态","活动","已结束"] }
            SwirlComboBox { id:sort; model:["域名","延迟","下载","进程"] }
            SwirlButton { development:true; enabled:false; text:AppState.zh("导出"); iconName:"folder"; onClicked:AppState.notice("导出连接记录") }
            SwirlButton { development:true; enabled:false; text:AppState.zh("Clear"); onClicked:{page.selectedId="";AppState.notice("清空连接记录")} }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(8)
            SwirlStatusBadge { label:visibleRows.length+" 条记录"; tone:"accent" }
            SwirlText { text:AppState.zh("Click a row to examine a connection"); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { text:AppState.detailOpen?"隐藏详情":"显示详情"; quiet:false; onClicked:AppState.detailOpen=!AppState.detailOpen }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                clip:true
                SwirlDataTable {
                    id:connectionTable;anchors.fill:parent; anchors.margins:Theme.dp(1)
                    incrementalRows:true;animateRowChanges:false;rows:page.visibleRows
                    selectedId:page.selected?page.selected.id:""
                    columns:[
                        {key:"host",label:AppState.zh("HOST"),w:220},{key:"ip",label:AppState.zh("IP ADDRESS"),w:125},
                        {key:"process",label:AppState.zh("PROCESS"),w:115},{key:"protocol",label:AppState.zh("PROTO"),w:80},
                        {key:"policy",label:AppState.zh("POLICY"),w:119},{key:"up",label:AppState.zh("UPLOAD"),w:89},
                        {key:"down",label:AppState.zh("DOWNLOAD"),w:100},{key:"latency",label:AppState.zh("LATENCY"),w:95},
                        {key:"time",label:AppState.zh("SINCE"),w:88},{key:"status",label:AppState.zh("状态"),w:88}
                    ]
                    onRowSelected:function(record){page.selectedId=String(record.id);AppState.detailOpen=true;connectionDetail.present(connectionTable.selectedItem)}
                }
                SwirlEmptyState {
                    visible:page.visibleRows.length===0
                    anchors.centerIn:parent
                    headline:AppState.zh("没有匹配的连接")
                    detail:AppState.zh("Adjust the search or status filter")
                }
            }
            SwirlLinkedDetail {
                id:connectionDetail;animationLayer:page;sourceViewport:connectionTable;detailOpen:AppState.detailOpen
                visible:AppState.detailOpen||moving
                enabled:AppState.detailOpen
                Layout.preferredWidth:Theme.dp(290); Layout.fillHeight:true
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
