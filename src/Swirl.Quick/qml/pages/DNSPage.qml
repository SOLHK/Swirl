import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string tab: "查询日志"
    property var selectedRecord: null
    property var dnsRecords: []
    readonly property var visibleRecords:dnsRecords.filter(function(r){
        return (r.domain+" "+r.answer+" "+r.type).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"尚未实现"; tone:"accent" }
            Text { text:"尚未实现"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("Test Resolver"); iconName:"activity"; primary:true; onClicked:testDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(130)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(20); spacing:Theme.dp(22)
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(7)
                    Text { text:AppState.zh("Primary resolver"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    Text { text:AppState.zh("https://dns.example.test/dns-query"); color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold; elide:Text.ElideRight; Layout.fillWidth:true }
                    Text { text:AppState.zh("DoH · DNSSEC option · synthetic endpoint"); color:Theme.muted; font.pixelSize:Theme.fontSize(12) }
                }
                Rectangle { width:Theme.dp(1); Layout.fillHeight:true; color:Theme.border }
                ColumnLayout {
                    spacing:Theme.dp(8); Layout.preferredWidth:Theme.dp(190)
                    Text { text:AppState.zh("Protocols enabled"); color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                    RowLayout {
                        SwirlStatusBadge { label:AppState.zh("DoH"); tone:"success" }
                        SwirlStatusBadge { label:AppState.zh("DoT"); tone:"accent" }
                        SwirlStatusBadge { label:AppState.zh("DoQ"); tone:"accent" }
                    }
                    Text { text:"DNS 配置尚未实现"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(7)
            Repeater {
                model:["查询日志","Resolvers","Hosts","Cache","Fake-IP"]
                SwirlButton { enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { enabled:false; text:AppState.zh("清空"); onClicked:AppState.notice("尚未实现") }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(12); visible:page.tab==="查询日志"
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:AppState.zh("Search DNS domain, answer or record type") }
            SwirlComboBox { model:["全部记录类型","A","AAAA","CNAME","TXT","HTTPS"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="查询日志"
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.visibleRecords
                    selectedId:page.selectedRecord?page.selectedRecord.id:""
                    columns:[{key:"domain",label:AppState.zh("DOMAIN"),w:245},{key:"type",label:AppState.zh("TYPE"),w:70},
                             {key:"answer",label:AppState.zh("ANSWER"),w:175},{key:"server",label:AppState.zh("RESOLVER"),w:130},
                             {key:"duration",label:AppState.zh("时间"),w:85},{key:"result",label:AppState.zh("RESULT"),w:95}]
                    onRowSelected:function(r){page.selectedRecord=r}
                }
                ColumnLayout {
                    visible:page.tab!=="查询日志"
                    anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(14)
                    Text { text:AppState.zh(page.tab); color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    Repeater {
                        model:[]
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:modelData; Layout.fillWidth:true; color:Theme.text; font.pixelSize:Theme.fontSize(12); elide:Text.ElideRight }
                            SwirlToggle { enabled:false;checked:false; onToggled:AppState.notice("DNS "+page.tab) }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { enabled:false; text:AppState.zh("Add ")+page.tab+" entry"; onClicked:editDialog.open() }
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
                    width:detailScroll0.availableWidth; spacing:Theme.dp(14)
                    Text { text:AppState.zh("DNS 检查"); font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold; color:Theme.text }
                    SwirlStatusBadge { label:page.selectedRecord?page.selectedRecord.result:"尚未选择"; tone:page.selectedRecord?"success":"neutral" }
                    Repeater {
                        model:[
                            ["DOMAIN",page.selectedRecord?page.selectedRecord.domain:"—"],
                            ["ANSWER",page.selectedRecord?page.selectedRecord.answer:"—"],
                            ["RECORD TYPE",page.selectedRecord?page.selectedRecord.type:"—"],
                            ["RESOLVER",page.selectedRecord?page.selectedRecord.server:"—"],
                            ["ELAPSED",page.selectedRecord?page.selectedRecord.duration:"—"]
                        ]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:Theme.dp(4)
                            Text { text:AppState.zh(modelData[0]); color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                            Text { text:AppState.zh(modelData[1]); color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }

                        }
                    }

                    SwirlButton { enabled:false; text:AppState.zh("复制解析结果"); onClicked:AppState.notice("尚未实现") }
                    SwirlButton { enabled:false; text:AppState.zh("Edit mapping"); onClicked:editDialog.open() }

                }
            }
        }
    }
    SwirlDialog {
        id:testDialog; title:"解析器测试"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(13)
            Text { text:AppState.zh("域名"); color:Theme.text }
            SwirlTextField { id:domainInput; Layout.fillWidth:true; placeholderText:AppState.zh("example.test") }
            Text { text:"尚未实现"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("取消"); onClicked:testDialog.close() }
                SwirlButton { enabled:false;
                    text:"尚未实现"; primary:true

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
    SwirlDialog {
        id:editDialog; title:"编辑 DNS 映射"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:AppState.zh("Hostname"); color:Theme.text }
            SwirlTextField { id:hostInput; Layout.fillWidth:true; placeholderText:AppState.zh("internal.example.test") }
            Text { text:AppState.zh("Target / answer"); color:Theme.text }
            SwirlTextField { id:answerInput; Layout.fillWidth:true; placeholderText:AppState.zh("192.0.2.15") }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:AppState.zh("取消"); onClicked:editDialog.close() }
                SwirlButton { enabled:false;
                    text:AppState.zh("应用"); primary:true

                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
