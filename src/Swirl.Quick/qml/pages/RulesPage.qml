import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property var selectedRule:null
    property var rules:[
        {id:"001",order:"001",type:"DOMAIN-SUFFIX",pattern:"example.test",policy:"Auto Select",enabled:"Enabled",hits:"148"},
        {id:"002",order:"002",type:"DOMAIN-KEYWORD",pattern:"updates",policy:"DIRECT",enabled:"Enabled",hits:"92"},
        {id:"003",order:"003",type:"IP-CIDR",pattern:"203.0.113.0/24",policy:"Global / SG",enabled:"Enabled",hits:"31"},
        {id:"004",order:"004",type:"PROCESS-NAME",pattern:"Browser.exe",policy:"DIRECT",enabled:"Disabled",hits:"0"},
        {id:"005",order:"005",type:"FINAL",pattern:"MATCH",policy:"Auto Select",enabled:"Enabled",hits:"468"}
    ]
    readonly property var displayRules:rules.filter(function(r){
        return (r.type+" "+r.pattern+" "+r.policy).toLowerCase().indexOf(search.text.toLowerCase())>=0 &&
               (policyFilter.currentText==="All policies"||r.policy===policyFilter.currentText)
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("ORDERED DEMO RULESET"); tone:"accent" }
            Text { text:AppState.zh("Priority is evaluated top to bottom in this preview."); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Test rule"); iconName:"activity"; onClicked:testDialog.open() }
            SwirlButton { text:AppState.zh("New rule"); primary:true; onClicked:editorDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search pattern, type or target strategy") }
            SwirlComboBox { id:policyFilter; model:["All policies","Auto Select","DIRECT","Global / SG","REJECT"] }
            SwirlButton { text:AppState.zh("Import"); onClicked:AppState.notice("Import rules") }
            SwirlButton { text:AppState.zh("Export"); onClicked:AppState.notice("Export rules") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
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
                Layout.preferredWidth:310; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:13
                    Text { text:AppState.zh("Rule inspection"); color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:page.selectedRule?page.selectedRule.enabled:"SELECT A RULE"; tone:"accent" }
                    Repeater {
                        model:[
                            ["PRIORITY",page.selectedRule?page.selectedRule.order:"—"],
                            ["MATCHER",page.selectedRule?page.selectedRule.type:"—"],
                            ["PATTERN",page.selectedRule?page.selectedRule.pattern:"—"],
                            ["STRATEGY",page.selectedRule?page.selectedRule.policy:"—"],
                            ["SIMULATED MATCHES",page.selectedRule?page.selectedRule.hits:"—"]
                        ]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:4
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:AppState.zh("Enable rule"); color:Theme.text; Layout.fillWidth:true }
                        SwirlToggle {
                            checked:page.selectedRule&&page.selectedRule.enabled==="Enabled"
                            onToggled:{
                                if(page.selectedRule) {
                                    var arr=page.rules.map(function(r){return r.id===page.selectedRule.id?
                                        {id:r.id,order:r.order,type:r.type,pattern:r.pattern,policy:r.policy,
                                         enabled:checked?"Enabled":"Disabled",hits:r.hits}:r})
                                    page.rules=arr
                                    page.selectedRule=arr.filter(function(r){return r.id===page.selectedRule.id})[0]
                                }
                            }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:AppState.zh("Edit selected"); onClicked:editorDialog.open() }
                    SwirlButton { text:AppState.zh("View match details"); quiet:true; onClicked:AppState.notice("Rule hit details") }
                }
            }
        }
    }
    SwirlDialog {
        id:editorDialog; title:"Rule editor"
        ColumnLayout {
            width:parent.width; spacing:13
            Text { text:AppState.zh("Rule type"); color:Theme.text }
            SwirlComboBox { id:typeInput; Layout.fillWidth:true; model:["DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","PROCESS-NAME","FINAL"] }
            Text { text:AppState.zh("Match pattern"); color:Theme.text }
            SwirlTextField { id:patternInput; Layout.fillWidth:true; placeholderText:AppState.zh("example.test") }
            Text { text:AppState.zh("Target policy"); color:Theme.text }
            SwirlComboBox { id:policyInput; Layout.fillWidth:true; model:["Auto Select","DIRECT","Global / SG","REJECT"] }
            Text { text:AppState.zh("Changes are local to the UI; no routing rules are installed."); color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; wrapMode:Text.Wrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Cancel"); onClicked:editorDialog.close() }
                SwirlButton {
                    text:AppState.zh("Add demo rule"); primary:true
                    enabled:patternInput.text.trim().length>0
                    onClicked:{
                        var n=page.rules.length+1
                        page.rules=page.rules.concat([{id:"R"+n,order:String(n).padStart(3,"0"),
                            type:typeInput.currentText,pattern:patternInput.text.trim(),
                            policy:policyInput.currentText,enabled:"Enabled",hits:"0"}])
                        patternInput.text=""
                        editorDialog.close()
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:testDialog; title:"Rule matching test"
        ColumnLayout {
            width:parent.width; spacing:13
            Text { text:AppState.zh("Host or IP to evaluate"); color:Theme.text }
            SwirlTextField { id:testInput; Layout.fillWidth:true; placeholderText:AppState.zh("api.example.test") }
            Rectangle {
                Layout.fillWidth:true; implicitHeight:68; radius:9; color:Theme.field
                Text {
                    anchors.fill:parent; anchors.margins:12
                    text:AppState.zh("Demo evaluator only.\nNo real DNS lookup or proxy routing occurs.")
                    color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Close"); onClicked:testDialog.close() }
                SwirlButton {
                    text:AppState.zh("Evaluate"); primary:true; enabled:testInput.text.trim().length>0
                    onClicked:{
                        var match=page.rules.find(function(r){return r.type==="DOMAIN-SUFFIX" && testInput.text.endsWith(r.pattern)})
                        AppState.notice("Test match: "+(match?match.policy:"FINAL · Auto Select"))
                        testDialog.close()
                    }
                }
            }
        }
    }
}