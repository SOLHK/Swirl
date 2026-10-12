import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string tab:"Configurations"
    property string currentProfile: ""
    property var profiles:[]
    property string editorText: ""
    readonly property var visibleProfiles:profiles.filter(function(r){return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0})
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"尚未实现"; tone:"accent" }
            Text { text:"尚未实现"; Layout.fillWidth:true; color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
            SwirlButton { enabled:false; text:AppState.zh("Import"); onClicked:AppState.notice("导入配置") }
            SwirlButton { enabled:false; text:AppState.zh("New profile"); primary:true; onClicked:addDialog.open() }
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
                SwirlButton { enabled:false; text:AppState.zh("Validate"); onClicked:AppState.notice("检查配置") }
                SwirlButton { enabled:false; text:"尚未实现"; onClicked:AppState.notice("导出配置") }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(7)
            Repeater {
                model:["Configurations","Editor","历史版本","Backups"]
                SwirlButton { enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("Update remote"); onClicked:AppState.notice("更新远程配置") }
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
                        SwirlStatusBadge { label:"尚未实现"; tone:"warning" }
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
                    SwirlButton { enabled:false; text:"保存（尚未实现）"; onClicked:AppState.notice("尚未实现") }
                }
                ColumnLayout {
                    visible:page.tab==="历史版本"||page.tab==="Backups"
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(16)
                    Text { text:AppState.zh(page.tab); color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    Repeater {
                        model:[]
                        RowLayout {
                            Layout.fillWidth:true
                            SwirlIcon { name:"folder"; color:Theme.muted; size:Theme.dp(18) }
                            Text { text:modelData; color:Theme.text; Layout.fillWidth:true; font.pixelSize:Theme.fontSize(12) }
                            SwirlButton { enabled:false; text:AppState.zh("Compare"); onClicked:AppState.notice("比较配置版本") }
                            SwirlButton { enabled:false; text:AppState.zh("Restore"); onClicked:AppState.notice("恢复配置预览") }
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
                               ["POLICY GROUPS","—"],["PROXY NODES","—"],
                               ["RULES","—"],["SOURCE","本地"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("Use profile in UI"); primary:true; onClicked:AppState.notice("Select "+page.currentProfile) }
                    SwirlButton { enabled:false; text:AppState.zh("View editor"); onClicked:page.tab="Editor" }

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
                SwirlButton { enabled:false; text:AppState.zh("取消"); onClicked:addDialog.close() }
                SwirlButton { enabled:false;
                    text:"尚未实现"; primary:true;
                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
