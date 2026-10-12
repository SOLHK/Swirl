import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:true
    property var selectedRule:null
    readonly property var rules:engineController.routingRules
    readonly property var displayRules:rules.filter(function(r){
        return (r.type+" "+r.pattern+" "+r.policy).toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
               (policyFilter.currentText==="全部策略"||r.policy===policyFilter.currentText)
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.mode+"模式"; tone:"accent" }
            Text { text:"私有地址直连 → 国外关键域名代理 → 国内域名/IP 直连 → 其余走所选节点。"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("测试规则"); iconName:"activity"; onClicked:testDialog.open() }
            SwirlButton { enabled:false; text:AppState.zh("New rule"); primary:true; onClicked:editorDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search pattern, type or target strategy") }
            SwirlComboBox { id:policyFilter; model:["全部策略","DIRECT","SWIRL"] }
            SwirlButton { enabled:false; text:AppState.zh("Import"); onClicked:AppState.notice("导入规则") }
            SwirlButton { enabled:false; text:AppState.zh("Export"); onClicked:AppState.notice("导出规则") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.displayRules; selectedId:page.selectedRule?page.selectedRule.id:""
                    columns:[{key:"order",label:AppState.zh("PRIORITY"),w:82},{key:"type",label:AppState.zh("TYPE"),w:170},
                             {key:"pattern",label:AppState.zh("MATCH PATTERN"),w:208},{key:"policy",label:AppState.zh("POLICY"),w:126},
                             {key:"hits",label:AppState.zh("HITS"),w:77},{key:"enabled",label:AppState.zh("STATE"),w:100}]
                    onRowSelected:function(r){page.selectedRule=r}
                }
                SwirlEmptyState {
                    visible:page.displayRules.length===0; anchors.centerIn:parent
                    headline:AppState.zh("No matching rules")
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(310); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(13)
                    Text { text:AppState.zh("Rule inspection"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selectedRule?page.selectedRule.enabled:"请选择规则"; tone:"accent" }
                    Repeater {
                        model:[
                            ["PRIORITY",page.selectedRule?page.selectedRule.order:"—"],
                            ["MATCHER",page.selectedRule?page.selectedRule.type:"—"],
                            ["PATTERN",page.selectedRule?page.selectedRule.pattern:"—"],
                            ["STRATEGY",page.selectedRule?page.selectedRule.policy:"—"],
                            ["命中次数",page.selectedRule?page.selectedRule.hits:"—"]
                        ]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(4)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:AppState.zh("Enable rule"); color:Theme.text; Layout.fillWidth:true }
                        SwirlToggle { enabled:false;checked:false;

                            onToggled:{
                                if(page.selectedRule) {
                                    var arr=page.rules.map(function(r){return r.id===page.selectedRule.id?
                                        {id:r.id,order:r.order,type:r.type,pattern:r.pattern,policy:r.policy,
                                         }:r})
                                    page.rules=arr
                                    page.selectedRule=arr.filter(function(r){return r.id===page.selectedRule.id})[0]
                                }
                            }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("Edit selected"); onClicked:editorDialog.open() }
                    SwirlButton { enabled:false; text:AppState.zh("View match details"); quiet:false; onClicked:AppState.notice("规则命中详情") }

                }
            }
        }
    }
    SwirlDialog {
        id:editorDialog; title:"规则编辑器"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(13)
            Text { text:AppState.zh("Rule type"); color:Theme.text }
            SwirlComboBox { id:typeInput; Layout.fillWidth:true; model:["DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","PROCESS-NAME","FINAL"] }
            Text { text:AppState.zh("Match pattern"); color:Theme.text }
            SwirlTextField { id:patternInput; Layout.fillWidth:true; placeholderText:AppState.zh("example.test") }
            Text { text:AppState.zh("Target policy"); color:Theme.text }
            SwirlComboBox { id:policyInput; Layout.fillWidth:true; model:["自动选择","DIRECT","全局 / 新加坡","REJECT"] }
            Text { text:AppState.zh("Changes are local to the UI; no routing rules are installed."); color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.Wrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("Cancel"); onClicked:editorDialog.close() }
                SwirlButton { enabled:false;
                    text:"尚未实现"; primary:true

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
    SwirlDialog {
        id:testDialog; title:"规则匹配测试"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(13)
            Text { text:AppState.zh("Host or IP to evaluate"); color:Theme.text }
            SwirlTextField { id:testInput; Layout.fillWidth:true; placeholderText:AppState.zh("api.example.test") }
            Rectangle {
                Layout.fillWidth:true; implicitHeight:Theme.dp(68); radius:Theme.roundedRadius(width,height); color:Theme.field
                Text {
                    anchors.fill:parent; anchors.margins:Theme.dp(12)
                    text:AppState.zh("Demo evaluator only.\nNo real DNS lookup or proxy routing occurs.")
                    color:Theme.muted; font.pixelSize:Theme.fontSize(12); wrapMode:Text.WordWrap
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("Close"); onClicked:testDialog.close() }
                SwirlButton { enabled:false;
                    text:AppState.zh("Evaluate"); primary:true;
                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
