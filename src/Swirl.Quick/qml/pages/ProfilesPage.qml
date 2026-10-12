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
        {id:"p1",name:"Default",source:"本地 · default.yaml",version:"v1.4",updated:"Today",state:"Active"},
        {id:"p2",name:"Travel",source:"本地 · travel.yaml",version:"v1.2",updated:"10 月 8 日",state:"Available"},
        {id:"p3",name:"Office",source:"远程 · example.test",version:"v2.1",updated:"10 月 6 日",state:"Available"},
        {id:"p4",name:"Minimal",source:"本地 · minimal.yaml",version:"v1.0",updated:"9 月 20 日",state:"Available"}
    ]
    property string editorText:"# Swirl local configuration example\n# Preview-only: no Mihomo profile is loaded.\n\nmode: rule\nlog-level: info\n\nproxy-groups:\n  - name: Auto Select\n    type: select\n\nrules:\n  - MATCH,Auto Select\n"
    readonly property var visibleProfiles:profiles.filter(function(r){return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("CONFIGURATION DEMO"); tone:"accent" }
            Text { text:AppState.zh("Synthetic configuration records only. Existing YAML and subscription data are never read or overwritten."); Layout.fillWidth:true; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
            SwirlButton { text:AppState.zh("Import"); onClicked:AppState.notice("导入配置") }
            SwirlButton { text:AppState.zh("New profile"); primary:true; onClicked:addDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(110)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(19); spacing:Theme.dp(18)
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(6)
                    Text { text:AppState.zh("CURRENT PREVIEW CONFIGURATION"); color:Theme.muted; font.pixelSize:Theme.fontSize(11); font.letterSpacing:1.1 }
                    Text { text:page.currentProfile; color:Theme.text; font.pixelSize:Theme.fontSize(23); font.weight:Font.DemiBold }
                    Text { text:AppState.zh("Manual selection · no network engine initialized"); color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                SwirlStatusBadge { label:AppState.zh("LOCAL FIXTURE"); tone:"success" }
                SwirlButton { text:AppState.zh("Validate"); onClicked:AppState.notice("检查配置") }
                SwirlButton { text:AppState.zh("Export demo"); onClicked:AppState.notice("导出配置") }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(7)
            Repeater {
                model:["Configurations","Editor","历史版本","Backups"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Update remote"); onClicked:AppState.notice("更新远程配置") }
        }
        RowLayout {
            visible:page.tab==="Configurations"; Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search profiles and sources") }
            SwirlComboBox { model:["All sources","Local","Remote"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Configurations"
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.visibleProfiles
                    columns:[{key:"name",label:AppState.zh("PROFILE NAME"),w:187},{key:"source",label:AppState.zh("SOURCE"),w:240},
                             {key:"version",label:AppState.zh("VERSION"),w:100},{key:"updated",label:AppState.zh("UPDATED"),w:105},
                             {key:"state",label:AppState.zh("状态"),w:112}]
                    onRowSelected:function(r){page.currentProfile=r.name}
                }
                ColumnLayout {
                    visible:page.tab==="Editor"
                    anchors.fill:parent; anchors.margins:Theme.dp(16); spacing:Theme.dp(10)
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:page.currentProfile+".yaml"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SwirlStatusBadge { label:AppState.zh("UNSAVED DEMO CONTENT"); tone:"warning" }
                    }
                    ScrollView {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        TextArea {
                            id:editor
                            text:page.editorText
                            font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(12); color:Theme.text
                            wrapMode:TextEdit.NoWrap; selectByMouse:true
                            background:Rectangle { color:Theme.field; radius:Theme.roundedRadius(width,height); border.color:Theme.border }
                        }
                    }
                    SwirlButton { text:AppState.zh("Save preview"); onClicked:{page.editorText=editor.text;AppState.notice("保存编辑器预览")} }
                }
                ColumnLayout {
                    visible:page.tab==="历史版本"||page.tab==="Backups"
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(16)
                    Text { text:AppState.zh(page.tab); color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="历史版本"?
                            ["v1.4  ·  Today  ·  Enabled rule changes","v1.3  ·  Oct 8  ·  Update endpoint strategy",
                             "v1.2  ·  Oct 4  ·  Updated DNS","v1.1  ·  Sep 29  ·  Created configuration"]:
                            ["Backup snapshot  ·  Oct 8","Backup snapshot  ·  Oct 1","Backup snapshot  ·  Sep 25"]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"folder"; color:Theme.muted; size:Theme.dp(18) }
                            Text { text:modelData; color:Theme.text; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlButton { text:AppState.zh("Compare"); onClicked:AppState.notice("比较配置版本") }
                            SwirlButton { text:AppState.zh("Restore"); onClicked:AppState.notice("恢复配置预览") }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(284); Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(12)
                    ScrollView {
                        id:detailScroll0; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                        ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                        ColumnLayout {
                    width:detailScroll0.availableWidth; spacing:Theme.dp(13)
                    Text { text:AppState.zh("Profile summary"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Repeater {
                        model:[["SELECTED",page.currentProfile],["FORMAT","Clash / Mihomo YAML"],
                               ["POLICY GROUPS","4 (sample)"],["PROXY NODES","18 (sample)"],
                               ["RULES","253 (sample)"],["SOURCE","本地"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }

                        }
                    }

                    SwirlButton { text:AppState.zh("Use profile in UI"); primary:true; onClicked:AppState.notice("Select "+page.currentProfile) }
                    SwirlButton { text:AppState.zh("View editor"); onClicked:page.tab="Editor" }

                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"创建配置预览"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:AppState.zh("Name"); color:Theme.text }
            SwirlTextField { id:profileName; Layout.fillWidth:true; placeholderText:AppState.zh("New profile name") }
            SwirlComboBox { id:source; Layout.fillWidth:true; model:["Local","Remote"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("取消"); onClicked:addDialog.close() }
                SwirlButton {
                    text:AppState.zh("Add demo"); primary:true; enabled:profileName.text.trim().length>0
                    onClicked:{
                        page.profiles=page.profiles.concat([{id:"p"+Date.now(),name:profileName.text.trim(),
                            source:source.currentText+" · preview",version:"v0.1",updated:"现在",state:"Available"}])
                        profileName.text="";addDialog.close()
                    }
                }
            }
        }
    }
}