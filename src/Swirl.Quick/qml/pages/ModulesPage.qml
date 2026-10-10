import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"Installed"
    property var chosen:null
    property var modules:[
        {id:"mod1",name:"Privacy Rules",author:"Local fixture",version:"1.4.2",state:"Enabled",source:"Local module",update:"Current"},
        {id:"mod2",name:"Header Utilities",author:"Local fixture",version:"2.0.1",state:"Enabled",source:"Local module",update:"Update available"},
        {id:"mod3",name:"Device Monitor",author:"Local fixture",version:"0.9.0",state:"Disabled",source:"Remote (sample)",update:"Current"},
        {id:"mod4",name:"Request Tools",author:"Local fixture",version:"1.0.3",state:"Disabled",source:"Remote (sample)",update:"Current"}
    ]
    readonly property var filtered:modules.filter(function(m){return (m.name+" "+m.author).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"EXTENSION CATALOG · DEMO"; tone:"accent" }
            Text { text:"No third-party scripts or extensions are loaded."; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Import local"; onClicked:importDialog.open() }
            SwirlButton { text:"Add remote"; primary:true; onClicked:importDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["Installed","Marketplace","Updates"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlSearchField { id:search; implicitWidth:250; placeholderText:"Search extensions" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Installed"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.filtered
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"name",label:"MODULE NAME",w:220},{key:"version",label:"VERSION",w:102},
                             {key:"source",label:"SOURCE",w:172},{key:"update",label:"UPDATES",w:153},
                             {key:"state",label:"STATE",w:110}]
                    onRowSelected:function(r){page.chosen=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Installed"
                    anchors.fill:parent; anchors.margins:19; spacing:16
                    Text { text:page.tab==="Marketplace"?"Module marketplace (visual preview)":"Module updates"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="Marketplace"?["Rule helper · sample","DNS tools · sample","Telemetry visualizer · sample"]:
                            ["Header Utilities · v2.1 available (sample)","No other available updates"]
                        SwirlGlassPanel {
                            Layout.fillWidth:true; Layout.preferredHeight:66
                            RowLayout {
                                anchors.fill:parent; anchors.margins:12
                                SwirlIcon { name:"grid"; color:Theme.accent; size:22 }
                                Text { text:modelData; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true }
                                SwirlButton { text:page.tab==="Marketplace"?"View":"Details"; onClicked:AppState.notice("Extension listing") }
                            }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:305; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:"Extension inspector"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.name:"Select a module"; color:Theme.accent; font.pixelSize:16; font.weight:Font.DemiBold; wrapMode:Text.WordWrap; Layout.fillWidth:true }
                    Repeater {
                        model:[["VERSION",page.chosen?page.chosen.version:"—"],["AUTHOR",page.chosen?page.chosen.author:"—"],
                               ["SOURCE",page.chosen?page.chosen.source:"—"],["UPDATE",page.chosen?page.chosen.update:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:4
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:12 }
                        }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"Enable extension (preview)"; color:Theme.text; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                        SwirlToggle {
                            checked:page.chosen&&page.chosen.state==="Enabled"
                            onToggled:if(page.chosen){
                                var id=page.chosen.id
                                page.modules=page.modules.map(function(m){return m.id===id?
                                    {id:m.id,name:m.name,author:m.author,version:m.version,state:checked?"Enabled":"Disabled",source:m.source,update:m.update}:m})
                                page.chosen=page.modules.find(function(m){return m.id===id})
                            }
                        }
                    }
                    Text { text:"Parameters"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"Module-specific parameter" }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Save local parameters"; onClicked:AppState.notice("Save extension parameters") }
                    SwirlButton { text:"Check for updates"; onClicked:AppState.notice("Check extension updates") }
                }
            }
        }
    }
    SwirlDialog {
        id:importDialog; title:"Import extension"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Module name"; color:Theme.text }
            SwirlTextField { id:moduleName; Layout.fillWidth:true; placeholderText:"My extension" }
            Text { text:"Source URL (optional)"; color:Theme.text }
            SwirlTextField { id:sourceUrl; Layout.fillWidth:true; placeholderText:"https://example.test/module" }
            Text { text:"No files or scripts are downloaded or executed."; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:importDialog.close() }
                SwirlButton {
                    text:"Add demo"; primary:true; enabled:moduleName.text.trim().length>0
                    onClicked:{
                        page.modules=page.modules.concat([{id:"mod"+Date.now(),name:moduleName.text.trim(),
                            author:"Demo author",version:"0.1",state:"Disabled",
                            source:sourceUrl.text.trim()||"Local demo",update:"Not checked"}])
                        moduleName.text="";sourceUrl.text="";importDialog.close()
                    }
                }
            }
        }
    }
}