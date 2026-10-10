import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string tab:"API Explorer"
    property var routes:[
        {id:"api1",method:"GET",path:"/v1/status",permission:"Read status",status:"Planned"},
        {id:"api2",method:"GET",path:"/v1/connections",permission:"Read sessions",status:"Planned"},
        {id:"api3",method:"POST",path:"/v1/profiles/select",permission:"Update profile",status:"Planned"},
        {id:"api4",method:"GET",path:"/v1/logs",permission:"Read diagnostics",status:"Planned"}
    ]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:112
            RowLayout {
                anchors.fill:parent; anchors.margins:20; spacing:16
                SwirlIcon { name:"terminal"; size:31; color:Theme.accent }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:6
                    Text { text:"Local control API"; font.pixelSize:20; color:Theme.text; font.weight:Font.DemiBold }
                    Text { text:"API endpoint: not listening · CLI: demonstration command reference"; color:Theme.muted; font.pixelSize:12 }
                }
                SwirlStatusBadge { label:"SERVER OFFLINE"; tone:"warning" }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            Repeater {
                model:["API Explorer","CLI Commands","Permissions","Access Logs"]
                SwirlButton { text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
            }
            Item { Layout.fillWidth:true }
            SwirlButton { text:"Server settings"; onClicked:settingsDialog.open() }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                SwirlDataTable {
                    visible:page.tab==="API Explorer"
                    anchors.fill:parent; anchors.margins:1
                    rows:page.routes
                    columns:[{key:"method",label:"METHOD",w:100},{key:"path",label:"ENDPOINT",w:260},
                             {key:"permission",label:"SCOPE",w:160},{key:"status",label:"STATE",w:112}]
                    onRowSelected:function(r){pathInput.text=r.path;methodInput.currentIndex=methodInput.model.indexOf(r.method)}
                }
                ColumnLayout {
                    visible:page.tab!=="API Explorer"
                    anchors.fill:parent; anchors.margins:18; spacing:15
                    Text { text:page.tab; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    Repeater {
                        model:page.tab==="CLI Commands"?
                            ["swirl status","swirl profiles list","swirl proxies show","swirl dns query example.test","swirl logs --tail"]:
                            page.tab==="Permissions"?
                            ["Read-only status","Read-only connections","Profile management","Diagnostics export"]:
                            ["No API requests received in this demonstration.","Local control listener has not been created."]
                        RowLayout {
                            Layout.fillWidth:true
                            Text { text:modelData; color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:12; Layout.fillWidth:true }
                            SwirlButton { text:"Preview"; onClicked:AppState.notice("CLI/API sample") }
                        }
                    }
                    Item { Layout.fillHeight:true }
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:313; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:12
                    Text { text:"Request example"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlComboBox { id:methodInput; Layout.fillWidth:true; model:["GET","POST","PUT","DELETE"] }
                    SwirlTextField { id:pathInput; Layout.fillWidth:true; text:"/v1/status" }
                    Text { text:"JSON RESPONSE PREVIEW"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:9
                            TextArea {
                                readOnly:true
                                text:"HTTP/1.1 503 Preview Only\nContent-Type: application/json\n\n{\n  \"running\": false,\n  \"demo\": true,\n  \"path\": \""+pathInput.text+"\"\n}"
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:11
                                wrapMode:Text.WrapAnywhere; background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { text:"Test locally (demo)"; primary:true; onClicked:AppState.notice("API request not sent") }
                }
            }
        }
    }
    SwirlDialog {
        id:settingsDialog; title:"Local API settings"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"Listener address"; color:Theme.text }
            SwirlTextField { Layout.fillWidth:true; text:"127.0.0.1"; readOnly:true }
            Text { text:"Port"; color:Theme.text }
            SwirlTextField { Layout.fillWidth:true; text:"6170"; validator:IntValidator { bottom:1024; top:65535 } }
            RowLayout {
                Layout.fillWidth:true
                Text { text:"Allow API requests (visual switch only)"; Layout.fillWidth:true; color:Theme.muted; font.pixelSize:12 }
                SwirlToggle { onToggled:AppState.notice("API listener") }
            }
            SwirlButton { text:"Close"; Layout.alignment:Qt.AlignRight; onClicked:settingsDialog.close() }
        }
    }
}