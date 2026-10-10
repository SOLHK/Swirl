import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property bool tlsPreview:false
    property string activeTab:"Included domains"
    property var selected:null
    property var domainRows:[
        {id:"tls-1",name:"api.example.test",type:"Include",mode:"Full inspection",status:"Enabled"},
        {id:"tls-2",name:"*.assets.example.test",type:"Include",mode:"Headers only",status:"Enabled"},
        {id:"tls-3",name:"*.bank.example.test",type:"Exclude",mode:"Pass through",status:"Excluded"},
        {id:"tls-4",name:"*.private.example.test",type:"Exclude",mode:"Pass through",status:"Excluded"}
    ]
    readonly property var shown:domainRows.filter(function(r){
        return (activeTab==="Included domains"?r.type==="Include":r.type==="Exclude") &&
               r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:157
            RowLayout {
                anchors.fill:parent; anchors.margins:23; spacing:18
                Rectangle {
                    width:52; height:52; radius:16; color:Theme.selected
                    SwirlIcon { name:"shield"; size:27; color:Theme.accent; anchors.centerIn:parent }
                }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:7
                    Text { text:"HTTPS inspection"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                    Text {
                        text:"The switch previews the future MITM workflow. No root certificate is generated, installed, trusted or revoked."
                        color:Theme.muted; font.pixelSize:12; wrapMode:Text.WordWrap; Layout.fillWidth:true
                    }
                    RowLayout {
                        SwirlStatusBadge { label:"LOCAL CA: NOT INSTALLED"; tone:"warning" }
                        SwirlStatusBadge { label:"TLS SESSIONS: 0 REAL"; tone:"neutral" }
                    }
                }
                ColumnLayout {
                    Text { text:"Preview decrypt toggle"; color:Theme.muted; font.pixelSize:11 }
                    SwirlToggle { checked:page.tlsPreview; onToggled:{page.tlsPreview=checked;AppState.notice("HTTPS decrypt preview")} }
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:["Included domains","Excluded domains"]
                SwirlButton { text:modelData; quiet:page.activeTab!==modelData; onClicked:page.activeTab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"Certificate manager"; iconName:"shield"; onClicked:certDialog.open() }
            SwirlButton { text:"Add domain"; primary:true; onClicked:addDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"Filter host patterns" }
            SwirlStatusBadge { label:page.shown.length+" DEMO HOSTS"; tone:"accent" }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.fillHeight:true; Layout.fillWidth:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.shown
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"name",label:"HOST PATTERN",w:258},{key:"type",label:"RULE",w:107},
                             {key:"mode",label:"ACTION",w:166},{key:"status",label:"STATE",w:110}]
                    onRowSelected:function(r){page.selected=r}
                }
                SwirlEmptyState {
                    anchors.centerIn:parent; visible:page.shown.length===0
                    headline:"No host patterns"
                    detail:"Try another filter, or add a demo domain"
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:285; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:18; spacing:14
                    Text { text:"Certificate & session"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    Repeater {
                        model:[["CA STATUS","Absent · demonstration"],["TRUST","Not configured"],
                               ["ACTIVE REAL SESSIONS","0"],["TLS VERSION","TLS 1.3 (sample)"],
                               ["CIPHER","AES_128_GCM_SHA256 (sample)"],
                               ["SELECTED HOST",page.selected?page.selected.name:"—"]]
                        ColumnLayout {
                            Layout.fillWidth:true; spacing:3
                            Text { text:modelData[0]; font.pixelSize:10; color:Theme.muted }
                            Text { text:modelData[1]; font.pixelSize:12; color:Theme.text; wrapMode:Text.WrapAnywhere; Layout.fillWidth:true }
                        }
                    }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Trust certificate"; onClicked:AppState.notice("Trust CA: blocked in demo") }
                    SwirlButton { text:"Revoke trust"; danger:true; onClicked:AppState.notice("Revoke CA: blocked in demo") }
                }
            }
        }
    }
    SwirlDialog {
        id:certDialog; title:"CA certificate manager"
        ColumnLayout {
            width:parent.width; spacing:11
            SwirlStatusBadge { label:"NO CERTIFICATE MATERIAL AVAILABLE"; tone:"warning" }
            Text {
                text:"In this UI-only build, Swirl does not generate certificates, access Windows certificate stores, or intercept HTTPS traffic. These buttons only demonstrate the future workflow."
                color:Theme.text; font.pixelSize:13; wrapMode:Text.WordWrap; Layout.fillWidth:true
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Close"; onClicked:certDialog.close() }
                SwirlButton { text:"Certificate preview"; onClicked:AppState.notice("Certificate details") }
            }
        }
    }
    SwirlDialog {
        id:addDialog; title:"Add HTTPS host pattern"
        ColumnLayout {
            width:parent.width; spacing:11
            Text { text:"Host pattern"; color:Theme.text }
            SwirlTextField { id:hostName; Layout.fillWidth:true; placeholderText:"*.example.test" }
            SwirlComboBox { id:ruleType; Layout.fillWidth:true; model:["Include","Exclude"]; currentIndex:page.activeTab==="Included domains"?0:1 }
            Text { text:"Only a local UI fixture will be added."; color:Theme.muted; font.pixelSize:11 }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:addDialog.close() }
                SwirlButton {
                    text:"Save demo"; primary:true
                    enabled:hostName.text.includes(".")&&!hostName.text.includes(" ")
                    onClicked:{
                        var name=hostName.text.trim()
                        page.domainRows=page.domainRows.concat([{id:"tls-"+Date.now(),
                            name:name,type:ruleType.currentText,
                            mode:ruleType.currentText==="Include"?"Full inspection":"Pass through",
                            status:ruleType.currentText==="Include"?"Enabled":"Excluded"}])
                        page.activeTab=ruleType.currentText==="Include"?"Included domains":"Excluded domains"
                        hostName.text="";addDialog.close()
                    }
                }
            }
        }
    }
}