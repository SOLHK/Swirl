import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property var selected:null
    property var viewRows:{
        var needle=search.text.toLowerCase()
        var country=region.currentText
        var list=demoProvider.nodes().filter(function(n){
            return n.name.toLowerCase().indexOf(needle)>=0 &&
                   (country==="全部地区"||n.region===country)
        })
        list.sort(function(a,b){
            return sort.currentText==="Latency"?a.latency-b.latency:a.name.localeCompare(b.name)
        })
        return list
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(24); spacing:Theme.dp(15)
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(110)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(18)
                ColumnLayout {
                    Layout.fillWidth:true
                    Text { text:AppState.zh("Active proxy strategy"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    Text { text:AppState.policy; color:Theme.text; font.pixelSize:Theme.fontSize(22); font.weight:Font.DemiBold }
                    Text { text:AppState.zh("当前节点：")+AppState.selectedNode; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                SwirlStatusBadge { label:AppState.zh("节点"); tone:"accent" }
                SwirlButton { text:AppState.zh("全部测试"); iconName:"activity"; onClicked:AppState.notice("延迟测试") }
                SwirlButton { text:AppState.zh("Add node"); primary:true; onClicked:addDialog.open() }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(9)
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Find a node or region") }
            SwirlComboBox { id:region; objectName:"proxyRegionCombo"; model:["全部地区","HK","SG","JP","US","KR","DE","TW","GB","AU"] }
            SwirlComboBox { id:sort; model:["Name","Latency"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.viewRows
                    selectedId:page.selected?page.selected.name:""
                    columns:[
                        {key:"name",label:AppState.zh("PROXY ENDPOINT"),w:240},
                        {key:"region",label:AppState.zh("REGION"),w:93},
                        {key:"protocol",label:AppState.zh("PROTOCOL"),w:122},
                        {key:"latency",label:AppState.zh("LATENCY (ms)"),w:115},
                        {key:"status",label:AppState.zh("HEALTH"),w:132}
                    ]
                    onRowSelected:function(r){page.selected=r;AppState.selectNode(r)}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(280); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(19); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(16)
                    Text { text:AppState.zh("Endpoint inspector"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlIcon { name:"globe"; size:Theme.dp(45); color:Theme.accent; Layout.alignment:Qt.AlignHCenter }
                    Text {
                        Layout.fillWidth:true
                        text:page.selected?page.selected.name:AppState.selectedNode
                        color:Theme.text; font.pixelSize:Theme.fontSize(19); font.weight:Font.DemiBold
                        horizontalAlignment:Text.AlignHCenter; wrapMode:Text.WordWrap
                    }
                    Text { text:AppState.zh("Synthetic node · No connection established"); color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.WordWrap; horizontalAlignment:Text.AlignHCenter }
                    Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                    Text { text:AppState.zh("协议　")+(page.selected?page.selected.protocol:"Trojan"); color:Theme.muted }
                    Text { text:AppState.zh("延迟　")+(page.selected?page.selected.latency:"38")+" 毫秒"; color:Theme.muted }
                    Text { text:AppState.zh("策略　")+AppState.policy; color:Theme.muted }

                        }
                    }

                    SwirlButton { Layout.fillWidth:true; text:AppState.zh("选用"); primary:true; onClicked:AppState.notice("选择节点") }
                    SwirlButton { Layout.fillWidth:true; text:AppState.zh("Edit endpoint"); onClicked:addDialog.open() }

                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; objectName:"proxyAddDialog"
        title:"添加代理节点"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:AppState.zh("Endpoint label"); color:Theme.muted }
            SwirlTextField { id:nodeName; Layout.fillWidth:true; placeholderText:AppState.zh("e.g. Singapore · 03") }
            Text { text:nodeName.text.trim().length===0?"请输入名称":"仅供界面预览，不保存配置"; color:nodeName.text.trim().length===0?Theme.orange:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("取消"); onClicked:addDialog.close() }
                SwirlButton {
                    text:AppState.zh("Save demo"); primary:true; enabled:nodeName.text.trim().length>0
                    onClicked:{AppState.selectNode({name:nodeName.text.trim()});addDialog.close();AppState.notice("保存节点")}
                }
            }
        }
    }
}
