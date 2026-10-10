import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property var chosen:null
    property bool scheduleEnabled:true
    property var providers:[
        {id:"s1",name:"Primary · Singapore",source:"https://provider.example.test/sub/primary",nodes:48,used:34,limit:100,
         update:"2026-10-10 13:20",status:"Healthy",interval:"6 hours"},
        {id:"s2",name:"Travel endpoints",source:"https://provider.example.test/sub/travel",nodes:16,used:69,limit:150,
         update:"2026-10-09 21:05",status:"Healthy",interval:"12 hours"},
        {id:"s3",name:"Backup provider",source:"https://provider.example.test/sub/backup",nodes:0,used:0,limit:100,
         update:"2026-10-07 12:45",status:"Error (sample)",interval:"24 hours"}
    ]
    readonly property var listed:providers.filter(function(r){
        return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("SUBSCRIPTIONS · MOCK DATA"); tone:"accent" }
            Text { text:AppState.zh("No remote URLs are requested or saved."); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Update all (demo)"); iconName:"refresh"; onClicked:AppState.notice("Update subscriptions") }
            SwirlButton { text:AppState.zh("Add subscription"); primary:true; onClicked:addDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:12
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search subscription providers") }
            Text { text:AppState.zh("Auto update"); color:Theme.muted; font.pixelSize:12 }
            SwirlToggle { checked:page.scheduleEnabled; onToggled:page.scheduleEnabled=checked }
            SwirlComboBox { model:["Every 6 hours","Every 12 hours","Daily","Weekly","Off"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ScrollView {
                    id:scroll
                    anchors.fill:parent; anchors.margins:16; clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                        width:scroll.availableWidth; spacing:12
                        Repeater {
                            model:page.listed
                            SwirlGlassPanel {
                                id:provider
                                property var record:modelData
                                Layout.fillWidth:true
                                Layout.preferredHeight:151
                                selected:page.chosen&&page.chosen.id===record.id
                                ColumnLayout {
                                    anchors.fill:parent; anchors.margins:15; spacing:9
                                    RowLayout {
                                        Layout.fillWidth:true
                                        SwirlIcon { name:"refresh"; size:18; color:Theme.accent }
                                        Text { text:record.name; color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold; Layout.fillWidth:true }
                                        SwirlStatusBadge { label:record.status; tone:record.status==="Healthy"?"success":"warning" }
                                    }
                                    Text { text:record.source; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; elide:Text.ElideMiddle }
                                    Rectangle {
                                        Layout.fillWidth:true; height:7; radius:4; color:Theme.field
                                        Rectangle { width:parent.width*record.used/record.limit; height:parent.height; radius:4; color:record.used/record.limit>.75?Theme.orange:Theme.accent }
                                    }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:record.used+" GB / "+record.limit+" GB · synthetic traffic"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                                        Text { text:record.nodes+" nodes"; color:Theme.text; font.pixelSize:11 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh("Updated ")+record.update; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                                        SwirlButton { text:AppState.zh("Details"); quiet:true; onClicked:page.chosen=record }
                                        SwirlButton { text:AppState.zh("Refresh"); iconName:"refresh"; onClicked:AppState.notice("Refresh provider "+record.name) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:284; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:13
                    Text { text:AppState.zh("Provider inspector"); color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Text {
                        text:page.chosen?page.chosen.name:"Select a subscription"
                        color:Theme.accent; font.pixelSize:15; font.weight:Font.DemiBold
                        wrapMode:Text.WordWrap; Layout.fillWidth:true
                    }
                    Repeater {
                        model:[["STATUS",page.chosen?page.chosen.status:"—"],
                               ["NODES",page.chosen?String(page.chosen.nodes):"—"],
                               ["LAST UPDATED",page.chosen?page.chosen.update:"—"],
                               ["AUTOMATIC REFRESH",page.chosen?page.chosen.interval:"—"],
                               ["USED QUOTA",page.chosen?page.chosen.used+" GB":"—"],
                               ["PLAN LIMIT",page.chosen?page.chosen.limit+" GB":"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:3
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:AppState.zh("Edit provider"); onClicked:addDialog.open() }
                    SwirlButton { text:AppState.zh("View update errors"); onClicked:AppState.notice("Subscription error details") }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"Subscription source"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:AppState.zh("Display name"); color:Theme.text }
            SwirlTextField { id:displayName; Layout.fillWidth:true; placeholderText:AppState.zh("My subscription") }
            Text { text:AppState.zh("HTTPS URL (stored only in preview memory)"); color:Theme.text }
            SwirlTextField { id:urlField; Layout.fillWidth:true; placeholderText:AppState.zh("https://provider.example.test/sub") }
            Text { text:AppState.zh("Real subscriptions, credentials and tokens are not downloaded or saved."); color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Cancel"); onClicked:addDialog.close() }
                SwirlButton {
                    text:AppState.zh("Add demo"); primary:true
                    enabled:displayName.text.trim().length>0&&urlField.text.startsWith("https://")
                    onClicked:{
                        page.providers=page.providers.concat([{id:"s"+Date.now(),name:displayName.text.trim(),
                            source:urlField.text.trim(),nodes:0,used:0,limit:100,update:"Never",status:"Not checked",interval:"24 hours"}])
                        displayName.text="";urlField.text="";addDialog.close()
                    }
                }
            }
        }
    }
}