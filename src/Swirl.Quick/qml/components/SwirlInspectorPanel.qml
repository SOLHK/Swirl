import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
SwirlGlassPanel {
    id:inspector
    property var record:null
    property string activeTab:"Headers"
    property string mode:"Request"
    cornerRadius:13
    implicitWidth:450
    function detailsText() {
        if(!record) return "Select a request to inspect its details."
        if(activeTab==="Headers")
            return mode+" Headers\n\n:method: "+record.method+
                "\n:authority: "+record.host+"\n:path: "+record.path+
                "\naccept: application/json\nuser-agent: Swirl-Demo/0.1\ncontent-type: application/json\ncache-control: no-cache"
        if(activeTab==="Body")
            return '{\n  "demo": true,\n  "source": "local fixture",\n  "requestId": "'+record.id+'",\n  "items": [\n    { "name": "Swirl", "enabled": false }\n  ]\n}'
        if(activeTab==="XML")return '<response requestId="'+record.id+'">\n  <source>synthetic fixture</source>\n  <success>true</success>\n</response>'
        if(activeTab==="Preview")return "Synthetic image preview"
        if(activeTab==="Cookies")return "session_id = [synthetic]\nSameSite = Lax\nSecure = true\nHttpOnly = true"
        if(activeTab==="Query")return "q = swirl\npage = 1\nlimit = 20"
        if(activeTab==="TLS")return "Protocol: "+record.version+"\nCipher: TLS_AES_128_GCM_SHA256\nTLS version: 1.3\nCA trust: not inspected (demo)"
        if(activeTab==="Timeline")return "DNS Lookup          12 ms\nTCP Connect         21 ms\nTLS Handshake       31 ms\nRequest Sent         4 ms\nWaiting / TTFB      84 ms\nContent Download    18 ms"
        if(activeTab==="WebSocket")return "No WebSocket frames in this synthetic record."
        return record.path
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:17
        spacing:13
        RowLayout {
            Layout.fillWidth:true
            Text {
                Layout.fillWidth:true
                text:record?record.method+"  "+record.host:"Request details"
                color:Theme.text; font.pixelSize:15; font.weight:Font.DemiBold
                elide:Text.ElideRight
            }
            SwirlStatusBadge { label:record?String(record.status):"Idle"; tone:"accent" }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:7
            Repeater {
                model:["Request","Response"]
                SwirlButton {
                    text:modelData; quiet:inspector.mode!==modelData
                    primary:false
                    onClicked:inspector.mode=modelData
                }
            }
            Item { Layout.fillWidth:true }
        }
        Flickable {
            Layout.fillWidth:true; Layout.preferredHeight:39
            contentWidth:tabs.width; contentHeight:height
            clip:true
            Row {
                id:tabs; spacing:6
                Repeater {
                    model:["Headers","Body","XML","Preview","Cookies","Query","TLS","Timeline","WebSocket"]
                    SwirlButton {
                        text:modelData
                        quiet:inspector.activeTab!==modelData
                        onClicked:inspector.activeTab=modelData
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
        Item {
            Layout.fillWidth:true; Layout.fillHeight:true
            ScrollView {
                visible:inspector.activeTab!=="Preview"
                anchors.fill:parent
                clip:true
                TextArea {
                readOnly:true
                text:inspector.detailsText()
                wrapMode:Text.WrapAnywhere
                color:Theme.text
                font.family:"Cascadia Code"
                font.pixelSize:12
                leftPadding:5
                background:Rectangle { color:"transparent" }
                selectByMouse:true
                }
            }
            ColumnLayout {
                visible:inspector.activeTab==="Preview"
                anchors.centerIn:parent
                spacing:12
                Image {
                    source:"qrc:/swirl/swirl-256.png"
                    sourceSize.width:138; sourceSize.height:138
                    Layout.preferredWidth:138; Layout.preferredHeight:138
                    fillMode:Image.PreserveAspectFit
                    Layout.alignment:Qt.AlignHCenter
                }
                Text {
                    text:"Image body fixture · local Swirl brand asset"
                    color:Theme.muted; font.pixelSize:11
                    Layout.alignment:Qt.AlignHCenter
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlButton { text:"Copy"; iconName:"code"; onClicked:{demoProvider.copyText(inspector.detailsText()); AppState.toast="Copied synthetic request details"} }
            Item { Layout.fillWidth:true }
            Text { text:"SYNTHETIC RESPONSE"; color:Theme.muted; font.pixelSize:10 }
        }
    }
}