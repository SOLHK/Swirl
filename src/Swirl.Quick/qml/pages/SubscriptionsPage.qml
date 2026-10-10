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
        {id:"s1",name:"主订阅 · 新加坡",source:"https://provider.example.test/sub/primary",nodes:48,used:34,limit:100,
         update:"2026-10-10 13:20",status:"Healthy",interval:"6 hours"},
        {id:"s2",name:"旅行节点",source:"https://provider.example.test/sub/travel",nodes:16,used:69,limit:150,
         update:"2026-10-09 21:05",status:"Healthy",interval:"12 hours"},
        {id:"s3",name:"备用订阅",source:"https://provider.example.test/sub/backup",nodes:0,used:0,limit:100,
         update:"2026-10-07 12:45",status:"错误（模拟）",interval:"最近 24 小时"}
    ]
    readonly property var listed:providers.filter(function(r){
        return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("订阅管理 · 模拟数据"); tone:"accent" }
            Text { text:AppState.zh("No remote URLs are requested or saved."); color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:AppState.zh("Update all (demo)"); iconName:"refresh"; onClicked:AppState.notice("更新订阅") }
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
                                        Text { text:record.used+" GB / "+record.limit+" GB · 模拟流量"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                                        Text { text:record.nodes+" 个节点"; color:Theme.text; font.pixelSize:11 }
                                    }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh("Updated ")+record.update; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                                        SwirlButton { text:AppState.zh("Details"); quiet:true; onClicked:page.chosen=record }
                                        SwirlButton { text:AppState.zh("Refresh"); iconName:"refresh"; onClicked:AppState.notice("刷新订阅源"+record.name) }
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
                        text:page.chosen?page.chosen.name:"请选择订阅"
                        color:Theme.accent; font.pixelSize:15; font.weight:Font.DemiBold
                        wrapMode:Text.WordWrap; Layout.fillWidth:true
                    }
                    Repeater {
                        model:[["STATUS",page.chosen?page.chosen.status:"—"],
                               ["NODES",page.chosen?String(page.chosen.nodes):"—"],
                               ["上次更新",page.chosen?page.chosen.update:"—"],
                               ["自动刷新",page.chosen?page.chosen.interval:"—"],
                               ["已用流量",page.chosen?page.chosen.used+" GB":"—"],
                               ["流量限额",page.chosen?page.chosen.limit+" GB":"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:3
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:AppState.zh("编辑订阅源"); onClicked:addDialog.open() }
                    SwirlButton { text:AppState.zh("View update errors"); onClicked:AppState.notice("订阅错误详情") }
                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"订阅来源"
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
                    text:AppState.zh("添加演示"); primary:true
                    enabled:displayName.text.trim().length>0&&urlField.text.startsWith("https://")
                    onClicked:{
                        page.providers=page.providers.concat([{id:"s"+Date.now(),name:displayName.text.trim(),
                            source:urlField.text.trim(),nodes:0,used:0,limit:100,update:"Never",status:"未检查",interval:"最近 24 小时"}])
                        displayName.text="";urlField.text="";addDialog.close()
                    }
                }
            }
        }
    }
}