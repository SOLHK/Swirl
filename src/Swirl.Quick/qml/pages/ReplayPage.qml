import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string selectedRequest:""
    property string resultMessage:"No request has been replayed.\nAll operations are offline."
    property var samples:demoProvider.requests().slice(0,14)
    property var history:[]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:13
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"离线 HTTP 请求编辑器"; tone:"accent" }
            Text { text:"请求不会实际发送"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Compare"; onClicked:comparePopup.open() }
            SwirlButton { text:"发送演示"; iconName:"play"; primary:true; onClicked:{
                page.resultMessage="HTTP 200 OK (simulated)\nContent-Type: application/json\nX-Demo: SwirlQuick\n\n{\n  \"sent\": false,\n  \"message\": \"No network request performed\"\n}"
                page.history=[{name:verb.currentText+" "+urlField.text,time:"Now",status:"Simulated"}].concat(page.history)
                AppState.notice("HTTP 重放（未实际发送请求）")
            } }
        }
        SplitView {
            Layout.fillHeight:true; Layout.fillWidth:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:7; color:Theme.canvas }
            SwirlGlassPanel {
                SplitView.preferredWidth:272; SplitView.minimumWidth:200
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:13; spacing:10
                    Text { text:"捕获历史（演示）"; color:Theme.text; font.pixelSize:14; font.weight:Font.DemiBold }
                    SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"筛选请求" }
                    ListView {
                        Layout.fillHeight:true; Layout.fillWidth:true; clip:true; spacing:4
                        model:page.samples.filter(function(r){
                            return (r.method+" "+r.path).toLowerCase().indexOf(search.text.toLowerCase())>=0
                        })
                        delegate:Rectangle {
                            width:ListView.view.width; height:51; radius:9
                            color:page.selectedRequest===modelData.id?Theme.selected:tap.containsMouse?Theme.hover:"transparent"
                            ColumnLayout {
                                anchors.fill:parent; anchors.margins:8; spacing:3
                                Text { text:modelData.method+"   "+modelData.path; font.pixelSize:12; color:Theme.text; Layout.fillWidth:true; elide:Text.ElideRight }
                                Text { text:modelData.host+" · "+modelData.version; color:Theme.muted; font.pixelSize:10; Layout.fillWidth:true; elide:Text.ElideRight }
                            }
                            MouseArea {
                                id:tap; anchors.fill:parent; hoverEnabled:true
                                onClicked:{
                                    page.selectedRequest=modelData.id
                                    verb.currentIndex=verb.model.indexOf(modelData.method)
                                    urlField.text="https://"+modelData.host+modelData.path
                                }
                            }
                        }
                    }
                    SwirlButton { Layout.fillWidth:true; text:"导入 HAR"; onClicked:AppState.notice("导入 HAR") }
                }
            }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:400
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:12
                    Text { text:"请求编辑器"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox { id:verb; model:["GET","POST","PUT","PATCH","DELETE","HEAD"] }
                        SwirlTextField { id:urlField; Layout.fillWidth:true; text:"https://api.example.test/v1/user" }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Repeater {
                            model:["Headers","Body","Cookies","Query"]
                            SwirlButton { text:modelData; quiet:requestTab.current!==modelData; onClicked:requestTab.current=modelData }
                        }
                    }
                    QtObject { id:requestTab; property string current:"Headers" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:9
                            TextArea {
                                id:bodyEditor
                                text:requestTab.current==="Headers"?"Accept: application/json\nX-Swirl-Demo: true\nContent-Type: application/json":
                                    requestTab.current==="Body"?"{\n  \"test\": true\n}":
                                    requestTab.current==="Cookies"?"session=synthetic":"page=1\nq=swirl"
                                font.family:"Cascadia Code"; font.pixelSize:12; color:Theme.text
                                selectByMouse:true; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"执行历史："+page.history.length+" 次演示操作"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true }
                        SwirlButton { text:"Reset"; onClicked:{page.resultMessage="尚未重放请求。";page.history=[]} }
                    }
                }
            }
            SwirlGlassPanel {
                SplitView.preferredWidth:300; SplitView.minimumWidth:230
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:12
                    Text { text:"响应预览"; color:Theme.text; font.pixelSize:16; font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:"SIMULATED"; tone:"accent" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:9
                            TextArea {
                                readOnly:true; text:page.resultMessage
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:12
                                wrapMode:Text.WrapAnywhere; selectByMouse:true
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { text:"查看对比"; onClicked:comparePopup.open() }
                }
            }
        }
    }
    SwirlDialog {
        id:comparePopup; title:"重放对比"
        ColumnLayout {
            width:parent.width; spacing:11
            Text { text:"原始请求与本地模拟重放对比"; color:Theme.text; font.pixelSize:13; Layout.fillWidth:true }
            Text {
                text:"Original: HTTP 200  ·  108 ms (fixture)\nReplay: No request sent  ·  N/A\n\nWhen a network adapter is integrated, the comparison pane will show header, body and timing differences."
                color:Theme.muted; font.family:"Cascadia Code"; font.pixelSize:11
                Layout.fillWidth:true; wrapMode:Text.WordWrap
            }
            SwirlButton { text:"Close"; Layout.alignment:Qt.AlignRight; onClicked:comparePopup.close() }
        }
    }
}