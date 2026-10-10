import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
    id:page
    property string tool:"DNS Lookup"
    property string result:"No test has been run.\nEnter a target and choose Run demo."
    property var tools:["DNS Lookup","TCP Ping","Traceroute","HTTP Request","TLS Certificate Inspector","Port Check","IP Lookup","Whois","Connectivity Test","Network Interface Info"]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        Text { text:"Select a diagnostic tool. All results are local examples."; color:Theme.muted; font.pixelSize:12 }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:15
            SwirlGlassPanel {
                Layout.preferredWidth:235; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:13; spacing:9
                    Text { text:"NETWORK UTILITIES"; color:Theme.muted; font.pixelSize:11; leftPadding:8 }
                    ListView {
                        Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:4
                        model:page.tools
                        delegate:Rectangle {
                            width:ListView.view.width; height:40; radius:10
                            color:page.tool===modelData?Theme.selected:area.containsMouse?Theme.hover:"transparent"
                            RowLayout {
                                anchors.fill:parent; anchors.leftMargin:10
                                SwirlIcon { name:"tool"; size:17; color:Theme.muted }
                                Text { text:modelData; color:Theme.text; font.pixelSize:12; elide:Text.ElideRight; Layout.fillWidth:true }
                            }
                            MouseArea { id:area; anchors.fill:parent; hoverEnabled:true; onClicked:{page.tool=modelData;page.result="No test has been run.\nEnter a target and choose Run demo."} }
                        }
                    }
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:23; spacing:17
                    RowLayout {
                        Layout.fillWidth:true
                        ColumnLayout {
                            Layout.fillWidth:true
                            Text { text:page.tool; color:Theme.text; font.pixelSize:22; font.weight:Font.DemiBold }
                            Text { text:"Standalone inspection panel"; color:Theme.muted; font.pixelSize:12 }
                        }
                        SwirlStatusBadge { label:"LOCAL SIMULATION"; tone:"accent" }
                    }
                    Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
                    Text { text:page.tool==="Network Interface Info"?"Interface name":"Target host, address or URL"; color:Theme.text; font.pixelSize:13 }
                    SwirlTextField {
                        id:target; Layout.fillWidth:true
                        placeholderText:page.tool==="HTTP Request"?"https://example.test/path":"example.test"
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox {
                            visible:page.tool==="HTTP Request"
                            model:["GET","POST","PUT","DELETE","HEAD"]
                        }
                        SwirlTextField {
                            visible:page.tool==="Port Check" || page.tool==="TCP Ping"
                            Layout.preferredWidth:130
                            placeholderText:"Port (443)"
                            validator:IntValidator { bottom:1; top:65535 }
                        }
                        Item { Layout.fillWidth:true }
                        SwirlButton {
                            text:"Run demo"; primary:true; iconName:"play"
                            enabled:target.text.trim().length>0
                            onClicked:{
                                page.result="SIMULATED RESULT · "+page.tool+"\n"+
                                            "Target: "+target.text+"\n"+
                                            "Status: No network requests were made.\n"+
                                            "Backend connection: not configured.\n\n"+
                                            "This panel is prepared for a future tool adapter."
                            }
                        }
                    }
                    Text { text:"RESULTS"; color:Theme.muted; font.pixelSize:11; font.weight:Font.DemiBold }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        color:Theme.field; border.color:Theme.border; radius:12
                        ScrollView {
                            anchors.fill:parent; anchors.margins:12
                            TextArea {
                                readOnly:true; selectByMouse:true
                                text:page.result
                                color:Theme.text
                                wrapMode:Text.Wrap
                                font.family:"Cascadia Code"; font.pixelSize:12
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { text:"Copy results"; onClicked:{demoProvider.copyText(page.result);AppState.toast="Copied diagnostic preview"} }
                }
            }
        }
    }
}