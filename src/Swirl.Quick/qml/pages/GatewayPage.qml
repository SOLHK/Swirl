import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string selected:"LAN devices"
    readonly property var modules:["LAN devices","Gateway mode","DHCP server","Port forwarding","Remote devices","Network interfaces"]
    property var records:[
        {id:"d1",name:"Example workstation",address:"192.0.2.10",interface:"Ethernet (fixture)",status:"Demo"},
        {id:"d2",name:"Example tablet",address:"192.0.2.11",interface:"Wi-Fi (fixture)",status:"Demo"},
        {id:"d3",name:"Example router",address:"192.0.2.1",interface:"Gateway (fixture)",status:"Demo"}
    ]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:15
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:126
            RowLayout {
                anchors.fill:parent; anchors.margins:19; spacing:17
                SwirlIcon { name:"network"; size:35; color:Theme.orange }
                ColumnLayout {
                    Layout.fillWidth:true; spacing:7
                    Text { text:"Gateway & Devices"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                    Text { text:"Advanced platform integration reserved for a future release. No device discovery, DHCP or routing service is enabled."; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap }
                }
                SwirlStatusBadge { label:"PLANNED FOR WINDOWS"; tone:"warning" }
            }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:page.modules
                SwirlButton { text:modelData; quiet:page.selected!==modelData; onClicked:page.selected=modelData }
            }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.records
                    columns:[{key:"name",label:"DEVICE / INTERFACE",w:238},{key:"address",label:"IP",w:150},
                             {key:"interface",label:"NETWORK",w:204},{key:"status",label:"STATE",w:100}]
                    onRowSelected:function(r){AppState.notice("Device inspector "+r.name)}
                }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:315; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:19; spacing:13
                    Text { text:page.selected; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:"NOT AVAILABLE"; tone:"warning" }
                    Text {
                        text:page.selected==="DHCP server"?
                            "A future build may expose DHCP pool selection, lease history and gateway reservations.":
                            page.selected==="Port forwarding"?
                            "Preview forwarding rules, internal IP mappings, protocol and port ranges.":
                            page.selected==="Remote devices"?
                            "Remote device pairing, permissions and traffic policies are reserved.":
                            page.selected==="Network interfaces"?
                            "Future adapter enumeration, metrics and route information.":
                            page.selected==="Gateway mode"?
                            "Network gateway and routing modes require additional Windows-specific capabilities.":
                            "LAN inventory will require explicit authorization to discover devices."
                        color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:"CONFIGURATION MOCKUP"; color:Theme.muted; font.pixelSize:10 }
                    Text { text:"Interface"; color:Theme.muted; font.pixelSize:11 }
                    SwirlComboBox { Layout.fillWidth:true; model:["Ethernet (example)","Wi-Fi (example)","Custom adapter"] }
                    Text { text:"Device label"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; placeholderText:"Device name" }
                    Text { text:"Private subnet"; color:Theme.muted; font.pixelSize:11 }
                    SwirlTextField { Layout.fillWidth:true; text:"192.0.2.0/24" }
                    Item { Layout.fillHeight:true }
                    SwirlButton { text:"Preview settings"; onClicked:AppState.notice("Gateway configuration") }
                    SwirlButton { text:"Activate feature"; enabled:false; primary:true }
                }
            }
        }
    }
}