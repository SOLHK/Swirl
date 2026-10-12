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
    cornerRadius:Theme.containerRadius
    implicitWidth:Theme.dp(450)
    function detailsText() {
        if(!record) return "选择一条请求查看详细信息。"
        if(activeTab==="Headers" && mode==="Response")
            return "Response Headers\n:status: "+record.status+"\ncontent-type: application/json\nserver: Swirl"
        if(activeTab==="Headers")
            return mode+" Headers\n\n:method: "+record.method+
                "\n:authority: "+record.host+"\n:path: "+record.path+
                "\naccept: application/json\nuser-agent: Swirl/0.1\ncontent-type: application/json\ncache-control: no-cache"
        if(activeTab==="Body")
            return '{\n  "source": "Swirl",\n  "requestId": "'+record.id+'",\n  "items": [\n    { "name": "Swirl", "enabled": false }\n  ]\n}'
        if(activeTab==="XML")return '<response requestId="'+record.id+'">\n  <source>Swirl</source>\n  <success>true</success>\n</response>'
        if(activeTab==="Preview")return "图像预览"
        if(activeTab==="Cookies")return "session_id = [session]\nSameSite = Lax\nSecure = true\nHttpOnly = true"
        if(activeTab==="Query")return "q = swirl\npage = 1\nlimit = 20"
        if(activeTab==="TLS")return "Protocol: "+record.version+"\nCipher: TLS_AES_128_GCM_SHA256\nTLS version: 1.3\nCA trust: not inspected"
        if(activeTab==="Timeline")return "DNS Lookup          12 ms\nTCP Connect         21 ms\nTLS Handshake       31 ms\nRequest Sent         4 ms\nWaiting / TTFB      84 ms\nContent Download    18 ms"
        if(activeTab==="WebSocket")return "暂无 WebSocket 帧"
        return record.path
    }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(17)
        spacing:Theme.dp(13)
        RowLayout {
            Layout.fillWidth:true
            Text {
                Layout.fillWidth:true
                text:record?record.method+"  "+record.host:"请求详情"
                color:Theme.text; font.pixelSize:Theme.fontSize(15); font.weight:Font.DemiBold
                elide:Text.ElideRight
            }
            SwirlStatusBadge { label:record?String(record.status):"Idle"; tone:"accent" }
        }
        RowLayout {
            Layout.fillWidth:true; spacing:Theme.dp(7)
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
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(39)
            contentWidth:tabs.width; contentHeight:height
            clip:true
            Row {
                id:tabs; spacing:Theme.dp(6)
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
        Rectangle { Layout.fillWidth:true; height:Theme.dp(1); color:Theme.border }
        Item {
            Layout.fillWidth:true; Layout.fillHeight:true
            ScrollView {
                visible:inspector.activeTab!=="Preview"&&inspector.activeTab!=="WebSocket"
                anchors.fill:parent
                clip:true
                TextArea {
                readOnly:true
                text:inspector.detailsText()
                wrapMode:Text.WrapAnywhere
                color:Theme.text
                font.family:"Cascadia Code"
                font.pixelSize:Theme.fontSize(12)
                leftPadding:Theme.dp(5)
                background:Rectangle { color:"transparent" }
                selectByMouse:true
                }
            }
            SwirlDataTable {
                visible:inspector.activeTab==="WebSocket"
                anchors.fill:parent
                rows:[
                    {id:"ws1",direction:"Out",time:"14:08:10",opcode:"Text",size:"21 B",payload:"ping"},
                    {id:"ws2",direction:"In",time:"14:08:10",opcode:"Text",size:"32 B",payload:"pong"},
                    {id:"ws3",direction:"In",time:"14:08:12",opcode:"Binary",size:"128 B",payload:"[sample bytes]"}
                ]
                columns:[
                    {key:"direction",label:"DIR",w:52},{key:"time",label:"TIMESTAMP",w:100},
                    {key:"opcode",label:"TYPE",w:80},{key:"size",label:"SIZE",w:65},
                    {key:"payload",label:"PAYLOAD",w:160}
                ]
                onRowSelected:function(r){AppState.toast="已选择 WebSocket 帧："+r.opcode}
            }
            ColumnLayout {
                visible:inspector.activeTab==="Preview"
                anchors.centerIn:parent
                spacing:Theme.dp(12)
                Image {
                    source:Theme.dark ? "qrc:/swirl/icons/swirl_knot_dark.svg" : "qrc:/swirl/icons/swirl_knot_light.svg"
                    sourceSize.width:Theme.dp(138); sourceSize.height:Theme.dp(138)
                    Layout.preferredWidth:Theme.dp(138); Layout.preferredHeight:Theme.dp(138)
                    fillMode:Image.PreserveAspectFit
                    Layout.alignment:Qt.AlignHCenter
                }
                Text {
                    text:"Swirl 图像预览"
                    color:Theme.muted; font.pixelSize:Theme.fontSize(11)
                    Layout.alignment:Qt.AlignHCenter
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlButton { text:"Copy"; iconName:"code"; onClicked:{demoProvider.copyText(inspector.detailsText()); AppState.toast="已复制请求详情"} }
            Item { Layout.fillWidth:true }
            Text { text:"响应详情"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
        }
    }
}
