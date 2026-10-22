import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property var records:[]
    property var selected:null
    property string tab:"Headers"
    property string payload: ""
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"未启用实时拦截"; tone:"warning" }
            SwirlText { text:"仅编辑暂停请求，不会影响实际网络"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { development:true; enabled:false; text:"添加断点"; primary:true; onClicked:ruleDialog.open() }
        }
        SwirlGlassPanel {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(88)
            RowLayout {
                anchors.fill:parent; anchors.margins:Theme.dp(18); spacing:Theme.dp(15)
                ColumnLayout {
                    Layout.fillWidth:true; spacing:Theme.dp(5)
                    SwirlText { text:"断点队列"; color:Theme.text; font.pixelSize:Theme.fontSize(18); font.weight:Font.DemiBold }
                    SwirlText { text:"请求均为本地，不会暂停浏览器。"; color:Theme.muted; font.pixelSize:Theme.fontSize(11) }
                }
                SwirlStatusBadge { label:page.records.filter(function(r){return r.status==="Paused"}).length+" 已暂停"; tone:"accent" }
                SwirlButton { development:true; enabled:false; text:"全部继续"; onClicked:AppState.notice("研发中")}
            }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(380); Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.records
                    selectedId:page.selected?page.selected.id:""
                    columns:[{key:"method",label:"方法",w:87},{key:"url",label:"请求路径",w:215},
                             {key:"status",label:"状态",w:119},{key:"time",label:"时间",w:98}]
                    onRowSelected:function(r){page.selected=r}
                }
            }
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:Theme.dp(17); spacing:Theme.dp(13)
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlText { text:"暂停请求编辑器"; color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold; Layout.fillWidth:true }
                        SwirlStatusBadge { label:page.selected?page.selected.status:"尚未选择"; tone:"accent" }
                    }
                    SwirlText {
                        Layout.fillWidth:true; elide:Text.ElideMiddle; color:Theme.muted; font.pixelSize:Theme.fontSize(12)
                        text:page.selected?("https://"+page.selected.host+page.selected.url):"选择请求后查看详情"
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        Repeater {
                            model:["Headers","Body","Query"]
                            SwirlButton { development:true; enabled:false; text:modelData; quiet:page.tab!==modelData; onClicked:page.tab=modelData }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(8)
                            SwirlTextArea {
                                id:editor
                                text:"研发中；没有被拦截的请求。"
                                color:Theme.text; font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(12)
                                selectByMouse:true; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { development:true; enabled:false;
                            text:"继续"; primary:true;
                            onClicked:page.changeStatus("Continued")
                        }
                        SwirlButton { development:true; enabled:false;
                            text:"修改并继续";
                            onClicked:AppState.notice("研发中")
                        }
                        SwirlButton { development:true; enabled:false;
                            text:"丢弃"; danger:true;
                            onClicked:page.changeStatus("Dropped")
                        }
                    }
                }
            }
        }
    }
    function changeStatus(status) {
        if (!selected) return
        var id=selected.id
        records=records.map(function(r){return r.id===id?
            {id:r.id,method:r.method,url:r.url,host:r.host,status:status,time:r.time}:r})
        selected=records.find(function(r){return r.id===id})
        AppState.notice("Breakpoint "+status)
    }
    SwirlDialog {
        id:ruleDialog; title:"添加断点匹配条件"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            SwirlText { text:"URL 匹配表达式"; color:Theme.text }
            SwirlTextField { id:matcher; Layout.fillWidth:true; placeholderText:"/api/*" }
            SwirlText { text:"请求阶段"; color:Theme.text }
            SwirlComboBox { model:["发送请求前","收到响应后"] }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { development:true; enabled:false; text:"取消"; onClicked:ruleDialog.close() }
                SwirlButton { development:true; enabled:false; text:"添加"; primary:true;
                    onClicked:AppState.notice("研发中")
                }
            }
        }
    }
}
