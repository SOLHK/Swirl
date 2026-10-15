import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string selectedRequest:""
    property string resultMessage:"尚未重放请求。\n选择请求后查看重放结果。"
    property var samples:(systemProvider.revision,systemProvider.requests()).slice(0,14)
    property var history:[]
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(13)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"离线 HTTP 请求编辑器"; tone:"accent" }
            Text { text:"请求不会实际发送"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { development:true; enabled:false; text:"对比"; onClicked:comparePopup.open() }
            SwirlButton { development:true; enabled:false; text:"发送"; iconName:"play"; primary:true; onClicked:AppState.notice("研发中") }
        }
        SplitView {
            Layout.fillHeight:true; Layout.fillWidth:true
            orientation:Qt.Horizontal
            handle:Rectangle { implicitWidth:Theme.dp(7); color:Theme.canvas }
            SwirlGlassPanel {
                SplitView.preferredWidth:Theme.dp(272); SplitView.minimumWidth:Theme.dp(200)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(13); spacing:Theme.dp(10)
                    Text { text:"捕获历史"; color:Theme.text; font.pixelSize:Theme.fontSize(14); font.weight:Font.DemiBold }
                    SwirlSearchField { id:search; Layout.fillWidth:true; placeholderText:"筛选请求" }
                    ListView {
                    add: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";from:0;to:1;duration:SwirlMotion.duration} }
                    remove: Transition { enabled:!SwirlMotion.reduced; NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} }
                    move: Transition {enabled:!SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:!SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
                        Layout.fillHeight:true; Layout.fillWidth:true; clip:true; spacing:Theme.dp(4)
                        model:page.samples.filter(function(r){
                            return (r.method+" "+r.path).toLowerCase().indexOf(search.text.toLowerCase())>=0
                        })
                        delegate:Rectangle {
                            width:ListView.view.width; height:Theme.dp(51); radius:Theme.roundedRadius(width,height)
                            color:page.selectedRequest===modelData.id?Theme.selected:tap.containsMouse?Theme.hover:"transparent"
                            ColumnLayout {
                                anchors.fill:parent; anchors.margins:Theme.dp(8); spacing:Theme.dp(3)
                                Text { text:modelData.method+"   "+modelData.path; font.pixelSize:Theme.fontSize(12); color:Theme.text; Layout.fillWidth:true; elide:Text.ElideRight }
                                Text { text:modelData.host+" · "+modelData.version; color:Theme.muted; font.pixelSize:Theme.fontSize(10); Layout.fillWidth:true; elide:Text.ElideRight }
                            }
                            MouseArea {
                                id:tap; anchors.fill:parent; hoverEnabled:true
                                onClicked:AppState.notice("研发中")
                            }
                        }
                    }
                    SwirlButton { development:true; enabled:false; Layout.fillWidth:true; text:"导入 HAR"; onClicked:AppState.notice("导入 HAR") }
                }
            }
            SwirlGlassPanel {
                SplitView.fillWidth:true; SplitView.minimumWidth:Theme.dp(400)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(17); spacing:Theme.dp(12)
                    Text { text:"请求编辑器"; color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlComboBox { id:verb; model:["GET","POST","PUT","PATCH","DELETE","HEAD"] }
                        SwirlTextField { id:urlField; Layout.fillWidth:true; text:"" }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Repeater {
                            model:["Headers","Body","Cookies","Query"]
                            SwirlButton { development:true; enabled:false; text:modelData; quiet:requestTab.current!==modelData; onClicked:requestTab.current=modelData }
                        }
                    }
                    QtObject { id:requestTab; property string current:"Headers" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(9)
                            TextArea {
                                id:bodyEditor
                                text:""
                                font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(12); color:Theme.text
                                selectByMouse:true; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Text { text:"执行历史："+page.history.length+" 次操作"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true }
                        SwirlButton { development:true; enabled:false; text:"重置"; onClicked:AppState.notice("研发中") }
                    }
                }
            }
            SwirlGlassPanel {
                SplitView.preferredWidth:Theme.dp(300); SplitView.minimumWidth:Theme.dp(230)
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(17); spacing:Theme.dp(12)
                    Text { text:"响应预览"; color:Theme.text; font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold }
                    SwirlStatusBadge { label:""; tone:"accent" }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(9)
                            TextArea {
                                readOnly:true; text:page.resultMessage
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(12)
                                wrapMode:Text.WrapAnywhere; selectByMouse:true
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    SwirlButton { development:true; enabled:false; text:"查看对比"; onClicked:comparePopup.open() }
                }
            }
        }
    }
    SwirlDialog {
        id:comparePopup; title:"重放对比"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(11)
            Text { text:"原始请求与本地重放对比"; color:Theme.text; font.pixelSize:Theme.fontSize(13); Layout.fillWidth:true }
            Text {
                text:"研发中"
                color:Theme.muted; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(11)
                Layout.fillWidth:true; wrapMode:Text.WordWrap
            }

        }
    }
}
