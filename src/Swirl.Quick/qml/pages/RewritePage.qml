import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"

Item {
    id:page
    property string category:"URL 重写"
    property var chosen:null
    property var rules:[
        {id:"rw1",category:"URL 重写",pattern:"^https://api.example.test/old",action:"替换 URL",status:"Enabled",hits:"37"},
        {id:"rw2",category:"请求头重写",pattern:"*.example.test",action:"设置 X-Demo",status:"Enabled",hits:"148"},
        {id:"rw3",category:"响应体重写",pattern:"/v1/user",action:"JSON 模拟",status:"Disabled",hits:"0"},
        {id:"rw4",category:"Redirect",pattern:"/v1/legacy",action:"302 重定向",status:"Enabled",hits:"12"},
        {id:"rw5",category:"Reject",pattern:"/ads/*",action:"拒绝请求",status:"Enabled",hits:"83"},
        {id:"rw6",category:"模拟响应",pattern:"/api/config",action:"模拟 JSON",status:"Enabled",hits:"24"}
    ]
    readonly property var showRows:rules.filter(function(r){
        return r.category===page.category && (r.pattern+" "+r.action).toLowerCase().indexOf(query.text.toLowerCase())>=0
    })
    ColumnLayout {
        anchors.fill:parent; anchors.margins:23; spacing:14
        RowLayout {
            Layout.fillWidth:true
            SwirlStatusBadge { label:"HTTP 重写演示"; tone:"accent" }
            Text { text:"本地规则编辑器 · 不拦截真实流量"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true }
            SwirlButton { text:"Import"; onClicked:AppState.notice("导入重写规则") }
            SwirlButton { text:"新建重写"; primary:true; onClicked:editorDialog.open() }
        }
        Flow {
            Layout.fillWidth:true; Layout.preferredHeight:42; spacing:6
            Repeater {
                model:["URL 重写","请求头重写","响应体重写","Redirect","Reject","模拟响应"]
                SwirlButton { text:modelData; quiet:page.category!==modelData; onClicked:{page.category=modelData;page.chosen=null} }
            }
        }
        RowLayout {
            Layout.fillWidth:true
            SwirlSearchField { id:query; Layout.fillWidth:true; placeholderText:"搜索表达式或操作" }
            SwirlStatusBadge { label:showRows.length+" 条规则"; tone:"accent" }
            SwirlButton { text:"测试规则"; onClicked:AppState.notice("重写匹配测试") }
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:14
            SwirlGlassPanel {
                Layout.fillWidth:true; Layout.fillHeight:true; clip:true
                SwirlDataTable {
                    anchors.fill:parent; anchors.margins:1
                    rows:page.showRows
                    selectedId:page.chosen?page.chosen.id:""
                    columns:[{key:"pattern",label:"匹配表达式",w:280},{key:"action",label:"ACTION",w:160},
                             {key:"hits",label:"HITS",w:72},{key:"status",label:"STATE",w:105}]
                    onRowSelected:function(r){page.chosen=r}
                }
                SwirlEmptyState { visible:page.showRows.length===0; anchors.centerIn:parent; headline:"没有重写规则"; detail:"添加本地示例" }
            }
            SwirlGlassPanel {
                Layout.preferredWidth:323; Layout.fillHeight:true
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:17; spacing:12
                    Text { text:"重写编辑器"; color:Theme.text; font.pixelSize:17; font.weight:Font.DemiBold }
                    Text { text:page.chosen?page.chosen.pattern:"从列表中选择规则"; color:Theme.muted; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WrapAnywhere }
                    Text { text:"匹配表达式"; color:Theme.muted; font.pixelSize:10 }
                    SwirlTextField { id:expression; Layout.fillWidth:true; text:page.chosen?page.chosen.pattern:""; placeholderText:"https://example.test/.*" }
                    Text { text:"ACTION"; color:Theme.muted; font.pixelSize:10 }
                    SwirlComboBox { id:action; Layout.fillWidth:true; model:["替换 URL","设置请求头","替换响应体","302 重定向","拒绝请求","模拟 JSON"] }
                    Text { text:"结果预览"; color:Theme.muted; font.pixelSize:10 }
                    Rectangle {
                        Layout.fillWidth:true; Layout.fillHeight:true
                        radius:10; color:Theme.field; border.color:Theme.border
                        ScrollView {
                            anchors.fill:parent; anchors.margins:9
                            TextArea {
                                readOnly:true
                                text:"规则匹配："+(page.chosen?page.chosen.hits:"0")+" simulated hits\n"+
                                     "输入："+(page.chosen?page.chosen.pattern:"—")+"\n"+
                                     "输出："+(page.chosen?page.chosen.action:"—")+
                                     "\n\nNo outgoing requests are changed."
                                font.family:"Cascadia Code"; font.pixelSize:11
                                color:Theme.text; wrapMode:Text.WrapAnywhere
                                background:Rectangle { color:"transparent" }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth:true
                        SwirlButton { text:"Preview"; onClicked:AppState.notice("预览"+page.category) }
                        SwirlButton { text:"应用演示"; primary:true; onClicked:AppState.notice("应用重写") }
                    }
                }
            }
        }
    }
    SwirlDialog {
        id:editorDialog; title:"添加重写规则"
        ColumnLayout {
            width:parent.width; spacing:12
            Text { text:"匹配表达式"; color:Theme.text }
            SwirlTextField { id:newPattern; Layout.fillWidth:true; placeholderText:"https://example.test/api/.*" }
            Text { text:"Action"; color:Theme.text }
            SwirlComboBox { id:newAction; Layout.fillWidth:true; model:["替换 URL","设置请求头","替换响应体","302 重定向","拒绝请求","模拟 JSON"] }
            Text { text:"表达式仅用于演示，不会拦截网络或执行正则匹配。"; color:Theme.muted; font.pixelSize:11; Layout.fillWidth:true; wrapMode:Text.WordWrap }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:"Cancel"; onClicked:editorDialog.close() }
                SwirlButton {
                    text:"添加演示"; primary:true; enabled:newPattern.text.trim().length>2
                    onClicked:{
                        page.rules=page.rules.concat([{id:"rw"+Date.now(),category:page.category,
                            pattern:newPattern.text.trim(),action:newAction.currentText,status:"Enabled",hits:"0"}])
                        newPattern.text="";editorDialog.close()
                    }
                }
            }
        }
    }
}