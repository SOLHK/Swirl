import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    readonly property bool implemented:false
    property string category:"URL 重写"
    property var chosen:null
    property var rules:[]
    readonly property var showRows:rules.filter(function(r){
        return r.category===page.category && (r.pattern+" "+r.action).toLowerCase().indexOf(query.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:Theme.dp(23); spacing:Theme.dp(14)
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"HTTP 重写"; tone:"accent" }
            Text { text:"本地规则编辑器 · 不拦截真实流量"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true }
            SwirlButton { enabled:false; text:"导入"; onClicked:AppState.notice("导入重写规则") }
            SwirlButton { enabled:false; text:"新建重写"; primary:true; onClicked:editorDialog.open() }
        }
        Flow {
            Layout.fillWidth:true; Layout.preferredHeight:Theme.dp(42); spacing:Theme.dp(6)
            Repeater {
                model:["URL 重写","请求头重写","响应体重写","Redirect","Reject","响应"]
                SwirlButton { enabled:false; text:modelData; quiet:page.category!==modelData; onClicked:AppState.notice("尚未实现") }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:query; Layout.fillWidth:true; placeholderText:"搜索表达式或操作" }
            SwirlStatusBadge { label:showRows.length+" 条规则"; tone:"accent" }
            SwirlButton { enabled:false; text:"测试规则"; onClicked:AppState.notice("重写匹配测试") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:Theme.dp(14)
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:Theme.dp(1)
                    rows:page.showRows
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"pattern",label:"匹配表达式",w:280},{key:"action",label:"操作",w:160},
                             {key:"hits",label:"命中次数",w:72},{key:"status",label:"状态",w:105}]
                    onRowSelected:function(r){page.chosen=r}
                }
                SwirlEmptyState { visible:page.showRows.length===0; anchors.centerIn:parent; headline:"没有重写规则"; detail:"添加本地" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:Theme.dp(323); Layout.fillHeight:true
                ScrollView {
                    id:detailScroll0; anchors.fill:parent; anchors.margins:Theme.dp(17); clip:true
                    ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
                    ColumnLayout {
                    width:detailScroll0.availableWidth; height:Math.max(implicitHeight,detailScroll0.availableHeight); spacing:Theme.dp(12)
                    Text { text:"重写编辑器"; color:Theme.text; font.pixelSize:Theme.fontSize(17); font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.pattern:"从列表中选择规则"; color:Theme.muted; font.pixelSize:Theme.fontSize(12); Layout.fillWidth:true; wrapMode:Text.WrapAnywhere }
                    Text { text:"匹配表达式"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlTextField { id:expression; Layout.fillWidth:true; text:page.chosen?page.chosen.pattern:""; placeholderText:"https://example.test/.*" }
                    Text { text:"操作"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    SwirlComboBox { id:action; Layout.fillWidth:true; model:["替换 URL","设置请求头","替换响应体","302 重定向","拒绝请求"," JSON"] }
                    Text { text:"结果预览"; color:Theme.muted; font.pixelSize:Theme.fontSize(10) }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:Theme.roundedRadius(width,height); color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:Theme.dp(9)
                            TextArea {
                                readOnly:true
                                text:"规则匹配："+(page.chosen?page.chosen.hits:"0")+" 次命中\n"+
                                     "输入："+(page.chosen?page.chosen.pattern:"—")+"\n"+
                                     "输出："+(page.chosen?page.chosen.action:"—")+
                                     "\n\n匹配结果与重写内容。"
                                font.family:"Cascadia Code"; font.pixelSize:Theme.fontSize(11)
                                color:Theme.text; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { enabled:false; text:"预览"; onClicked:AppState.notice("预览"+page.category) }
                        SwirlButton { enabled:false; text:"应用"; primary:true; onClicked:AppState.notice("应用重写") }
                    }
                }
                }
            }
        }
    }
    SwirlDialog {
        id:editorDialog; title:"添加重写规则"
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            Text { text:"匹配表达式"; color:Theme.text }
            SwirlTextField { id:newPattern; Layout.fillWidth:true; placeholderText:"https://example.test/api/.*" }
            Text { text:"操作"; color:Theme.text }
            SwirlComboBox { id:newAction; Layout.fillWidth:true; model:["替换 URL","设置请求头","替换响应体","302 重定向","拒绝请求"," JSON"] }
            Text { text:"表达式仅用于，不会拦截网络或执行正则匹配。"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { enabled:false; text:"取消"; onClicked:editorDialog.close() }
                SwirlButton { enabled:false;
                    text:"添加"; primary:true;
                    onClicked:AppState.notice("尚未实现")
                }
            }
        }
    }
}
