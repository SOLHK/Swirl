import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string category:"URL Rewrite"
    property var chosen:null
    property var rules:[
        {id:"rw1",category:"URL Rewrite",pattern:"^https://api.example.test/old",action:"Replace URL",status:"Enabled",hits:"37"},
        {id:"rw2",category:"Header Rewrite",pattern:"*.example.test",action:"Set X-Demo",status:"Enabled",hits:"148"},
        {id:"rw3",category:"Body Rewrite",pattern:"/v1/user",action:"JSON mock",status:"Disabled",hits:"0"},
        {id:"rw4",category:"Redirect",pattern:"/v1/legacy",action:"302 Redirect",status:"Enabled",hits:"12"},
        {id:"rw5",category:"Reject",pattern:"/ads/*",action:"Reject request",status:"Enabled",hits:"83"},
        {id:"rw6",category:"Mock Response",pattern:"/api/config",action:"Mock JSON",status:"Enabled",hits:"24"}
    ]
    readonly property var showRows:rules.filter(function(r){
        return r.category===page.category && (r.pattern+" "+r.action).toLowerCase().indexOf(query.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"HTTP REWRITE DEMO"; tone:"accent" }
            Text { text:"Local rule editor · does not intercept traffic"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Import"; onClicked:AppState.notice("Import rewrite rules") }
            SwirlButton { text:"New rewrite"; primary:true; onClicked:editorDialog.open() }
        }
        Flow {
            Layout.fillWidth:true; Layout.preferredHeight:42; spacing:6
            Repeater {
                model:["URL Rewrite","Header Rewrite","Body Rewrite","Redirect","Reject","Mock Response"]
                SwirlButton { text:modelData; quiet:page.category!==modelData; onClicked:{page.category=modelData;page.chosen=null} }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:query; Layout.fillWidth:true; placeholderText:"Filter expressions and actions" }
            SwirlStatusBadge { label:showRows.length+" RULES"; tone:"accent" }
            SwirlButton { text:"Test rule"; onClicked:AppState.notice("Rewrite matching test") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.showRows
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"pattern",label:"MATCH EXPRESSION",w:280},{key:"action",label:"ACTION",w:160},
                             {key:"hits",label:"HITS",w:72},{key:"status",label:"STATE",w:105}]
                    onRowSelected:function(r){page.chosen=r}
                }
                SwirlEmptyState { visible:page.showRows.length===0; anchors.centerIn:parent; headline:"No rewrite rules"; detail:"Add a local fixture" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:323; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:12
                    Text { text:"Rewrite editor"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.pattern:"Select a rule from the list"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WrapAnywhere }
                    Text { text:"MATCH EXPRESSION"; color:Theme.muted; font.pixelSize:10 }
                    SwirlTextField { id:expression; Layout.fillWidth:true; text:page.chosen?page.chosen.pattern:""; placeholderText:"https://example.test/.*" }
                    Text { text:"ACTION"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { id:action; Layout.fillWidth:true; model:["Replace URL","Set Header","Replace Body","302 Redirect","Reject request","Mock JSON"] }
                    Text { text:"RESULT PREVIEW"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:9
                            TextArea {
                                readOnly:true
                                text:"Rule match: "+(page.chosen?page.chosen.hits:"0")+" simulated hits\n"+
                                     "Input: "+(page.chosen?page.chosen.pattern:"—")+"\n"+
                                     "Output: "+(page.chosen?page.chosen.action:"—")+
                                     "\n\nNo outgoing requests are changed."
                                font.family:"Cascadia Code"; font.pixelSize:11
                                color:Theme.text; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { text:"Preview"; onClicked:AppState.notice("Preview "+page.category) }
                        SwirlButton { text:"Apply demo"; primary:true; onClicked:AppState.notice("Apply rewrite") }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:editorDialog; title:"Add rewrite rule"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Match expression"; color:Theme.text }
            SwirlTextField { id:newPattern; Layout.fillWidth:true; placeholderText:"https://example.test/api/.*" }
            Text { text:"Action"; color:Theme.text }
            SwirlComboBox { id:newAction; Layout.fillWidth:true; model:["Replace URL","Set Header","Replace Body","302 Redirect","Reject request","Mock JSON"] }
            Text { text:"Expression is a demo string; no network interception or regex execution occurs."; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:editorDialog.close() }
                SwirlButton {
                    text:"Add demo"; primary:true; enabled:newPattern.text.trim().length>2
                    onClicked:{
                        page.rules=page.rules.concat([{id:"rw"+Date.now(),category:page.category,
                            pattern:newPattern.text.trim(),action:newAction.currentText,status:"Enabled",hits:"0"}])
                        newPattern.text="";editorDialog.close()
                    }
                }
            }
        }
    }
}