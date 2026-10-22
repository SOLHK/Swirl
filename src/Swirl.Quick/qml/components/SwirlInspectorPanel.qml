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
        if(!record)return "选择一条真实抓包记录。"
        if(activeTab==="Headers")return mode==="Response"?(record.responseHeaders||"未采集"):(record.requestHeaders||"未采集")
        if(activeTab==="Body" || activeTab==="XML")return mode==="Response"?(record.responseBody||"无正文"):(record.requestBody||"无正文")
        if(activeTab==="Timeline")return "总耗时："+record.duration+"；阶段耗时未采集。"
        if(activeTab==="TLS")return "未解密或采集 TLS 详情。"
        return "此类详情尚未采集。"
 }
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(17)
        spacing:Theme.dp(13)
        RowLayout {
            Layout.fillWidth:true
            SwirlText {
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
        Rectangle { Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(1); color:Theme.border }
        Item {
            Layout.fillWidth:true; Layout.fillHeight:true
            ScrollView {
                visible:inspector.activeTab!=="Preview"&&inspector.activeTab!=="WebSocket"
                anchors.fill:parent
                clip:true
                SwirlTextArea {
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
                rows:[]
                columns:[
                    {key:"direction",label:"DIR",w:52},{key:"time",label:"TIMESTAMP",w:100},
                    {key:"opcode",label:"TYPE",w:80},{key:"size",label:"SIZE",w:65},
                    {key:"payload",label:"PAYLOAD",w:160}
                ]
                onRowSelected:function(r){AppState.toast="已选择 WebSocket 帧："+r.opcode}
            }
            ColumnLayout {
                visible:false
                anchors.centerIn:parent
                spacing:Theme.dp(12)
                Image {
                    source:Theme.dark ? "qrc:/swirl/icons/swirl_knot_dark.svg" : "qrc:/swirl/icons/swirl_knot_light.svg"
                    sourceSize.width:Theme.dp(138); sourceSize.height:Theme.dp(138)
                    Layout.preferredWidth:Theme.dp(138); Layout.preferredHeight:Theme.dp(138)
                    fillMode:Image.PreserveAspectFit
                    Layout.alignment:Qt.AlignHCenter
                }
                SwirlText {
                    text:"Swirl 图像预览"
                    color:Theme.muted; font.pixelSize:Theme.fontSize(11)
                    Layout.alignment:Qt.AlignHCenter
                }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlButton { text:"Copy"; iconName:"code"; onClicked:{systemProvider.copyText(inspector.detailsText()); AppState.toast="已复制请求详情"} }
            Item { Layout.fillWidth:true }
            SwirlText { text:"响应详情"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
        }
    }
}
