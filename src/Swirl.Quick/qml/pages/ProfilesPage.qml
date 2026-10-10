import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"Configurations"
    property string currentProfile:"Default"
    property var profiles:[
        {id:"p1",name:"Default",source:"Local · default.yaml",version:"v1.4",updated:"Today",state:"Active"},
        {id:"p2",name:"Travel",source:"Local · travel.yaml",version:"v1.2",updated:"Oct 8",state:"Available"},
        {id:"p3",name:"Office",source:"Remote · example.test",version:"v2.1",updated:"Oct 6",state:"Available"},
        {id:"p4",name:"Minimal",source:"Local · minimal.yaml",version:"v1.0",updated:"Sep 20",state:"Available"}
    ]
    property string editorText:"# Swirl local configuration example\n# Preview-only: no Mihomo profile is loaded.\n\nmode: rule\nlog-level: info\n\nproxy-groups:\n  - name: Auto Select\n    type: select\n\nrules:\n  - MATCH,Auto Select\n"
    readonly property var visibleProfiles:profiles.filter(function(r){return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"CONFIGURATION DEMO"; tone:"accent" }
            Text { text:"Synthetic configuration records only. Existing YAML and subscription data are never read or overwritten."; Layout.fillWidth:true; color:Theme.muted; font.pixelSize:12 }
            SwirlButton { text:"Import"; onClicked:AppState.notice("Configuration import") }
            SwirlButton { text:"New profile"; primary:true; onClicked:addDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:110
            RowLayout {
                anchors.fill:parent; anchors.margins:19; spacing:18
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:"CURRENT PREVIEW CONFIGURATION"; color:Theme.muted; font.pixelSize:11; font.letterSpacing:1.1 }
                    Text { text:page.currentProfile; color:Theme.text; font.pixelSize:23; font.weight:Font.DemiBold }
                    Text { text:"Manual selection · no network engine initialized"; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlStatusBadge { label:"LOCAL FIXTURE"; tone:"success" }
                SwirlButton { text:"Validate"; onClicked:AppState.notice("Validate config") }
                SwirlButton { text:"Export demo"; onClicked:AppState.notice("Export configuration") }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:["Configurations","Editor","Version history","Backups"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"Update remote"; onClicked:AppState.notice("Update remote profile") }
        }
        RowLayout {
            visible:page.tab==="Configurations"; Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Search profiles and sources" }
            SwirlComboBox { model:["All sources","Local","Remote"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Configurations"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.visibleProfiles
                    columns:[{key:"name",label:"PROFILE NAME",w:187},{key:"source",label:"SOURCE",w:240},
                             {key:"version",label:"VERSION",w:100},{key:"updated",label:"UPDATED",w:105},
                             {key:"state",label:"STATE",w:112}]
                    onRowSelected:function(r){page.currentProfile=r.name}
                }
                ColumnLayout {
                    visible:page.tab==="Editor"
                    anchors.fill:parent; anchors.margins:16; spacing:10
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:page.currentProfile+".yaml"; color:Theme.text; font.pixelSize:14; font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SwirlStatusBadge { label:"UNSAVED DEMO CONTENT"; tone:"warning" }
                    }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        TextArea {
                            id:editor
                            text:page.editorText
                            font.family:"Cascadia Code"; font.pixelSize:12; color:Theme.text
                            wrapMode:TextEdit.NoWrap; selectByMouse:true
                            background:Rectangle { color:Theme.field; radius:10; border.color:Theme.border }
                        }
                    }
                    SwirlButton { text:"Save preview"; onClicked:{page.editorText=editor.text;AppState.notice("Save local editor preview")} }
                }
                ColumnLayout {
                    visible:page.tab==="Version history"||page.tab==="Backups"
                    anchors.fill:parent; anchors.margins:18; spacing:16
                    Text { text:page.tab; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="Version history"?
                            ["v1.4  ·  Today  ·  Enabled rule changes","v1.3  ·  Oct 8  ·  Update endpoint strategy",
                             "v1.2  ·  Oct 4  ·  Updated DNS","v1.1  ·  Sep 29  ·  Created configuration"]:
                            ["Backup snapshot  ·  Oct 8","Backup snapshot  ·  Oct 1","Backup snapshot  ·  Sep 25"]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"folder"; color:Theme.muted; size:18 }
                            Text { text:modelData; color:Theme.text; Layout.fillWidth:true; font.pixelSize:12 }
                            SwirlButton { text:"Compare"; onClicked:AppState.notice("Compare profile versions") }
                            SwirlButton { text:"Restore"; onClicked:AppState.notice("Restore profile preview") }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:284; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:13
                    Text { text:"Profile summary"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Repeater {
                        model:[["SELECTED",page.currentProfile],["FORMAT","Clash / Mihomo YAML"],
                               ["POLICY GROUPS","4 (sample)"],["PROXY NODES","18 (sample)"],
                               ["RULES","253 (sample)"],["SOURCE","Local preview only"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:3
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Use profile in UI"; primary:true; onClicked:AppState.notice("Select "+page.currentProfile) }
                    SwirlButton { text:"View editor"; onClicked:page.tab="Editor" }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"Create configuration preview"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Name"; color:Theme.text }
            SwirlTextField { id:profileName; Layout.fillWidth:true; placeholderText:"New profile name" }
            SwirlComboBox { id:source; Layout.fillWidth:true; model:["Local","Remote"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"Add demo"; primary:true; enabled:profileName.text.trim().length>0
                    onClicked:{
                        page.profiles=page.profiles.concat([{id:"p"+Date.now(),name:profileName.text.trim(),
                            source:source.currentText+" · preview",version:"v0.1",updated:"Now",state:"Available"}])
                        profileName.text="";addDialog.close()
                    }
                }
            }
        }
    }
}