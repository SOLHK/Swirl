import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id: page
    property string tab: "Query Log"
    property var selectedRecord: null
    property var dnsRecords: [
        {id:"Q100",domain:"api.example.test",type:"A",answer:"203.0.113.42",server:"DoH / Primary",duration:"23 ms",result:"NOERROR"},
        {id:"Q101",domain:"cdn.example.test",type:"AAAA",answer:"2001:db8::20",server:"DoQ / Backup",duration:"35 ms",result:"NOERROR"},
        {id:"Q102",domain:"private.example.test",type:"A",answer:"192.0.2.15",server:"Hosts",duration:"0 ms",result:"HOSTS"},
        {id:"Q103",domain:"blocked.example.test",type:"A",answer:"-",server:"Rule resolver",duration:"4 ms",result:"BLOCKED"},
        {id:"Q104",domain:"assets.example.test",type:"CNAME",answer:"edge.example.test",server:"DoH / Primary",duration:"19 ms",result:"NOERROR"}
    ]
    readonly property var visibleRecords:dnsRecords.filter(function(r){
        return (r.domain+" "+r.answer+" "+r.type).toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"DEMO DNS ENGINE"; tone:"accent" }
            Text { text:"Requests are local fixtures · no name resolution occurs"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Test Resolver"; iconName:"activity"; primary:true; onClicked:testDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:130
            RowLayout {
                anchors.fill:parent; anchors.margins:20; spacing:22
                ColumnLayout {
                    Layout.fillWidth:true; spacing:7
                    Text { text:"Primary resolver"; color:Theme.muted; font.pixelSize:11 }
                    Text { text:"https://dns.example.test/dns-query"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold; elide:Text.ElideRight; Layout.fillWidth:true }
                    Text { text:"DoH · DNSSEC option · synthetic endpoint"; color:Theme.muted; font.pixelSize:12 }
                }
                Rectangle { width:1; Layout.fillHeight:true; color:Theme.border }
                ColumnLayout {
                    spacing:8; Layout.preferredWidth:190
                    Text { text:"Protocols enabled"; color:Theme.muted; font.pixelSize:11 }
                    RowLayout {
                        SwirlStatusBadge { label:"DoH"; tone:"success" }
                        SwirlStatusBadge { label:"DoT"; tone:"accent" }
                        SwirlStatusBadge { label:"DoQ"; tone:"accent" }
                    }
                    Text { text:"IPv4 + IPv6 · Fake-IP Preview"; color:Theme.muted; font.pixelSize:11 }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:["Query Log","Resolvers","Hosts","Cache","Fake-IP"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"Clear demo"; onClicked:{page.dnsRecords=[];page.selectedRecord=null} }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:12; visible:page.tab==="Query Log"
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Search DNS domain, answer or record type" }
            SwirlComboBox { model:["All record types","A","AAAA","CNAME","TXT","HTTPS"] }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    visible:page.tab==="Query Log"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.visibleRecords
                    selectedId:page.selectedRecord?page.selectedRecord.id:""
                    columns:[{key:"domain",label:"DOMAIN",w:245},{key:"type",label:"TYPE",w:70},
                             {key:"answer",label:"ANSWER",w:175},{key:"server",label:"RESOLVER",w:130},
                             {key:"duration",label:"TIME",w:85},{key:"result",label:"RESULT",w:95}]
                    onRowSelected:function(r){page.selectedRecord=r}
                }
                ColumnLayout {
                    visible:page.tab!=="Query Log"
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:page.tab; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="Resolvers"?
                            ["Primary  ·  DoH  ·  https://dns.example.test/dns-query",
                             "Secondary  ·  DoT  ·  tls://resolver.example.test",
                             "Experimental  ·  DoQ  ·  quic://dns3.example.test"]:
                            page.tab==="Hosts"?
                            ["internal.example.test  →  192.0.2.15",
                             "lab.example.test  →  2001:db8::42"]:
                            page.tab==="Cache"?
                            ["api.example.test  ·  TTL 120 s","cdn.example.test · TTL 245 s"]:
                            ["Fake-IP range  198.18.0.0/15","Exclusions  *.local, *.lan"]
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:modelData; Layout.fillWidth:true; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight }
                            SwirlToggle { onToggled:AppState.notice("DNS "+page.tab) }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Add "+page.tab+" entry"; onClicked:editDialog.open() }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:284; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:"DNS inspection"; font.pixelSize:16; font.weight:Font.DemiBold; color:Theme.text }
                    SwirlStatusBadge { label:page.selectedRecord?page.selectedRecord.result:"NO SELECTION"; tone:page.selectedRecord?"success":"neutral" }
                    Repeater {
                        model:[
                            ["DOMAIN",page.selectedRecord?page.selectedRecord.domain:"—"],
                            ["ANSWER",page.selectedRecord?page.selectedRecord.answer:"—"],
                            ["RECORD TYPE",page.selectedRecord?page.selectedRecord.type:"—"],
                            ["RESOLVER",page.selectedRecord?page.selectedRecord.server:"—"],
                            ["ELAPSED",page.selectedRecord?page.selectedRecord.duration:"—"]
                        ]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:4
                            Text { text:modelData[0]; color:Theme.muted; font.pixelSize:10 }
                            Text { text:modelData[1]; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true; elide:Text.ElideRight }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Copy answer"; onClicked:AppState.notice("Copy DNS answer") }
                    SwirlButton { text:"Edit mapping"; onClicked:editDialog.open() }
                }
            }
        }
    }
    SwirlDialog {
        id:testDialog; title:"Resolver test"
        ColumnLayout {
            width:parent.width; spacing:13
            Text { text:"Domain name"; color:Theme.text }
            SwirlTextField { id:domainInput; Layout.fillWidth:true; placeholderText:"example.test" }
            Text { text:"This test returns an explanatory demo result. No DNS packets are sent."; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:testDialog.close() }
                SwirlButton {
                    text:"Run demo"; primary:true
                    enabled:domainInput.text.includes(".")&&domainInput.text.indexOf(" ")<0
                    onClicked:{testDialog.close();AppState.notice("Resolve "+domainInput.text)}
                }
            }
        }
    }
    SwirlDialog {
        id:editDialog; title:"Edit DNS mapping"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Hostname"; color:Theme.text }
            SwirlTextField { id:hostInput; Layout.fillWidth:true; placeholderText:"internal.example.test" }
            Text { text:"Target / answer"; color:Theme.text }
            SwirlTextField { id:answerInput; Layout.fillWidth:true; placeholderText:"192.0.2.15" }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:editDialog.close() }
                SwirlButton {
                    text:"Apply demo"; primary:true
                    enabled:hostInput.text.includes(".")&&answerInput.text.trim().length>0
                    onClicked:{editDialog.close();AppState.notice("DNS mapping")}
                }
            }
        }
    }
}