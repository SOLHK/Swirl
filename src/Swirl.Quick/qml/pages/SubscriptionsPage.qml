import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property var chosen:null
    property bool scheduleEnabled:true
    property var providers:[]
    readonly property var listed:providers.filter(function(r){
        return (r.name+" "+r.source).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:AppState.zh("订阅管理 · "); tone:"accent" }
            Text { text:AppState.zh("No remote URLs are requested or saved."); color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:"尚未实现"; iconName:"refresh"; onClicked:AppState.notice("更新订阅") }
            SwirlButton { enabled:false; text:AppState.zh("Add subscription"); primary:true; onClicked:addDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(12)
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search subscription providers") }
            Text { text:AppState.zh("Auto update"); color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
            SwirlToggle { enabled:false;checked:false;  onToggled:page.scheduleEnabled=checked }
            SwirlComboBox { model:["Every 6 hours","Every 12 hours","Daily","Weekly","Off"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ScrollView {
                    id:scroll
                    anchors.fill:parent; anchors.margins:Theme.dp(16); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                        width:scroll.availableWidth; spacing:Theme.dp(12)
                        Repeater {
                            model:page.listed
                            SwirlGlassPanel {
                                id:provider
                                property var record:modelData
                                Layout.fillWidth:true
                                Layout.preferredHeight:Math.max(Theme.dp(178),providerContent.implicitHeight+Theme.dp(30))
                                selected:page.chosen&&page.chosen.id===record.id
                                ColumnLayout {
                                    id:providerContent
                                    anchors.fill:parent; anchors.margins:Theme.dp(15); spacing:Theme.dp(9)
                                    RowLayout {
                                        Layout.fillWidth:true
                                        SwirlIcon { name:"refresh"; size:Theme.dp(18); color:Theme.accent }
                                        Text { text:record.name; color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold; Layout.fillWidth:true }
                                        SwirlStatusBadge { label:AppState.zh(record.status); tone:record.status==="Healthy"?"success":"warning" }
                                    }
                                    Text { text:record.source; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; elide:Text.ElideMiddle }
                                    Rectangle {
                                        Layout.fillWidth:true; height:Theme.dp(7); radius:Theme.roundedRadius(width,height); color:Theme.field
                                        Rectangle { width:parent.width*record.used/record.limit; height:parent.height; radius:Theme.roundedRadius(width,height); color:record.used/record.limit>.75?Theme.orange:Theme.accent }
                                    }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:record.used+" GB / "+record.limit+" GB"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
                                        Text { text:record.nodes+" 个节点"; color:Theme.text; font.pixelSize:Theme.fontSize(11) }
                                    }
                                    RowLayout {
                                        Layout.fillWidth:true
                                        Text { text:AppState.zh("Updated ")+record.update; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
                                        SwirlButton { enabled:false; text:AppState.zh("Details"); implicitHeight:Theme.dp(32); quiet:false; onClicked:page.chosen=record }
                                        SwirlButton { enabled:false; text:AppState.zh("Refresh"); implicitHeight:Theme.dp(32); iconName:"refresh"; onClicked:AppState.notice("刷新订阅源"+record.name) }
                                    }
                                }
                            }
                        }
                    }
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
                    Text { text:AppState.zh("Provider inspector"); color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    Text {
                        text:page.chosen?page.chosen.name:"请选择订阅"
                        color:Theme.accent; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold
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
                            Layout.fillWidth:true; spacing:Theme.dp(3)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("编辑订阅源"); onClicked:addDialog.open() }
                    SwirlButton { enabled:false; text:AppState.zh("View update errors"); onClicked:AppState.notice("订阅错误详情") }

                }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"订阅来源"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:AppState.zh("Display name"); color:Theme.text }
            SwirlTextField { id:displayName; Layout.fillWidth:true; placeholderText:AppState.zh("My subscription") }
            Text { text:"订阅功能尚未实现"; color:Theme.text }
            SwirlTextField { id:urlField; Layout.fillWidth:true; placeholderText:AppState.zh("https://provider.example.test/sub") }
            Text { text:AppState.zh("Real subscriptions, credentials and tokens are not downloaded or saved."); color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("Cancel"); onClicked:addDialog.close() }
                SwirlButton { enabled:false;
                    text:AppState.zh("添加"); primary:true

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
